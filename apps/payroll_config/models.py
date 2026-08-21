from decimal import Decimal

from django.db import models

from apps.org.models import Company


class FiscalYear(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="fiscal_years", verbose_name="شرکت"
    )
    year = models.PositiveSmallIntegerField("سال مالی (جلالی)")
    start_date = models.DateField("شروع سال")
    end_date = models.DateField("پایان سال")
    is_closed = models.BooleanField("بسته‌شده", default=False)

    class Meta:
        verbose_name = "سال مالی"
        verbose_name_plural = "سال‌های مالی"
        unique_together = [("company", "year")]
        ordering = ["-year"]

    def __str__(self):
        return f"سال مالی {self.year}"


class LegalParameter(models.Model):
    """پارامترهای قانونی هر سال.

    هیچ‌کدام از این اعداد در کد hard-code نشده‌اند: هر سال که وزارت کار نرخ‌ها را
    اعلام کند، یک رکورد جدید با effective_from ثبت می‌شود و فیش‌های قدیمی دست
    نمی‌خورند.
    """

    fiscal_year = models.ForeignKey(
        FiscalYear, on_delete=models.PROTECT, related_name="legal_parameters", verbose_name="سال مالی"
    )
    effective_from = models.DateField("شروع اعتبار")
    effective_to = models.DateField("پایان اعتبار", null=True, blank=True)

    # --- مزد و مزایای پایه
    min_daily_wage = models.DecimalField("حداقل دستمزد روزانه", max_digits=18, decimal_places=0)
    housing_allowance = models.DecimalField("حق مسکن ماهانه", max_digits=18, decimal_places=0)
    food_allowance = models.DecimalField("بن کارگری ماهانه", max_digits=18, decimal_places=0)
    child_allowance = models.DecimalField(
        "حق اولاد (هر فرزند)", max_digits=18, decimal_places=0,
        help_text="طبق قانون = ۳ × حداقل دستمزد روزانه — مبنایش حداقل دستمزد است، "
                  "نه مزد خودِ پرسنل، پس برای همه یک عدد است",
    )
    # حق تأهل قانونی نیست — سیاست شرکت است. در فایل ۱۴۰۵ مبلغی ثابت است که فقط
    # به متأهل‌ها تعلق می‌گیرد و مثل حق مسکن به نسبت روز کارکرد تسهیم می‌شود.
    # صفر یعنی شرکت چنین قلمی ندارد و سطرش اصلاً روی فیش نمی‌آید.
    marriage_allowance = models.DecimalField(
        "حق تأهل ماهانه", max_digits=18, decimal_places=0, default=Decimal("0"),
        help_text="فقط به پرسنل متأهل تعلق می‌گیرد؛ صفر یعنی این قلم را ندارید",
    )
    max_children = models.PositiveSmallIntegerField(
        "حداکثر فرزند مشمول", default=0, help_text="صفر یعنی بدون سقف"
    )
    seniority_daily = models.DecimalField("پایه سنوات روزانه", max_digits=18, decimal_places=0)

    # --- بیمه
    ins_employee_rate = models.DecimalField(
        "سهم کارگر", max_digits=7, decimal_places=4, default=Decimal("0.07")
    )
    ins_employer_rate = models.DecimalField(
        "سهم کارفرما", max_digits=7, decimal_places=4, default=Decimal("0.20")
    )
    unemployment_rate = models.DecimalField(
        "بیمه بیکاری", max_digits=7, decimal_places=4, default=Decimal("0.03")
    )
    ins_ceiling_factor = models.DecimalField(
        "ضریب سقف بیمه", max_digits=7, decimal_places=4, default=Decimal("7"),
        help_text="سقف مبنای بیمه = این ضریب × حداقل دستمزد ماهانه",
    )

    # --- ضرایب کارکرد
    overtime_factor = models.DecimalField(
        "ضریب اضافه‌کاری", max_digits=7, decimal_places=4, default=Decimal("1.4")
    )
    night_factor = models.DecimalField(
        "ضریب شب‌کاری", max_digits=7, decimal_places=4, default=Decimal("0.35")
    )
    friday_factor = models.DecimalField(
        "ضریب جمعه‌کاری", max_digits=7, decimal_places=4, default=Decimal("0.4")
    )
    holiday_factor = models.DecimalField(
        "ضریب تعطیل‌کاری", max_digits=7, decimal_places=4, default=Decimal("1.4")
    )
    shift_rates = models.JSONField(
        "نرخ نوبت‌کاری", default=dict, blank=True,
        help_text='مثال: {"MORNING_EVENING": 0.10, "MORNING_NIGHT": 0.225, "ALL": 0.15}',
    )

    # --- مبناهای زمانی
    monthly_days = models.DecimalField("روز کارکرد ماه", max_digits=5, decimal_places=2, default=Decimal("30"))
    leave_day_minutes = models.PositiveSmallIntegerField(
        "طول یک روز مرخصی (دقیقه)", default=440,
        help_text="۴۴۰ دقیقه = ۷ ساعت و ۲۰ دقیقه — مطابق فیش فعلی شرکت",
    )
    daily_work_hours = models.DecimalField(
        "ساعات کار روزانه", max_digits=5, decimal_places=2, default=Decimal("7.33")
    )

    rounding_unit = models.PositiveIntegerField(
        "واحد گرد کردن (ریال)", default=1,
        help_text="۱ یعنی بدون گرد کردن (توصیه‌شده). مقدار بزرگ‌تر یک سطر «تعدیل "
                  "گرد کردن» به فیش اضافه می‌کند که توضیحش برای پرسنل دشوار است.",
    )
    deduct_insurance_from_tax_base = models.BooleanField(
        "کسر بیمه سهم کارگر از درآمد مشمول مالیات",
        default=True,
        help_text="این تفسیر باید با حسابدار شرکت تأیید شود — روی مبلغ مالیات اثر مستقیم دارد",
    )

    class Meta:
        verbose_name = "پارامتر قانونی"
        verbose_name_plural = "پارامترهای قانونی"
        ordering = ["-effective_from"]

    def __str__(self):
        return f"پارامترهای {self.fiscal_year.year}"

    @property
    def min_monthly_wage(self) -> Decimal:
        return self.min_daily_wage * self.monthly_days

    @property
    def insurance_ceiling(self) -> Decimal:
        return self.min_monthly_wage * self.ins_ceiling_factor

    def as_snapshot(self) -> dict:
        """تصویر پارامترها برای ذخیره در خود فیش."""
        fields = [
            "min_daily_wage", "housing_allowance", "food_allowance", "child_allowance",
            "marriage_allowance", "seniority_daily", "ins_employee_rate", "ins_employer_rate", "unemployment_rate",
            "ins_ceiling_factor", "overtime_factor", "night_factor", "friday_factor",
            "holiday_factor", "monthly_days", "daily_work_hours", "rounding_unit",
        ]
        data = {name: str(getattr(self, name)) for name in fields}
        data["shift_rates"] = self.shift_rates
        data["insurance_ceiling"] = str(self.insurance_ceiling)
        return data


class TaxBracket(models.Model):
    """پلکان مالیات حقوق.

    مبنا (ماهانه/سالانه) صریح ذخیره می‌شود چون قانون بودجه هر سال ممکن است آن را
    تغییر دهد و حدس زدنش منشأ خطاست.
    """

    class Basis(models.TextChoices):
        MONTHLY = "MONTHLY", "ماهانه"
        ANNUAL = "ANNUAL", "سالانه"

    fiscal_year = models.ForeignKey(
        FiscalYear, on_delete=models.PROTECT, related_name="tax_brackets", verbose_name="سال مالی"
    )
    row_order = models.PositiveSmallIntegerField("ترتیب پله")
    basis = models.CharField("مبنا", max_length=8, choices=Basis.choices, default=Basis.MONTHLY)
    from_amount = models.DecimalField("از مبلغ", max_digits=18, decimal_places=0)
    to_amount = models.DecimalField(
        "تا مبلغ", max_digits=18, decimal_places=0, null=True, blank=True,
        help_text="خالی یعنی بی‌نهایت",
    )
    rate = models.DecimalField("نرخ", max_digits=7, decimal_places=4)
    is_exemption = models.BooleanField("ردیف معافیت", default=False)

    class Meta:
        verbose_name = "پله مالیاتی"
        verbose_name_plural = "پلکان مالیات"
        ordering = ["fiscal_year", "row_order"]
        unique_together = [("fiscal_year", "row_order")]

    def __str__(self):
        ceiling = f"{self.to_amount:,.0f}" if self.to_amount else "به بالا"
        return f"{self.from_amount:,.0f} تا {ceiling} — {self.rate * 100:.0f}٪"


class SalaryComponent(models.Model):
    """قلم حقوقی.

    منطق محاسبه اینجا نیست — در کد است. این مدل فقط می‌گوید کدام قاعده، با چه
    ضریبی، با چه ترتیبی، و آیا مشمول بیمه و مالیات هست یا نه.
    """

    class Kind(models.TextChoices):
        EARNING = "EARNING", "مزایا"
        DEDUCTION = "DEDUCTION", "کسور"
        EMPLOYER_COST = "EMPLOYER_COST", "هزینه کارفرما"
        INFO = "INFO", "اطلاعی"

    class CalcType(models.TextChoices):
        ENGINE_RULE = "ENGINE_RULE", "قاعده موتور"
        PARAMETRIC = "PARAMETRIC", "قاعده پارامتری (بدون کدنویسی)"
        FIXED = "FIXED", "مبلغ ثابت"
        PERCENTAGE = "PERCENTAGE", "درصدی از قلم دیگر"
        MANUAL = "MANUAL", "ورود دستی در هر دوره"

    class BaseSource(models.TextChoices):
        """مبنای قاعدهٔ پارامتری — عددی که در مقدار و ضریب ضرب می‌شود.

        چهار مبنا، چون بند ۳ سند همین چهار تا را می‌خواهد و هر کدام معنای
        روشنی روی فیش دارند. زبان فرمولِ باز عمداً ساخته نشد: عبارتی که کاربر
        می‌نویسد نه تست می‌شود نه ممیزی، و اشتباهش تا فیش پنهان می‌ماند.
        """

        MIN_WAGE = "MIN_WAGE", "حداقل دستمزد روزانه سال"
        PERSON_WAGE = "PERSON_WAGE", "مزد روزانه خود پرسنل"
        FIXED = "FIXED", "مبلغ ثابت"
        COMPONENT = "COMPONENT", "مبلغ یک قلم دیگر"

    class QuantitySource(models.TextChoices):
        """مقدار قاعدهٔ پارامتری."""

        PAID_DAYS = "PAID_DAYS", "روز کارکرد قابل پرداخت"
        DAY_RATIO = "DAY_RATIO", "به نسبت کارکرد ماه"
        TIMESHEET_ITEM = "TIMESHEET_ITEM", "یک قلم از جدول کارکرد"
        ONE = "ONE", "ثابت (بدون ضرب در کارکرد)"

    class DisplayUnit(models.TextChoices):
        """واحد نمایش سطر در فیش.

        غیبت، بیماری و مرخصی بدون حقوق مبلغ ریالی ندارند — اثرشان قبلاً با کم
        شدن از روز کارکرد اعمال شده و درج دوبارهٔ مبلغ، کسر مضاعف است. پس فقط
        تعداد روزشان روی فیش می‌آید. این رفتار باید دادهٔ قلم باشد، نه شرطِ
        کدنویسی‌شده روی کد قلم.
        """

        RIAL = "RIAL", "ریال"
        DAY = "DAY", "روز"
        HOUR = "HOUR", "ساعت"

    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="salary_components", verbose_name="شرکت"
    )
    code = models.CharField("کد", max_length=40)
    name = models.CharField("نام", max_length=80)
    kind = models.CharField("نوع", max_length=16, choices=Kind.choices, default=Kind.EARNING)
    calc_type = models.CharField(
        "نحوه محاسبه", max_length=12, choices=CalcType.choices, default=CalcType.ENGINE_RULE
    )
    engine_rule_key = models.CharField(
        "کلید قاعده", max_length=40, blank=True,
        help_text="نام قاعده ثبت‌شده در موتور محاسبه (apps/payroll/engine/rules.py)",
    )
    base_component = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="derived_components", verbose_name="قلم مبنا",
    )
    base_source = models.CharField(
        "مبنای محاسبه", max_length=12, choices=BaseSource.choices, blank=True,
        help_text="فقط برای قاعده پارامتری",
    )
    quantity_source = models.CharField(
        "مقدار", max_length=16, choices=QuantitySource.choices, blank=True,
        help_text="فقط برای قاعده پارامتری",
    )
    timesheet_item = models.ForeignKey(
        "attendance.TimesheetItem", on_delete=models.PROTECT, null=True, blank=True,
        related_name="components", verbose_name="قلم کارکرد",
        help_text="وقتی مقدار از جدول کارکرد می‌آید — مثل ساعت جمعه‌کاری",
    )
    rate = models.DecimalField("نرخ / ضریب", max_digits=9, decimal_places=4, default=Decimal("0"))
    fixed_amount = models.DecimalField(
        "مبلغ ثابت", max_digits=18, decimal_places=0, default=Decimal("0")
    )

    is_commission = models.BooleanField(
        "قلم پورسانت", default=False,
        help_text="مبلغ این اقلام وارد استخر تخصیص می‌شود و می‌تواند به حق "
                  "مأموریت یا اضافه‌کاری منتقل شود",
    )

    display_unit = models.CharField(
        "واحد نمایش در فیش", max_length=6,
        choices=DisplayUnit.choices, default=DisplayUnit.RIAL,
        help_text="«روز» یعنی در فیش فقط تعداد روز چاپ می‌شود و مبلغ ریالی ندارد",
    )

    is_insurable = models.BooleanField("مشمول بیمه", default=True)
    is_taxable = models.BooleanField("مشمول مالیات", default=True)
    affects_eid = models.BooleanField("در محاسبه عیدی لحاظ شود", default=True)
    affects_severance = models.BooleanField("در محاسبه سنوات لحاظ شود", default=True)

    sequence = models.PositiveSmallIntegerField("ترتیب محاسبه", default=100)
    gl_account = models.CharField("کد حساب دفتر کل", max_length=30, blank=True)
    color = models.CharField("رنگ نمایش", max_length=9, default="#3E8E5B")

    print_on_payslip = models.BooleanField("چاپ در فیش", default=True)
    is_system = models.BooleanField(
        "سیستمی", default=False, help_text="اقلام سیستمی قابل حذف نیستند"
    )
    is_active = models.BooleanField("فعال", default=True)
    description = models.CharField("توضیح", max_length=160, blank=True)

    class Meta:
        verbose_name = "قلم حقوقی"
        verbose_name_plural = "اقلام حقوقی"
        unique_together = [("company", "code")]
        ordering = ["sequence", "id"]

    def __str__(self):
        return self.name

    @property
    def tag_label(self):
        """برچسبی که در پنل اقلام نمایش داده می‌شود."""
        if self.kind == self.Kind.DEDUCTION:
            return "کسر از حقوق"
        if self.kind == self.Kind.EMPLOYER_COST:
            return "هزینه کارفرما"
        if self.is_insurable and self.is_taxable:
            return "مشمول بیمه و مالیات"
        if self.is_taxable:
            return "مشمول مالیات، معاف از بیمه"
        if self.is_insurable:
            return "مشمول بیمه، معاف از مالیات"
        return "معاف از بیمه و مالیات"

    @property
    def formula_label(self) -> str:
        """فرمول قلم به زبان آدم — همان چیزی که روی فیش هم توضیح داده می‌شود."""
        from apps.payroll.utils import fa_money, fa_number

        if self.calc_type != self.CalcType.PARAMETRIC:
            return ""
        if self.base_source == self.BaseSource.FIXED:
            base = f"{fa_money(self.fixed_amount)} ریال"
        elif self.base_source == self.BaseSource.COMPONENT:
            base = self.base_component.name if self.base_component_id else "قلم مبنا"
        else:
            base = self.get_base_source_display()
        parts = [base]
        if self.quantity_source == self.QuantitySource.PAID_DAYS:
            parts.append("× روز کارکرد")
        elif self.quantity_source == self.QuantitySource.DAY_RATIO:
            parts.append("× کارکرد ÷ روز ماه")
        elif self.quantity_source == self.QuantitySource.TIMESHEET_ITEM:
            label = self.timesheet_item.name if self.timesheet_item_id else "قلم کارکرد"
            unit = self.timesheet_item.unit_label if self.timesheet_item_id else ""
            parts.append(f"× {label}" + (f" ({unit})" if unit else ""))
        if self.rate and self.rate != 1:
            parts.append(f"× {fa_number(self.rate, 4)}")
        return " ".join(parts)

    def applies_to(self, contract) -> bool:
        """آیا این قلم به قرارداد داده‌شده تعلق می‌گیرد؟"""
        scopes = list(self.scopes.all())
        if not scopes:
            return True
        for scope in scopes:
            if scope.matches(contract):
                return True
        return False


class ComponentScope(models.Model):
    """دامنه شمول یک قلم حقوقی.

    بدون این جدول باید برای هر واحد اقلام تکراری ساخت. مثال واقعی: پورسانت
    سه‌سطحی فقط به مرکز هزینه «فروش» تعلق می‌گیرد، نه به انبار.
    """

    class ScopeType(models.TextChoices):
        ALL = "ALL", "همه پرسنل"
        DEPARTMENT = "DEPARTMENT", "واحد سازمانی"
        COST_CENTER = "COST_CENTER", "مرکز هزینه"
        JOB_TITLE = "JOB_TITLE", "پست سازمانی"
        CONTRACT_TYPE = "CONTRACT_TYPE", "نوع قرارداد"
        EMPLOYEE = "EMPLOYEE", "پرسنل مشخص"

    component = models.ForeignKey(
        SalaryComponent, on_delete=models.CASCADE, related_name="scopes", verbose_name="قلم حقوقی"
    )
    scope_type = models.CharField("نوع دامنه", max_length=16, choices=ScopeType.choices)
    scope_id = models.CharField(
        "شناسه مقصد", max_length=40, blank=True,
        help_text="شناسه واحد/مرکز هزینه/پست، یا مقدار نوع قرارداد",
    )

    class Meta:
        verbose_name = "دامنه شمول"
        verbose_name_plural = "دامنه‌های شمول"

    def __str__(self):
        return f"{self.component} → {self.get_scope_type_display()}"

    def matches(self, contract) -> bool:
        kind = self.scope_type
        if kind == self.ScopeType.ALL:
            return True
        if kind == self.ScopeType.DEPARTMENT:
            return str(contract.department_id) == self.scope_id
        if kind == self.ScopeType.COST_CENTER:
            return str(contract.cost_center_id) == self.scope_id
        if kind == self.ScopeType.JOB_TITLE:
            return str(contract.job_title_id) == self.scope_id
        if kind == self.ScopeType.CONTRACT_TYPE:
            return contract.contract_type == self.scope_id
        if kind == self.ScopeType.EMPLOYEE:
            return str(contract.employee_id) == self.scope_id
        return False
