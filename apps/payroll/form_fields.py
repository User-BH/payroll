"""فیلد تاریخ جلالی برای فرم‌ها.

در دیتابیس تاریخ‌ها میلادی ذخیره می‌شوند (تا مرتب‌سازی و مقایسه درست کار کند)
ولی کاربر هرگز تاریخ میلادی نمی‌بیند و وارد نمی‌کند. تبدیل فقط در همین لایه
اتفاق می‌افتد.
"""

from django import forms

from apps.payroll.utils import jalali_str, parse_jalali_input


class JalaliDateInput(forms.TextInput):
    """ورودی متنی با تقویم جلالی (static/js/jdate.js آن را فعال می‌کند)."""

    def __init__(self, attrs=None):
        defaults = {
            "class": "input jdate",
            "placeholder": "۱۴۰۵/۰۵/۳۱",
            "autocomplete": "off",
            "inputmode": "numeric",
            "dir": "ltr",
            "style": "text-align:right;",
        }
        if attrs:
            defaults.update(attrs)
        super().__init__(defaults)

    def format_value(self, value):
        """مقدار ذخیره‌شده (میلادی) را جلالی نشان بده."""
        if value in (None, ""):
            return ""
        if isinstance(value, str):
            # مقدار برگشتی از فرمِ ناموفق — همان چیزی که کاربر نوشته بود
            return value
        return jalali_str(value)


class JalaliDateField(forms.DateField):
    widget = JalaliDateInput

    def to_python(self, value):
        if value in (None, "", []):
            return None
        if not isinstance(value, str):
            return super().to_python(value)
        parsed = parse_jalali_input(value)
        if parsed is None:
            raise forms.ValidationError(
                "تاریخ معتبر نیست. به شکل ۱۴۰۵/۰۵/۳۱ وارد کنید.", code="invalid"
            )
        return parsed
