"""فاز ۷ — قاعدهٔ پارامتری برای ساخت قلم حقوقی بدون کدنویسی.

فقط سه فیلد اضافه می‌شود و هیچ دادهٔ موجودی دست نمی‌خورد: اقلام امروزی همان
`calc_type` قبلی‌شان را نگه می‌دارند و قاعدهٔ پارامتری گزینهٔ تازه‌ای برای
اقلام بعدی است.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payroll_config", "0005_phase4_commission_allocation"),
    ]

    operations = [
        migrations.AddField(
            model_name="salarycomponent",
            name="base_source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("MIN_WAGE", "حداقل دستمزد روزانه سال"),
                    ("PERSON_WAGE", "مزد روزانه خود پرسنل"),
                    ("FIXED", "مبلغ ثابت"),
                    ("COMPONENT", "مبلغ یک قلم دیگر"),
                ],
                help_text="فقط برای قاعده پارامتری",
                max_length=12,
                verbose_name="مبنای محاسبه",
            ),
        ),
        migrations.AddField(
            model_name="salarycomponent",
            name="quantity_source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("PAID_DAYS", "روز کارکرد قابل پرداخت"),
                    ("DAY_RATIO", "به نسبت کارکرد ماه"),
                    ("ONE", "ثابت (بدون ضرب در کارکرد)"),
                ],
                help_text="فقط برای قاعده پارامتری",
                max_length=10,
                verbose_name="مقدار",
            ),
        ),
        migrations.AlterField(
            model_name="salarycomponent",
            name="calc_type",
            field=models.CharField(
                choices=[
                    ("ENGINE_RULE", "قاعده موتور"),
                    ("PARAMETRIC", "قاعده پارامتری (بدون کدنویسی)"),
                    ("FIXED", "مبلغ ثابت"),
                    ("PERCENTAGE", "درصدی از قلم دیگر"),
                    ("MANUAL", "ورود دستی در هر دوره"),
                ],
                default="ENGINE_RULE",
                max_length=12,
                verbose_name="نحوه محاسبه",
            ),
        ),
    ]
