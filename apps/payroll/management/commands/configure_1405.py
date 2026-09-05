"""اعمال پیکربندی شرکت برای فایل حقوق ۱۴۰۵.

    python manage.py configure_1405

`setup_operational` اقلام پایه را می‌سازد؛ این دستور آن چیزی را اضافه می‌کند
که بک‌تست تیر ۱۴۰۵ لازم داشت و تا امروز فقط در یک دیتابیس زندگی می‌کرد:
زنجیرهٔ مازاد گروه پشتیبانی، جذب در پورسانت فروش، و گروه راننده استجاری.

**بعد از ورود پرسنل اجرا شود.** دامنهٔ زنجیرهٔ مازاد از پست‌های واقعیِ
قراردادهای فعال ساخته می‌شود؛ روی دیتابیس بی‌پرسنل، دامنه‌ای برای ساختن نیست.

اجرای دوباره‌اش بی‌خطر است: هر بار همان وضعیت را می‌سازد و فقط تغییرات را
گزارش می‌کند.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.org.models import Company
from apps.payroll.company_config import configure


class Command(BaseCommand):
    help = "پیکربندی زنجیرهٔ مازاد، جذب پورسانت و گروه راننده استجاری"

    def add_arguments(self, parser):
        parser.add_argument("--company", default="")

    @transaction.atomic
    def handle(self, *args, **options):
        name = options["company"]
        if name:
            company = Company.objects.filter(name=name).first()
            if company is None:
                # پیام قبلی می‌گفت «شرکتی پیدا نشد، setup_operational را اجرا
                # کنید» — که وقتی شعبه‌ها هستند و فقط این یکی نیست، آدم را
                # دنبال کار اشتباه می‌فرستد.
                names = "، ".join(Company.objects.values_list("name", flat=True))
                self.stdout.write(self.style.ERROR(
                    f"شعبه‌ای به نام «{name}» نیست."
                    + (f" شعبه‌های موجود: {names}" if names else "")
                ))
                self.stdout.write(
                    f'برای ساختنش: python manage.py branches --add "{name}"'
                )
                return
        else:
            company = Company.objects.order_by("pk").first()
            if company is None:
                self.stdout.write(self.style.ERROR(
                    "شرکتی پیدا نشد. اول `python manage.py setup_operational` را اجرا کنید."
                ))
                return

        self.stdout.write(f"شرکت: {company.name}\n")
        changes = configure(company, stdout=self.stdout)
        if not changes:
            self.stdout.write(self.style.SUCCESS("\nپیکربندی از قبل درست بود — چیزی عوض نشد."))
        else:
            self.stdout.write(self.style.SUCCESS(f"\n{len(changes)} مورد اعمال شد."))
