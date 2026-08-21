"""تیک «بازنشسته» به «بدون بیمه» تغییر نام داد.

علتش این است که بازنشستگی تنها دلیلِ نداشتن بیمه نیست: کسی ممکن است خودش
نخواهد بیمه شود. چیزی که موتور محاسبه لازم دارد بداند فقط همین است که بیمه
دارد یا نه؛ علتش جداگانه ثبت می‌شود تا بعداً روی پرونده معلوم باشد.

**تغییر نام است، نه حذف و ساخت.** جنگو خودش برای این تغییر
`RemoveField` + `AddField` پیشنهاد می‌دهد که یعنی تیکِ همهٔ بازنشسته‌های فعلی
پاک می‌شود و بیمه‌شان از ماه بعد کسر می‌شود — بی‌آنکه کسی خبردار شود. پس
مهاجرت دستی نوشته شد.

علتِ پیش‌فرض هم برای همان‌ها پر می‌شود: تا امروز تنها معنای این تیک
«بازنشسته» بوده، پس همان در پرونده‌شان ثبت می‌شود.
"""

from django.db import migrations, models


def fill_reason(apps, schema_editor):
    Employee = apps.get_model("employees", "Employee")
    Employee.objects.filter(is_insurance_exempt=True, insurance_exempt_reason="").update(
        insurance_exempt_reason="بازنشسته"
    )


def clear_reason(apps, schema_editor):
    Employee = apps.get_model("employees", "Employee")
    Employee.objects.filter(insurance_exempt_reason="بازنشسته").update(
        insurance_exempt_reason=""
    )


class Migration(migrations.Migration):

    dependencies = [("employees", "0005_phase2_workdays_and_wage")]

    operations = [
        migrations.RenameField(
            model_name="employee",
            old_name="is_retired",
            new_name="is_insurance_exempt",
        ),
        migrations.AlterField(
            model_name="employee",
            name="is_insurance_exempt",
            field=models.BooleanField(
                default=False,
                help_text="حق بیمه برایش محاسبه نمی‌شود و در لیست تأمین اجتماعی نمی‌آید",
                verbose_name="بدون بیمه",
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="insurance_exempt_reason",
            field=models.CharField(
                blank=True, max_length=120,
                help_text="مثلاً «بازنشسته» یا «انصراف کتبی» — روی پرونده می‌ماند تا بعداً معلوم باشد چرا",
                verbose_name="علت نداشتن بیمه",
            ),
        ),
        migrations.RunPython(fill_reason, clear_reason),
    ]
