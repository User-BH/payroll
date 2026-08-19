"""اتصال اقلام ثابت به قاعده‌ای که مقدارشان را از پارامترهای سال می‌خواند.

مسئله‌ای که این دستور حل می‌کند: در نصب عملیاتی، «حق مسکن»، «وجه بن» و «پایه
سنوات» به‌صورت «مبلغ ثابت» با مبلغ صفر ساخته شده بودند، در حالی که عددشان در
پارامترهای سال ثبت شده بود. نتیجه: قاعدهٔ مبلغ ثابت با مبلغ صفر هیچ سطری تولید
نمی‌کرد و آن اقلام بی‌سروصدا از فیش غایب بودند.

یک عدد نباید دو جا زندگی کند. مقدار این اقلام جای درستش «پارامترهای سال» است،
پس خودِ قلم باید به همان قاعده وصل باشد نه به مبلغ ثابتِ خودش.

    python manage.py fix_component_wiring          # فقط گزارش می‌دهد
    python manage.py fix_component_wiring --apply  # اعمال می‌کند

دوره‌های قفل‌شده دست نمی‌خورند: فیش‌ها snapshot خودشان را دارند.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

# کد قلم → کلید قاعده‌ای که مقدارش را از پارامتر سال می‌خواند
WIRING = {
    "HOUSING": "housing_allowance",
    "FOOD": "food_allowance",
    "SENIORITY": "seniority",
}

# مبناهای محاسبه (اقلام اطلاعی). در جمع‌ها وارد نمی‌شوند و روی فیش چاپ
# نمی‌شوند؛ فقط نشان می‌دهند هر محاسبه روی چه عددی نشسته است.
# (کد، نام، کلید قاعده، ترتیب، واحد نمایش)
INFO_COMPONENTS = [
    ("INFO_PAID_DAYS", "روز کارکرد قابل پرداخت", "info_paid_days", 500, "DAY"),
    ("INFO_DAILY_WAGE", "مزد روزانه", "info_daily_wage", 510, "RIAL"),
    ("INFO_HOURLY_WAGE", "مزد ساعتی", "info_hourly_wage", 520, "RIAL"),
    ("INFO_GROSS", "جمع ناخالص", "info_gross", 530, "RIAL"),
    ("INFO_INS_BASE", "ماخذ بیمه", "info_insurance_base", 540, "RIAL"),
    ("INFO_TAX_BASE", "ماخذ مالیات", "info_tax_base", 550, "RIAL"),
    ("INFO_EMPLOYER_COST", "کل هزینه کارفرما", "info_employer_cost", 560, "RIAL"),
]


class Command(BaseCommand):
    help = "اتصال اقلام ثابتِ بی‌مبلغ به قاعدهٔ پارامتر سال"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="تغییرات را ذخیره کن")

    def handle(self, *args, **options):
        from apps.payroll.engine.rules import RULES
        from apps.payroll_config.models import SalaryComponent

        apply = options["apply"]
        planned = []

        for code, rule_key in WIRING.items():
            for component in SalaryComponent.objects.filter(code=code):
                if component.calc_type == SalaryComponent.CalcType.ENGINE_RULE:
                    continue
                # مبلغ ثابتِ ناصفر یعنی کاربر آگاهانه عددی گذاشته؛ دست نمی‌زنیم.
                if component.fixed_amount:
                    self.stdout.write(
                        f"  ↷ {component.name}: مبلغ ثابت {component.fixed_amount:,.0f} "
                        "دارد و دست‌نخورده ماند."
                    )
                    continue
                if rule_key not in RULES:
                    continue
                planned.append((component, rule_key))

        missing = []
        for company in {c.company for c in SalaryComponent.objects.all()}:
            existing = set(
                SalaryComponent.objects.filter(company=company).values_list("code", flat=True)
            )
            for code, name, rule_key, seq, unit in INFO_COMPONENTS:
                if code not in existing:
                    missing.append((company, code, name, rule_key, seq, unit))

        if not planned and not missing:
            self.stdout.write(self.style.SUCCESS("همهٔ اقلام درست وصل‌اند؛ کاری لازم نبود."))
            return

        for component, rule_key in planned:
            self.stdout.write(
                f"  {component.name} ({component.code}): "
                f"{component.get_calc_type_display()} → قاعده موتور «{rule_key}»"
            )

        for _, code, name, *_ in missing:
            self.stdout.write(f"  + قلم اطلاعی تازه: {name} ({code})")

        if not apply:
            self.stdout.write(
                self.style.WARNING("\nاین فقط گزارش بود. برای اعمال: --apply")
            )
            return

        with transaction.atomic():
            for component, rule_key in planned:
                component.calc_type = SalaryComponent.CalcType.ENGINE_RULE
                component.engine_rule_key = rule_key
                component.save(update_fields=["calc_type", "engine_rule_key"])

            for company, code, name, rule_key, seq, unit in missing:
                SalaryComponent.objects.create(
                    company=company, code=code, name=name,
                    kind=SalaryComponent.Kind.INFO,
                    calc_type=SalaryComponent.CalcType.ENGINE_RULE,
                    engine_rule_key=rule_key, sequence=seq, display_unit=unit,
                    is_insurable=False, is_taxable=False,
                    affects_eid=False, affects_severance=False,
                    print_on_payslip=False, is_system=True, color="#8A8175",
                )

        self.stdout.write(
            self.style.SUCCESS(f"\n{len(planned)} قلم وصل شد · {len(missing)} قلم اطلاعی ساخته شد.")
        )
        self.stdout.write(
            "دوره‌های باز را دوباره محاسبه کنید تا این اقلام روی فیش بنشینند. "
            "دوره‌های قفل‌شده تغییر نمی‌کنند."
        )
