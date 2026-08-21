"""سابقه دیگر روی قرارداد ذخیره نمی‌شود؛ از تاریخ استخدام حساب می‌شود.

عددِ `seniority_years` یک بار تایپ می‌شد و بعد کهنه می‌ماند — در دیتابیس
عملیاتی یک نفر ۳ سال ثبت شده بود در حالی که ۴ سال سر کار بود، و در دادهٔ نمونه
۱۲ نفر از ۱۴۶ نفر با تاریخ استخدامشان نمی‌خواندند.

حالا سابقه در موتور و **نسبت به دورهٔ حقوقی** حساب می‌شود، و آنچه ذخیره می‌شود
فقط چیزی است که از تاریخ استخدام درنمی‌آید: **سابقهٔ قبلی**.

## تبدیل

    سابقهٔ قبلی (ماه) = max(۰ ، سابقهٔ ثبت‌شده×۱۲ − ماه‌های گذشته از استخدام)

اگر عدد ثبت‌شده از تاریخ استخدام بیشتر بوده، تفاوتش سابقهٔ واقعیِ جای دیگر است
و نگه داشته می‌شود. اگر کمتر یا برابر بوده، یعنی فقط کهنه شده و صفر می‌شود —
محاسبهٔ خودکار جایش را می‌گیرد.

**این تبدیل روی پول اثر دارد:** کسی که عدد ثبت‌شده‌اش زیر یک سال بوده ولی
واقعاً بیشتر کار کرده، از این به بعد پایه سنوات می‌گیرد. پیش از اجرا روی
سرور، گزارش `python manage.py seniority_report` را ببینید.
"""

from datetime import date

from django.db import migrations, models


def months_between(start, end):
    if not start or not end or end < start:
        return 0
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(0, months)


def to_prior_service(apps, schema_editor):
    Employee = apps.get_model("employees", "Employee")
    Contract = apps.get_model("employees", "EmploymentContract")
    today = date.today()

    for employee in Employee.objects.all():
        contract = (
            Contract.objects.filter(employee=employee)
            .order_by("-effective_from")
            .first()
        )
        if contract is None:
            continue
        stored_months = int(contract.seniority_years or 0) * 12
        earned = months_between(employee.hire_date, today)
        extra = stored_months - earned
        if extra > 0:
            employee.prior_service_months = min(extra, 65535)
            employee.save(update_fields=["prior_service_months"])


def back(apps, schema_editor):
    """برگشت: سابقهٔ قبلی + گذشته از استخدام، به سال."""
    Employee = apps.get_model("employees", "Employee")
    Contract = apps.get_model("employees", "EmploymentContract")
    today = date.today()
    for employee in Employee.objects.all():
        total = months_between(employee.hire_date, today) + int(
            employee.prior_service_months or 0
        )
        Contract.objects.filter(employee=employee).update(seniority_years=total // 12)


class Migration(migrations.Migration):

    dependencies = [("employees", "0007_daily_wage")]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="prior_service_months",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="سابقهٔ پیش از این استخدام — در همین کارگاه یا جای دیگر. "
                          "به سابقهٔ محاسبه‌شده از تاریخ استخدام اضافه می‌شود.",
                verbose_name="سابقهٔ قبلی (ماه)",
            ),
        ),
        migrations.RunPython(to_prior_service, back),
        migrations.RemoveField(model_name="employmentcontract", name="seniority_years"),
    ]
