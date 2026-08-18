"""راه‌اندازی عملیاتی — بدون هیچ داده ساختگی.

    python manage.py setup_operational

شرکت، ساختار سازمانی، سال مالی ۱۴۰۵، پلکان مالیات و اقلام حقوقی را دقیقاً
مطابق فیش‌های واقعی شرکت می‌سازد. هیچ پرسنل نمونه‌ای ساخته نمی‌شود؛ پرسنل از
طریق سامانه یا ورود اکسل وارد می‌شوند.

تفاوتش با seed_demo این است که seed_demo برای نمایش است و داده ساختگی می‌سازد.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.attendance.leave import DEFAULT_DAY_MINUTES
from apps.org.models import Company, CostCenter, Department, JobTitle
from apps.payroll.utils import jalali_to_gregorian, jalali_month_range
from apps.payroll_config.models import (
    ComponentScope,
    FiscalYear,
    LegalParameter,
    SalaryComponent,
    TaxBracket,
)

User = get_user_model()

MT = 10_000_000  # یک میلیون تومان = ده میلیون ریال

# پلکان مالیات حقوق ۱۴۰۵ — ماهانه، به ریال
TAX_BRACKETS_1405 = [
    (0,      40 * MT,  "0.00", True),   # تا ۴۰ میلیون تومان — معاف
    (40 * MT,  80 * MT,  "0.10", False),
    (80 * MT,  100 * MT, "0.15", False),
    (100 * MT, 120 * MT, "0.20", False),
    (120 * MT, 140 * MT, "0.25", False),
    (140 * MT, None,     "0.30", False),
]

DEPARTMENTS = ["اداری و مالی", "فروش", "توزیع", "انبار", "پشتیبانی و فنی"]
COST_CENTERS = ["اداری و مالی", "فروش", "توزیع", "انبار", "پشتیبانی و فنی"]
JOB_TITLES = [
    "کارگزین", "حسابدار", "مسئول دفتر", "کارشناس اداری",
    "بازاریاب", "سرپرست فروش", "ویزیتور",
    "راننده", "کمک راننده",
    "انباردار", "کارگر انبار",
    "تکنسین", "نگهبان",
]

GREEN, RED, AMBER, GREY = "#3E8E5B", "#E2231A", "#B57B14", "#8A8175"

# (کد، نام، نوع، قاعده، ترتیب، مشمول‌بیمه، مشمول‌مالیات، عیدی، سنوات، رنگ، سیستمی)
#
# مشمولیت بیمه و مالیات از سه فیش واقعی تیر ۱۴۰۵ استخراج و ریال‌به‌ریال تأیید شد:
#     مبنای بیمه   = جمع پرداختی‌ها − حق ماموریت − حق اولاد
#     مبنای مالیات = جمع پرداختی‌ها − حق ماموریت
COMPONENTS = [
    # ---------- پرداختی‌ها
    ("BASE_SALARY",  "حقوق ثابت",       "EARNING", "base_salary",     10,  True,  True,  True,  True,  GREEN, True),
    ("SENIORITY",    "پایه سنوات",      "EARNING", "fixed",           20,  True,  True,  True,  True,  GREEN, False),
    ("HOUSING",      "حق مسکن",         "EARNING", "fixed",           30,  True,  True,  True,  False, GREEN, False),
    ("CHILD",        "حق اولاد",        "EARNING", "child_allowance", 40,  False, True,  False, False, AMBER, False),
    ("MARRIAGE",     "حق تاهل",         "EARNING", "fixed",           50,  True,  True,  False, False, GREEN, False),
    ("FOOD",         "وجه بن",          "EARNING", "fixed",           60,  True,  True,  True,  False, GREEN, False),
    ("OVERTIME",     "اضافه کار",       "EARNING", "overtime",        70,  True,  True,  False, False, GREEN, False),
    ("MISSION",      "حق ماموریت",      "EARNING", "mission_allowance",          80,  False, False, False, False, AMBER, False),
    ("PREV_CLAIM",   "طلب ماه قبل",     "EARNING", "manual",          90,  True,  True,  False, False, GREEN, False),
    ("LEAVE_PAY",    "وجه مرخصی",       "EARNING", "manual",          100, True,  True,  False, False, GREEN, False),
    # هزینه تلفن مشمول بیمه است — از فیش تیر ۱۴۰۵ آقای سعادتی تأیید شد:
    # بدون احتساب آن، بیمه ۱۵٬۷۴۳٬۵۷۷ می‌شد نه ۱۵٬۸۱۳٬۵۷۷ که در فیش آمده.
    ("PHONE",        "هزینه تلفن",      "EARNING", "manual",          110, True,  True,  False, False, GREEN, False),
    ("DIFF",         "مابه التفاوت",    "EARNING", "manual",          120, True,  True,  False, False, GREEN, False),
    # ---------- کسورات
    ("ADVANCE",      "علی الحساب واریزی", "DEDUCTION", "manual",           200, False, False, False, False, RED, False),
    ("LOAN",         "وام ضروری",         "DEDUCTION", "loan_installment", 210, False, False, False, False, RED, False),
    ("INSURANCE_EMP", "حق بیمه",          "DEDUCTION", "insurance_employee", 220, False, False, False, False, RED, True),
    ("INCOME_TAX",   "مالیات",            "DEDUCTION", "income_tax",       230, False, False, False, False, RED, True),
    ("GOODS",        "خرید کالا",         "DEDUCTION", "manual",           240, False, False, False, False, RED, False),
    ("PREV_DEBT",    "بدهی ماه قبل",      "DEDUCTION", "manual",           250, False, False, False, False, RED, False),
    ("OTHER_DEBT",   "سایر بدهی",         "DEDUCTION", "manual",           260, False, False, False, False, RED, False),
    ("SUPP_INS",     "بیمه تکمیلی",       "DEDUCTION", "manual",           270, False, False, False, False, RED, False),
    ("MEDICAL",      "آزمایش و طب کار",   "DEDUCTION", "manual",           280, False, False, False, False, RED, False),
    ("LATE",         "کسر کار و تاخیر ورود", "DEDUCTION", "manual",        290, False, False, False, False, RED, False),
    ("ABSENCE_DED",  "غیبت",              "DEDUCTION", "absence_days",           300, False, False, False, False, RED, False),
    ("UNPAID_LEAVE", "مرخصی بدون حقوق",   "DEDUCTION", "unpaid_leave_days",           310, False, False, False, False, RED, False),
    ("SICK",         "بیماری",            "DEDUCTION", "sick_days",           320, False, False, False, False, RED, False),
    ("ROUNDING_ADJ", "تعدیل گرد کردن",    "DEDUCTION", "",                 390, False, False, False, False, GREY, True),
    # ---------- هزینه کارفرما
    ("INSURANCE_EMPLOYER", "بیمه سهم کارفرما", "EMPLOYER_COST", "insurance_employer",     400, False, False, False, False, GREY, True),
    ("UNEMPLOYMENT",       "بیمه بیکاری",      "EMPLOYER_COST", "unemployment_insurance", 410, False, False, False, False, GREY, True),
]

# اقلامی که فقط به یک مرکز هزینه یا سمت تعلق می‌گیرند
SCOPED = [
    ("COMM_1", "پورسانت یک",         130, "COST_CENTER", "فروش"),
    ("COMM_2", "پورسانت دو (دورتو)", 140, "COST_CENTER", "فروش"),
    ("COMM_3", "پورسانت سه",         150, "COST_CENTER", "فروش"),
]
# اقلامی که روی فیش فقط تعداد روز نشان می‌دهند، نه مبلغ ریالی: اثر مالی‌شان
# قبلاً با کم شدن از روز کارکرد اعمال شده و مبلغ ریالی یعنی کسر مضاعف.
DAY_UNIT_CODES = {"ABSENCE_DED", "SICK", "UNPAID_LEAVE"}

DRIVER_ONLY = ("VEHICLE_FINE", "جرائم و خلافی خودرو", 330, "راننده")


class Command(BaseCommand):
    help = "راه‌اندازی عملیاتی: شرکت، ساختار سازمانی، سال مالی ۱۴۰۵ و اقلام حقوقی"

    def add_arguments(self, parser):
        parser.add_argument("--company", default="تامین کالا باختر")
        parser.add_argument("--year", type=int, default=1405)

    @transaction.atomic
    def handle(self, *args, **options):
        year = options["year"]

        if Company.objects.exists():
            self.stdout.write(self.style.ERROR(
                "قبلاً شرکتی تعریف شده است. این دستور فقط روی دیتابیس خالی اجرا می‌شود.\n"
                "برای شروع از صفر: python manage.py flush   سپس دوباره این دستور."
            ))
            return

        company = Company.objects.create(name=options["company"])
        for name in DEPARTMENTS:
            Department.objects.create(company=company, name=name)
        for name in COST_CENTERS:
            CostCenter.objects.create(company=company, name=name)
        for name in JOB_TITLES:
            JobTitle.objects.create(company=company, name=name)

        fiscal_year = self._fiscal_year(company, year)
        self._components(company)

        self.stdout.write(self.style.SUCCESS(f"\n راه‌اندازی سال {year} انجام شد.\n"))
        self.stdout.write(
            f"  واحد سازمانی : {Department.objects.count()}\n"
            f"  مرکز هزینه   : {CostCenter.objects.count()}\n"
            f"  پست سازمانی  : {JobTitle.objects.count()}\n"
            f"  اقلام حقوقی  : {SalaryComponent.objects.count()}\n"
            f"  پله مالیاتی  : {TaxBracket.objects.filter(fiscal_year=fiscal_year).count()}\n"
        )
        self.stdout.write(self.style.WARNING(
            "  قدم‌های بعدی:\n"
            "   ۱) کاربر مدیر بسازید:  python manage.py createsuperuser\n"
            "   ۲) در «تنظیمات سال مالی» مبالغ قانونی را با بخشنامه ۱۴۰۵ تطبیق دهید\n"
            "   ۳) پرسنل را از منوی «پرسنل» وارد یا از اکسل بارگذاری کنید\n"
            "   ۴) دوره مرداد ۱۴۰۵ را بسازید و کارکرد را ثبت کنید\n"
        ))

    def _fiscal_year(self, company, year):
        start = jalali_to_gregorian(year, 1, 1)
        _, end = jalali_month_range(year, 12)
        fiscal_year = FiscalYear.objects.create(
            company=company, year=year, start_date=start, end_date=end
        )

        # مقادیری که از فیش‌های واقعی تیر ۱۴۰۵ خوانده شدند. بقیه باید در صفحه
        # «تنظیمات سال مالی» با بخشنامه سال تطبیق داده شوند.
        LegalParameter.objects.create(
            fiscal_year=fiscal_year,
            effective_from=start,
            min_daily_wage=Decimal("0"),
            housing_allowance=Decimal("3000000"),
            food_allowance=Decimal("2200000"),
            child_allowance=Decimal("0"),
            max_children=0,
            seniority_daily=Decimal("0"),
            ins_employee_rate=Decimal("0.07"),
            ins_employer_rate=Decimal("0.20"),
            unemployment_rate=Decimal("0.03"),
            ins_ceiling_factor=Decimal("7"),
            overtime_factor=Decimal("1.4"),
            night_factor=Decimal("0.35"),
            friday_factor=Decimal("0.4"),
            holiday_factor=Decimal("1.4"),
            shift_rates={},
            monthly_days=Decimal("30"),
            daily_work_hours=Decimal("7.33"),
            leave_day_minutes=DEFAULT_DAY_MINUTES,
            # بدون گرد کردن. در فیش‌های واقعی شرکت خالص پرداختی رقم دقیق ریالی
            # است (۲۲۳٬۲۲۰٬۲۱۲ و ۲۷۰٬۶۲۴٬۰۰۶ و …) و هیچ‌کدام رُند نیستند.
            # ضمناً توضیح «۳۶۹ ریال تعدیل شد» برای پرسنل قابل دفاع نیست و در
            # اداره کار هم محل ایراد است.
            rounding_unit=1,
            # از فیش‌های واقعی: بیمه سهم کارگر از مبنای مالیات کسر نمی‌شود
            deduct_insurance_from_tax_base=False,
        )

        for index, (low, high, rate, exempt) in enumerate(TAX_BRACKETS_1405, start=1):
            TaxBracket.objects.create(
                fiscal_year=fiscal_year,
                row_order=index,
                basis=TaxBracket.Basis.MONTHLY,
                from_amount=Decimal(low),
                to_amount=Decimal(high) if high else None,
                rate=Decimal(rate),
                is_exemption=exempt,
            )
        return fiscal_year

    def _components(self, company):
        rule_map = {"fixed": "", "manual": ""}
        for code, name, kind, rule, seq, ins, tax, eid, sev, color, system in COMPONENTS:
            if rule == "fixed":
                calc_type, engine_key = "FIXED", ""
            elif rule == "manual":
                calc_type, engine_key = "MANUAL", ""
            elif rule == "":
                calc_type, engine_key = "FIXED", ""
            else:
                calc_type, engine_key = "ENGINE_RULE", rule
            SalaryComponent.objects.create(
                company=company, code=code, name=name, kind=kind,
                calc_type=calc_type, engine_rule_key=engine_key, sequence=seq,
                display_unit="DAY" if code in DAY_UNIT_CODES else "RIAL",
                is_insurable=ins, is_taxable=tax,
                affects_eid=eid, affects_severance=sev,
                color=color, is_system=system,
            )

        sales = CostCenter.objects.get(company=company, name="فروش")
        for code, name, seq, scope_type, target in SCOPED:
            component = SalaryComponent.objects.create(
                company=company, code=code, name=name, kind="EARNING",
                calc_type="MANUAL", sequence=seq, is_commission=True,
                is_insurable=True, is_taxable=True,
                affects_eid=False, affects_severance=False, color=RED,
                description="مبلغ در هر دوره وارد می‌شود",
            )
            ComponentScope.objects.create(
                component=component, scope_type=scope_type, scope_id=str(sales.pk)
            )

        code, name, seq, job_name = DRIVER_ONLY
        driver = JobTitle.objects.get(company=company, name=job_name)
        fine = SalaryComponent.objects.create(
            company=company, code=code, name=name, kind="DEDUCTION",
            calc_type="MANUAL", sequence=seq,
            is_insurable=False, is_taxable=False,
            affects_eid=False, affects_severance=False, color=RED,
            description="فقط برای رانندگان",
        )
        ComponentScope.objects.create(
            component=fine, scope_type="JOB_TITLE", scope_id=str(driver.pk)
        )
