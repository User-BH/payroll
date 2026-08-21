"""مزد قرارداد از «ماهانه» به «روزانه» تغییر کرد.

چرا: فایل واقعی شرکت مزد روزانه را ثبت می‌کند و حقوق ماهانه را از روی آن
می‌سازد. نگهداری ماهانه یعنی مزد روزانه هر ماه با تقسیم بر طول همان ماه ساخته
شود — یعنی یک قرارداد در مرداد (۳۱ روزه) و مهر (۳۰ روزه) دو مزد روزانهٔ متفاوت
داشت، و حاصلِ تقسیم کسر متناوب بود.

**تغییر نام است، نه حذف و ساخت.** جنگو خودش `RemoveField` + `AddField`
پیشنهاد می‌دهد که یعنی مزد همهٔ قراردادها صفر می‌شود و ماه بعد همه با حداقل
دستمزد حساب می‌شوند — بی‌آنکه کسی خبردار شود.

## مخرج تبدیل

عدد قدیمی ماهانه بود و باید بر چیزی تقسیم شود. حدس زدن اینجا یعنی کم یا زیاد
کردن حقوق مردم، پس حدس نمی‌زنیم: **مخرج را از آخرین فیشی می‌گیریم که واقعاً
صادر شده.** موتور تا امروز `مزد ماهانه ÷ طول ماه دوره` را می‌پرداخت، پس تقسیم
بر طول همان ماه یعنی آخرین فیشِ صادرشده دقیقاً همان می‌ماند که بود.

طول ماه از بازهٔ تاریخی خود دوره درمی‌آید (`end_date − start_date + 1`)، نه از
تقویم — چون همان است که موتور استفاده کرده.

قراردادی که هیچ فیشی ندارد، بر ۳۰ تقسیم می‌شود: قرارداد کار حقوق ماهانه را
`مزد روزانه × ۳۰` تعریف می‌کند و فایل ۱۴۰۵ شرکت هم `حقوق ماهانه = S × ۳۰`
دارد. این تنها جایی است که فرض می‌کنیم، و چون فیشی صادر نشده، چیزی را هم
تغییر نمی‌دهد.

**بعد از این مهاجرت مزد روزانهٔ هر قرارداد را یک بار چشمی ببینید**؛ اگر عدد
قدیمی با مخرج دیگری وارد شده بود، همین‌جا معلوم می‌شود.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations, models

FALLBACK_DIVISOR = Decimal("30")


def monthly_to_daily(apps, schema_editor):
    Contract = apps.get_model("employees", "EmploymentContract")
    Payslip = apps.get_model("payroll", "Payslip")

    for contract in Contract.objects.all():
        monthly = Decimal(contract.daily_wage or 0)
        if not monthly:
            continue
        slip = (
            Payslip.objects.filter(contract=contract)
            .select_related("period")
            .order_by("-period__year", "-period__month")
            .first()
        )
        divisor = FALLBACK_DIVISOR
        if slip and slip.period.start_date and slip.period.end_date:
            days = (slip.period.end_date - slip.period.start_date).days + 1
            if days > 0:
                divisor = Decimal(days)
        contract.daily_wage = (monthly / divisor).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        contract.save(update_fields=["daily_wage"])


def daily_to_monthly(apps, schema_editor):
    """برگشت: همان مخرج، در جهت معکوس."""
    Contract = apps.get_model("employees", "EmploymentContract")
    Payslip = apps.get_model("payroll", "Payslip")

    for contract in Contract.objects.all():
        daily = Decimal(contract.daily_wage or 0)
        if not daily:
            continue
        slip = (
            Payslip.objects.filter(contract=contract)
            .select_related("period")
            .order_by("-period__year", "-period__month")
            .first()
        )
        divisor = FALLBACK_DIVISOR
        if slip and slip.period.start_date and slip.period.end_date:
            days = (slip.period.end_date - slip.period.start_date).days + 1
            if days > 0:
                divisor = Decimal(days)
        contract.daily_wage = (daily * divisor).quantize(Decimal("1"))
        contract.save(update_fields=["daily_wage"])


class Migration(migrations.Migration):

    dependencies = [
        ("employees", "0006_insurance_exempt"),
        ("payroll", "0011_alter_payslip_insurance_applies"),
    ]

    operations = [
        migrations.RenameField(
            model_name="employmentcontract",
            old_name="base_salary",
            new_name="daily_wage",
        ),
        migrations.AlterField(
            model_name="employmentcontract",
            name="daily_wage",
            field=models.DecimalField(
                decimal_places=0, default=Decimal("0"), max_digits=18,
                help_text="خالی یا صفر یعنی از «حداقل دستمزد روزانه» سال مالی استفاده شود",
                verbose_name="مزد روزانه (ریال)",
            ),
        ),
        migrations.RunPython(monthly_to_daily, daily_to_monthly),
    ]
