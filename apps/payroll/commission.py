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


def build_plan(period, employee, params, source, timesheet=None, contract=None):
    """ساخت نقشهٔ تخصیص با مبناها و سقف‌های همان ماه.

    مبنای روزانهٔ مأموریت از **همان تابعی** می‌آید که موتور استفاده می‌کند، نه
    از نرخ ثابت ماهانه. تا امروز اینجا `params.mission_daily_rate` خوانده
    می‌شد و چون این شرکت حالت «مزد خودِ پرسنل» را دارد آن عدد صفر بود — یعنی
    ظرفیت مأموریت صفر می‌شد و **هیچ پورسانتی هرگز تبدیل نمی‌شد**، بی‌آنکه
    خطایی دیده شود یا صفحه چیزی بگوید.
    """
    from apps.payroll.engine.context import mission_daily_base

    used_mission_days = getattr(timesheet, "mission_days", ZERO) or ZERO
    used_overtime_hours = getattr(timesheet, "overtime_hours", ZERO) or ZERO
    contract = contract or _contract_of(employee, period)
    daily_wage = _daily_wage(contract, params)

    # ضریبِ قلم مأموریتی که به همین پرسنل می‌خورَد — در گروه فروش ۲.
    #
    # بدون آن، ظرفیت نصف حساب می‌شد و «۲۵ روز» روی فیش کنار مبلغی می‌نشست که
    # نصفِ ۲۵ روزِ واقعی است. سند EXCEL-1405 صریح است: نرخ مأموریت فروش
    # «روز × (مزد + سنوات) × ۲» است، پس هر روزِ مصرف‌شده از سقف دو برابر
    # ارزش دارد.
    rate = mission_daily_base(params, daily_wage, params.seniority_daily)
    rate *= _mission_factor(period, contract)

    return AllocationPlan(
        source=source,
        mission_rate=rate,
        mission_max_days=params.mission_max_days,
        overtime_rate=_overtime_rate(params, daily_wage),
        overtime_max_hours=params.overtime_max_hours,
        used_mission_days=used_mission_days,
        used_overtime_hours=used_overtime_hours,
    )


def _contract_of(employee, period):
    """قرارداد فعالِ همان دوره — همان شرطی که موتور می‌گذارد."""
    from django.db.models import Q

    from apps.employees.models import EmploymentContract

    return (
        EmploymentContract.objects.filter(
            employee=employee,
            status=EmploymentContract.Status.ACTIVE,
            effective_from__lte=period.end_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=period.start_date))
        .order_by("-effective_from")
        .first()
    )


MISSION_CODES = ("MISSION2", "MISSION", "MISSION_SURPLUS")


def _mission_factor(period, contract) -> Decimal:
    """ضریبِ قلمِ مأموریتی که به این قرارداد تعلق می‌گیرد.

    از **دامنه شمول** پیدا می‌شود نه از کدِ سخت‌شده، چون همان ساز و کاری است
    که موتور با آن تصمیم می‌گیرد کدام قلم مأموریت به چه کسی برسد. اگر هیچ‌کدام
    نخورد یا ضریبی ثبت نشده باشد، ۱ برمی‌گردد و رفتار عوض نمی‌شود.
    """
    from apps.payroll_config.models import SalaryComponent

    if contract is None:
        return Decimal("1")
    for component in (
        SalaryComponent.objects.filter(
            company=period.company, code__in=MISSION_CODES, is_active=True
        )
        .prefetch_related("scopes")
        .order_by("sequence")
    ):
        if component.applies_to(contract) and component.rate:
            return Decimal(component.rate)
    return Decimal("1")


def _daily_wage(contract, params) -> Decimal:
    """مزد روزانه؛ قراردادِ بی‌عدد از حداقل دستمزد سال پر می‌شود — مثل موتور."""
    wage = Decimal(getattr(contract, "daily_wage", 0) or 0)
    return wage if wage else Decimal(params.min_daily_wage or ZERO)


def _overtime_rate(params, daily_wage=None) -> Decimal:
    """مبنای ساعتی اضافه‌کاری همان ماه.

    اگر نرخ مشترکِ ماه ثبت نشده باشد، از مزد خودِ پرسنل ساخته می‌شود — همان
    کاری که موتور برای اضافه‌کاری می‌کند. صفر بودنِ نرخِ مشترک نباید یعنی
    «انتقال به اضافه‌کاری ممکن نیست».
    """
    rate = Decimal(params.overtime_hourly_rate or ZERO)
    if rate or daily_wage is None:
        return rate
    hours = Decimal(params.daily_work_hours or Decimal("7.33"))
    return (Decimal(daily_wage) / hours) if hours else ZERO
