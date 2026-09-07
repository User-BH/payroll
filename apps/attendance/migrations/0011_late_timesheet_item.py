# -*- coding: utf-8 -*-
"""ستون «تأخیر ورود» را در اقلام کارکرد سرِ جایش می‌نشاند.

سه چیز را درست می‌کند:

۱. در دیتابیس عملیاتی دو قلمِ تأخیر ساخته شده بود (`LATE` و `LATE_DEDUCTION`)
   که هیچ‌کدام `source_field` نداشتند. یعنی عددی که کاربر در آن ستون می‌زد در
   جدول مقادیر می‌نشست و موتور — که `late_hours` را می‌خوانَد — هرگز نمی‌دیدش.
   ورودی می‌رفت و کسری حساب نمی‌شد، بی‌آنکه خطایی دیده شود.

۲. `LATE` به `late_hours` وصل می‌شود و جزو ستون‌های «قالب‌کشیده» درمی‌آید، پس
   قالب دو ورودیِ ساعت و دقیقه را کنار هم می‌کشد.

۳. شعبه‌هایی که بعد از مهاجرت ۰۰۰۵ ساخته شده‌اند (اردبیل) اصلاً قلم کارکرد
   نداشتند؛ اقلام استاندارد برایشان ساخته می‌شود.

هیچ داده‌ای حذف نمی‌شود: قلم تکراری فقط غیرفعال می‌شود.
"""

from django.db import migrations

from apps.attendance.standard_items import seed_standard_items


def forwards(apps, schema_editor):
    Company = apps.get_model("org", "Company")
    TimesheetItem = apps.get_model("attendance", "TimesheetItem")

    for company in Company.objects.all():
        seed_standard_items(TimesheetItem, company)

        late = TimesheetItem.objects.filter(company=company, code="LATE").first()
        if late is not None:
            late.name = "تأخیر ورود"
            late.unit = "HOUR"
            late.source_field = "late_hours"
            late.reduces_work_days = False
            late.sequence = 75
            late.is_active = True
            late.is_system = True
            late.description = (
                "ساعت و دقیقه جدا وارد می‌شود؛ کسرش از مبنای ماهانه حساب می‌شود"
            )
            late.save()

        # قلم تکراریِ بی‌مصرف — غیرفعال، نه حذف.
        TimesheetItem.objects.filter(
            company=company, code="LATE_DEDUCTION"
        ).update(is_active=False, is_system=False)


def backwards(apps, schema_editor):
    """برگرداندن `LATE` به حالتِ بدون ستون — بدون حذف چیزی."""
    TimesheetItem = apps.get_model("attendance", "TimesheetItem")
    TimesheetItem.objects.filter(code="LATE").update(source_field="")


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0010_leaveentitlement_annual_is_manual"),
        ("org", "0001_initial"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
