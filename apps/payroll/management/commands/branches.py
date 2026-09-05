# -*- coding: utf-8 -*-
"""مدیریت شعبه‌ها از خط فرمان.

    python manage.py branches                              فهرست شعبه‌ها
    python manage.py branches --add "اردبیل"               ساخت شعبه + کپی پیکربندی
    python manage.py branches --rename "تامین کالا باختر" --to "تبریز"
    python manage.py branches --legal-name "تامین کالا باختر"

ساختن شعبه از رابط کاربری هم هست، ولی روی سرور دست‌وپاگیر است و مراحل
استقرار باید یک اسکریپت باشند.

`--add` همان کاری را می‌کند که صفحهٔ «افزودن شعبه»: اقلام حقوقی، سال مالی،
پارامترها و پله‌های مالیاتی را از قدیمی‌ترین شعبه **کپی** می‌کند، نه به
اشتراک می‌گذارد — تغییر یک نرخ در یک شعبه نباید فیش شعبهٔ دیگر را تکان بدهد.

`--legal-name` نام کل مجموعه است که روی فیش و سربرگ چاپ می‌شود و با سوییچ
شعبه عوض نمی‌شود. روی **همهٔ** شعبه‌ها می‌نشیند، چون یک مجموعه‌اند.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.org.clone import clone_configuration
from apps.org.models import Company


class Command(BaseCommand):
    help = "فهرست، ساخت و تغییر نام شعبه‌ها"

    def add_arguments(self, parser):
        parser.add_argument("--add", default="", help="نام شعبهٔ تازه")
        parser.add_argument("--rename", default="", help="نام فعلی شعبه")
        parser.add_argument("--to", default="", help="نام تازه (همراه --rename)")
        parser.add_argument(
            "--legal-name", default="",
            help="نام مجموعه که روی فیش چاپ می‌شود؛ روی همهٔ شعبه‌ها می‌نشیند",
        )

    # ------------------------------------------------------------------

    def _list(self):
        rows = list(Company.objects.order_by("pk"))
        if not rows:
            self.stdout.write("هیچ شعبه‌ای نیست.")
            return
        self.stdout.write(f"{'شعبه':22}{'روی فیش':24}{'فعال':>6}{'پرسنل':>8}{'دوره':>7}")
        self.stdout.write("-" * 67)
        for c in rows:
            self.stdout.write(
                f"{c.name[:20]:22}{c.display_name[:22]:24}"
                f"{'بله' if c.is_active else 'خیر':>6}"
                f"{c.employees.count():>8}{c.payroll_periods.count() if hasattr(c, 'payroll_periods') else c.periods.count():>7}"
            )

    @transaction.atomic
    def handle(self, *args, **options):
        did = False

        if options["legal_name"]:
            n = Company.objects.update(legal_name=options["legal_name"])
            self.stdout.write(self.style.SUCCESS(
                f"نام مجموعه روی {n} شعبه ثبت شد: «{options['legal_name']}»"
            ))
            did = True

        if options["rename"]:
            target = options["to"].strip()
            if not target:
                self.stderr.write("با --rename باید --to هم بدهید.")
                return
            company = Company.objects.filter(name=options["rename"]).first()
            if company is None:
                names = "، ".join(Company.objects.values_list("name", flat=True))
                self.stderr.write(f"شعبهٔ «{options['rename']}» نیست. موجود: {names}")
                return
            if Company.objects.filter(name=target).exclude(pk=company.pk).exists():
                self.stderr.write(f"شعبهٔ دیگری از قبل «{target}» نام دارد.")
                return
            # نام قدیمی اگر نام مجموعه است، از دست نرود.
            if not company.legal_name:
                company.legal_name = company.name
            old = company.name
            company.name = target
            company.save(update_fields=["name", "legal_name"])
            self.stdout.write(self.style.SUCCESS(
                f"«{old}» → «{target}» · روی فیش: «{company.display_name}»"
            ))
            did = True

        if options["add"]:
            name = options["add"].strip()
            if Company.objects.filter(name=name).exists():
                self.stderr.write(f"شعبه‌ای به نام «{name}» از قبل هست.")
                return
            source = Company.objects.order_by("pk").first()
            company = Company.objects.create(
                name=name,
                legal_name=source.legal_name if source else "",
                activity=source.activity if source else "",
            )
            stats = clone_configuration(source, company)
            self.stdout.write(self.style.SUCCESS(
                "شعبهٔ «{}» ساخته شد — {} قلم حقوقی، {} سال مالی، {} مجموعه "
                "پارامتر و {} پلهٔ مالیاتی از «{}» کپی شد.".format(
                    name, stats["components"], stats["fiscal_years"],
                    stats["parameters"], stats["brackets"],
                    source.name if source else "—",
                )
            ))
            self.stdout.write(
                "حالا پرسنلش را وارد کنید، بعد:\n"
                f'   python manage.py configure_1405 --company "{name}"'
            )
            did = True

        if not did:
            self._list()
