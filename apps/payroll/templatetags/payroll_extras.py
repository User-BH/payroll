from django import template

from apps.payroll import utils

register = template.Library()


@register.filter(name="rial")
def rial(value):
    """مبلغ ریالی با جداکننده هزارگان و ارقام فارسی."""
    return utils.fa_money(value)


@register.filter(name="fanum")
def fanum(value):
    return utils.fa_number(value)


@register.filter(name="fadec")
def fadec(value):
    """عدد با حداکثر دو رقم اعشار — برای ساعت و روز کارکرد."""
    return utils.fa_number(value, decimals=2)


@register.filter(name="fadigits")
def fadigits(value):
    return utils.fa_digits(value)


@register.filter(name="milliard")
def milliard(value):
    """میلیارد ریال با یک رقم اعشار — برای کارت‌های داشبورد."""
    return utils.rial_to_milliard(value)


@register.filter(name="jalali")
def jalali(value):
    return utils.jalali_str(value)


@register.filter(name="jalali_long")
def jalali_long(value):
    return utils.jalali_str(value, with_month_name=True)


PARAM_LABELS = {
    "min_daily_wage": "حداقل دستمزد روزانه",
    "housing_allowance": "حق مسکن",
    "food_allowance": "بن کارگری",
    "child_allowance": "حق اولاد",
    "seniority_daily": "پایه سنوات روزانه",
    "ins_employee_rate": "نرخ بیمه سهم کارگر",
    "ins_employer_rate": "نرخ بیمه سهم کارفرما",
    "unemployment_rate": "نرخ بیمه بیکاری",
    "insurance_ceiling": "سقف مبنای بیمه",
    "overtime_factor": "ضریب اضافه‌کاری",
    "night_factor": "ضریب شب‌کاری",
    "friday_factor": "ضریب جمعه‌کاری",
    "daily_work_hours": "ساعات کار روزانه",
    "rounding_unit": "واحد گرد کردن",
    "ins_ceiling_factor": "ضریب سقف بیمه",
    "holiday_factor": "ضریب تعطیل‌کاری",
    "monthly_days": "روز کارکرد ماه",
    "max_children": "حداکثر فرزند مشمول",
}


@register.filter(name="dictget")
def dictget(mapping, key):
    """خواندن یک کلید از دیکشنری در قالب — برای مانده‌های از پیش محاسبه‌شده."""
    if not mapping:
        return None
    return mapping.get(key)


@register.filter(name="dhm")
def dhm(minutes):
    """دقیقه → «۲۴ روز و ۷ ساعت و ۱۰ دقیقه»."""
    from apps.attendance.leave import format_dhm

    return format_dhm(minutes)


@register.filter(name="param_label")
def param_label(key):
    return PARAM_LABELS.get(key, key)


@register.filter(name="snapshot_value")
def snapshot_value(value):
    """مقادیر snapshot: مبالغ با جداکننده، نرخ‌ها با اعشار کوتاه."""
    from decimal import Decimal, InvalidOperation

    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return utils.fa_digits(value)
    if abs(number) >= 1000:
        return utils.fa_money(number)
    return utils.fa_number(number, decimals=4)


@register.filter(name="percent")
def percent(value, decimals=2):
    """نرخ اعشاری (۰٫۰۷) را به درصد (۷٪) تبدیل می‌کند."""
    if value is None:
        return "—"
    from decimal import Decimal

    return utils.fa_number(Decimal(value) * 100, decimals=int(decimals))
