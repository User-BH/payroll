# -*- coding: utf-8 -*-
"""مبالغ دستیِ جامانده — ورودی‌هایی که دیگر نباید وجود داشته باشند.

    python manage.py stale_inputs                 گزارش
    python manage.py stale_inputs --year 1405
    python manage.py stale_inputs --delete        پاک کردن جاماندگان

بعضی اقلام که روزی دستی وارد می‌شدند حالا فرمول دارند — مابه‌التفاوت، کسر
کار، وجه مرخصی، عیدی و سنوات. اگر از دورانِ قبل ورودیِ دستی‌شان در دیتابیس
مانده باشد، دو اتفاق می‌افتد و هیچ‌کدام دیده نمی‌شود:

  ۱) صفحهٔ «مبالغ دستی» اصلاً نشانشان نمی‌دهد، چون فهرستش را از روی
     `calc_type` می‌سازد و این اقلام دیگر MANUAL نیستند.

  ۲) استخر مازاد `recurring_or_manual` را صدا می‌زند و آنجا **مبلغ دستی بر
     قاعده مقدم است**. پس عددِ جامانده فرمول را کنار می‌زند و روز مأموریت و
     ساعت اضافه‌کاری را عوض می‌کند.

یعنی عددی که هیچ صفحه‌ای نشان نمی‌دهد، فیش را عوض می‌کند.

اقلامی که قاعده دارند ولی عمداً ورودی هم می‌گیرند (مأموریت، اضافه‌کاری)
جامانده نیستند و دست نمی‌خورند — همان تفکیکی که صفحهٔ مبالغ دستی می‌کند.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Sum

from apps.payroll.engine.rules import manual_input_note
from apps.payroll.models import PayrollInput, PayrollPeriod
from apps.payroll_config.models import SalaryComponent


class Command(BaseCommand):
    help = "یافتن مبالغ دستیِ جامانده از اقلامی که حالا فرمول دارند"

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, help="سال (پیش‌فرض: تازه‌ترین)")
        parser.add_argument("--month", type=int)
        parser.add_argument(
            "--delete", action="store_true", help="جاماندگان را پاک کن"
        )

    def _expects_input(self, component) -> bool:
        """آیا این قلم قرار است ورودی دستی داشته باشد؟

        عیناً همان شرطی که صفحهٔ «مبالغ دستی» با آن فهرستش را می‌سازد. اگر
        اینجا فرق کند، این دستور چیزی را جامانده می‌شمارد که کاربر هر ماه
        عمداً وارد می‌کند.
        """
        if component.calc_type == SalaryComponent.CalcType.MANUAL:
            return True
        return bool(
            component.calc_type == SalaryComponent.CalcType.ENGINE_RULE
            and manual_input_note(component.engine_rule_key)
        )

    def handle(self, *args, **options):
        periods = PayrollPeriod.objects.all()
        year = options.get("year")
        if not year:
            newest = PayrollPeriod.objects.order_by("-year").first()
            if newest is None:
                self.stderr.write("هیچ دوره‌ای در سامانه نیست.")
                return
            year = newest.year
        periods = periods.filter(year=year)
        if options.get("month"):
            periods = periods.filter(month=options["month"])

        total_stale = 0
        stale_ids = []

        for period in periods.order_by("month"):
            rows = (
                PayrollInput.objects.filter(period=period)
                .values("component_id")
                .annotate(n=Count("id"), total=Sum("amount"))
                .order_by("-n")
            )
            if not rows:
                self.stdout.write(f"\n— {period}: هیچ مبلغ دستی‌ای ندارد")
                continue

            components = {
                c.id: c
                for c in SalaryComponent.objects.filter(
                    id__in=[r["component_id"] for r in rows]
                )
            }
            self.stdout.write(f"\n— {period}")
            for r in rows:
                c = components[r["component_id"]]
                ok = self._expects_input(c)
                mark = "" if ok else "  ← جامانده"
                line = (
                    f"   {c.code:18} {c.calc_type:12} "
                    f"{r['n']:>4} نفر  {r['total']:>16,}{mark}"
                )
                self.stdout.write(line if ok else self.style.ERROR(line))
                if not ok:
                    total_stale += r["n"]
                    stale_ids.append((period.id, c.id))

        if not stale_ids:
            self.stdout.write(self.style.SUCCESS("\nهیچ ورودی جامانده‌ای نیست."))
            return

        self.stdout.write(
            self.style.ERROR(
                f"\n{total_stale} ورودی جامانده در {len(stale_ids)} ترکیبِ "
                f"دوره×قلم. اینها روی هیچ صفحه‌ای دیده نمی‌شوند ولی فیش را "
                f"عوض می‌کنند."
            )
        )
        if not options["delete"]:
            self.stdout.write(
                "چیزی پاک نشد. برای پاک کردن --delete، و بعد دوره‌ها را "
                "دوباره محاسبه کنید."
            )
            return

        with transaction.atomic():
            for period_id, component_id in stale_ids:
                PayrollInput.objects.filter(
                    period_id=period_id, component_id=component_id
                ).delete()
        self.stdout.write(
            self.style.SUCCESS(f"{total_stale} ورودی جامانده پاک شد.")
        )
        self.stdout.write("حالا دوره‌ها را دوباره محاسبه کنید.")
