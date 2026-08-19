"""ستون‌های تازهٔ جدول کارکرد — از روی `TimesheetItem`، نه از روی کد.

چرا همهٔ ستون‌ها از اینجا ساخته نمی‌شوند؟ چون هفت ستون اولِ جدول ویجت خاص
خودشان را دارند: مرخصی و اضافه‌کاری سه ورودی (روز/ساعت/دقیقه) می‌گیرند،
«کارکرد قابل پرداخت» محاسبه‌شده است و «مانده مرخصی» از کارتابل می‌آید. آن‌ها
همان‌جا می‌مانند و بازنویسی‌شان چیزی به کاربر اضافه نمی‌کرد.

هر قلمِ **دیگری** که فعال باشد — جمعه‌کاری، شب‌کاری، یا هر چیزی که کاربر تازه
تعریف کند — خودکار به‌صورت یک ستون عددی به همین جدول اضافه می‌شود و با
غیرفعال کردنش برمی‌گردد. این همان چیزی است که «افزودن قلم بدون کدنویسی»
یعنی‌اش.
"""

from apps.attendance.models import TimesheetItem

# ستون‌هایی که قالب جدول خودش با ویجت اختصاصی می‌کشد.
RENDERED_FIELDS = {
    "work_days",
    "leave_minutes",
    "absence_days",
    "sick_leave_days",
    "unpaid_leave_days",
    "mission_days",
    "overtime_minutes",
}

# پیشوند نام ورودی در فرم؛ با شناسهٔ قلم یکتا می‌شود.
FIELD_PREFIX = "item_"


def extra_items(company):
    """اقلام فعالی که ستون ثابتی در قالب ندارند — به ترتیب `sequence`."""
    return [
        item
        for item in TimesheetItem.objects.filter(company=company, is_active=True)
        if item.source_field not in RENDERED_FIELDS
    ]


def field_name(item) -> str:
    return f"{FIELD_PREFIX}{item.pk}"


def attach_cells(timesheets, items):
    """به هر سطر، فهرست (قلم، نام ورودی، مقدار) را می‌چسباند.

    قالب نمی‌تواند `value_of(item)` را با آرگومان صدا بزند، پس مقدارها یک بار
    اینجا خوانده می‌شوند. `prefetch_related("entries")` در همان کوئریِ سطرها
    انجام شده تا این حلقه کوئری اضافه نزند.
    """
    rows = list(timesheets)
    for sheet in rows:
        sheet.extra_cells = [
            {"item": item, "field": field_name(item), "value": sheet.value_of(item)}
            for item in items
        ]
    return rows


def save_cells(timesheet, post, items):
    """مقدارهای ارسالی همین اقلام را روی سطر می‌نشاند.

    فقط اقلامی که در POST آمده‌اند لمس می‌شوند تا ذخیرهٔ جزئی (مثلاً از یک
    فرم دیگر) بقیه را صفر نکند.
    """
    from apps.payroll.utils import parse_decimal

    for item in items:
        name = field_name(item)
        if name not in post:
            continue
        timesheet.set_value(item, max(parse_decimal(post.get(name)), 0))
