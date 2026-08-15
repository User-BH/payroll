from django.db import migrations


def promote_superusers(apps, schema_editor):
    """ابرکاربرهایی که با نقش پیش‌فرض «کارمند» ساخته شده‌اند را مدیر سیستم کن.

    createsuperuser نقش را ست نمی‌کرد و مقدار پیش‌فرض فیلد «کارمند» بود، پس
    ابرکاربر پشت پیام «این حساب دسترسی به بخش مالی ندارد» می‌ماند.
    """
    User = apps.get_model("accounts", "User")
    User.objects.filter(is_superuser=True).exclude(role="ADMIN").update(role="ADMIN")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_user_must_change_password")]
    operations = [migrations.RunPython(promote_superusers, noop)]
