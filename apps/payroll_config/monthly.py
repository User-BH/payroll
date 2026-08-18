"""پارامترهایی که می‌توانند ماهانه مقدار متفاوتی داشته باشند.

سند به‌روزرسانی دو خانواده را از هم جدا می‌کند:

* **سالانه و ثابت** — حداقل دستمزد، پایه سنوات، حق مسکن، بن، حق اولاد. جایشان
  «تنظیمات سال مالی» است و برای همهٔ ماه‌های سال یکی است.
* **ماهانه و متغیر** — مبنای حق مأموریت، مبنای اضافه‌کاری و هر مقداری که ممکن
  است هر ماه فرق کند.

پیاده‌سازی عمداً «سالانه را جابه‌جا نمی‌کند»: همان مقدار سالانه سر جایش می‌ماند و
دورهٔ خاص می‌تواند رویش یک **مقدار ماهانه** بگذارد. ترتیب خواندن در موتور:
مقدار ماهانهٔ همان دوره، وگرنه مقدار سالانه.

با این کار هیچ قاعده‌ای در `rules.py` تغییر نمی‌کند — قاعده‌ها همچنان
`ctx.params.housing_allowance` می‌خوانند و لایهٔ `EffectiveParams` تصمیم می‌گیرد
عدد از کجا بیاید.
"""

from decimal import Decimal

# واحدها فقط برای نمایش و اعتبارسنجی فرم‌اند
RIAL = "RIAL"
RATE = "RATE"
DAYS = "DAYS"
HOURS = "HOURS"

UNIT_LABELS = {
    RIAL: "ریال",
    RATE: "ضریب",
    DAYS: "روز",
    HOURS: "ساعت",
}


class Group:
    WAGE = "دستمزد و مزایا"
    WORK = "ضرایب کارکرد"
    INSURANCE = "بیمه و مالیات"
    TIME = "مبناهای زمانی"


# (کلید، عنوان، واحد، گروه، توضیح)
#
# کلید دقیقاً نام همان فیلد روی LegalParameter است — به‌جز کلیدهایی که فقط
# ماهانه معنا دارند و مقدار سالانه‌شان صفر است.
MONTHLY_PARAMS = [
    ("mission_daily_rate", "مبنای روزانه حق مأموریت", RIAL, Group.WAGE,
     "مبلغ هر روز مأموریت در همین ماه — معمولاً هر ماه فرق می‌کند"),
    ("overtime_hourly_rate", "مبنای ساعتی اضافه‌کاری", RIAL, Group.WAGE,
     "خالی یا صفر یعنی از مزد ساعتی خود پرسنل حساب شود"),
    ("mission_max_days", "سقف روز مأموریت", DAYS, Group.WAGE,
     "حداکثر روز مأموریت قابل ثبت در ماه"),

    ("min_daily_wage", "حداقل دستمزد روزانه", RIAL, Group.WAGE, ""),
    ("seniority_daily", "پایه سنوات روزانه", RIAL, Group.WAGE, ""),
    ("housing_allowance", "حق مسکن ماهانه", RIAL, Group.WAGE, ""),
    ("food_allowance", "بن کارگری ماهانه", RIAL, Group.WAGE, ""),
    ("child_allowance", "حق اولاد (هر فرزند)", RIAL, Group.WAGE, ""),

    ("overtime_factor", "ضریب اضافه‌کاری", RATE, Group.WORK, ""),
    ("holiday_factor", "ضریب تعطیل‌کاری", RATE, Group.WORK, ""),

    ("ins_employee_rate", "نرخ بیمه سهم کارگر", RATE, Group.INSURANCE, ""),
    ("ins_employer_rate", "نرخ بیمه سهم کارفرما", RATE, Group.INSURANCE, ""),
    ("unemployment_rate", "نرخ بیمه بیکاری", RATE, Group.INSURANCE, ""),
    ("ins_ceiling_factor", "ضریب سقف بیمه", RATE, Group.INSURANCE, ""),

    ("daily_work_hours", "ساعات کار روزانه", HOURS, Group.TIME, ""),
    ("leave_day_minutes", "طول یک روز مرخصی (دقیقه)", HOURS, Group.TIME, ""),
]

# کلیدهایی که روی LegalParameter فیلد ندارند و فقط ماهانه‌اند
MONTHLY_ONLY_DEFAULTS = {
    "mission_daily_rate": Decimal("0"),
    "overtime_hourly_rate": Decimal("0"),
    "mission_max_days": Decimal("25"),
}

PARAM_KEYS = [key for key, *_ in MONTHLY_PARAMS]
PARAM_LABELS = {key: label for key, label, *_ in MONTHLY_PARAMS}
PARAM_UNITS = {key: unit for key, _, unit, *_ in MONTHLY_PARAMS}


def grouped_params():
    """پارامترها به تفکیک گروه، برای نمایش در صفحهٔ آیتم‌های ماهانه."""
    groups = {}
    for key, label, unit, group, note in MONTHLY_PARAMS:
        groups.setdefault(group, []).append(
            {"key": key, "label": label, "unit": unit,
             "unit_label": UNIT_LABELS[unit], "note": note}
        )
    return groups


def annual_value(legal_parameter, key):
    """مقدار سالانهٔ یک کلید — یا از LegalParameter، یا پیش‌فرض ماهانه‌ها."""
    if key in MONTHLY_ONLY_DEFAULTS:
        return MONTHLY_ONLY_DEFAULTS[key]
    return getattr(legal_parameter, key, None)


class EffectiveParams:
    """پارامتر سالانه + مقادیر ماهانهٔ همان دوره.

    قاعده‌های موتور همان `params.<field>` را می‌خوانند و نمی‌دانند عدد از سال
    آمده یا از ماه — و همین باعث می‌شود این تغییر هیچ قاعده‌ای را دست نزند.
    """

    def __init__(self, legal_parameter, overrides=None):
        self.base = legal_parameter
        self.overrides = {k: v for k, v in (overrides or {}).items() if v is not None}

    def __getattr__(self, name):
        # فقط وقتی صدا زده می‌شود که روی خودِ نمونه پیدا نشود
        if name in self.overrides:
            return self.overrides[name]
        if name in MONTHLY_ONLY_DEFAULTS:
            return MONTHLY_ONLY_DEFAULTS[name]
        return getattr(self.base, name)

    def is_monthly(self, key) -> bool:
        return key in self.overrides

    # این دو از روی مقادیر مؤثر ساخته می‌شوند، نه از روی مقادیر سالانه —
    # وگرنه تغییر ماهانهٔ حداقل دستمزد در سقف بیمه اثر نمی‌کرد.
    @property
    def min_monthly_wage(self) -> Decimal:
        return self.min_daily_wage * self.base.monthly_days

    @property
    def insurance_ceiling(self) -> Decimal:
        return self.min_monthly_wage * self.ins_ceiling_factor

    def as_snapshot(self) -> dict:
        """تصویر پارامترها برای فیش، به‌همراه اینکه کدام مقدار ماهانه بوده."""
        data = self.base.as_snapshot()
        for key in PARAM_KEYS:
            value = getattr(self, key, None)
            if value is not None:
                data[key] = str(value)
        data["insurance_ceiling"] = str(self.insurance_ceiling)
        if self.overrides:
            data["monthly_overrides"] = {k: str(v) for k, v in self.overrides.items()}
        return data
