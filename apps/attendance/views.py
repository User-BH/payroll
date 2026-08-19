from django import forms
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import can_edit_required, payroll_staff_required
from apps.attendance.importer import build_template, import_timesheets
from apps.attendance.items import RENDERED_FIELDS, attach_cells, extra_items, save_cells
from apps.attendance.leave import DEFAULT_DAY_MINUTES, balances_for, compute_balance
from apps.attendance.models import Timesheet
from apps.attendance.services import default_work_days


class TimesheetImportForm(forms.Form):
    file = forms.FileField(
        label="فایل اکسل کارکرد",
        help_text="ابتدا فایل الگوی این دوره را دانلود کنید، اعداد را پر کنید و برگردانید",
    )
from apps.employees.models import Employee
from apps.payroll.models import PayrollPeriod
from apps.payroll.utils import parse_decimal

# فیلدهایی که در جدول قابل ویرایش‌اند.
# شب‌کاری و جمعه‌کاری عمداً نیستند: فیش‌های واقعی شرکت چنین قلمی ندارند.
EDITABLE_FIELDS = [
    "work_days",
    "absence_days",
    "sick_leave_days",
    "unpaid_leave_days",
    "mission_days",
]

# مرخصی و اضافه‌کاری جدا هندل می‌شوند چون ورودی هرکدام سه‌تایی است:
# دقیقه، ساعت، روز
LEAVE_FIELDS = ["leave_d", "leave_h", "leave_m"]
OVERTIME_FIELDS = ["ot_d", "ot_h", "ot_m"]


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
        # کارکرد اولیه از بازهٔ اشتغال همان پرسنل می‌آید. صفر یعنی در این ماه
        # اصلاً شاغل نبوده، پس ردیف کارکرد هم لازم ندارد.
        initial_days = default_work_days(period, employee)
        if initial_days <= 0:
            continue
        new_rows.append(
            Timesheet(
                period=period,
                employee=employee,
                contract=contract,
                work_days=initial_days,
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
    # period و پارامترش هم لازم‌اند: طول روز کاری برای نمایش مرخصی و
    # اضافه‌کاری از آن‌ها خوانده می‌شود و بدون select_related هر ردیف دو کوئری
    # اضافه می‌زند (۱۴۶ ردیف = ۲۹۲ کوئری).
    timesheets = Timesheet.objects.filter(period=period).select_related(
        "employee", "contract", "contract__department", "period", "period__legal_parameter"
    ).prefetch_related("entries")
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
    approved = timesheets.filter(status=Timesheet.Status.APPROVED).count()
    total = timesheets.count()
    items = extra_items(period.company)
    return render(
        request,
        "timesheets/grid.html",
        {
            "period": period,
            "timesheets": attach_cells(timesheets, items),
            "extra_items": items,
            "q": query,
            "approved_count": approved,
            "total": total,
            "balances": balances_for(period, _day_minutes(period)),
        },
    )


@payroll_staff_required
def timesheet_rows(request, pk):
    period = get_object_or_404(PayrollPeriod, pk=pk)
    timesheets, query = _rows(request, period)
    items = extra_items(period.company)
    return render(
        request,
        "timesheets/_rows.html",
        {
            "period": period,
            "timesheets": attach_cells(timesheets, items),
            "extra_items": items,
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
def employee_timesheet_save(request, pk):
    """ست کردن دستی کارکرد ماهانهٔ یک پرسنل از صفحهٔ خودش.

    برای پرسنلِ تازه‌افزوده‌شده لازم است: کاربر نمی‌خواهد برای یک نفر، جدول
    کارکرد کل دوره را باز کند. رکورد مقصد همان Timesheet دوره است.
    """
    from apps.attendance.services import apply_manual_timesheet, get_or_create_timesheet
    from apps.employees.models import Employee

    employee = get_object_or_404(Employee, pk=pk)
    period = get_object_or_404(
        PayrollPeriod.objects.select_related("legal_parameter"),
        pk=request.POST.get("period") or 0,
    )

    if not period.is_editable:
        messages.error(request, "کارکرد این دوره دیگر قابل ویرایش نیست.")
        return redirect("employee_detail", pk=employee.pk)

    if employee.contract_on(period.end_date) is None:
        messages.error(
            request,
            "این پرسنل در این دوره قرارداد فعال ندارد؛ کارکردش در محاسبه لحاظ نمی‌شود.",
        )
        return redirect("employee_detail", pk=employee.pk)

    approve = None
    if request.POST.get("approve") == "1":
        approve = True
    elif request.POST.get("approve") == "0":
        approve = False

    timesheet = get_or_create_timesheet(employee, period)
    apply_manual_timesheet(timesheet, request.POST, user=request.user, approve=approve)

    messages.success(request, f"کارکرد {employee.full_name} در {period.title} ثبت شد.")
    return redirect("employee_detail", pk=employee.pk)


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
        Timesheet.objects.select_related(
            "employee", "period", "period__legal_parameter", "contract", "contract__department"
        ),
        pk=pk,
    )
    period = timesheet.period

    items = extra_items(period.company)

    if not period.is_editable:
        return render(
            request,
            "timesheets/_row.html",
            {
                "ts": attach_cells([timesheet], items)[0],
                "period": period,
                "extra_items": items,
                "error": "دوره قابل ویرایش نیست.",
            },
        )

    from apps.attendance.services import minutes_from_parts

    for field in EDITABLE_FIELDS:
        if field in request.POST:
            setattr(timesheet, field, max(parse_decimal(request.POST.get(field)), 0))

    day_minutes = (
        period.legal_parameter.leave_day_minutes
        if period.legal_parameter
        else DEFAULT_DAY_MINUTES
    )
    if any(f in request.POST for f in LEAVE_FIELDS):
        timesheet.leave_minutes = minutes_from_parts(request.POST, "leave", day_minutes)
    if any(f in request.POST for f in OVERTIME_FIELDS):
        timesheet.overtime_minutes = minutes_from_parts(request.POST, "ot", day_minutes)

    if request.POST.get("approve") == "1":
        timesheet.status = Timesheet.Status.APPROVED
        timesheet.approved_by = request.user
        timesheet.approved_at = timezone.now()
    elif request.POST.get("approve") == "0":
        timesheet.status = Timesheet.Status.DRAFT
        timesheet.approved_by = None
        timesheet.approved_at = None

    # اقلام تازه: آن‌هایی که ستون قدیمی دارند روی خودِ سطر می‌نشینند و با
    # همین save ذخیره می‌شوند؛ بقیه رکورد جدا می‌سازند و به یک سطرِ ذخیره‌شده
    # نیاز دارند، پس بعد از save دوباره صدا زده می‌شود.
    save_cells(timesheet, request.POST, [i for i in items if i.source_field])
    timesheet.entered_by = request.user
    timesheet.save()
    save_cells(timesheet, request.POST, [i for i in items if not i.source_field])

    return render(
        request,
        "timesheets/_row.html",
        {
            "ts": attach_cells([timesheet], items)[0],
            "extra_items": items,
            "period": period,
            "saved": True,
            "balance": compute_balance(
                timesheet.employee, period,
                period.legal_parameter.leave_day_minutes
                if period.legal_parameter else DEFAULT_DAY_MINUTES,
            ),
        },
    )


# ==================================================== اقلام کارکرد (ستون‌ها)


class TimesheetItemForm(forms.ModelForm):
    """تعریف یک ستون تازه برای جدول کارکرد.

    `source_field` عمداً در فرم نیست: ستون‌های قدیمی از پیش تعریف شده‌اند و
    قلم تازه‌ای که کاربر می‌سازد باید مقدارش را در جدول مقادیر بگذارد، نه در
    یک فیلد دلخواه روی مدل. اجازهٔ نوشتن نام فیلد یعنی اجازهٔ نوشتن روی هر
    ستون دیگری از کارکرد.
    """

    class Meta:
        from apps.attendance.models import TimesheetItem as _Item

        model = _Item
        fields = ["code", "name", "unit", "reduces_work_days", "sequence",
                  "is_active", "description"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                continue
            widget.attrs.setdefault("class", "input")

    def clean_code(self):
        from apps.attendance.models import TimesheetItem

        code = (self.cleaned_data.get("code") or "").strip().upper()
        queryset = TimesheetItem.objects.filter(company=self.company, code=code)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("این کد قبلاً برای قلم کارکرد دیگری استفاده شده است.")
        return code


@payroll_staff_required
def timesheet_items(request):
    """فهرست ستون‌های جدول کارکرد، با امکان افزودن ستون تازه.

    این صفحه پاسخ همان خواستهٔ «هر وقت خواستیم جمعه‌کاری را اضافه کنیم» است:
    یک تیک، و ستون در جدول کارکرد ظاهر می‌شود. برای اینکه آن ستون به پول
    تبدیل شود، یک قلم حقوقی پارامتری هم لازم است که مقدارش را از همین قلم
    بگیرد — لینک ساختش در همین صفحه است.
    """
    from apps.attendance.models import TimesheetItem
    from apps.org.models import Company

    company = Company.objects.first()
    can_edit = getattr(request.user, "can_edit_payroll", False)
    form = TimesheetItemForm(
        request.POST or None, company=company
    ) if can_edit else None

    if request.method == "POST" and can_edit and form.is_valid():
        item = form.save(commit=False)
        item.company = company
        item.save()
        messages.success(
            request,
            f"ستون «{item.name}» به جدول کارکرد اضافه شد. برای اینکه به مبلغ تبدیل شود، "
            "یک قلم حقوقی با مقدارِ «یک قلم جدول کارکرد» بسازید.",
        )
        return redirect("timesheet_items")

    items = TimesheetItem.objects.filter(company=company)
    used_by = {}
    from apps.payroll_config.models import SalaryComponent

    for component in SalaryComponent.objects.filter(
        timesheet_item__isnull=False
    ).select_related("timesheet_item"):
        used_by.setdefault(component.timesheet_item_id, []).append(component)

    rows = []
    for item in items:
        rows.append({
            "item": item,
            "components": used_by.get(item.pk, []),
            "in_grid": item.source_field not in RENDERED_FIELDS,
        })

    return render(
        request,
        "timesheets/items.html",
        {"rows": rows, "form": form, "company": company},
    )


@can_edit_required
@require_POST
def timesheet_item_toggle(request, pk):
    """روشن/خاموش کردن یک ستون — همان یک تیکی که قلم تازه را به جدول می‌آورد."""
    from apps.attendance.models import TimesheetItem

    item = get_object_or_404(TimesheetItem, pk=pk)
    item.is_active = not item.is_active
    item.save(update_fields=["is_active"])
    state = "به جدول کارکرد اضافه شد" if item.is_active else "از جدول کارکرد برداشته شد"
    messages.success(request, f"ستون «{item.name}» {state}.")
    return redirect("timesheet_items")
