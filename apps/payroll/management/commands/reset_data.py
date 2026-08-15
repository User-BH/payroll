"""پاک کردن داده — برای وقتی که داده نمونه روی سرور مانده و باید واقعی شود.

    python manage.py reset_data --scope data --confirm    # فقط پرسنل و دوره‌ها
    python manage.py reset_data --scope all  --confirm    # همه‌چیز، حتی پیکربندی

بدون --confirm فقط گزارش می‌دهد که چه چیزی پاک خواهد شد و دست به داده نمی‌زند.
این عمدی است: پاک کردن داده حقوق برگشت‌پذیر نیست.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

User = get_user_model()


class Command(BaseCommand):
    help = "پاک کردن داده نمونه یا شروع دوباره از صفر"

    def add_arguments(self, parser):
        parser.add_argument(
            "--scope", choices=["data", "all"], default="data",
            help="data = پرسنل، دوره، فیش، کارکرد، وام (پیکربندی می‌ماند) · "
                 "all = به‌علاوه شرکت، ساختار سازمانی، اقلام و سال مالی",
        )
        parser.add_argument("--confirm", action="store_true", help="واقعاً پاک کن")
        # کاربران مالی به‌صورت پیش‌فرض حفظ می‌شوند؛ حذفشان باید انتخاب صریح باشد،
        # وگرنه ممکن است راه ورود به سامانه بسته شود.
        parser.add_argument(
            "--delete-staff-users", action="store_true",
            help="کاربران مالی هم پاک شوند (به‌جز مدیر ارشد)",
        )

    def handle(self, *args, **options):
        from apps.attendance.models import LeaveEntitlement, Timesheet, TimesheetImport
        from apps.employees.models import (
            BankAccount, ContractAllowance, Dependent, Employee, EmploymentContract,
        )
        from apps.loans.models import Loan, LoanInstallment
        from apps.org.models import Branch, Company, CostCenter, Department, JobTitle
        from apps.payroll.models import (
            PayrollExport, PayrollInput, PayrollPeriod, PayrollRun,
            Payslip, PayslipLine, PayslipView,
        )
        from apps.payroll_config.models import (
            ComponentScope, FiscalYear, LegalParameter, SalaryComponent, TaxBracket,
        )

        scope = options["scope"]

        # ترتیب مهم است: کلیدهای خارجی مالی PROTECT هستند، پس ابتدا
        # مصرف‌کننده‌ها پاک می‌شوند و بعد چیزی که به آن ارجاع داده شده.
        data_models = [
            (LoanInstallment, "قسط وام"),
            (Loan, "وام"),
            (PayslipView, "لاگ مشاهده فیش"),
            (PayslipLine, "سطر فیش"),
            (Payslip, "فیش"),
            (PayrollExport, "خروجی قانونی"),
            (PayrollRun, "اجرای محاسبه"),
            (PayrollInput, "مبلغ دستی"),
            (TimesheetImport, "لاگ ورود کارکرد"),
            (Timesheet, "کارکرد"),
            (LeaveEntitlement, "سهمیه مرخصی"),
            (PayrollPeriod, "دوره حقوقی"),
            (ContractAllowance, "مزایای مستمر قرارداد"),
            (EmploymentContract, "قرارداد"),
            (Dependent, "فرد تحت تکفل"),
            (BankAccount, "حساب بانکی"),
            (Employee, "پرسنل"),
        ]
        config_models = [
            (ComponentScope, "دامنه شمول"),
            (SalaryComponent, "قلم حقوقی"),
            (TaxBracket, "پله مالیاتی"),
            (LegalParameter, "پارامتر قانونی"),
            (FiscalYear, "سال مالی"),
            (JobTitle, "پست سازمانی"),
            (CostCenter, "مرکز هزینه"),
            (Department, "واحد سازمانی"),
            (Branch, "شعبه"),
            (Company, "شرکت"),
        ]
        targets = data_models + (config_models if scope == "all" else [])

        counts = [(label, model.objects.count()) for model, label in targets]
        total = sum(count for _, count in counts)

        self.stdout.write(
            self.style.WARNING(
                f"\nدامنه: {'همه‌چیز شامل پیکربندی' if scope == 'all' else 'فقط داده عملیاتی'}\n"
            )
        )
        for label, count in counts:
            if count:
                self.stdout.write(f"  {count:>6}  {label}")
        if not total:
            self.stdout.write(self.style.SUCCESS("  چیزی برای پاک کردن نیست."))
            return

        employee_users = User.objects.filter(role=User.Role.EMPLOYEE).count()
        if employee_users:
            self.stdout.write(f"  {employee_users:>6}  حساب پرتال پرسنل (پاک می‌شود)")

        self.stdout.write(f"\n  جمع: {total} رکورد")

        if not options["confirm"]:
            self.stdout.write(self.style.ERROR(
                "\nهیچ‌چیز پاک نشد — این فقط گزارش بود.\n"
                "برای پاک کردن واقعی --confirm را اضافه کنید.\n"
            ))
            self.stdout.write(
                "  پیش از آن حتماً بکاپ بگیرید:\n"
                "    mysqldump --single-transaction --default-character-set=utf8mb4 \\\n"
                "      -upayroll -p payroll | gzip > ~/payroll-before-reset.sql.gz\n"
            )
            return

        with transaction.atomic():
            for model, _label in targets:
                model.objects.all().delete()
            # حساب‌های پرتال به پرسنل حذف‌شده وصل بودند
            User.objects.filter(role=User.Role.EMPLOYEE).delete()
            if options["delete_staff_users"]:
                User.objects.filter(is_superuser=False).delete()

        self.stdout.write(self.style.SUCCESS(f"\n{total} رکورد پاک شد."))
        remaining = User.objects.count()
        self.stdout.write(f"  {remaining} کاربر مالی حفظ شد.")
        if scope == "all":
            self.stdout.write(self.style.WARNING(
                "\n  قدم بعد: python manage.py setup_operational\n"
            ))
        else:
            self.stdout.write(
                "\n  پیکربندی (شرکت، اقلام حقوقی، سال مالی) دست‌نخورده ماند.\n"
                "  حالا می‌توانید پرسنل واقعی را وارد کنید.\n"
            )
