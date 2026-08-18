"""کارتابل مرخصی — ثبت مرخصی و اعمال خودکارش در کارکرد ماه.

هدف سند: «اطلاعات ثبت‌شده در این بخش باید مستقیماً در محاسبات حقوق و کارکرد
همان ماه اعمال شود تا نیازی به ورود مجدد اطلاعات یا رفت‌وبرگشت اطلاعات بین
بخش کارگزینی و حقوق و دستمزد وجود نداشته باشد.»

قاعدهٔ همگام‌سازی — دقیق و قابل توضیح:

    اگر برای یک **نوع** مرخصی در آن دوره رکوردی در کارتابل وجود داشته باشد —
    ثبت‌شده یا لغوشده — آن ستونِ کارکرد «مال کارتابل» است و از **جمع رکوردهای
    ثبت‌شده** ساخته می‌شود؛ حتی اگر آن جمع صفر باشد. نوعی که هیچ رکوردی ندارد
    دست‌نخورده می‌ماند.

لغوشده‌ها هم به همین دلیل شمرده می‌شوند: اگر تنها رکوردِ بیماری لغو شود، ستون
بیماری باید صفر شود، نه اینکه عدد قبلی در کارکرد جا بماند.

این‌طوری کارتابل روی مقادیری که کاربر دستی در جدول کارکرد زده دست نمی‌اندازد،
مگر برای همان نوعی که واقعاً در کارتابل ثبت شده است. و چون هر بار از صفر
جمع می‌زند، ثبت و لغو مکرر هرگز مقدار را دوباره‌شماری نمی‌کند.
"""

from decimal import Decimal

from apps.attendance.models import LeaveRecord, Timesheet
from apps.payroll.models import PayrollPeriod

ZERO = Decimal("0")


def periods_covering(employee, start, end):
    """دوره‌هایی از شرکت این پرسنل که با بازهٔ [start, end] هم‌پوشانی دارند."""
    return PayrollPeriod.objects.filter(
        company=employee.company, start_date__lte=end, end_date__gte=start
    ).select_related("legal_parameter")


def sync_employee_period(employee, period):
    """ستون‌های مرخصی کارکرد این پرسنل در این دوره را از کارتابل بازسازی می‌کند.

    اگر دوره قابل ویرایش نباشد کاری نمی‌کند: کارکرد قفل‌شده نباید با ثبت
    مرخصیِ بعدی عوض شود.
    """
    if not period.is_editable:
        return None

    records = LeaveRecord.objects.filter(
        employee=employee,
        start_date__lte=period.end_date,
        end_date__gte=period.start_date,
    )

    totals = {}
    for record in records:
        # هر نوعی که رکورد دارد وارد جدول می‌شود؛ لغوشده با سهم صفر، تا ستونش
        # پاک شود.
        totals.setdefault(record.kind, 0)
        if record.is_active:
            totals[record.kind] += record.minutes_in(
                period.start_date, period.end_date
            )
    if not totals:
        return None

    timesheet = Timesheet.objects.filter(period=period, employee=employee).first()
    if timesheet is None:
        from apps.attendance.services import get_or_create_timesheet

        timesheet = get_or_create_timesheet(employee, period)

    day_minutes = Decimal(timesheet.day_minutes)
    for kind, minutes in totals.items():
        field = LeaveRecord.TIMESHEET_FIELD[kind]
        if field == "leave_minutes":
            value = int(minutes)
        else:
            value = (Decimal(minutes) / day_minutes).quantize(Decimal("0.01"))
        setattr(timesheet, field, value)

    timesheet.save()
    return timesheet


def sync_record(record):
    """رکورد را در همهٔ دوره‌هایی که لمس می‌کند اعمال می‌کند."""
    touched = []
    for period in periods_covering(record.employee, record.start_date, record.end_date):
        result = sync_employee_period(record.employee, period)
        if result is not None:
            touched.append(period)
    return touched


def sync_period(period):
    """همگام‌سازی کل یک دوره — برای دکمهٔ «اعمال در کارکرد»."""
    employee_ids = set(
        LeaveRecord.objects.filter(
            start_date__lte=period.end_date,
            end_date__gte=period.start_date,
            employee__company=period.company,
        ).values_list("employee_id", flat=True)
    )
    from apps.employees.models import Employee

    count = 0
    for employee in Employee.objects.filter(pk__in=employee_ids):
        if sync_employee_period(employee, period) is not None:
            count += 1
    return count


def minutes_from_parts(days, hours, minutes, day_minutes) -> int:
    """«۱ روز و ۲ ساعت و ۳۰ دقیقه» → دقیقه."""
    return max(
        int(days or 0) * int(day_minutes) + int(hours or 0) * 60 + int(minutes or 0), 0
    )
