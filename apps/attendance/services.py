"""ست کردن دستی کارکرد ماهانهٔ یک پرسنل، بیرون از جدول کارکرد دوره.

جدول کارکرد دوره (`timesheet_grid`) برای پر کردن انبوه است. وقتی یک پرسنل تازه
اضافه می‌شود، کاربر می‌خواهد همان‌جا کارکردش را بگذارد و منتظر باز کردن جدول
دوره نماند. هر دو مسیر به همان یک رکورد `Timesheet` می‌رسند — هیچ داده‌ای دو
جا نگهداری نمی‌شود.
"""

from decimal import Decimal

from django.utils import timezone

from apps.attendance.leave import DEFAULT_DAY_MINUTES
from apps.attendance.models import Timesheet
from apps.payroll.models import PayrollPeriod
from apps.payroll.utils import parse_decimal

# فیلدهای عددی قابل ست کردن دستی
NUMERIC_FIELDS = [
    "work_days",
    "absence_days",
    "unpaid_leave_days",
    "sick_leave_days",
    "mission_days",
    "overtime_hours",
    "night_hours",
    "friday_hours",
    "holiday_hours",
]


def open_period_for(company):
    """آخرین دورهٔ قابل ویرایش (پیش‌نویس) شرکت — همان دوره‌ای که کارکردش باز است."""
    return (
        PayrollPeriod.objects.filter(
            company=company, status=PayrollPeriod.Status.DRAFT
        )
        .select_related("legal_parameter")
        .order_by("-year", "-month")
        .first()
    )


def day_minutes_of(period):
    if period and period.legal_parameter:
        return period.legal_parameter.leave_day_minutes
    return DEFAULT_DAY_MINUTES


def default_work_days(period):
    """روز کارکرد پیش‌فرض — از پارامتر قانونی همان دوره، وگرنه ۳۰."""
    if period and period.legal_parameter:
        return Decimal(period.legal_parameter.monthly_days)
    return Decimal("30")


def get_or_create_timesheet(employee, period):
    """رکورد کارکرد پرسنل در دوره؛ اگر نبود ساخته می‌شود.

    قرارداد معتبر در پایان دوره ضمیمه می‌شود تا موتور محاسبه بداند با کدام
    حقوق پایه کار کند.
    """
    timesheet = Timesheet.objects.filter(period=period, employee=employee).first()
    if timesheet is not None:
        return timesheet
    return Timesheet(
        period=period,
        employee=employee,
        contract=employee.contract_on(period.end_date),
        work_days=default_work_days(period),
    )


def apply_manual_timesheet(timesheet, data, user=None, approve=None):
    """مقادیر فرم دستی را روی رکورد کارکرد می‌نشاند و ذخیره می‌کند.

    `data` هر نگاشتی مثل request.POST است؛ فقط کلیدهای موجود اعمال می‌شوند تا
    فرم‌های نیمه‌کامل، بقیهٔ اعداد را صفر نکنند.
    """
    for field in NUMERIC_FIELDS:
        if field in data:
            value = parse_decimal(data.get(field))
            setattr(timesheet, field, max(value, Decimal("0")))

    if any(key in data for key in ("leave_d", "leave_h", "leave_m")):
        minutes_per_day = day_minutes_of(timesheet.period)
        days = int(parse_decimal(data.get("leave_d")))
        hours = int(parse_decimal(data.get("leave_h")))
        minutes = int(parse_decimal(data.get("leave_m")))
        timesheet.leave_minutes = max(days * minutes_per_day + hours * 60 + minutes, 0)

    if "shift_type" in data and data.get("shift_type"):
        timesheet.shift_type = data.get("shift_type")

    if timesheet.contract_id is None:
        timesheet.contract = timesheet.employee.contract_on(timesheet.period.end_date)

    timesheet.source = Timesheet.Source.MANUAL
    if user is not None and getattr(user, "pk", None):
        timesheet.entered_by = user

    if approve is True:
        timesheet.status = Timesheet.Status.APPROVED
        timesheet.approved_by = user if getattr(user, "pk", None) else None
        timesheet.approved_at = timezone.now()
    elif approve is False:
        timesheet.status = Timesheet.Status.DRAFT
        timesheet.approved_by = None
        timesheet.approved_at = None

    timesheet.save()
    return timesheet


def set_initial_timesheet(employee, work_days, user=None):
    """کارکرد ماهانهٔ پرسنل تازه‌افزوده‌شده در دورهٔ باز.

    اگر دورهٔ بازی نباشد یا پرسنل قرارداد نداشته باشد، بی‌صدا کاری نمی‌کند و
    None برمی‌گرداند؛ صدا زدنش نباید ثبت پرسنل را شکست بدهد.
    """
    if work_days is None:
        return None
    period = open_period_for(employee.company)
    if period is None:
        return None
    timesheet = get_or_create_timesheet(employee, period)
    if timesheet.pk:
        return timesheet
    timesheet.work_days = max(Decimal(work_days), Decimal("0"))
    if user is not None and getattr(user, "pk", None):
        timesheet.entered_by = user
    timesheet.source = Timesheet.Source.MANUAL
    timesheet.save()
    return timesheet
