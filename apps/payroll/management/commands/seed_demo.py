"""ساخت داده نمونه برای دمو.

    python manage.py seed_demo            # ساخت (اگر داده هست، خطا می‌دهد)
    python manage.py seed_demo --reset    # پاک کردن و ساخت دوباره

هشدار: مقادیر قانونی (حداقل دستمزد، پلکان مالیات، حق مسکن و…) داده نمونه‌اند و
باید پیش از استفاده واقعی با بخشنامه‌های سال تطبیق داده شوند.
"""

import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.attendance.models import Timesheet
from apps.employees.models import (
    BankAccount,
    ContractAllowance,
    Dependent,
    Employee,
    EmploymentContract,
)
from apps.loans.models import Loan, LoanInstallment
from apps.org.models import Company, CostCenter, Department, JobTitle
from apps.payroll.engine.runner import calculate_period
from apps.payroll.models import PayrollInput, PayrollPeriod
from apps.payroll.utils import jalali_month_range, jalali_to_gregorian
from apps.payroll_config.models import (
    ComponentScope,
    FiscalYear,
    LegalParameter,
    SalaryComponent,
    TaxBracket,
)

User = get_user_model()

FIRST_NAMES_M = [
    "علی", "محمد", "حسین", "رضا", "مهدی", "امیر", "سعید", "مجید", "کاظم", "بهروز",
    "فرهاد", "ناصر", "پیمان", "کیوان", "بابک", "شهرام", "جواد", "احمد", "یاسر", "میلاد",
]
FIRST_NAMES_F = [
    "مریم", "فاطمه", "زهرا", "سارا", "الهام", "نگین", "شیوا", "لیلا", "نازنین", "پریسا",
    "سمیه", "مینا", "رویا", "آزاده", "نسرین", "بهاره", "شقایق", "هانیه",
]
LAST_NAMES = [
    "تستی", "کرمی", "بیگی", "نجفی", "صادقی", "رضایی", "محمدی", "حسینی", "کاظمی", "مرادی",
    "شریفی", "زارعی", "قاسمی", "اکبری", "جعفری", "سلطانی", "نوری", "فتحی", "عباسی", "یوسفی",
    "امینی", "کریمی", "رحیمی", "سبحانی", "طاهری", "غفاری", "لطفی", "هاشمی", "وحیدی", "بهرامی",
]
BANKS = [("ملت", "012"), ("صادرات", "019"), ("تجارت", "018"), ("ملی", "017"), ("سپه", "015")]


def make_national_id(seed: int) -> str:
    """کد ملی با چک‌سام معتبر."""
    base = f"{seed % 1000000000:09d}"
    total = sum(int(base[i]) * (10 - i) for i in range(9))
    remainder = total % 11
    check = remainder if remainder < 2 else 11 - remainder
    return base + str(check)


class Command(BaseCommand):
    help = "ساخت داده نمونه برای دموی سامانه حقوق و دستمزد"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="پاک کردن داده قبلی")
        parser.add_argument("--employees", type=int, default=146, help="تعداد پرسنل")

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(1405)

        if options["reset"]:
            self.stdout.write("پاک کردن داده قبلی…")
            from apps.payroll.models import PayrollRun, Payslip, PayslipLine

            # ترتیب مهم است: کلیدهای خارجی مالی PROTECT هستند، پس ابتدا باید
            # مصرف‌کننده‌ها (فیش و سطرهایش) پاک شوند و بعد قرارداد و پرسنل.
            for model in (
                LoanInstallment, Loan,
                PayslipLine, Payslip, PayrollRun,
                PayrollInput, Timesheet, PayrollPeriod,
                ContractAllowance, Dependent, BankAccount, EmploymentContract,
                Employee,
                ComponentScope, SalaryComponent,
                TaxBracket, LegalParameter, FiscalYear,
                JobTitle, CostCenter, Department, Company,
            ):
                model.objects.all().delete()
            User.objects.all().delete()

        if Company.objects.exists():
            self.stdout.write(self.style.ERROR(
                "داده قبلی وجود دارد. برای ساخت دوباره از --reset استفاده کنید."
            ))
            return

        company = self._create_org()
        users = self._create_users()
        years = self._create_fiscal_data(company)
        components = self._create_components(company)
        employees = self._create_employees(company, options["employees"], users)

        prev_period = self._create_period(company, years[1404], 1404, 12)
        curr_period = self._create_period(company, years[1405], 1405, 1)

        self._create_timesheets(prev_period, employees, approve_all=True)
        self._create_timesheets(curr_period, employees, approve_all=False)
        self._create_commissions(prev_period, curr_period, employees, components)
        self._create_loans(employees)

        self.stdout.write("محاسبه دوره اسفند ۱۴۰۴…")
        calculate_period(prev_period, user=users["ali"])
        prev_period.refresh_from_db()
        prev_period.status = PayrollPeriod.Status.LOCKED
        prev_period.save()

        self.stdout.write("محاسبه دوره فروردین ۱۴۰۵…")
        calculate_period(curr_period, user=users["ali"])
        curr_period.refresh_from_db()
        # دوره جاری عمداً به «پیش‌نویس» برمی‌گردد: هم داشبورد ارقام واقعی نشان
        # می‌دهد، هم جدول کارکرد برای نمایش ویرایش درجا باز می‌ماند.
        curr_period.status = PayrollPeriod.Status.DRAFT
        curr_period.save()

        self.stdout.write(self.style.SUCCESS("\n داده نمونه ساخته شد."))
        self.stdout.write(
            f"  پرسنل: {Employee.objects.count()} نفر\n"
            f"  دوره جاری: {curr_period.title} — "
            f"ناخالص {curr_period.total_gross:,.0f} ریال، "
            f"خالص {curr_period.total_net:,.0f} ریال\n"
            f"\n  ورود مالی:  ali / demo1234   یا   admin / demo1234"
            f"\n  ورود پرتال: کد پرسنلی 1001 / demo1234\n"
        )

    # ------------------------------------------------------------------ org

    def _create_org(self):
        company = Company.objects.create(
            name="تامین کالا باختر",
            legal_name="شرکت تامین کالا باختر (سهامی خاص)",
            national_id="10861234567",
            economic_code="411234567890",
            insurance_workshop_code="1234567890",
            tax_file_number="987654321",
            address="کرمانشاه، بلوار شهید بهشتی",
            phone="083-38200000",
        )
        for name in ["اداری", "فروش", "انبار", "توزیع", "مالی", "فنی"]:
            Department.objects.create(company=company, name=name)
        for name in ["اداری", "فروش", "انبار", "توزیع"]:
            CostCenter.objects.create(company=company, name=name)
        for name, group in [
            ("کارشناس فروش", 8), ("سرپرست فروش", 12), ("انباردار", 6),
            ("راننده توزیع", 5), ("کارشناس اداری", 9), ("حسابدار", 11),
            ("تکنسین", 7), ("کارگر انبار", 4),
        ]:
            JobTitle.objects.create(company=company, name=name, job_group=group)
        return company

    def _create_users(self):
        users = {}
        admin, _ = User.objects.get_or_create(
            username="admin",
            defaults={
                "first_name": "مدیر", "last_name": "سیستم",
                "role": User.Role.ADMIN, "is_staff": True, "is_superuser": True,
                "job_title_label": "مدیر سیستم",
            },
        )
        admin.set_password("demo1234")
        admin.save()
        users["admin"] = admin

        ali, _ = User.objects.get_or_create(
            username="ali",
            defaults={
                "first_name": "علی", "last_name": "رضایی",
                "role": User.Role.PAYROLL, "job_title_label": "مسئول مالی",
            },
        )
        ali.set_password("demo1234")
        ali.save()
        users["ali"] = ali
        return users

    # --------------------------------------------------------- fiscal data

    def _create_fiscal_data(self, company):
        years = {}
        # ارقام نمونه — پیش از استفاده واقعی باید با بخشنامه سال تطبیق شوند
        settings_by_year = {
            1404: {
                "min_daily_wage": 2_700_000, "housing": 8_000_000, "food": 20_000_000,
                "child": 8_100_000, "seniority": 350_000,
                "brackets": [
                    (0, 180_000_000, 0, True),
                    (180_000_000, 360_000_000, "0.10", False),
                    (360_000_000, 540_000_000, "0.15", False),
                    (540_000_000, 900_000_000, "0.20", False),
                    (900_000_000, None, "0.30", False),
                ],
            },
            1405: {
                "min_daily_wage": 3_000_000, "housing": 9_000_000, "food": 22_000_000,
                "child": 9_000_000, "seniority": 400_000,
                "brackets": [
                    (0, 200_000_000, 0, True),
                    (200_000_000, 400_000_000, "0.10", False),
                    (400_000_000, 600_000_000, "0.15", False),
                    (600_000_000, 1_000_000_000, "0.20", False),
                    (1_000_000_000, None, "0.30", False),
                ],
            },
        }

        for year, conf in settings_by_year.items():
            start = jalali_to_gregorian(year, 1, 1)
            end_year, end_month = (year, 12)
            _, end = jalali_month_range(end_year, end_month)
            fiscal_year = FiscalYear.objects.create(
                company=company, year=year, start_date=start, end_date=end
            )
            LegalParameter.objects.create(
                fiscal_year=fiscal_year,
                effective_from=start,
                min_daily_wage=Decimal(conf["min_daily_wage"]),
                housing_allowance=Decimal(conf["housing"]),
                food_allowance=Decimal(conf["food"]),
                child_allowance=Decimal(conf["child"]),
                max_children=0,
                seniority_daily=Decimal(conf["seniority"]),
                shift_rates={"MORNING_EVENING": 0.10, "MORNING_NIGHT": 0.225, "ALL": 0.15},
                rounding_unit=1000,
                deduct_insurance_from_tax_base=True,
            )
            for index, (low, high, rate, is_exemption) in enumerate(conf["brackets"], start=1):
                TaxBracket.objects.create(
                    fiscal_year=fiscal_year,
                    row_order=index,
                    basis=TaxBracket.Basis.MONTHLY,
                    from_amount=Decimal(low),
                    to_amount=Decimal(high) if high else None,
                    rate=Decimal(str(rate)),
                    is_exemption=is_exemption,
                )
            years[year] = fiscal_year
        return years

    # ---------------------------------------------------------- components

    def _create_components(self, company):
        green, red, amber, grey = "#3E8E5B", "#E2231A", "#B57B14", "#8A8175"
        specs = [
            # code, name, kind, rule, seq, insurable, taxable, eid, sev, color, system
            ("BASE_SALARY", "حقوق پایه", "EARNING", "base_salary", 10, True, True, True, True, green, True),
            ("SENIORITY", "پایه سنوات", "EARNING", "seniority", 20, True, True, True, True, green, False),
            ("HOUSING", "حق مسکن", "EARNING", "housing_allowance", 30, True, True, True, False, green, False),
            ("FOOD", "بن کارگری", "EARNING", "food_allowance", 40, True, True, True, False, green, False),
            ("CHILD", "حق اولاد", "EARNING", "child_allowance", 50, True, False, False, False, amber, False),
            ("JOB_ALLOWANCE", "فوق‌العاده شغل", "EARNING", "contract_allowance", 60, True, True, True, True, green, False),
            ("OVERTIME", "اضافه‌کاری", "EARNING", "overtime", 70, True, True, False, False, green, False),
            ("NIGHT", "شب‌کاری", "EARNING", "night_work", 80, True, True, False, False, green, False),
            ("FRIDAY", "جمعه‌کاری", "EARNING", "friday_work", 90, True, True, False, False, green, False),
            ("HOLIDAY", "تعطیل‌کاری", "EARNING", "holiday_work", 100, True, True, False, False, green, False),
            ("SHIFT", "نوبت‌کاری", "EARNING", "shift_work", 110, True, True, False, False, green, False),
            ("INSURANCE_EMP", "بیمه سهم کارگر", "DEDUCTION", "insurance_employee", 200, False, False, False, False, red, True),
            ("INCOME_TAX", "مالیات بر درآمد حقوق", "DEDUCTION", "income_tax", 210, False, False, False, False, red, True),
            ("LOAN", "اقساط وام و مساعده", "DEDUCTION", "loan_installment", 220, False, False, False, False, red, False),
            ("ROUNDING_ADJ", "تعدیل گرد کردن", "DEDUCTION", "", 290, False, False, False, False, grey, True),
            ("INSURANCE_EMPLOYER", "بیمه سهم کارفرما", "EMPLOYER_COST", "insurance_employer", 300, False, False, False, False, grey, True),
            ("UNEMPLOYMENT", "بیمه بیکاری", "EMPLOYER_COST", "unemployment_insurance", 310, False, False, False, False, grey, True),
        ]

        components = {}
        for code, name, kind, rule, seq, ins, tax, eid, sev, color, system in specs:
            components[code] = SalaryComponent.objects.create(
                company=company, code=code, name=name, kind=kind,
                calc_type="ENGINE_RULE" if rule else "FIXED",
                engine_rule_key=rule, sequence=seq,
                is_insurable=ins, is_taxable=tax,
                affects_eid=eid, affects_severance=sev,
                color=color, is_system=system,
            )

        # پورسانت سه‌سطحی — فقط برای مرکز هزینه فروش، مشمول مالیات و معاف از بیمه
        sales_cc = CostCenter.objects.get(company=company, name="فروش")
        persian_levels = {1: "۱", 2: "۲", 3: "۳"}
        for level, seq in [(1, 120), (2, 130), (3, 140)]:
            component = SalaryComponent.objects.create(
                company=company,
                code=f"COMMISSION_{level}",
                name=f"پورسانت سطح {persian_levels[level]}",
                kind="EARNING",
                calc_type="MANUAL",
                sequence=seq,
                is_insurable=False,
                is_taxable=True,
                affects_eid=False,
                affects_severance=False,
                color="#E2231A",
                description="مبلغ از سیستم فروش وارد می‌شود",
            )
            ComponentScope.objects.create(
                component=component, scope_type="COST_CENTER", scope_id=str(sales_cc.pk)
            )
            components[f"COMMISSION_{level}"] = component

        return components

    # ----------------------------------------------------------- employees

    def _create_employees(self, company, count, users):
        departments = {d.name: d for d in Department.objects.filter(company=company)}
        cost_centers = {c.name: c for c in CostCenter.objects.filter(company=company)}
        job_titles = list(JobTitle.objects.filter(company=company))

        # توزیع پرسنل بین واحدها
        distribution = (
            ["فروش"] * 46 + ["انبار"] * 26 + ["توزیع"] * 30
            + ["اداری"] * 22 + ["مالی"] * 12 + ["فنی"] * 10
        )
        job_allowance = SalaryComponent.objects.get(company=company, code="JOB_ALLOWANCE")

        employees = []
        for index in range(count):
            code = 1001 + index
            dept_name = distribution[index % len(distribution)]
            cc_name = dept_name if dept_name in cost_centers else "اداری"

            is_female = index % 4 == 1
            first = random.choice(FIRST_NAMES_F if is_female else FIRST_NAMES_M)
            last = random.choice(LAST_NAMES)
            if index == 0:
                first, last = "علی", "تستی"

            hire_year = random.choice([1398, 1399, 1400, 1401, 1402, 1403])
            hire_date = jalali_to_gregorian(hire_year, random.randint(1, 12), random.randint(1, 28))
            seniority = max(1404 - hire_year, 0)

            employee = Employee.objects.create(
                company=company,
                personnel_code=str(code),
                first_name=first,
                last_name=last,
                father_name=random.choice(FIRST_NAMES_M),
                national_id=make_national_id(3200000000 + index * 7919),
                birth_date=jalali_to_gregorian(
                    random.randint(1355, 1381), random.randint(1, 12), random.randint(1, 28)
                ),
                gender="F" if is_female else "M",
                marital_status="MARRIED" if index % 3 else "SINGLE",
                insurance_number=f"{50000000 + index * 13:010d}",
                mobile=f"0912{random.randint(1000000, 9999999)}",
                hire_date=hire_date,
                status=Employee.Status.ACTIVE,
            )

            bank_name, bank_code = random.choice(BANKS)
            BankAccount.objects.create(
                employee=employee,
                bank_name=bank_name,
                bank_code=bank_code,
                iban=f"IR{bank_code}0{code:010d}{index:010d}"[:26],
                is_default=True,
            )

            if employee.marital_status == "MARRIED":
                children = random.choice([0, 1, 1, 2, 2, 3])
                for child in range(children):
                    Dependent.objects.create(
                        employee=employee,
                        relation="CHILD",
                        first_name=random.choice(FIRST_NAMES_M + FIRST_NAMES_F),
                        last_name=last,
                        birth_date=jalali_to_gregorian(
                            random.randint(1390, 1402), random.randint(1, 12), random.randint(1, 28)
                        ),
                        child_allowance_eligible=True,
                        start_date=hire_date,
                    )

            base = random.randrange(140, 310) * 1_000_000
            contract = EmploymentContract.objects.create(
                employee=employee,
                contract_number=f"C-{code}",
                contract_type="PERMANENT" if index % 7 else "TEMPORARY",
                department=departments[dept_name],
                cost_center=cost_centers[cc_name],
                job_title=random.choice(job_titles),
                effective_from=hire_date,
                base_salary=Decimal(base),
                seniority_years=seniority,
                status="ACTIVE",
            )

            # حدود یک‌سوم پرسنل فوق‌العاده شغل دارند
            if index % 3 == 0:
                ContractAllowance.objects.create(
                    contract=contract,
                    component=job_allowance,
                    amount=Decimal(random.randrange(5, 25) * 1_000_000),
                    effective_from=hire_date,
                )

            employees.append(employee)

        # حساب پرتال برای اولین پرسنل (کد ۱۰۰۱)
        first_employee = employees[0]
        portal_user = User.objects.create(
            username=first_employee.personnel_code,
            first_name=first_employee.first_name,
            last_name=first_employee.last_name,
            role=User.Role.EMPLOYEE,
            job_title_label="کارشناس فروش",
        )
        portal_user.set_password("demo1234")
        portal_user.save()
        first_employee.user = portal_user
        first_employee.save()

        return employees

    # -------------------------------------------------------------- period

    def _create_period(self, company, fiscal_year, year, month):
        start, end = jalali_month_range(year, month)
        return PayrollPeriod.objects.create(
            company=company,
            fiscal_year=fiscal_year,
            year=year,
            month=month,
            start_date=start,
            end_date=end,
            status=PayrollPeriod.Status.DRAFT,
        )

    def _create_timesheets(self, period, employees, approve_all):
        """کارکرد ماهانه. برای دوره جاری عمداً ۴ نفر تأیید نشده می‌مانند تا
        وضعیت «۱۴۲ از ۱۴۶ نفر» در داشبورد دیده شود."""
        pending = 0 if approve_all else 4
        rows = []
        for index, employee in enumerate(employees):
            contract = employee.contract_on(period.end_date)
            if contract is None:
                continue
            absence = Decimal("0")
            leave = Decimal("0")
            if index % 11 == 0:
                leave = Decimal(random.choice([1, 2, 3]))
            if index % 23 == 0:
                absence = Decimal(random.choice([1, 2]))

            approved = index < (len(employees) - pending)
            rows.append(
                Timesheet(
                    period=period,
                    employee=employee,
                    contract=contract,
                    work_days=Decimal("30") - absence - leave,
                    paid_leave_days=leave,
                    absence_days=absence,
                    overtime_hours=Decimal(random.randrange(0, 60)),
                    night_hours=Decimal(random.choice([0, 0, 0, 8, 16])),
                    friday_hours=Decimal(random.choice([0, 0, 8])),
                    status=Timesheet.Status.APPROVED if approved else Timesheet.Status.DRAFT,
                    source=Timesheet.Source.IMPORT,
                )
            )
        Timesheet.objects.bulk_create(rows)

    def _create_commissions(self, prev_period, curr_period, employees, components):
        """پورسانت فروش — ورودی دستی دوره (در واقعیت از سیستم فروش می‌آید)."""
        sales = [
            e for e in employees
            if e.contracts.first() and e.contracts.first().cost_center.name == "فروش"
        ]
        for period in (prev_period, curr_period):
            rows = []
            for employee in sales:
                for level in (1, 2, 3):
                    if random.random() < (0.9 if level == 1 else 0.4 if level == 2 else 0.15):
                        rows.append(
                            PayrollInput(
                                period=period,
                                employee=employee,
                                component=components[f"COMMISSION_{level}"],
                                amount=Decimal(random.randrange(5, 60) * 1_000_000),
                                note="ورودی نمونه — در واقعیت از سیستم فروش",
                            )
                        )
            PayrollInput.objects.bulk_create(rows)

    def _create_loans(self, employees):
        """چند وام فعال با اقساط سررسید در دوره‌های نمونه."""
        for employee in employees[::13]:
            principal = random.randrange(100, 500) * 1_000_000
            installments = random.choice([12, 18, 24])
            amount = Decimal(principal) / installments
            loan = Loan.objects.create(
                employee=employee,
                loan_type=random.choice(["LOAN", "ADVANCE"]),
                title="وام ضروری",
                principal=Decimal(principal),
                total_installments=installments,
                installment_amount=amount.quantize(Decimal("1")),
                first_year=1404,
                first_month=10,
                status="ACTIVE",
            )
            year, month = 1404, 10
            rows = []
            for number in range(1, installments + 1):
                rows.append(
                    LoanInstallment(
                        loan=loan,
                        number=number,
                        due_year=year,
                        due_month=month,
                        amount=loan.installment_amount,
                        status=LoanInstallment.Status.DUE,
                    )
                )
                month += 1
                if month > 12:
                    month, year = 1, year + 1
            LoanInstallment.objects.bulk_create(rows)
