"""ابزارهای مشترک: ارقام فارسی، مبالغ ریالی و تاریخ جلالی."""

from datetime import date, datetime
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


def _to_decimal(value):
    """تبدیل امن به Decimal.

    در قالب‌ها ممکن است مقدار «رشتهٔ خالی» برسد — مثلاً وقتی پرسنل هنوز قرارداد
    فعالی ندارد و جنگو `current_contract.base_salary` را به "" تبدیل می‌کند.
    بدون این محافظ، `Decimal("")` استثنا می‌دهد و کل صفحه با خطای ۵۰۰ می‌خوابد.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = text.translate(ARABIC_INDIC).replace("٬", "").replace(",", "")
    try:
        return Decimal(text)
    except Exception:
        return None


def fa_money(value, persian=True) -> str:
    """مبلغ ریالی با جداکننده هزارگان."""
    amount = _to_decimal(value)
    if amount is None:
        return "—"
    amount = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    text = f"{amount:,}"
    return _localize(text) if persian else text


def fa_number(value, decimals=0, persian=True) -> str:
    """عدد معمولی؛ اعشار صفر حذف می‌شود تا «۳۰» به‌جای «۳۰٫۰۰» نمایش داده شود."""
    number = _to_decimal(value)
    if number is None:
        return "—"
    if decimals == 0 or number == number.to_integral_value():
        text = f"{number.to_integral_value():,}"
    else:
        text = f"{number:,.{decimals}f}".rstrip("0").rstrip(".")
    return _localize(text) if persian else text


def rial_to_milliard(value) -> str:
    """نمایش خلاصه برای کارت‌های داشبورد: میلیارد ریال با یک رقم اعشار."""
    number = _to_decimal(value)
    if not number:
        return fa_digits("0")
    number = number / Decimal("1000000000")
    return _localize(f"{number:,.1f}")


def to_jalali(value):
    """تبدیل date/datetime میلادی به jdatetime.date.

    در قالب ممکن است مقدار خالی یا رشته برسد (مثلاً وقتی رابطه‌ای None است و
    جنگو آن را به رشته خالی تبدیل می‌کند). در آن حالت None برمی‌گردد تا فیلتر
    تاریخ کل صفحه را با خطا نخواباند.
    """
    if value is None or value == "":
        return None
    if isinstance(value, jdatetime.date):
        return value
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        return None
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


def parse_jalali_input(text):
    """«۱۴۰۵/۰۵/۲۰» یا «1405-05-20» یا تاریخ میلادی → date میلادی."""
    if not text:
        return None
    if isinstance(text, date):
        return text
    cleaned = str(text).translate(ARABIC_INDIC).replace("-", "/").strip()
    parts = [p for p in cleaned.split("/") if p]
    if len(parts) != 3:
        return None
    try:
        year, month, day = (int(p) for p in parts)
    except ValueError:
        return None
    try:
        if year < 1500:
            return jdatetime.date(year, month, day).togregorian()
        return date(year, month, day)
    except ValueError:
        return None


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
