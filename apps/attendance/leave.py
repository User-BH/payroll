"""مانده مرخصی.

مرخصی در فیش شرکت به روز و ساعت و دقیقه نمایش داده می‌شود («۲۴ روز و ۷ ساعت و
۱۰ دقیقه»). نگهداری این عدد به‌صورت اعشاری روز، خطای گرد کردن تولید می‌کند، پس
واحد پایه **دقیقه** است و روز فقط برای نمایش ساخته می‌شود.

طول روز کاری از خود فیش استخراج شد: ۳۵ روز = ۲۵۶ ساعت و ۴۰ دقیقه
    ۱۵٬۴۰۰ دقیقه ÷ ۳۵ = ۴۴۰ دقیقه = ۷ ساعت و ۲۰ دقیقه
این مقدار در LegalParameter.leave_day_minutes قابل تغییر است.
"""

from dataclasses import dataclass

from apps.payroll.utils import fa_digits

DEFAULT_DAY_MINUTES = 440  # ۷ ساعت و ۲۰ دقیقه


def days_to_minutes(days, day_minutes=DEFAULT_DAY_MINUTES) -> int:
    return int(round(float(days) * day_minutes))


def split_dhm(minutes: int, day_minutes=DEFAULT_DAY_MINUTES):
    """تبدیل دقیقه به (روز، ساعت، دقیقه) — با علامت برای مانده منفی."""
    sign = -1 if minutes < 0 else 1
    total = abs(int(minutes))
    days, rest = divmod(total, day_minutes)
    hours, mins = divmod(rest, 60)
    return sign, days, hours, mins


def format_dhm(minutes, day_minutes=DEFAULT_DAY_MINUTES) -> str:
    """«۲۴ روز و ۷ ساعت و ۱۰ دقیقه» — بخش‌های صفر حذف می‌شوند."""
    if minutes is None:
        return "—"
    sign, days, hours, mins = split_dhm(minutes, day_minutes)
    parts = []
    if days:
        parts.append(f"{fa_digits(days)} روز")
    if hours:
        parts.append(f"{fa_digits(hours)} ساعت")
    if mins:
        parts.append(f"{fa_digits(mins)} دقیقه")
    if not parts:
        return "۰"
    text = " و ".join(parts)
    return f"منفی {text}" if sign < 0 else text


@dataclass
class LeaveBalance:
    """وضعیت مرخصی یک پرسنل تا پایان یک دوره."""

    day_minutes: int
    carried_over: int      # انتقالی از سال قبل
    annual: int            # استحقاقی سال جاری
    used_period: int       # مصرفی همین دوره
    used_ytd: int          # مصرفی از اول سال تا پایان همین دوره
    opening_used: int = 0  # سهمِ ماه‌های پیش از راه‌اندازی سامانه، داخل used_ytd

    @property
    def total(self) -> int:
        """کل مرخصی قابل استفاده در سال."""
        return self.carried_over + self.annual

    @property
    def remaining(self) -> int:
        return self.total - self.used_ytd

    def as_snapshot(self) -> dict:
        return {
            "day_minutes": self.day_minutes,
            "carried_over": self.carried_over,
            "annual": self.annual,
            "total": self.total,
            "used_period": self.used_period,
            "used_ytd": self.used_ytd,
            "opening_used": self.opening_used,
            "remaining": self.remaining,
        }


def _opening(entitlement):
    """(مصرفی افتتاحیه، مرزِ ماه) — یا صفر اگر افتتاحیه‌ای تعریف نشده باشد."""
    if entitlement is None:
        return 0, 0
    return (
        int(entitlement.opening_used_minutes or 0),
        int(entitlement.opening_through_month or 0),
    )


def _ytd(period, entitlement, timesheet_total_for) -> tuple:
    """مصرفی از اول سال = افتتاحیه + جمع کارکردِ ماه‌های بعد از مرز.

    اگر خودِ این دوره داخل بازهٔ افتتاحیه باشد (ماهش از مرز بزرگ‌تر نیست)،
    افتتاحیه اصلاً اعمال نمی‌شود: آن عدد جمعِ همان ماه‌هاست و نمی‌شود وسطش را
    جدا کرد. در عمل هم کسی دوره‌ای را که خودش داخل افتتاحیه است محاسبه
    نمی‌کند.
    """
    opening, through = _opening(entitlement)
    if not opening or period.month <= through:
        return timesheet_total_for(0), 0
    return opening + timesheet_total_for(through), opening


def balances_for(period, day_minutes=DEFAULT_DAY_MINUTES) -> dict:
    """مانده مرخصی همه پرسنل یک دوره — سه کوئری، نه یکی به‌ازای هر نفر.

    برای جدول کارکرد که ۱۴۶ ردیف دارد، محاسبه ردیف‌به‌ردیف یعنی صدها کوئری.
    """
    from django.db.models import Sum

    from apps.attendance.models import LeaveEntitlement, Timesheet

    entitlements = {
        item.employee_id: item
        for item in LeaveEntitlement.objects.filter(fiscal_year=period.fiscal_year)
    }
    # به تفکیک ماه، چون مرزِ افتتاحیه برای هر نفر می‌تواند فرق کند و جمعِ
    # یک‌کاسه اجازهٔ کنار گذاشتن ماه‌های پیش از مرز را نمی‌دهد.
    by_month = {}
    for row in (
        Timesheet.objects.filter(
            period__fiscal_year=period.fiscal_year,
            period__year=period.year,
            period__month__lte=period.month,
        )
        .values("employee_id", "period__month")
        .annotate(total=Sum("leave_minutes"))
    ):
        by_month.setdefault(row["employee_id"], []).append(
            (row["period__month"], row["total"] or 0)
        )
    current = {
        row["employee_id"]: row["total"] or 0
        for row in Timesheet.objects.filter(period=period)
        .values("employee_id")
        .annotate(total=Sum("leave_minutes"))
    }

    result = {}
    for employee_id in set(by_month) | set(current) | set(entitlements):
        item = entitlements.get(employee_id)
        months = by_month.get(employee_id, [])
        used_ytd, opening = _ytd(
            period, item,
            lambda after: sum(total for month, total in months if month > after),
        )
        result[employee_id] = LeaveBalance(
            day_minutes=day_minutes,
            carried_over=item.carried_over_minutes if item else 0,
            annual=item.annual_minutes if item else 0,
            used_period=int(current.get(employee_id, 0)),
            used_ytd=int(used_ytd),
            opening_used=int(opening),
        )
    return result


def compute_balance(employee, period, day_minutes=DEFAULT_DAY_MINUTES) -> LeaveBalance:
    """مانده مرخصی تا پایان دوره داده‌شده.

    «مصرفی از اول سال» یعنی جمع مرخصی همه دوره‌های همان سال مالی تا همین ماه —
    به همین دلیل وقتی کارکرد مرداد به‌روز می‌شود، مانده هم خودکار به‌روز می‌شود
    و جایی برای نگهداری دستی مانده وجود ندارد.

    تنها استثنا ماه‌های پیش از راه‌اندازی سامانه است که کارکردی در سامانه
    ندارند؛ آن‌ها با «مانده‌گیری افتتاحیه» روی سهمیهٔ مرخصی بیان می‌شوند.
    """
    from django.db.models import Sum

    from apps.attendance.models import LeaveEntitlement, Timesheet

    entitlement = LeaveEntitlement.objects.filter(
        employee=employee, fiscal_year=period.fiscal_year
    ).first()

    def timesheet_total_for(after_month):
        return (
            Timesheet.objects.filter(
                employee=employee,
                period__fiscal_year=period.fiscal_year,
                period__year=period.year,
                period__month__lte=period.month,
                period__month__gt=after_month,
            ).aggregate(total=Sum("leave_minutes"))["total"]
            or 0
        )

    used_ytd, opening = _ytd(period, entitlement, timesheet_total_for)
    used_period = (
        Timesheet.objects.filter(employee=employee, period=period)
        .aggregate(total=Sum("leave_minutes"))["total"]
        or 0
    )

    return LeaveBalance(
        day_minutes=day_minutes,
        carried_over=entitlement.carried_over_minutes if entitlement else 0,
        annual=entitlement.annual_minutes if entitlement else 0,
        used_period=int(used_period),
        used_ytd=int(used_ytd),
        opening_used=int(opening),
    )
