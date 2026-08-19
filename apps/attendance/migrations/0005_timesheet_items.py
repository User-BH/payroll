"""ستون‌های جدول کارکرد، به‌صورت داده.

ستون‌های موجود جابه‌جا نمی‌شوند: هر کدام یک سطر در `TimesheetItem` می‌گیرند که
با `source_field` به همان ستون اشاره می‌کند. پس هیچ عددی حرکت نمی‌کند و هیچ
فیشی عوض نمی‌شود؛ فقط از این به بعد جدول کارکرد ستون‌هایش را از این فهرست
می‌سازد نه از کد.

شب‌کاری، جمعه‌کاری و تعطیل‌کاری غیرفعال ثبت می‌شوند — همان‌طور که امروز از فرم
برداشته شده‌اند — ولی حالا با یک تیک قابل روشن شدن‌اند، بدون کدنویسی.
"""

import django.db.models.deletion
from django.db import migrations, models

# فهرست در `apps/attendance/standard_items.py` است تا نصب تازه هم بتواند از
# همان استفاده کند: این مهاجرت روی دیتابیسِ بدون شرکت چیزی نمی‌سازد، و شرکت
# در `setup_operational` بعد از migrate ساخته می‌شود.
from apps.attendance.standard_items import STANDARD_ITEMS, seed_standard_items


def seed_items(apps, schema_editor):
    Company = apps.get_model("org", "Company")
    TimesheetItem = apps.get_model("attendance", "TimesheetItem")
    for company in Company.objects.all():
        seed_standard_items(TimesheetItem, company)

def unseed_items(apps, schema_editor):
    """فقط اقلام استانداردِ ستون‌دار پاک می‌شوند؛ اقلام تازهٔ کاربر می‌مانند."""
    TimesheetItem = apps.get_model("attendance", "TimesheetItem")
    TimesheetItem.objects.filter(
        code__in=[item[0] for item in STANDARD_ITEMS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0004_phase5_leave_desk"),
        ("org", "0003_phase6_org_tree"),
    ]

    operations = [
        migrations.CreateModel(
            name="TimesheetItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("code", models.CharField(max_length=40, verbose_name="کد")),
                ("name", models.CharField(max_length=60, verbose_name="نام ستون")),
                (
                    "unit",
                    models.CharField(
                        choices=[("DAY", "روز"), ("HOUR", "ساعت"), ("MINUTE", "دقیقه")],
                        default="HOUR",
                        max_length=8,
                        verbose_name="واحد",
                    ),
                ),
                (
                    "source_field",
                    models.CharField(
                        blank=True,
                        help_text="اگر این قلم روی خود جدول کارکرد ستون دارد، نام همان فیلد. خالی یعنی مقدارش در جدول مقادیر کارکرد ذخیره می\u200cشود.",
                        max_length=40,
                        verbose_name="ستون قدیمی",
                    ),
                ),
                (
                    "reduces_work_days",
                    models.BooleanField(
                        default=False,
                        help_text="مثل غیبت و مرخصی بدون حقوق. مرخصی استحقاقی و مأموریت کم نمی\u200cشوند.",
                        verbose_name="از کارکرد قابل پرداخت کم می\u200cشود",
                    ),
                ),
                (
                    "sequence",
                    models.PositiveSmallIntegerField(
                        default=100, verbose_name="ترتیب ستون"
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True, verbose_name="در جدول کارکرد نمایش داده شود"
                    ),
                ),
                (
                    "is_system",
                    models.BooleanField(
                        default=False,
                        help_text="اقلامی که موتور مستقیم به آن\u200cها وابسته است و حذف نمی\u200cشوند",
                        verbose_name="سیستمی",
                    ),
                ),
                (
                    "description",
                    models.CharField(blank=True, max_length=160, verbose_name="توضیح"),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="timesheet_items",
                        to="org.company",
                        verbose_name="شرکت",
                    ),
                ),
            ],
            options={
                "verbose_name": "قلم کارکرد",
                "verbose_name_plural": "اقلام کارکرد",
                "ordering": ["sequence", "id"],
                "unique_together": {("company", "code")},
            },
        ),
        migrations.CreateModel(
            name="TimesheetEntry",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "value",
                    models.DecimalField(
                        decimal_places=2, default=0, max_digits=10, verbose_name="مقدار"
                    ),
                ),
                (
                    "timesheet",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entries",
                        to="attendance.timesheet",
                        verbose_name="کارکرد",
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="entries",
                        to="attendance.timesheetitem",
                        verbose_name="قلم",
                    ),
                ),
            ],
            options={
                "verbose_name": "مقدار قلم کارکرد",
                "verbose_name_plural": "مقادیر اقلام کارکرد",
                "unique_together": {("timesheet", "item")},
            },
        ),
        migrations.RunPython(seed_items, unseed_items),
    ]
