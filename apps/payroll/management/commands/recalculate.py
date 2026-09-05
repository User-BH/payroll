# -*- coding: utf-8 -*-
"""محاسبهٔ دوبارهٔ دوره‌ها از خط فرمان.

    python manage.py recalculate                      همهٔ دوره‌های باز
    python manage.py recalculate --year 1405 --month 5
    python manage.py recalculate --company "اردبیل"

تا امروز محاسبه فقط از رابط کاربری بود، و بعد از هر تغییرِ پیکربندی روی سرور
باید یکی‌یکی دستی زده می‌شد. فیش تا وقتی دوباره محاسبه نشود عکسِ قدیمی است —
یعنی تغییری که در تنظیمات اعمال شده روی کاغذ دیده نمی‌شود و کسی هم خبردار
نمی‌شود.

دورهٔ **قفل‌شده** دست نمی‌خورد و در گزارش با دلیلش می‌آید؛ قفل یعنی فیش‌ها
صادر شده‌اند و نباید زیر پای کسی عوض شوند.
"""

from django.core.management.base import BaseCommand

from apps.org.current import active_company
from apps.payroll.engine.runner import calculate_period
from apps.payroll.models import PayrollPeriod


class Command(BaseCommand):
    help = "محاسبهٔ دوبارهٔ دوره‌های حقوق"

    def add_arguments(self, parser):
        parser.add_argument("--company", default="", help="نام شعبه")
        parser.add_argument("--year", type=int)
        parser.add_argument("--month", type=int)

    def handle(self, *args, **options):
        from apps.org.models import Company

        name = options["company"]
        if name:
            company = Company.objects.filter(name=name).first()
            if company is None:
                names = "، ".join(Company.objects.values_list("name", flat=True))
                self.stderr.write(f"شعبهٔ «{name}» نیست. شعبه‌ها: {names}")
                return
        else:
            company = active_company()

        periods = PayrollPeriod.objects.filter(company=company)
        if options.get("year"):
            periods = periods.filter(year=options["year"])
        if options.get("month"):
            periods = periods.filter(month=options["month"])
        periods = periods.order_by("year", "month")

        if not periods:
            self.stdout.write("دوره‌ای با این مشخصات نیست.")
            return

        self.stdout.write(f"شعبه: {company.name}")
        ok = failed = skipped = 0
        for period in periods:
            # موتور خودش هم روی دورهٔ قفل‌شده خطا می‌دهد؛ اینجا پیش از
            # تلاش رد می‌شود تا گزارش «خطا» نگوید وقتی چیزی خراب نیست.
            if period.is_locked:
                self.stdout.write(f"  {period} — قفل است، رد شد")
                skipped += 1
                continue
            try:
                run = calculate_period(period)
            except Exception as exc:  # noqa: BLE001
                self.stdout.write(self.style.ERROR(f"  {period} — خطا: {exc}"))
                failed += 1
                continue
            ok += 1
            line = f"  {period} — {run.success_count} فیش"
            if run.error_count:
                line += f" · {run.error_count} خطا"
            self.stdout.write(
                self.style.WARNING(line) if run.error_count
                else self.style.SUCCESS(line)
            )

        self.stdout.write(
            f"\nمحاسبه‌شده {ok} · رد‌شده {skipped} · خطا {failed}"
        )
