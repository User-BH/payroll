"""زنجیرهٔ مازاد — تبدیل یک استخر ریالی به روز مأموریت و ساعت اضافه‌کاری.

گروه پشتیبانی در فایل ۱۴۰۵ شرکت، ساعت اضافه‌کاری و روز مأموریتِ فیش را
**وارد نمی‌کند**؛ آن‌ها خروجی یک تبدیل‌اند. آنچه وارد می‌شود اضافه‌کاری
*واقعی* و چند مبلغ مازاد است، و سامانه باید همان تبدیل را انجام بدهد.

منطقش این است که مبلغِ توافق‌شدهٔ ماه ثابت است و باید در قالب اقلام قانونی
بیان شود: اول بزرگ‌ترین واحد (روز مأموریت)، بعد ساعت، بعد دقیقه. مابه‌التفاوت
پایه سنوات تجمیعی هم — که سطر خودش را روی فیش دارد — از همین استخر کم می‌شود،
وگرنه دو بار پرداخت می‌شد.

    استخر       = مبلغ اضافه‌کاری واقعی + مازادها
    قابل پرداخت = استخر − کسرها
    روز مأموریت = ROUNDDOWN(قابل پرداخت ÷ مبنای روزانهٔ مأموریت)
    ساعت        = ROUNDDOWN(ماندهٔ یک ÷ نرخ ساعت)
    دقیقه       = ROUNDUP(ماندهٔ دو ÷ نرخ دقیقه)

**گرد کردن‌ها عمداً نامتقارن‌اند و همان چیزی‌اند که در فایل شرکت است.** دو گام
اول رو به پایین‌اند تا از استخر بیشتر نشود، و گام آخر رو به بالا. نتیجه این
است که پرداخت همیشه کمی **بیشتر** از استخر درمی‌آید؛ این باقی‌مانده در
`residue` نگه داشته می‌شود تا پیدا باشد، نه اینکه بی‌سروصدا گم شود.

نکتهٔ ظریفی که بدون آن اعداد چند هزار ریال جابه‌جا می‌شوند: **تقسیم‌ها با نرخِ
گردشده انجام می‌شوند ولی ضرب‌های برگشتی با نرخِ گرد‌نشده.** فایل شرکت همین
کار را می‌کند و روی ۱۰۸ نفر-ماه ریال‌به‌ریال بازتولید شد.
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal

ZERO = Decimal("0")
ONE = Decimal("1")


def _round(value):
    return Decimal(value).quantize(ONE, rounding=ROUND_HALF_UP)


def _down(value):
    return Decimal(value).quantize(ONE, rounding=ROUND_DOWN)


def _up(value):
    return Decimal(value).quantize(ONE, rounding=ROUND_UP)


class SurplusPlan:
    """نتیجهٔ یک زنجیره — بدون دست زدن به دیتابیس، تا تست‌پذیر بماند.

    `hourly_base` مبنای هر ساعت **پیش از ضریب** است و `factor` ضریب
    اضافه‌کاری؛ همان دو عددی که قاعدهٔ اضافه‌کاری عادی هم با آن‌ها کار می‌کند.
    اگر اینجا عدد دیگری بگذاریم، دو جای سامانه دو نرخ متفاوت خواهند داشت.
    """

    def __init__(self, real_minutes, additions, deductions,
                 hourly_base, factor, mission_daily_base):
        self.real_minutes = Decimal(real_minutes or ZERO)
        self.additions = Decimal(additions or ZERO)
        self.deductions = Decimal(deductions or ZERO)
        self.hourly_base = Decimal(hourly_base or ZERO)
        self.factor = Decimal(factor or ONE)
        self.mission_daily_base = Decimal(mission_daily_base or ZERO)

    # ------------------------------------------------------------- نرخ‌ها

    @property
    def hour_rate(self) -> Decimal:
        """نرخ یک ساعت اضافه‌کاری، گردشده — فقط برای **تقسیم**."""
        return _round(self.hourly_base * self.factor)

    @property
    def minute_rate(self) -> Decimal:
        """نرخ یک دقیقه، گردشده — فقط برای **تقسیم**."""
        return _round(self.hourly_base / Decimal("60") * self.factor)

    def money_for(self, hours=ZERO, minutes=ZERO) -> Decimal:
        """مبلغ ساعت و دقیقه با نرخِ گرد‌نشده — همان فرمول قلم اضافه‌کاری."""
        exact = self.hourly_base * self.factor
        return _round(exact * Decimal(hours) + exact / Decimal("60") * Decimal(minutes))

    # ------------------------------------------------------------- استخر

    @property
    def real_amount(self) -> Decimal:
        """مبلغ اضافه‌کاری واقعیِ ثبت‌شده در جدول کارکرد."""
        return self.money_for(minutes=self.real_minutes)

    @property
    def pool(self) -> Decimal:
        return self.real_amount + self.additions

    @property
    def payable(self) -> Decimal:
        return self.pool - self.deductions

    # ------------------------------------------------------------ زنجیره

    @property
    def mission_days(self) -> Decimal:
        """روز کامل مأموریت.

        **منفی می‌شود و عمداً صفر نمی‌شود.** استخرِ منفی یعنی کسرها از خودِ
        مازاد بیشتر بوده‌اند؛ چون آن کسرها سطر پرداختیِ خودشان را روی فیش
        دارند، پس‌گرفتنشان از همین‌جا انجام می‌شود. صفر کردنش یعنی همان مبلغ
        دو بار پرداخت شود. فایل شرکت هم منفی می‌دهد.

        `ROUND_DOWN` در پایتون مثل `ROUNDDOWN` اکسل به سمت صفر می‌برد، پس
        ۶٫۳۹− می‌شود ۶− نه ۷−.
        """
        if not self.mission_daily_base:
            return ZERO
        return _down(self.payable / self.mission_daily_base)

    @property
    def after_mission(self) -> Decimal:
        return self.payable - self.mission_days * self.mission_daily_base

    @property
    def overtime_hours(self) -> Decimal:
        """ساعت کامل. مثل روز مأموریت می‌تواند منفی باشد."""
        if not self.hour_rate:
            return ZERO
        return _down(self.after_mission / self.hour_rate)

    @property
    def after_hours(self) -> Decimal:
        return self.after_mission - self.money_for(hours=self.overtime_hours)

    @property
    def overtime_extra_minutes(self) -> Decimal:
        """دقیقه‌های خردهٔ آخر.

        ماندهٔ کمتر از نرخِ یک دقیقه صفر می‌شود، نه یک دقیقه — وگرنه هرکس با
        چند ریال مانده یک دقیقه اضافه‌کاری می‌گرفت. همین شرط، ماندهٔ **منفی**
        را هم صفر می‌کند: زنجیره در گام دقیقه دیگر عقب‌تر نمی‌رود.
        """
        rest, rate = self.after_hours, self.minute_rate
        if rest < rate or not rate:
            return ZERO
        return _up(rest / rate)

    @property
    def overtime_minutes(self) -> Decimal:
        """کل دقیقهٔ اضافه‌کاریِ قابل پرداخت — ساعت‌ها هم به دقیقه."""
        return self.overtime_hours * Decimal("60") + self.overtime_extra_minutes

    @property
    def residue(self) -> Decimal:
        """قابل پرداخت منهای آنچه واقعاً پرداخت می‌شود.

        معمولاً منفی است، یعنی چند هزار ریال بیشتر پرداخت شده — نتیجهٔ رو به
        بالا بودنِ گام دقیقه. عمداً جبران نمی‌شود چون در فایل شرکت هم جبران
        نمی‌شود؛ فقط اینجا **دیده** می‌شود.
        """
        paid = self.mission_days * self.mission_daily_base + self.money_for(
            hours=self.overtime_hours, minutes=self.overtime_extra_minutes
        )
        return self.payable - paid

    @property
    def is_empty(self) -> bool:
        return not (self.real_minutes or self.additions or self.deductions)
