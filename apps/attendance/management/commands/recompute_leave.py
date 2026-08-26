# -*- coding: utf-8 -*-
"""محاسبهٔ دوبارهٔ سهمیهٔ مرخصی همه پرسنل، از روی تاریخ استخدام.

بدون سوییچ فقط **گزارش** می‌دهد و چیزی را عوض نمی‌کند — سهمیهٔ مرخصی روی فیش
چاپ می‌شود و بی‌خبر عوض کردنش یعنی عددی که کارمند دیده دیگر درست نیست.

    python manage.py recompute_leave                 گزارش اختلاف‌ها
    python manage.py recompute_leave --apply         اعمال قاعده
    python manage.py recompute_leave --pin-existing  عددهای فعلی «دستی» شوند

`--pin-existing` برای مهاجرتِ بی‌خطر است: هر ردیفی که با قاعده جور درنمی‌آید
تیکِ «دستی» می‌خورد، پس عددش دست‌نخورده می‌ماند ولی از این به بعد صریحاً یک
استثناست، نه یک عددِ فراموش‌شده.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.attendance.leave import DEFAULT_DAY_MINUTES, annual_entitlement_minutes
from apps.attendance.models import LeaveEntitlement
from apps.payroll_config.models import FiscalYear


class Command(BaseCommand):
    help = "محاسبهٔ سهمیهٔ مرخصی از تاریخ استخدام"

    def add_arguments(self, parser):
        parser.add_argument(
            "--year", type=int, help="سال مالی (پیش‌فرض: تازه‌ترین سالِ باز)"
        )
        parser.add_argument("--apply", action="store_true", help="اعمال کن")
        parser.add_argument(
            "--pin-existing", action="store_true",
            help="ردیف‌های ناهم‌خوان را «دستی» علامت بزن تا عوض نشوند",
        )

    def _fiscal_year(self, year):
        if year:
            fy = FiscalYear.objects.filter(year=year).first()
            if fy is None:
                self.stderr.write(f"سال مالی {year} در سامانه نیست.")
            return fy
        # تازه‌ترین سالِ باز، وگرنه تازه‌ترین سال — همان روالی که بقیهٔ سامانه
        # دارد. سالِ انتخاب‌شده چاپ می‌شود، چون این دستور روی داده‌ای کار
        # می‌کند که روی فیش چاپ شده و «کدام سال» نباید حدس باشد.
        fy = (
            FiscalYear.objects.filter(is_closed=False).order_by("-year").first()
            or FiscalYear.objects.order_by("-year").first()
        )
        if fy is None:
            self.stderr.write("هیچ سال مالی‌ای در سامانه نیست.")
        return fy

    def handle(self, *args, **options):
        fy = self._fiscal_year(options.get("year"))
        if fy is None:
            return

        params = fy.legal_parameters.order_by("-effective_from").first()
        day_minutes = getattr(params, "leave_day_minutes", DEFAULT_DAY_MINUTES)

        rows = list(
            LeaveEntitlement.objects.select_related("employee").filter(fiscal_year=fy)
        )

        # ردیف‌های «دستی» استثنای اعلام‌شده‌اند، نه ناهم‌خوانی. جدا نگه داشته
        # می‌شوند وگرنه `--apply` همان تیکی را برمی‌دارد که عمداً گذاشته شده.
        diffs, pinned = [], []
        for row in rows:
            want = annual_entitlement_minutes(row.employee, fy, params, day_minutes)
            # پارامتر سال نیست؛ سکوت بهتر از صفر کردن سهمیهٔ همه است.
            if want is None or want == row.annual_minutes:
                continue
            (pinned if row.annual_is_manual else diffs).append((row, want))

        self.stdout.write(f"سال مالی {fy.year} — {len(rows)} ردیف سهمیه")

        def table(items):
            header = f"{'نام':30}{'استخدام':>12}{'فعلی':>8}{'قاعده':>8}"
            self.stdout.write(header)
            self.stdout.write("-" * len(header))
            for row, want in sorted(items, key=lambda r: r[0].employee.full_name):
                self.stdout.write(
                    f"{row.employee.full_name[:28]:30}"
                    f"{str(row.employee.hire_date):>12}"
                    f"{row.annual_minutes / day_minutes:>8.0f}"
                    f"{want / day_minutes:>8.0f}"
                )

        if pinned:
            self.stdout.write("")
            self.stdout.write(f"{len(pinned)} ردیف «دستی» است و دست نمی‌خورد:")
            table(pinned)

        if not diffs:
            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS("بقیه با قاعده جور درمی‌آیند؛ کاری لازم نیست.")
            )
            return

        self.stdout.write("")
        self.stdout.write(f"{len(diffs)} ردیف با قاعده جور درنمی‌آید:")
        table(diffs)
        self.stdout.write("")

        if options["pin_existing"]:
            with transaction.atomic():
                for row, _ in diffs:
                    LeaveEntitlement.objects.filter(pk=row.pk).update(
                        annual_is_manual=True
                    )
            self.stdout.write(
                self.style.SUCCESS(f"{len(diffs)} ردیف «دستی» علامت خورد.")
            )
        elif options["apply"]:
            with transaction.atomic():
                for row, want in diffs:
                    LeaveEntitlement.objects.filter(pk=row.pk).update(
                        annual_minutes=want, annual_is_manual=False
                    )
            self.stdout.write(self.style.SUCCESS(f"{len(diffs)} ردیف به‌روز شد."))
        else:
            self.stdout.write(
                "چیزی عوض نشد. برای اعمال --apply و برای نگه داشتن "
                "عددهای فعلی --pin-existing."
            )
