"""ابزارهای مشترک: ارقام فارسی، مبالغ ریالی و تاریخ جلالی."""

from decimal import Decimal, ROUND_HALF_UP

import jdatetime

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

JALALI_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]


def fa_digits(value) -> str:
    """تبدیل ارقام لاتین به فارسی."""
    return str(value).translate(PERSIAN_DIGITS)


def _localize(text: str) -> str:
    """ارقام فارسی + جداکننده‌های استاندارد فارسی (٬ برای هزارگان، ٫ برای اعشار)."""
    return fa_digits(text).replace(",", "٬").replace(".", "٫")


def fa_money(value, persian=True) -> str:
    """مبلغ ریالی با جداکننده هزارگان."""
    if value is None:
        return "—"
    amount = Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    text = f"{amount:,}"
    return _localize(text) if persian else text


def fa_number(value, decimals=0, persian=True) -> str:
    """عدد معمولی؛ اعشار صفر حذف می‌شود تا «۳۰» به‌جای «۳۰٫۰۰» نمایش داده شود."""
    if value is None:
        return "—"
    number = Decimal(value)
    if decimals == 0 or number == number.to_integral_value():
        text = f"{number.to_integral_value():,}"
    else:
        text = f"{number:,.{decimals}f}".rstrip("0").rstrip(".")
    return _localize(text) if persian else text


def rial_to_milliard(value) -> str:
    """نمایش خلاصه برای کارت‌های داشبورد: میلیارد ریال با یک رقم اعشار."""
    if not value:
        return fa_digits("0")
    number = Decimal(value) / Decimal("1000000000")
    return _localize(f"{number:,.1f}")


def to_jalali(value):
    """تبدیل date/datetime میلادی به jdatetime.date."""
    if value is None:
        return None
    if hasattr(value, "date") and not isinstance(value, jdatetime.date):
        value = value.date()
    return jdatetime.date.fromgregorian(date=value)


def jalali_str(value, with_month_name=False) -> str:
    """رشته تاریخ جلالی. ذخیره در دیتابیس میلادی است؛ فقط نمایش جلالی می‌شود."""
    jdate = to_jalali(value)
    if jdate is None:
        return "—"
    if with_month_name:
        return fa_digits(f"{jdate.day} {JALALI_MONTHS[jdate.month - 1]} {jdate.year}")
    return fa_digits(f"{jdate.year}/{jdate.month:02d}/{jdate.day:02d}")


def jalali_to_gregorian(year: int, month: int, day: int):
    return jdatetime.date(year, month, day).togregorian()


def jalali_month_range(year: int, month: int):
    """اولین و آخرین روز یک ماه جلالی، به میلادی."""
    start = jdatetime.date(year, month, 1)
    if month < 12:
        next_start = jdatetime.date(year, month + 1, 1)
    else:
        next_start = jdatetime.date(year + 1, 1, 1)
    end = next_start - jdatetime.timedelta(days=1)
    return start.togregorian(), end.togregorian()


def quantize_rial(value) -> Decimal:
    """هر مبلغ ریالی عدد صحیح است — ریال جزء اعشاری ندارد."""
    return Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


ARABIC_INDIC = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def parse_decimal(value, default=Decimal("0")) -> Decimal:
    """خواندن عددی که کاربر ممکن است با ارقام فارسی یا جداکننده هزارگان بنویسد."""
    if value is None:
        return default
    text = str(value).translate(ARABIC_INDIC).replace(",", "").replace("٬", "").strip()
    if not text:
        return default
    try:
        return Decimal(text)
    except Exception:
        return default


def floor_to_unit(value, unit: int) -> Decimal:
    """گرد کردن رو به پایین به واحد مشخص (مثلاً نزدیک‌ترین ۱۰۰۰ ریال)."""
    if not unit or unit <= 1:
        return quantize_rial(value)
    unit_dec = Decimal(unit)
    return (Decimal(value) // unit_dec) * unit_dec
