import io

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import can_edit_required, payroll_staff_required
from apps.attendance.models import Timesheet
from apps.employees.models import Employee
from apps.org.models import CostCenter
from apps.payroll.engine.runner import CalculationError, calculate_period
from apps.payroll.models import PayrollPeriod, Payslip
from apps.payroll.utils import fa_money, jalali_str
from apps.payroll_config.models import SalaryComponent


def _period_progress(period):
    """چند نفر از پرسنل فعال کارکرد تأییدشده دارند."""
    if period is None:
        return {"total": 0, "done": 0, "remaining": 0}
    total = Employee.objects.filter(
        company=period.company, status=Employee.Status.ACTIVE
    ).count()
    done = Timesheet.objects.filter(
        period=period, status=Timesheet.Status.APPROVED
    ).count()
    return {"total": total, "done": done, "remaining": max(total - done, 0)}


@payroll_staff_required
def dashboard(request):
    period = PayrollPeriod.objects.select_related("company").order_by("-year", "-month").first()

    progress = _period_progress(period)
    previous = None
    if period:
        previous = (
            PayrollPeriod.objects.filter(company=period.company)
            .exclude(pk=period.pk)
            .filter(status__in=[
                PayrollPeriod.Status.CALCULATED,
                PayrollPeriod.Status.APPROVED,
                PayrollPeriod.Status.LOCKED,
                PayrollPeriod.Status.PAID,
            ])
            .order_by("-year", "-month")
            .first()
        )

    def delta(current, before):
        if not before or not current:
            return None
        change = (current - before) / before * 100
        return round(float(change), 1)

    recent_payslips = []
    if period:
        recent_payslips = list(
            Payslip.objects.filter(period=period)
            .select_related("employee", "department")
            .order_by("-gross_total")[:5]
        )

    # پنل اقلام حقوقی — مثل ماکاپ، بر اساس یک مرکز هزینه فیلتر می‌شود
    cost_center_id = request.GET.get("cc")
    cost_centers = CostCenter.objects.filter(is_active=True).order_by("name")
    selected_cc = None
    if cost_center_id:
        selected_cc = cost_centers.filter(pk=cost_center_id).first()
    if selected_cc is None:
        selected_cc = cost_centers.first()

    components = SalaryComponent.objects.filter(is_active=True).prefetch_related("scopes")
    visible_components = []
    for component in components.order_by("sequence")[:40]:
        scopes = list(component.scopes.all())
        if not scopes:
            visible_components.append(component)
        elif selected_cc and any(
            s.scope_type == "COST_CENTER" and s.scope_id == str(selected_cc.pk) for s in scopes
        ):
            visible_components.append(component)
    visible_components = visible_components[:8]

    return render(
        request,
        "dashboard.html",
        {
            "period": period,
            "progress": progress,
            "recent_payslips": recent_payslips,
            "components": visible_components,
            "cost_centers": cost_centers,
            "selected_cc": selected_cc,
            "active_employees": progress["total"],
            "deltas": {
                "gross": delta(period.total_gross, previous.total_gross) if period and previous else None,
                "net": delta(period.total_net, previous.total_net) if period and previous else None,
                "employer": delta(
                    period.total_employer_cost, previous.total_employer_cost
                ) if period and previous else None,
            },
        },
    )


@payroll_staff_required
def period_list(request):
    periods = (
        PayrollPeriod.objects.select_related("company")
        .annotate(payslip_count=Count("payslips"))
        .order_by("-year", "-month")
    )
    return render(request, "periods/list.html", {"periods": periods})


@payroll_staff_required
def period_detail(request, pk):
    period = get_object_or_404(PayrollPeriod.objects.select_related("company", "fiscal_year"), pk=pk)
    progress = _period_progress(period)
    runs = period.runs.select_related("run_by").order_by("-started_at")[:5]

    by_department = (
        Payslip.objects.filter(period=period)
        .values("department__name")
        .annotate(
            count=Count("id"),
            gross=Sum("gross_total"),
            net=Sum("net_payable"),
            tax=Sum("tax_amount"),
            insurance=Sum("ins_employee"),
        )
        .order_by("-gross")
    )

    return render(
        request,
        "periods/detail.html",
        {
            "period": period,
            "progress": progress,
            "runs": runs,
            "by_department": by_department,
            "payslip_count": Payslip.objects.filter(period=period).count(),
        },
    )


@can_edit_required
@require_POST
def period_calculate(request, pk):
    period = get_object_or_404(PayrollPeriod, pk=pk)
    try:
        run = calculate_period(period, user=request.user)
    except CalculationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"محاسبه دوره {period.title} انجام شد — {run.success_count} فیش صادر شد "
            f"(جمع خالص: {fa_money(period.total_net)} ریال).",
        )
    return redirect("period_detail", pk=period.pk)


@can_edit_required
@require_POST
def period_transition(request, pk, action):
    period = get_object_or_404(PayrollPeriod, pk=pk)

    if action == "advance":
        target = period.next_status
        if target is None:
            messages.error(request, "این دوره در آخرین وضعیت است.")
        elif target == PayrollPeriod.Status.CALCULATED and not period.payslips.exists():
            messages.error(request, "ابتدا باید محاسبه دوره اجرا شود.")
        else:
            period.status = target
            if target == PayrollPeriod.Status.APPROVED:
                period.approved_at = timezone.now()
            if target == PayrollPeriod.Status.LOCKED:
                period.locked_at = timezone.now()
                period.locked_by = request.user
            period.save()
            messages.success(request, f"وضعیت دوره به «{period.get_status_display()}» تغییر کرد.")
    elif action == "revert":
        target = period.previous_status
        if target is None:
            messages.error(
                request,
                "برگشت از این وضعیت ممکن نیست. دوره قفل‌شده فقط با فیش اصلاحی تغییر می‌کند.",
            )
        else:
            period.status = target
            period.save()
            messages.info(request, f"وضعیت دوره به «{period.get_status_display()}» برگشت.")
    else:
        messages.error(request, "عملیات نامعتبر است.")

    return redirect("period_detail", pk=period.pk)


@payroll_staff_required
def payslip_list(request, pk):
    period = get_object_or_404(PayrollPeriod, pk=pk)
    query = request.GET.get("q", "").strip()

    payslips = Payslip.objects.filter(period=period).select_related(
        "employee", "department", "cost_center"
    )
    if query:
        payslips = payslips.filter(
            Q(employee__first_name__icontains=query)
            | Q(employee__last_name__icontains=query)
            | Q(employee__personnel_code__icontains=query)
        )
    payslips = payslips.order_by("employee__personnel_code")

    paginator = Paginator(payslips, 30)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    template = "payslips/_rows.html" if request.headers.get("HX-Request") else "payslips/list.html"
    return render(
        request,
        template,
        {"period": period, "page_obj": page_obj, "q": query, "total": payslips.count()},
    )


@payroll_staff_required
def payslip_detail(request, pk):
    payslip = get_object_or_404(
        Payslip.objects.select_related(
            "period", "employee", "contract", "department", "cost_center"
        ),
        pk=pk,
    )
    lines = payslip.lines.all().order_by("sequence", "id")
    return render(
        request,
        "payslips/detail.html",
        {
            "payslip": payslip,
            "earnings": [l for l in lines if l.kind == SalaryComponent.Kind.EARNING],
            "deductions": [l for l in lines if l.kind == SalaryComponent.Kind.DEDUCTION],
            "employer_costs": [l for l in lines if l.kind == SalaryComponent.Kind.EMPLOYER_COST],
        },
    )


@payroll_staff_required
def payslip_print(request, pk):
    payslip = get_object_or_404(
        Payslip.objects.select_related("period", "employee", "contract", "department"), pk=pk
    )
    lines = payslip.lines.all().order_by("sequence", "id")
    return render(
        request,
        "payslips/print.html",
        {
            "payslip": payslip,
            "earnings": [l for l in lines if l.kind == SalaryComponent.Kind.EARNING],
            "deductions": [l for l in lines if l.kind == SalaryComponent.Kind.DEDUCTION],
        },
    )


# ----------------------------------------------------------------- گزارش‌ها


@payroll_staff_required
def reports(request):
    periods = (
        PayrollPeriod.objects.annotate(payslip_count=Count("payslips"))
        .filter(payslip_count__gt=0)
        .order_by("-year", "-month")
    )
    return render(request, "reports/index.html", {"periods": periods})


def _report_rows(period):
    return (
        Payslip.objects.filter(period=period)
        .select_related("employee", "department")
        .order_by("employee__personnel_code")
    )


@payroll_staff_required
def report_insurance(request, pk):
    period = get_object_or_404(PayrollPeriod.objects.select_related("company"), pk=pk)
    rows = _report_rows(period)
    totals = rows.aggregate(
        insurable=Sum("insurable_base"),
        employee=Sum("ins_employee"),
        employer=Sum("ins_employer"),
    )
    return render(
        request,
        "reports/insurance.html",
        {"period": period, "rows": rows, "totals": totals, "count": rows.count()},
    )


@payroll_staff_required
def report_tax(request, pk):
    period = get_object_or_404(PayrollPeriod.objects.select_related("company"), pk=pk)
    rows = _report_rows(period).filter(tax_amount__gt=0)
    totals = rows.aggregate(taxable=Sum("taxable_base"), tax=Sum("tax_amount"))
    return render(
        request,
        "reports/tax.html",
        {"period": period, "rows": rows, "totals": totals, "count": rows.count()},
    )


@payroll_staff_required
def report_bank(request, pk):
    period = get_object_or_404(PayrollPeriod.objects.select_related("company"), pk=pk)
    rows = _report_rows(period)
    totals = rows.aggregate(net=Sum("net_payable"))
    missing_iban = rows.filter(iban_snapshot="").count()
    return render(
        request,
        "reports/bank.html",
        {
            "period": period,
            "rows": rows,
            "totals": totals,
            "count": rows.count(),
            "missing_iban": missing_iban,
        },
    )


REPORT_SPECS = {
    "insurance": {
        "title": "لیست بیمه",
        "headers": [
            "ردیف", "کد پرسنلی", "نام", "نام خانوادگی", "کد ملی", "شماره بیمه",
            "روز کارکرد", "مبنای بیمه", "سهم کارگر", "سهم کارفرما",
        ],
        "fields": lambda p, i: [
            i,
            p.employee.personnel_code,
            p.employee.first_name,
            p.employee.last_name,
            p.employee.national_id,
            p.employee.insurance_number,
            p.work_days,
            p.insurable_base,
            p.ins_employee,
            p.ins_employer,
        ],
    },
    "tax": {
        "title": "لیست مالیات",
        "headers": [
            "ردیف", "کد پرسنلی", "نام و نام خانوادگی", "کد ملی",
            "ناخالص", "مبنای مالیات", "مالیات",
        ],
        "fields": lambda p, i: [
            i,
            p.employee.personnel_code,
            p.employee.full_name,
            p.employee.national_id,
            p.gross_total,
            p.taxable_base,
            p.tax_amount,
        ],
    },
    "bank": {
        "title": "فایل پرداخت بانک",
        "headers": ["ردیف", "کد پرسنلی", "نام و نام خانوادگی", "شماره شبا", "مبلغ خالص"],
        "fields": lambda p, i: [
            i,
            p.employee.personnel_code,
            p.employee.full_name,
            p.iban_snapshot,
            p.net_payable,
        ],
    },
    "payslips": {
        "title": "خلاصه فیش‌ها",
        "headers": [
            "ردیف", "کد پرسنلی", "نام و نام خانوادگی", "واحد", "روز کارکرد",
            "ناخالص", "مبنای بیمه", "مبنای مالیات", "بیمه", "مالیات", "خالص",
        ],
        "fields": lambda p, i: [
            i,
            p.employee.personnel_code,
            p.employee.full_name,
            p.department.name,
            p.work_days,
            p.gross_total,
            p.insurable_base,
            p.taxable_base,
            p.ins_employee,
            p.tax_amount,
            p.net_payable,
        ],
    },
}


@payroll_staff_required
def report_export(request, pk, kind):
    """خروجی اکسل. برای دمو فایل مستقیم تولید می‌شود؛ در فاز ۴ رکورد ارسال
    (کد رهگیری و زمان) هم کنارش ذخیره خواهد شد."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    spec = REPORT_SPECS.get(kind)
    if spec is None:
        messages.error(request, "نوع گزارش نامعتبر است.")
        return redirect("reports")

    period = get_object_or_404(PayrollPeriod.objects.select_related("company"), pk=pk)
    rows = _report_rows(period)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = spec["title"][:30]
    sheet.sheet_view.rightToLeft = True

    sheet.append([f"{spec['title']} — {period.title} — {period.company.name}"])
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(spec["headers"]))
    sheet.cell(row=1, column=1).font = Font(bold=True, size=13)
    sheet.cell(row=1, column=1).alignment = Alignment(horizontal="center")

    sheet.append(spec["headers"])
    header_fill = PatternFill("solid", fgColor="F3EEE4")
    for cell in sheet[2]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for index, payslip in enumerate(rows, start=1):
        sheet.append(spec["fields"](payslip, index))

    # عرض ستون‌ها بر اساس محتوا. سطر اول merge شده است و سلول‌های merge شده
    # column_letter ندارند، پس از شماره ستون حرف را می‌سازیم.
    for index in range(1, len(spec["headers"]) + 1):
        letter = get_column_letter(index)
        width = max(
            (len(str(sheet.cell(row=row, column=index).value or "")) for row in range(2, sheet.max_row + 1)),
            default=10,
        )
        sheet.column_dimensions[letter].width = min(max(width + 3, 12), 42)

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    filename = f"{kind}-{period.year}-{period.month:02d}.xlsx"
    response = HttpResponse(
        buffer.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
