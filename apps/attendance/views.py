from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import can_edit_required, payroll_staff_required
from apps.attendance.models import Timesheet
from apps.employees.models import Employee
from apps.payroll.models import PayrollPeriod
from apps.payroll.utils import parse_decimal

# فیلدهایی که در جدول قابل ویرایش‌اند
EDITABLE_FIELDS = [
    "work_days",
    "paid_leave_days",
    "absence_days",
    "overtime_hours",
    "night_hours",
    "friday_hours",
]


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
        },
    )


@payroll_staff_required
def timesheet_rows(request, pk):
    period = get_object_or_404(PayrollPeriod, pk=pk)
    timesheets, query = _rows(request, period)
    return render(
        request,
        "timesheets/_rows.html",
        {"period": period, "timesheets": timesheets, "q": query},
    )


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
        {"ts": timesheet, "period": period, "saved": True},
    )
