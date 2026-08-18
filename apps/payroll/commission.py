"""تخصیص پورسانت به حق مأموریت و اضافه‌کاری.

سند به‌روزرسانی سه قاعده دارد و هر سه اینجا پیاده شده‌اند:

۱. **سقف‌ها در کد ثابت نیستند.** مبنای روزانهٔ مأموریت، سقف روز مأموریت،
   مبنای ساعتی اضافه‌کاری و سقف ساعت اضافه‌کاری همگی «آیتم محاسباتی ماهانه»
   هستند و هر ماه جداگانه تنظیم می‌شوند.

۲. **مبلغ گم نمی‌شود.** آنچه در ظرفیت مأموریت و اضافه‌کاری جا نشود، به‌عنوان
   ماندهٔ پورسانت باقی می‌ماند. همیشه:

       پورسانت اولیه = مأموریت + اضافه‌کاری + مانده

۳. **ظرفیت یعنی ظرفیت باقی‌مانده.** مأموریت و اضافه‌کاریِ واقعیِ همان ماه
   (از جدول کارکرد) اول جای خودشان را می‌گیرند و پورسانت فقط فضای خالی را پر
   می‌کند — وگرنه سقف قانونی رد می‌شود.
"""

from decimal import Decimal

from apps.payroll.utils import quantize_rial

ZERO = Decimal("0")


def _q2(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


class AllocationPlan:
    """نتیجهٔ یک تخصیص — بدون دست زدن به دیتابیس، تا تست‌پذیر بماند."""

    def __init__(self, source, mission_rate, mission_max_days, overtime_rate,
                 overtime_max_hours, used_mission_days=ZERO, used_overtime_hours=ZERO):
        self.source = quantize_rial(source or ZERO)
        self.mission_rate = Decimal(mission_rate or ZERO)
        self.mission_max_days = Decimal(mission_max_days or ZERO)
        self.overtime_rate = Decimal(overtime_rate or ZERO)
        self.overtime_max_hours = Decimal(overtime_max_hours or ZERO)
        self.used_mission_days = Decimal(used_mission_days or ZERO)
        self.used_overtime_hours = Decimal(used_overtime_hours or ZERO)

        self.to_mission = ZERO
        self.to_overtime = ZERO

    # ------------------------------------------------------------ ظرفیت‌ها

    @property
    def mission_free_days(self) -> Decimal:
        """روز مأموریت باقی‌مانده تا سقف — مأموریت واقعی جای خودش را گرفته است."""
        return max(self.mission_max_days - self.used_mission_days, ZERO)

    @property
    def mission_capacity(self) -> Decimal:
        """حداکثر مبلغ قابل تخصیص به حق مأموریت = مبنای ماه × روز آزاد."""
        return quantize_rial(self.mission_rate * self.mission_free_days)

    @property
    def overtime_free_hours(self) -> Decimal:
        return max(self.overtime_max_hours - self.used_overtime_hours, ZERO)

    @property
    def overtime_capacity(self) -> Decimal:
        """صفر بودن سقف ساعت یعنی سقفی تعریف نشده و انتقال انجام نمی‌شود.

        سند صریح است: «این جابه‌جایی نباید نامحدود باشد». نبودِ سقف را
        «بی‌نهایت» تفسیر نمی‌کنیم.
        """
        return quantize_rial(self.overtime_rate * self.overtime_free_hours)

    # ------------------------------------------------------------ تخصیص

    def auto(self):
        """تقسیم خودکار: اول مأموریت تا سقف، بعد اضافه‌کاری تا سقف، بقیه مانده."""
        rest = self.source
        self.to_mission = min(rest, self.mission_capacity)
        rest -= self.to_mission
        self.to_overtime = min(rest, self.overtime_capacity)
        return self

    def manual(self, to_mission=None, to_overtime=None):
        """تقسیم دستی — هر دو عدد به ظرفیت و به مبلغ پورسانت مقید می‌شوند.

        ترتیب مهم است: اول مأموریت مقید می‌شود، بعد اضافه‌کاری از باقی‌ماندهٔ
        واقعی. این‌طوری کاربر نمی‌تواند با دو عدد بزرگ، جمع را از پورسانت
        بیشتر کند.
        """
        mission = self.to_mission if to_mission is None else quantize_rial(to_mission)
        mission = max(min(mission, self.mission_capacity, self.source), ZERO)
        self.to_mission = mission

        rest = self.source - mission
        overtime = self.to_overtime if to_overtime is None else quantize_rial(to_overtime)
        overtime = max(min(overtime, self.overtime_capacity, rest), ZERO)
        self.to_overtime = overtime
        return self

    # ------------------------------------------------------------ خروجی

    @property
    def remaining(self) -> Decimal:
        """آنچه در هیچ ظرفیتی جا نشد — حذف نمی‌شود."""
        return self.source - self.to_mission - self.to_overtime

    @property
    def mission_days(self) -> Decimal:
        if not self.mission_rate:
            return ZERO
        return _q2(self.to_mission / self.mission_rate)

    @property
    def overtime_hours(self) -> Decimal:
        if not self.overtime_rate:
            return ZERO
        return _q2(self.to_overtime / self.overtime_rate)

    def as_fields(self) -> dict:
        return {
            "source_amount": self.source,
            "to_mission": self.to_mission,
            "mission_days": self.mission_days,
            "to_overtime": self.to_overtime,
            "overtime_hours": self.overtime_hours,
            "remaining": self.remaining,
            "mission_daily_rate": quantize_rial(self.mission_rate),
            "mission_max_days": self.mission_max_days,
            "overtime_hourly_rate": quantize_rial(self.overtime_rate),
            "overtime_max_hours": self.overtime_max_hours,
        }


def commission_components(company):
    """اقلامی که مبلغشان وارد استخر تخصیص می‌شود."""
    from apps.payroll_config.models import SalaryComponent

    return SalaryComponent.objects.filter(
        company=company, is_active=True, is_commission=True
    )


def commission_totals(period):
    """جمع پورسانت هر پرسنل در یک دوره — {employee_id: مبلغ}."""
    from django.db.models import Sum

    from apps.payroll.models import PayrollInput

    rows = (
        PayrollInput.objects.filter(
            period=period, component__in=commission_components(period.company)
        )
        .values("employee_id")
        .annotate(total=Sum("amount"))
    )
    return {row["employee_id"]: row["total"] or ZERO for row in rows}


def build_plan(period, employee, params, source, timesheet=None):
    """ساخت نقشهٔ تخصیص با مبناها و سقف‌های همان ماه."""
    used_mission_days = getattr(timesheet, "mission_days", ZERO) or ZERO
    used_overtime_hours = getattr(timesheet, "overtime_hours", ZERO) or ZERO
    return AllocationPlan(
        source=source,
        mission_rate=params.mission_daily_rate,
        mission_max_days=params.mission_max_days,
        overtime_rate=_overtime_rate(params),
        overtime_max_hours=params.overtime_max_hours,
        used_mission_days=used_mission_days,
        used_overtime_hours=used_overtime_hours,
    )


def _overtime_rate(params) -> Decimal:
    """مبنای ساعتی اضافه‌کاری همان ماه. صفر یعنی تعریف نشده."""
    return Decimal(params.overtime_hourly_rate or ZERO)
