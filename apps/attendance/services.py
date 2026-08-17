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

# فیلدهای عددی قابل ست کردن دستی.
# اضافه‌کاری اینجا نیست چون ورودی‌اش سه‌تایی (دقیقه/ساعت/روز) است، و شب‌کاری و
# جمعه‌کاری هم از فرم کارکرد ماهانه برداشته شده‌اند.
NUMERIC_FIELDS = [
    "work_days",
    "absence_days",
    "unpaid_leave_days",
    "sick_leave_days",
    "mission_days",
    "holiday_hours",
]


def minutes_from_parts(data, prefix, day_minutes) -> int:
    """«۱ روز و ۲ ساعت و ۳۰ دقیقه» از سه ورودی → دقیقه.

    prefix نام سه کلید را می‌سازد: `leave_d/h/m` یا `ot_d/h/m`.
    """
    days = int(parse_decimal(data.get(f"{prefix}_d")))
    hours = int(parse_decimal(data.get(f"{prefix}_h")))
    minutes = int(parse_decimal(data.get(f"{prefix}_m")))
    return max(days * day_minutes + hours * 60 + minutes, 0)


def has_parts(data, prefix) -> bool:
    return any(f"{prefix}_{part}" in data for part in ("d", "h", "m"))


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


def default_work_days(period, employee=None):
    """کارکرد اولیهٔ پیش‌فرض یک پرسنل در یک دوره.

    اگر پرسنل داده شود، از **بازهٔ اشتغال** او حساب می‌شود: تاریخ استخدام،
    تاریخ خاتمه کار و تاریخ شروع به کار مجدد. کسی که وسط ماه رفته یا آمده،
    نباید کارکرد کاملِ ماه بگیرد — خاتمهٔ ۱۶ مرداد یعنی ۱۵ روز، نه ۳۱.

    بدون پرسنل، طول خود ماه برمی‌گردد (شش‌ماههٔ اول ۳۱، دوم ۳۰، اسفند ۲۹/۳۰).
    در هر حال فقط مقدار اولیهٔ ورودی است و دستی قابل اصلاح.
    """
    if period is None:
        return Decimal("30")

    if employee is not None:
        return Decimal(
            employee.employed_days_in(period.start_date, period.end_date)
        )

    days = period.month_days
    if days:
        return Decimal(days)
    if period.legal_parameter:
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
        work_days=default_work_days(period, employee),
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

    minutes_per_day = day_minutes_of(timesheet.period)
    if has_parts(data, "leave"):
        timesheet.leave_minutes = minutes_from_parts(data, "leave", minutes_per_day)
    if has_parts(data, "ot"):
        timesheet.overtime_minutes = minutes_from_parts(data, "ot", minutes_per_day)

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

    `work_days` خالی یعنی «خودت حساب کن» — آن وقت از بازهٔ اشتغال همان پرسنل
    گرفته می‌شود، نه از طول کامل ماه.

    اگر دورهٔ بازی نباشد بی‌صدا کاری نمی‌کند و None برمی‌گرداند؛ صدا زدنش نباید
    ثبت پرسنل را شکست بدهد.
    """
    period = open_period_for(employee.company)
    if period is None:
        return None
    timesheet = get_or_create_timesheet(employee, period)
    if timesheet.pk:
        return timesheet
    if work_days is None:
        work_days = default_work_days(period, employee)
    timesheet.work_days = max(Decimal(work_days), Decimal("0"))
    if user is not None and getattr(user, "pk", None):
        timesheet.entered_by = user
    timesheet.source = Timesheet.Source.MANUAL
    timesheet.save()
    return timesheet
