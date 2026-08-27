# -*- coding: utf-8 -*-
"""چرا یک قلمِ ورودی روی فیش نیامده؟

    python manage.py why_missing 1151167            همه دوره‌های سال جاری
    python manage.py why_missing 1151167 --month 5  فقط یک ماه
    python manage.py why_missing "علی تقی پور"      با نام هم می‌شود

برای هر «مبلغ دستی» ثبت‌شده، دروازه‌هایی که سر راهش هست یکی‌یکی آزموده
می‌شوند و اولین دروازهٔ بسته گزارش می‌شود. هیچ‌چیزی نوشته نمی‌شود.

این دستور برای همان حالتی است که عدد در «مبالغ دستی» دیده می‌شود ولی روی فیش
نیست — و از بیرون هیچ نشانه‌ای ندارد که کدام‌یک از این پنج علت است.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.employees.models import Employee
from apps.payroll.models import PayrollInput, PayrollPeriod, Payslip


class Command(BaseCommand):
    help = "علتِ نیامدنِ یک قلم ورودی روی فیش"

    def add_arguments(self, parser):
        parser.add_argument("employee", help="کد پرسنلی یا بخشی از نام")
        parser.add_argument("--year", type=int, help="سال (پیش‌فرض: تازه‌ترین)")
        parser.add_argument("--month", type=int, help="ماه (پیش‌فرض: همه)")

    def _employee(self, term):
        matches = list(
            Employee.objects.filter(
                Q(personnel_code=term)
                | Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
            )[:10]
        )
        if not matches:
            # جست‌وجوی نام کامل، چون «علی تقی پور» در دو ستون جدا ذخیره شده
            matches = [
                e for e in Employee.objects.all()
                if term.replace(" ", "") in e.full_name.replace(" ", "")
            ][:10]
        if not matches:
            self.stderr.write(f"پرسنلی با «{term}» پیدا نشد.")
            return None
        if len(matches) > 1:
            self.stderr.write(f"«{term}» به {len(matches)} نفر می‌خورد:")
            for e in matches:
                self.stderr.write(f"  {e.personnel_code} — {e.full_name}")
            return None
        return matches[0]

    def handle(self, *args, **options):
        employee = self._employee(options["employee"])
        if employee is None:
            return

        periods = PayrollPeriod.objects.all()
        year = options.get("year")
        if year:
            periods = periods.filter(year=year)
        else:
            newest = PayrollPeriod.objects.order_by("-year").first()
            if newest is None:
                self.stderr.write("هیچ دوره‌ای در سامانه نیست.")
                return
            periods = periods.filter(year=newest.year)
        if options.get("month"):
            periods = periods.filter(month=options["month"])

        self.stdout.write(
            f"پرسنل: {employee.full_name} · کد {employee.personnel_code}"
        )

        for period in periods.order_by("month"):
            self._report(employee, period)

    # ------------------------------------------------------------------

    def _report(self, employee, period):
        inputs = list(
            PayrollInput.objects.filter(employee=employee, period=period)
            .select_related("component")
            .prefetch_related("component__scopes")
        )
        payslip = Payslip.objects.filter(employee=employee, period=period).first()

        self.stdout.write("")
        head = f"— {period}"
        if payslip is None:
            self.stdout.write(self.style.WARNING(f"{head} · فیشی محاسبه نشده"))
        else:
            self.stdout.write(
                f"{head} · فیش دارد · محاسبه {payslip.calculated_at:%Y-%m-%d %H:%M}"
            )
        if not inputs:
            self.stdout.write("   مبلغ دستی‌ای ثبت نشده.")
            return

        contract = self._contract(employee, period)
        if contract is None:
            self.stdout.write(
                self.style.ERROR(
                    f"   موتور قرارداد فعالی برایش پیدا نمی‌کند — "
                    f"وضعیت پرسنل «{employee.get_status_display()}»، "
                    f"شرکت {employee.company_id} (دوره: {period.company_id}). "
                    f"هیچ قلمی روی فیشش نمی‌آید."
                )
            )

        for row in inputs:
            self._explain(row, payslip, contract, period)

    def _contract(self, employee, period):
        """عیناً همان کوئری‌ای که موتور برای انتخاب قرارداد می‌زند.

        اگر اینجا شرطی کم یا زیاد باشد، این دستور «همه‌چیز مرتب است» می‌گوید
        در حالی که موتور آن پرسنل را اصلاً نمی‌بیند — یعنی بدتر از نبودنش.
        """
        from apps.employees.models import EmploymentContract

        return (
            EmploymentContract.objects.filter(
                employee=employee,
                status=EmploymentContract.Status.ACTIVE,
                effective_from__lte=period.end_date,
                employee__company=period.company,
                employee__status="ACTIVE",
            )
            .filter(
                Q(effective_to__isnull=True)
                | Q(effective_to__gte=period.start_date)
            )
            .order_by("-effective_from")
            .first()
        )

    def _explain(self, row, payslip, contract, period):
        c = row.component
        label = f"   {c.code:20} {row.amount:>14,}  "
        line = payslip.lines.filter(component=c).first() if payslip else None

        if line is not None:
            self.stdout.write(self.style.SUCCESS(f"{label}→ روی فیش: {line.amount:,}"))
            return

        # دروازه‌ها، به همان ترتیبی که موتور از آن‌ها رد می‌شود
        if not c.is_active:
            reason = "قلم غیرفعال است (is_active خاموش)"
        elif c.company_id != period.company_id:
            reason = (
                f"قلم مال شرکت دیگری است "
                f"(قلم: {c.company_id} · دوره: {period.company_id})"
            )
        elif contract is None:
            reason = "قرارداد فعالی در این دوره ندارد"
        elif not c.applies_to(contract):
            targets = "، ".join(f"«{s.target_label()}»" for s in c.scopes.all())
            reason = f"دامنهٔ شمول نمی‌خورد — قلم فقط برای {targets} است"
        elif payslip is None:
            reason = "فیش هنوز محاسبه نشده"
        else:
            reason = (
                "همهٔ دروازه‌ها باز است ولی سطری روی فیش نیست — "
                "یعنی فیش پیش از ثبت این مبلغ محاسبه شده. دوره را دوباره محاسبه کنید."
            )
        self.stdout.write(self.style.ERROR(f"{label}→ {reason}"))
