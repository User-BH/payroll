"""فاز ۶ — چارت سازمانی چندسطحی.

سه کار انجام می‌شود و ترتیبشان مهم است:

۱. مرکز هزینه بالادست می‌گیرد و واحد به مرکز هزینه وصل می‌شود.
۲. کدهای خالی پر می‌شوند و واحدها به مرکز هزینه‌شان می‌چسبند — **پیش از** آنکه
   یکتایی کد الزامی شود، وگرنه همهٔ رکوردهای موجود (که کد خالی دارند) با هم
   تداخل می‌کنند و مهاجرت روی دادهٔ واقعی می‌شکند.
۳. یکتایی «شرکت + کد» اعمال می‌شود.

دادهٔ فعلی بازنویسی نمی‌شود: ساختار تک‌سطحی امروز همان‌طور می‌ماند و فقط
لبه‌های درخت به آن اضافه می‌شود.
"""

from django.db import migrations, models
import django.db.models.deletion


def next_code(used, start=10):
    """۱۰، ۲۰، ۳۰ … — پله‌های ده‌تایی تا برای گره‌های بعدی جا بماند."""
    number = start
    while f"{number:02d}" in used:
        number += 10
    return f"{number:02d}"


def fill_tree(apps, schema_editor):
    Company = apps.get_model("org", "Company")
    CostCenter = apps.get_model("org", "CostCenter")
    Department = apps.get_model("org", "Department")
    EmploymentContract = apps.get_model("employees", "EmploymentContract")

    for company in Company.objects.all():
        # --- کد برای هر گره، در یک فضای مشترک
        # مرکز هزینه و واحد کد را از یک دنباله می‌گیرند، وگرنه دو گرهٔ خواهر
        # (یک واحد و یک مرکز هزینه، هر دو زیر یک پدر) می‌توانند کد یکسان بگیرند
        # و کد کاملشان دیگر آن‌ها را از هم جدا نکند.
        used = set()
        for model in (CostCenter, Department):
            used.update(
                model.objects.filter(company=company)
                .exclude(code="")
                .values_list("code", flat=True)
            )
        for model in (CostCenter, Department):
            for node in model.objects.filter(company=company, code="").order_by("pk"):
                node.code = next_code(used)
                used.add(node.code)
                node.save(update_fields=["code"])

        # --- وصل کردن واحد به مرکز هزینه
        centers_by_name = {
            center.name.strip(): center
            for center in CostCenter.objects.filter(company=company)
        }
        for department in Department.objects.filter(company=company, cost_center__isnull=True):
            # قاعدهٔ اول: اگر همهٔ قراردادهای این واحد یک مرکز هزینه دارند، همان
            # است. این تنها استنتاجی است که نمی‌تواند اشتباه باشد.
            center_ids = set(
                EmploymentContract.objects.filter(department=department)
                .values_list("cost_center_id", flat=True)
            )
            center_ids.discard(None)
            if len(center_ids) == 1:
                department.cost_center_id = center_ids.pop()
                department.save(update_fields=["cost_center"])
                continue
            # قاعدهٔ دوم (برای واحد بدون قرارداد): هم‌نامی با یک مرکز هزینه.
            match = centers_by_name.get(department.name.strip())
            if match is not None:
                department.cost_center_id = match.pk
                department.save(update_fields=["cost_center"])
            # وگرنه بدون مرکز هزینه می‌ماند و در صفحهٔ چارت با هشدار دیده می‌شود؛
            # حدس زدن یعنی هزینه را به مرکز اشتباه بردن.


def unfill_tree(apps, schema_editor):
    """برگشت‌پذیری: فقط اتصال‌ها باز می‌شوند، کدها می‌مانند.

    کد پاک نمی‌شود چون ممکن است بعد از مهاجرت دستی ویرایش شده باشد و پاک کردنش
    یعنی از دست دادن دادهٔ کاربر.
    """
    Department = apps.get_model("org", "Department")
    Department.objects.update(cost_center=None)


class Migration(migrations.Migration):

    dependencies = [
        ("org", "0002_company_bank_file_columns_and_more"),
        ("employees", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="costcenter",
            name="parent",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="children", to="org.costcenter",
                verbose_name="مرکز هزینه بالادست",
            ),
        ),
        migrations.AddField(
            model_name="department",
            name="cost_center",
            field=models.ForeignKey(
                blank=True, null=True,
                help_text="فقط برای واحدهای سطح اول؛ واحد زیرمجموعه، مرکز هزینه را از واحد بالادست به ارث می‌برد",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="departments", to="org.costcenter",
                verbose_name="مرکز هزینه",
            ),
        ),
        migrations.RunPython(fill_tree, unfill_tree),
        migrations.AlterUniqueTogether(
            name="costcenter",
            unique_together={("company", "name"), ("company", "code")},
        ),
        migrations.AlterUniqueTogether(
            name="department",
            unique_together={("company", "name"), ("company", "code")},
        ),
    ]
