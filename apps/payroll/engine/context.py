"""بستر محاسبه یک فیش.

همه‌ی چیزی که یک قاعده برای محاسبه لازم دارد اینجا جمع شده تا قواعد به دیتابیس
دست نزنند: قاعده‌ها توابع خالص‌اند و همین تست‌پذیرشان می‌کند.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from apps.payroll.utils import quantize_rial

ZERO = Decimal("0")


@dataclass
class LineResult:
    """خروجی یک قاعده — یک سطر فیش."""

    amount: Decimal
    base_amount: Decimal = ZERO
    quantity: Decimal = ZERO
    rate: Decimal = ZERO
    explanation: str = ""

    def rounded(self):
        self.amount = quantize_rial(self.amount)
        self.base_amount = quantize_rial(self.base_amount)
        return self


@dataclass
class PayrollContext:
    """بستر محاسبه یک پرسنل در یک دوره."""

    period: object
    employee: object
    contract: object
    timesheet: object
    params: object

    children_count: int = 0
    manual_inputs: dict = field(default_factory=dict)       # component_id -> Decimal
    contract_allowances: dict = field(default_factory=dict)  # component_id -> Decimal
    due_installments: list = field(default_factory=list)
    allocation: object = None                                # CommissionAllocation

    # نتایج تجمعی حین محاسبه
    amounts: dict = field(default_factory=dict)   # component_code -> Decimal
    gross: Decimal = ZERO
    insurable_base: Decimal = ZERO
    taxable_base: Decimal = ZERO
    total_deductions: Decimal = ZERO
    employer_cost: Decimal = ZERO

    # ---------------------------------------------------------------- زمان

    @property
    def initial_days(self) -> Decimal:
        """کارکرد اولیهٔ ماه — پیش از کسر روزهای بدون حقوق."""
        if not self.timesheet:
            return Decimal(self.employee.employed_days_in(
                self.period.start_date, self.period.end_date
            ))
        return self.timesheet.work_days

    @property
    def unpaid_days(self) -> Decimal:
        """غیبت + بیماری + مرخصی بدون حقوق."""
        if not self.timesheet:
            return ZERO
        return self.timesheet.unpaid_days

    @property
    def paid_days(self) -> Decimal:
        """روزهای مشمول پرداخت = کارکرد اولیه − روزهای بدون حقوق."""
        if not self.timesheet:
            return self.initial_days
        return self.timesheet.paid_days

    @property
    def month_days(self) -> Decimal:
        """طول ماه دوره: ۳۱ روز در شش‌ماههٔ اول، ۳۰ در شش‌ماههٔ دوم، اسفند ۲۹/۳۰.

        مخرج مزد روزانه و تسهیم مزایای ثابت است. از تقویم خودِ دوره می‌آید نه
        از عدد ثابت `LegalParameter.monthly_days` — آن فقط وقتی به کار می‌آید
        که دوره بازهٔ تاریخی نداشته باشد.
        """
        days = self.period.month_days if self.period is not None else None
        return days or self.params.monthly_days or Decimal("30")

    @property
    def day_ratio(self) -> Decimal:
        """نسبت کارکرد به ماه کامل — مبنای تسهیم مزایای ثابت."""
        if not self.month_days:
            return ZERO
        return self.paid_days / self.month_days

    # ---------------------------------------------------------------- مزد

    @property
    def uses_minimum_wage(self) -> bool:
        """آیا مبنای مزد این پرسنل «حداقل دستمزد» است؟

        مزد روزانهٔ خالیِ قرارداد (صفر) یعنی «مزد اختصاصی ندارد، از حداقل
        دستمزد همان سال استفاده کن». هر که عدد اختصاصی دارد، همان ملاک است.
        """
        return not self.contract.daily_wage

    @property
    def daily_base(self) -> Decimal:
        """مزد روزانهٔ این پرسنل — مبنای حقوق ثابت و هر قلمی که به «دستمزد فرد» بسته است.

        هر دو طرف روزانه‌اند، پس هیچ تقسیمی در کار نیست. تا پیش از این، مزد
        قرارداد ماهانه بود و بر طول همان ماه تقسیم می‌شد — یعنی یک قرارداد در
        مرداد (۳۱ روزه) و مهر (۳۰ روزه) دو مزد روزانهٔ متفاوت داشت، و حاصلِ
        تقسیم هم کسر متناوب بود. حالا عددِ ثبت‌شده همان عددی است که ضرب می‌شود.
        """
        if self.uses_minimum_wage:
            return self.params.min_daily_wage or ZERO
        return self.contract.daily_wage

    @property
    def wage_basis_label(self) -> str:
        return "حداقل دستمزد" if self.uses_minimum_wage else "دستمزد قرارداد"

    @property
    def hourly_base(self) -> Decimal:
        hours = self.params.daily_work_hours or Decimal("7.33")
        return self.daily_base / hours

    # ---------------------------------------------------------------- بیمه

    @property
    def insurance_applies(self) -> bool:
        """آیا برای این پرسنل در این دوره حق بیمه محاسبه می‌شود؟

        **تنها جای تصمیم دربارهٔ بیمه.** سه قاعدهٔ بیمه، اجرای دوره، گزارش بیمه،
        جمع بیمهٔ ماه و فایل خروجی تأمین اجتماعی همگی از همین‌جا می‌آیند —
        وگرنه یکی از پنج مسیر جا می‌ماند و مغایرت با تأمین اجتماعی همان‌جا
        ساخته می‌شود.

        دو شرط: قرارداد مشمول بیمه باشد، و خودِ پرسنل «بدون بیمه» علامت نخورده
        باشد. علتِ بدون بیمه بودن (بازنشستگی، انصراف کتبی، …) روی پرونده ثبت
        می‌شود ولی برای موتور فرقی ندارد — تصمیم یکی است.
        """
        if not getattr(self.contract, "is_insured", True):
            return False
        return not getattr(self.employee, "is_insurance_exempt", False)

    # ------------------------------------------------------------- پورسانت

    @property
    def commission_to_mission(self) -> Decimal:
        return getattr(self.allocation, "to_mission", ZERO) or ZERO

    @property
    def commission_mission_days(self) -> Decimal:
        return getattr(self.allocation, "mission_days", ZERO) or ZERO

    @property
    def commission_to_overtime(self) -> Decimal:
        return getattr(self.allocation, "to_overtime", ZERO) or ZERO

    @property
    def commission_overtime_hours(self) -> Decimal:
        return getattr(self.allocation, "overtime_hours", ZERO) or ZERO

    @property
    def commission_transferred(self) -> Decimal:
        return self.commission_to_mission + self.commission_to_overtime

    def commission_share(self, component_amount: Decimal) -> Decimal:
        """سهم این قلم پورسانت از ماندهٔ کل.

        پورسانت ممکن است چند قلم باشد (سطح ۱، ۲، ۳) و تخصیص روی جمعشان انجام
        شده است. مانده به نسبت سهم هر قلم تقسیم می‌شود تا جمع سطرها دقیقاً
        برابر ماندهٔ کل بماند و هیچ ریالی گم یا اضافه نشود.
        """
        from apps.payroll.utils import quantize_rial

        source = getattr(self.allocation, "source_amount", ZERO) or ZERO
        remaining = getattr(self.allocation, "remaining", ZERO) or ZERO
        if not source:
            return Decimal(component_amount)
        return quantize_rial(Decimal(component_amount) * remaining / source)

    # ---------------------------------------------------------------- کمکی

    def amount_of(self, code: str) -> Decimal:
        return self.amounts.get(code, ZERO)

    def register(self, component, result: LineResult):
        """ثبت نتیجه یک قلم و به‌روزرسانی مبناها.

        اینجاست که تفکیک «مبنای بیمه» و «مبنای مالیات» اتفاق می‌افتد — دو عدد
        متفاوت که هر قلم بسته به پرچم‌هایش در یکی، هر دو، یا هیچ‌کدام می‌نشیند.
        """
        from apps.payroll_config.models import SalaryComponent

        self.amounts[component.code] = result.amount

        if component.kind == SalaryComponent.Kind.EARNING:
            self.gross += result.amount
            if component.is_insurable:
                self.insurable_base += result.amount
            if component.is_taxable:
                self.taxable_base += result.amount
        elif component.kind == SalaryComponent.Kind.DEDUCTION:
            self.total_deductions += result.amount
        elif component.kind == SalaryComponent.Kind.EMPLOYER_COST:
            self.employer_cost += result.amount

    @property
    def capped_insurable(self) -> Decimal:
        """مبنای بیمه پس از اعمال سقف قانونی."""
        ceiling = self.params.insurance_ceiling
        return min(self.insurable_base, ceiling) if ceiling else self.insurable_base

    @property
    def taxable_after_insurance(self) -> Decimal:
        """درآمد مشمول مالیات — همان عددی که مالیات روی آن حساب می‌شود.

        اینجاست نه داخل قاعدهٔ مالیات، چون قلم اطلاعیِ «ماخذ مالیات» هم باید
        **همین** عدد را نشان دهد. دو جا حساب کردنش یعنی روزی که پرچم کسر بیمه
        عوض شود، عددِ نمایش‌داده‌شده با عددی که مالیات از آن درآمده فرق کند.
        """
        taxable = self.taxable_base
        if self.params.deduct_insurance_from_tax_base:
            taxable -= self.amount_of("INSURANCE_EMP")
        return taxable

    @property
    def net_payable(self) -> Decimal:
        return self.gross - self.total_deductions
