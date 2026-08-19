"""فهرست ستون‌های استانداردِ جدول کارکرد — یک جا، برای مهاجرت و برای نصب تازه.

چرا اینجا و نه فقط داخل مهاجرت: مهاجرت روی دیتابیسی که **هنوز شرکتی ندارد**
هیچ چیز نمی‌سازد (حلقه‌اش روی شرکت‌هاست). در نصب تازه ترتیب همین است — اول
`migrate`، بعد `setup_operational` که شرکت را می‌سازد — پس بدون این ماژول،
نصب تازه با صفر قلم کارکرد بالا می‌آمد و کل صفحهٔ «اقلام کارکرد» خالی بود.

پس فهرست یک جا تعریف می‌شود و دو مصرف‌کننده دارد: مهاجرت (برای دیتابیس‌هایی
که از قبل شرکت داشته‌اند) و `ensure_standard_items` (برای شرکتی که تازه ساخته
می‌شود). هر دو «اگر نبود بساز» هستند، پس اجرای دوباره چیزی را خراب نمی‌کند.

هشدار برای آینده: مهاجرتِ ۰۰۰۵ همین فهرست را import می‌کند. اگر روزی قلمی از
این فهرست حذف شود، آن مهاجرت روی دیتابیس خالی دیگر آن قلم را نمی‌سازد. تغییر
این فهرست باید با یک مهاجرت تازه بیاید، نه با ویرایش بی‌سروصدای اینجا.
"""

# (کد، نام، واحد، ستون قدیمی، از کارکرد کم می‌شود، ترتیب، فعال، سیستمی، توضیح)
STANDARD_ITEMS = [
    ("WORK_DAYS", "روز کارکرد", "DAY", "work_days", False, 10, True, True,
     "کارکرد اولیه ماه، پیش از کسر روزهای بی‌حقوق"),
    ("LEAVE", "مرخصی استحقاقی", "MINUTE", "leave_minutes", False, 20, True, True,
     "به دقیقه ذخیره می‌شود؛ روز و ساعت از روی آن ساخته می‌شوند"),
    ("ABSENCE", "غیبت", "DAY", "absence_days", True, 30, True, True, ""),
    ("SICK", "مرخصی استعلاجی", "DAY", "sick_leave_days", True, 40, True, True, ""),
    ("UNPAID_LEAVE", "مرخصی بدون حقوق", "DAY", "unpaid_leave_days", True, 50, True, True, ""),
    ("MISSION", "حق مأموریت", "DAY", "mission_days", False, 60, True, True,
     "از کارکرد کم نمی‌شود چون پرداخت دارد"),
    ("OVERTIME", "اضافه‌کاری", "MINUTE", "overtime_minutes", False, 70, True, True,
     "به دقیقه ذخیره می‌شود؛ ساعت از روی آن ساخته می‌شود"),
    ("NIGHT_WORK", "شب‌کاری", "HOUR", "night_hours", False, 80, False, False,
     "فیش فعلی شرکت این قلم را ندارد؛ با فعال کردن این تیک به جدول کارکرد برمی‌گردد"),
    ("FRIDAY_WORK", "جمعه‌کاری", "HOUR", "friday_hours", False, 90, False, False,
     "فیش فعلی شرکت این قلم را ندارد؛ با فعال کردن این تیک به جدول کارکرد برمی‌گردد"),
    ("HOLIDAY_WORK", "تعطیل‌کاری", "HOUR", "holiday_hours", False, 100, False, False,
     "فیش فعلی شرکت این قلم را ندارد؛ با فعال کردن این تیک به جدول کارکرد برمی‌گردد"),
]


def seed_standard_items(model, company):
    """اقلام نبودهٔ یک شرکت را می‌سازد. `model` می‌تواند مدل تاریخیِ مهاجرت باشد."""
    existing = set(model.objects.filter(company=company).values_list("code", flat=True))
    created = 0
    for code, name, unit, field, reduces, seq, active, system, note in STANDARD_ITEMS:
        if code in existing:
            continue
        model.objects.create(
            company=company, code=code, name=name, unit=unit,
            source_field=field, reduces_work_days=reduces, sequence=seq,
            is_active=active, is_system=system, description=note,
        )
        created += 1
    return created


def ensure_standard_items(company):
    """همان کار، با مدل واقعی — برای دستورهای راه‌اندازی."""
    from apps.attendance.models import TimesheetItem

    return seed_standard_items(TimesheetItem, company)
