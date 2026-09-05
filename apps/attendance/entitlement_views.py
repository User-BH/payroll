"""ثبت سهمیه مرخصی سالانه پرسنل."""

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.org.current import active_company
from django.views.decorators.http import require_POST

from apps.accounts.decorators import can_edit_required, payroll_staff_required
from apps.attendance.leave import (
    DEFAULT_DAY_MINUTES,
    annual_entitlement_minutes,
    balances_for,
    format_dhm,
)
from apps.attendance.models import LeaveEntitlement
from apps.employees.models import Employee
from apps.payroll.models import JALALI_MONTHS, PayrollPeriod
from apps.payroll.utils import is_partial_request, parse_decimal
from apps.payroll_config.models import FiscalYear


# شماره و نام ماه، برای انتخاب مرزِ مانده‌گیری افتتاحیه
MONTH_CHOICES = list(enumerate(JALALI_MONTHS, start=1))


def _day_minutes(fiscal_year):
    """طول روز مرخصی روی LegalParameter است، نه روی FiscalYear."""
    params = (
        fiscal_year.legal_parameters.order_by("-effective_from").first()
        if fiscal_year
        else None
    )
    return params.leave_day_minutes if params else DEFAULT_DAY_MINUTES


def _rows(fiscal_year, query):
    employees = Employee.objects.filter(
        company=fiscal_year.company, status=Employee.Status.ACTIVE
    )
    if query:
        employees = employees.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(personnel_code__icontains=query)
        )
    employees = employees.order_by("personnel_code")

    entitlements = {
        item.employee_id: item
        for item in LeaveEntitlement.objects.filter(fiscal_year=fiscal_year)
    }
    last_period = (
        PayrollPeriod.objects.filter(fiscal_year=fiscal_year).order_by("-month").first()
    )
    day_minutes = _day_minutes(fiscal_year)
    params = fiscal_year.legal_parameters.order_by("-effective_from").first()
    balances = balances_for(last_period, day_minutes) if last_period else {}

    rows = []
    for employee in employees:
        item = entitlements.get(employee.pk)
        balance = balances.get(employee.pk)
        computed = annual_entitlement_minutes(
            employee, fiscal_year, params, day_minutes
        ) or 0
        rows.append({
            "employee": employee,
            "carried_days": round((item.carried_over_minutes if item else 0) / day_minutes, 2),
            "annual_days": round(
                (item.annual_minutes if item else computed) / day_minutes, 2
            ),
            "computed_days": round(computed / day_minutes, 2),
            "is_manual": bool(item and item.annual_is_manual),
            "opening_days": round((item.opening_used_minutes if item else 0) / day_minutes, 2),
            "opening_through_month": item.opening_through_month if item else 0,
            "months": MONTH_CHOICES,
            "used": format_dhm(balance.used_ytd, day_minutes) if balance else "۰",
            "remaining": format_dhm(balance.remaining, day_minutes) if balance else None,
            "missing": item is None,
        })
    return rows


def _fiscal_year(request):
    years = (
        FiscalYear.objects.filter(company=active_company(request))
        .select_related("company").order_by("-year")
    )
    year_id = request.GET.get("year")
    return years.filter(pk=year_id).first() if year_id else years.first(), years


@payroll_staff_required
def entitlement_list(request):
    fiscal_year, years = _fiscal_year(request)
    if fiscal_year is None:
        return render(request, "leave/entitlements.html", {"years": years})

    query = request.GET.get("q", "").strip()
    rows = _rows(fiscal_year, query)
    template = (
        "leave/_entitlement_rows.html"
        if is_partial_request(request)
        else "leave/entitlements.html"
    )
    return render(
        request,
        template,
        {
            "years": years,
            "fiscal_year": fiscal_year,
            "rows": rows,
            "q": query,
            "missing_count": sum(1 for row in rows if row["missing"]),
            "day_minutes": _day_minutes(fiscal_year),
        },
    )


@can_edit_required
@require_POST
def entitlement_save(request):
    """ذخیره درجای سهمیه یک نفر. ورودی به روز است و به دقیقه تبدیل می‌شود."""
    fiscal_year = get_object_or_404(FiscalYear, pk=request.POST.get("fiscal_year"))
    employee = get_object_or_404(Employee, pk=request.POST.get("employee"))
    day_minutes = _day_minutes(fiscal_year)

    carried = parse_decimal(request.POST.get("carried_days"))
    annual = parse_decimal(request.POST.get("annual_days"))
    opening = parse_decimal(request.POST.get("opening_days"))

    # مرز فقط وقتی معنا دارد که عددی هم باشد، و برعکس: عددِ افتتاحیه بدون مرز
    # یعنی سامانه نمی‌داند تا کجا را نباید از کارکرد بشمارد، و روزی که آن
    # ماه‌ها وارد شوند دو بار حساب می‌شوند. پس هر کدام بدون دیگری صفر می‌شود.
    try:
        through = int(request.POST.get("opening_through_month") or 0)
    except ValueError:
        through = 0
    through = through if 1 <= through <= 12 else 0
    opening_minutes = int(round(float(opening) * day_minutes))
    if not through or not opening_minutes:
        through, opening_minutes = 0, 0

    # تا وقتی تیکِ «دستی» نخورده، عددِ داخل کادر خوانده نمی‌شود و قاعده حاکم
    # است — همان کاری که `LeaveEntitlement.save()` می‌کند.
    is_manual = request.POST.get("annual_is_manual") in ("on", "1", "true")
    row_obj = LeaveEntitlement.objects.filter(
        employee=employee, fiscal_year=fiscal_year
    ).first() or LeaveEntitlement(employee=employee, fiscal_year=fiscal_year)
    row_obj.carried_over_minutes = int(round(float(carried) * day_minutes))
    row_obj.annual_is_manual = is_manual
    if is_manual:
        row_obj.annual_minutes = int(round(float(annual) * day_minutes))
    row_obj.opening_used_minutes = opening_minutes
    row_obj.opening_through_month = through
    row_obj.save()
    rows = _rows(fiscal_year, "")
    row = next(r for r in rows if r["employee"].pk == employee.pk)
    return render(
        request,
        "leave/_entitlement_row.html",
        {"row": row, "fiscal_year": fiscal_year, "saved": True},
    )


@can_edit_required
@require_POST
def entitlement_fill_all(request):
    """ثبت یکجای سهمیه برای همه کسانی که هنوز سهمیه ندارند."""
    fiscal_year = get_object_or_404(FiscalYear, pk=request.POST.get("fiscal_year"))
    day_minutes = _day_minutes(fiscal_year)
    carried = parse_decimal(request.POST.get("carried_days"))
    params = fiscal_year.legal_parameters.order_by("-effective_from").first()

    have = set(
        LeaveEntitlement.objects.filter(fiscal_year=fiscal_year).values_list(
            "employee_id", flat=True
        )
    )
    missing = Employee.objects.filter(
        company=fiscal_year.company, status=Employee.Status.ACTIVE
    ).exclude(pk__in=have)

    created = [
        LeaveEntitlement(
            employee=employee,
            fiscal_year=fiscal_year,
            carried_over_minutes=int(round(float(carried) * day_minutes)),
            annual_minutes=annual_entitlement_minutes(
                employee, fiscal_year, params, day_minutes
            ) or 0,
        )
        for employee in missing
    ]
    LeaveEntitlement.objects.bulk_create(created)
    messages.success(
        request,
        f"سهمیه برای {len(created)} نفری که سهمیه نداشتند از تاریخ استخدامشان "
        "محاسبه و ثبت شد. کسانی که قبلاً سهمیه داشتند دست‌نخورده ماندند.",
    )
    return redirect(f"/leave/entitlements/?year={fiscal_year.pk}")
