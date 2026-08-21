"""گزارش سابقهٔ هر پرسنل، و اینکه چه کسی پایه سنوات می‌گیرد.

    python manage.py seniority_report
    python manage.py seniority_report --period 12

سابقه دیگر عددی ثبت‌شده نیست؛ از تاریخ استخدام + سابقهٔ قبلی و **نسبت به
پایان دوره** حساب می‌شود. این دستور همان محاسبه را نشان می‌دهد تا پیش از
اجرای حقوق معلوم باشد چه کسی مشمول پایه سنوات هست و چه کسی نه.

مخصوصاً بعد از مهاجرت `employees.0008_prior_service` یک بار اجرا شود: کسی که
عدد قدیمی‌اش کهنه شده بود ممکن است از این ماه پایه سنوات بگیرد.
"""

from django.core.management.base import BaseCommand

from apps.employees.models import Employee
from apps.payroll.models import PayrollPeriod
from apps.payroll.utils import fa_money, fa_number, to_jalali


class Command(BaseCommand):
    help = "سابقهٔ پرسنل و مشمولیت پایه سنوات، نسبت به پایان دوره"

    def add_arguments(self, parser):
        parser.add_argument(
            "--period", type=int, default=None,
            help="شناسهٔ دوره؛ پیش‌فرض تازه‌ترین دوره",
        )
        parser.add_argument(
            "--only-eligible", action="store_true",
            help="فقط کسانی که پایه سنوات می‌گیرند",
        )

    def handle(self, *args, **options):
        period = (
            PayrollPeriod.objects.filter(pk=options["period"]).first()
            if options["period"]
            else PayrollPeriod.objects.order_by("-year", "-month").first()
        )
        if period is None:
            self.stdout.write(self.style.ERROR("هیچ دوره‌ای تعریف نشده است."))
            return

        params = period.legal_parameter
        daily = params.seniority_daily if params else 0
        self.stdout.write(
            f"\nسابقه در پایان {period.title} "
            f"({to_jalali(period.end_date)}) · پایه سنوات روزانه {fa_money(daily)} ریال\n"
        )

        rows = []
        for employee in Employee.objects.filter(
            company=period.company, status=Employee.Status.ACTIVE
        ).order_by("personnel_code"):
            months = employee.seniority_months_at(period.end_date)
            years = months // 12
            rows.append((employee, months, years))

        eligible = [r for r in rows if r[2] >= 1]
        if options["only_eligible"]:
            rows = eligible

        header = f"{'کد':>10}  {'نام':24}{'استخدام':>12}{'قبلی':>8}{'سابقه':>10}  مشمول"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for employee, months, years in rows:
            prior = employee.prior_service_months or 0
            mark = "بله" if years >= 1 else "—"
            self.stdout.write(
                f"{employee.personnel_code:>10}  {employee.full_name[:22]:24}"
                f"{str(to_jalali(employee.hire_date)):>12}"
                f"{(fa_number(prior) + ' ماه') if prior else '—':>8}"
                f"{fa_number(years) + ' سال':>10}  {mark}"
            )

        self.stdout.write(
            f"\n{len(eligible)} نفر از {len(rows)} نفر مشمول پایه سنوات‌اند."
        )
        self.stdout.write(self.style.WARNING(
            "  سابقه نسبت به **پایان دوره** حساب می‌شود، نه امروز — پس محاسبهٔ\n"
            "  دوبارهٔ یک ماه قدیمی همان عدد قدیمی را می‌دهد.\n"
            "  اگر کسی سابقهٔ کار پیش از این استخدام دارد (در همین کارگاه یا جای\n"
            "  دیگر)، آن را در «ویرایش پرسنل ← سابقهٔ قبلی (ماه)» ثبت کنید."
        ))
