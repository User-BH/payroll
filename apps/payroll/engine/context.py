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

    # نتایج تجمعی حین محاسبه
    amounts: dict = field(default_factory=dict)   # component_code -> Decimal
    gross: Decimal = ZERO
    insurable_base: Decimal = ZERO
    taxable_base: Decimal = ZERO
    total_deductions: Decimal = ZERO

    # ---------------------------------------------------------------- زمان

    @property
    def paid_days(self) -> Decimal:
        """روزهای مشمول پرداخت."""
        if not self.timesheet:
            return self.month_days
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
    def daily_base(self) -> Decimal:
        return self.contract.base_salary / self.month_days

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

        دو شرط: قرارداد مشمول بیمه باشد، و پرسنل بازنشسته نباشد.
        """
        if not getattr(self.contract, "is_insured", True):
            return False
        return not getattr(self.employee, "is_retired", False)

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

    @property
    def capped_insurable(self) -> Decimal:
        """مبنای بیمه پس از اعمال سقف قانونی."""
        ceiling = self.params.insurance_ceiling
        return min(self.insurable_base, ceiling) if ceiling else self.insurable_base

    @property
    def net_payable(self) -> Decimal:
        return self.gross - self.total_deductions
