from django import forms
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import can_edit_required, payroll_staff_required
from apps.attendance.importer import build_template, import_timesheets
from apps.attendance.leave import DEFAULT_DAY_MINUTES, balances_for, compute_balance
from apps.attendance.models import Timesheet


class TimesheetImportForm(forms.Form):
    file = forms.FileField(
        label="فایل اکسل کارکرد",
        help_text="ابتدا فایل این دوره را دانلود کنید، اعداد را پر کنید و برگردانید",
    )
from apps.employees.models import Employee
from apps.payroll.models import PayrollPeriod
from apps.payroll.utils import parse_decimal

# فیلدهایی که در جدول قابل ویرایش‌اند
EDITABLE_FIELDS = [
    "work_days",
    "absence_days",
    "overtime_hours",
    "night_hours",
    "friday_hours",
]

# مرخصی جدا هندل می‌شود چون ورودی‌اش سه‌تایی است: روز، ساعت، دقیقه
LEAVE_FIELDS = ["leave_d", "leave_h", "leave_m"]


def _ensure_timesheets(period):
    """برای هر پرسنل فعالِ دارای قرارداد، یک رکورد کارکرد بساز اگر نیست."""
    existing = set(
        Timesheet.objects.filter(period=period).values_list("employee_id", flat=True)
    )
    employees = Employee.objects.filter(
        company=period.company, status=Employee.Status.ACTIVE
    ).exclude(pk__in=existing)

    new_rows = []
    for employee in employees:
        contract = employee.contract_on(period.end_date)
        if contract is None:
            continue
        new_rows.append(
            Timesheet(
                period=period,
                employee=employee,
                contract=contract,
                work_days=period.legal_parameter.monthly_days if period.legal_parameter else 30,
            )
        )
    if new_rows:
        Timesheet.objects.bulk_create(new_rows)


def _day_minutes(period):
    if period.legal_parameter:
        return period.legal_parameter.leave_day_minutes
    return DEFAULT_DAY_MINUTES


def _rows(request, period):
    query = request.GET.get("q", "").strip()
    timesheets = Timesheet.objects.filter(period=period).select_related(
        "employee", "contract", "contract__department"
    )
    if query:
        timesheets = timesheets.filter(
            Q(employee__first_name__icontains=query)
            | Q(employee__last_name__icontains=query)
            | Q(employee__personnel_code__icontains=query)
        )
    return timesheets.order_by("employee__personnel_code"), query


@payroll_staff_required
def timesheet_grid(request, pk):
    period = get_object_or_404(PayrollPeriod.objects.select_related("legal_parameter"), pk=pk)
    if period.is_editable:
        _ensure_timesheets(period)
    timesheets, query = _rows(request, period)
    return render(
        request,
        "timesheets/grid.html",
        {
            "period": period,
            "timesheets": timesheets,
            "q": query,
            "approved_count": timesheets.filter(status=Timesheet.Status.APPROVED).count(),
            "total": timesheets.count(),
            "balances": balances_for(period, _day_minutes(period)),
        },
    )


@payroll_staff_required
def timesheet_rows(request, pk):
    period = get_object_or_404(PayrollPeriod, pk=pk)
    timesheets, query = _rows(request, period)
    return render(
        request,
        "timesheets/_rows.html",
        {
            "period": period,
            "timesheets": timesheets,
            "q": query,
            "balances": balances_for(period, _day_minutes(period)),
        },
    )


@payroll_staff_required
def timesheet_import_template(request, pk):
    period = get_object_or_404(PayrollPeriod.objects.select_related("legal_parameter"), pk=pk)
    if period.is_editable:
        _ensure_timesheets(period)
    response = HttpResponse(
        build_template(period),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="timesheet-{period.year}-{period.month:02d}.xlsx"'
    )
    return response


@can_edit_required
def timesheet_import(request, pk):
    period = get_object_or_404(PayrollPeriod.objects.select_related("legal_parameter"), pk=pk)
    form = TimesheetImportForm(request.POST or None, request.FILES or None)
    result = None

    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        try:
            result = import_timesheets(
                upload, period, user=request.user, file_name=upload.name
            )
        except Exception as exc:  # noqa: BLE001 — خطای فایل باید به کاربر برسد
            messages.error(request, f"فایل خوانده نشد: {exc}")
        else:
            if result["errors"]:
                messages.error(
                    request,
                    f"{len(result['errors'])} سطر ایراد دارد و هیچ ردیفی به‌روز نشد.",
                )
            else:
                messages.success(request, f"کارکرد {result['updated']} نفر به‌روز شد.")
                return redirect("timesheet_grid", pk=period.pk)

    return render(
        request,
        "timesheets/import.html",
        {"period": period, "form": form, "result": result},
    )


@can_edit_required
@require_POST
def timesheet_approve_all(request, pk):
    """تأیید یکجای همه کارکردهای دوره."""
    period = get_object_or_404(PayrollPeriod, pk=pk)
    if not period.is_editable:
        messages.error(request, "دوره در وضعیت پیش‌نویس نیست.")
        return redirect("timesheet_grid", pk=period.pk)

    count = Timesheet.objects.filter(period=period).exclude(
        status=Timesheet.Status.APPROVED
    ).update(
        status=Timesheet.Status.APPROVED,
        approved_by=request.user,
        approved_at=timezone.now(),
    )
    messages.success(request, f"{count} ردیف کارکرد تأیید شد.")
    return redirect("timesheet_grid", pk=period.pk)


@can_edit_required
@require_POST
def timesheet_save(request, pk):
    """ذخیره درجای یک سطر کارکرد — پاسخ HTMX فقط همان سطر است.

    این همان صفحه‌ای است که رفرش کامل در آن آزاردهنده می‌شود: ۱۴۶ ردیف و چند
    ستون عددی.
    """
    timesheet = get_object_or_404(
        Timesheet.objects.select_related("employee", "period", "contract", "contract__department"),
        pk=pk,
    )
    period = timesheet.period

    if not period.is_editable:
        return render(
            request,
            "timesheets/_row.html",
            {"ts": timesheet, "period": period, "error": "دوره قابل ویرایش نیست."},
        )

    for field in EDITABLE_FIELDS:
        if field in request.POST:
            setattr(timesheet, field, parse_decimal(request.POST.get(field)))

    if any(f in request.POST for f in LEAVE_FIELDS):
        day_minutes = (
            period.legal_parameter.leave_day_minutes
            if period.legal_parameter
            else DEFAULT_DAY_MINUTES
        )
        days = int(parse_decimal(request.POST.get("leave_d")))
        hours = int(parse_decimal(request.POST.get("leave_h")))
        minutes = int(parse_decimal(request.POST.get("leave_m")))
        timesheet.leave_minutes = max(days * day_minutes + hours * 60 + minutes, 0)

    if request.POST.get("approve") == "1":
        timesheet.status = Timesheet.Status.APPROVED
        timesheet.approved_by = request.user
        timesheet.approved_at = timezone.now()
    elif request.POST.get("approve") == "0":
        timesheet.status = Timesheet.Status.DRAFT
        timesheet.approved_by = None
        timesheet.approved_at = None

    timesheet.entered_by = request.user
    timesheet.save()

    return render(
        request,
        "timesheets/_row.html",
        {
            "ts": timesheet,
            "period": period,
            "saved": True,
            "balance": compute_balance(
                timesheet.employee, period,
                period.legal_parameter.leave_day_minutes
                if period.legal_parameter else DEFAULT_DAY_MINUTES,
            ),
        },
    )
