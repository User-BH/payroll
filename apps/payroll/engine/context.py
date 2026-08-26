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
    # اقلامی که دامنه شمولشان به این قرارداد می‌خورد. `compute_lines` پرش
    # می‌کند. زنجیرهٔ مازاد لازمش دارد تا بفهمد چه چیزهایی وارد استخر می‌شوند
    # — بدون این، هر قاعده باید خودش دیتابیس را می‌خواند.
    applicable_components: list = field(default_factory=list)
    _surplus: object = None

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
        """نسبت کارکرد به ماه کامل — مبنای تسهیم مزایای ثابت.

        سه روش، چون بین شرکت‌ها فرق می‌کند:

          روزهای ماه کاری : کارکرد قابل پرداخت ÷ روزهای ماه کاری  ← توصیه‌شده
          مخرج ثابت ۳۱    : کارکرد ۳۰ یا ۳۱ → کامل، وگرنه کارکرد ÷ ۳۱
          ماهِ ۳۰          : ماهِ کامل → کامل، ناقص → کارکرد ÷ ۳۰

        **روش اول همان چیزی است که باید باشد**، چون «روزهای ماه کاری» خودش
        هر دوره تعیین می‌شود: در اسفندِ ۲۹ روزه مخرج ۲۹ است، پس کسی که کل
        ماه را کار کرده ۲۹ ÷ ۲۹ می‌گیرد و مزایای ثابتش **کامل** است. این
        اقلام فقط وقتی کم می‌شوند که غیبت یا بیماری یا مرخصی بدون حقوق باشد
        — یعنی وقتی کارکرد قابل پرداخت از کارکرد اولیه کمتر شود.

        مخرج ثابت ۳۱ عیناً فرمول فایل ۱۴۰۵ است و همین‌جا می‌لنگد: در اسفند،
        کسی که تمام ماه را کار کرده ۲۹ ÷ ۳۱ می‌گیرد، یعنی بابت ماهی که
        تمامش را کار کرده نزدیک ۵ میلیون ریال کمتر. روی داده‌های تیر و مرداد
        این دو روش **هیچ اختلافی ندارند** (هیچ‌کس دقیقاً ۳۰ روز کارکرد
        ندارد)، پس تفاوتشان فقط از اسفند و ماه‌های ۳۰ روزه شروع می‌شود.
        """
        if not self.month_days:
            return ZERO
        mode = getattr(self.params, "allowance_proration", "MONTH_DAYS")

        if mode == "FIXED_31":
            if self.paid_days >= Decimal("30"):
                return Decimal("1")
            return self.paid_days / Decimal("31")

        if mode == "MONTH_30":
            # رویهٔ رایج: «ماهِ کاری ۳۰ روز است».
            #
            # ماهِ کامل — چه ۲۹ روزه باشد چه ۳۱ روزه — مزایای ثابتش کامل
            # پرداخت می‌شود؛ همان چیزی که قانون کار حقوق ماهانه را با آن
            # تعریف می‌کند (مزد روزانه × ۳۰). ماهِ ناقص بر ۳۰ تقسیم می‌شود.
            #
            # سقف لازم است: در ماه ۳۱ روزه، ۳۱ ÷ ۳۰ می‌شد ۱۰۳٪ و مزایای ثابت
            # بیشتر از مبلغ ماهانه‌اش پرداخت می‌شد.
            if self.paid_days >= self.month_days:
                return Decimal("1")
            return min(self.paid_days / Decimal("30"), Decimal("1"))

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
    def overtime_hourly_base(self) -> Decimal:
        """مبنای هر ساعت اضافه‌کاری — پیش از اعمال ضریب.

        دو روش، چون بین شرکت‌ها فرق می‌کند و بک‌تست تیر ۱۴۰۵ نشان داد فایل
        واقعی شرکت روش دوم را به کار می‌برد:

          مزد ساعتی      : مزد روزانه ÷ ساعات کار روزانه
          مبنای ماهانه   : (مزد روزانه × ۳۰ + پایه سنوات روزانه × کارکرد) ÷ ۲۲۰
          مبنای ماهانه۳۰ : (مزد روزانه + پایه سنوات روزانه) × ۳۰ ÷ ۲۲۰

        عدد ۳۰ عمدی است و طول واقعی ماه نیست: قرارداد کار حقوق ماهانه را
        «مزد روزانه × ۳۰» تعریف می‌کند و فایل شرکت هم همین را مبنای
        اضافه‌کاری گرفته.

        تفاوت دو حالت ماهانه فقط در پایهٔ سنوات است — یکی در کارکرد واقعی ضرب
        می‌کند، دیگری در ۳۰ — و در ماه‌های ۳۱ روزه به‌اندازهٔ یک روز پایه سنوات
        از هم فاصله می‌گیرند. هر دو در فایل‌های واقعی دیده شده‌اند، پس هیچ‌کدام
        سخت‌کد نشد: فایل تیر ۱۴۰۵ («حقوق دستمزد تیر») در هر ۶۷ سطر حالت سوم را
        به کار می‌برد، و فایل ۱۴۰۵ قبلی حالت دوم را.
        """
        mode = getattr(self.params, "overtime_base", "HOURLY_WAGE")
        if mode not in {"MONTHLY_BASE", "MONTHLY_BASE_30"}:
            return self.hourly_base
        hours = self.params.monthly_work_hours or Decimal("220")
        if not hours:
            return self.hourly_base
        if mode == "MONTHLY_BASE_30":
            monthly = (self.daily_base + self.seniority_daily) * Decimal("30")
        else:
            monthly = self.daily_base * Decimal("30") + self.seniority_daily * self.paid_days
        return monthly / hours

    @property
    def seniority_years(self) -> int:
        """سابقهٔ این پرسنل **در پایان همین دوره**، نه امروز.

        از تاریخ استخدام + سابقهٔ قبلی ساخته می‌شود، نه از عددی که کسی یک بار
        تایپ کرده و بعد کهنه شده. سابقهٔ قبلی همان چیزی است که استخدام مجددِ
        بعد از خروج را ممکن می‌کند: کسی که برمی‌گردد، سابقهٔ کارگاه را با خود
        دارد.
        """
        return self.employee.seniority_years_at(self.period.end_date)

    @property
    def full_child_allowance(self) -> Decimal:
        """حق اولاد **ماه کامل** — پیش از تسهیم روی کارکرد.

        قاعدهٔ کسر تأخیر لازمش دارد: تأخیر از حقوق ماه کم می‌شود و مبنایش
        مبلغ کاملِ ماه است، نه سهمِ روزهای کارکرد.
        """
        count = self.children_count
        if count <= 0:
            return ZERO
        max_children = self.params.max_children or 0
        effective = min(count, max_children) if max_children else count
        return Decimal(self.params.child_allowance or ZERO) * effective

    @property
    def full_marriage_allowance(self) -> Decimal:
        """حق تأهل ماه کامل — صفر برای مجرد."""
        from apps.employees.models import Employee

        married = (
            getattr(self.employee, "marital_status", None) == Employee.MaritalStatus.MARRIED
        )
        return Decimal(self.params.marriage_allowance or ZERO) if married else ZERO

    @property
    def seniority_daily(self) -> Decimal:
        """پایهٔ سنوات روزانه — صفر برای کسی که هنوز یک سال سابقه ندارد."""
        if self.seniority_years < 1:
            return ZERO
        return Decimal(self.params.seniority_daily or ZERO)

    @property
    def mission_daily_base(self) -> Decimal:
        """مبنای روزانهٔ حق مأموریت.

        یا عددِ مشترکِ ثبت‌شده در آیتم‌های ماهانه، یا مزد خودِ پرسنل به‌علاوهٔ
        پایهٔ سنوات روزانه‌اش. دومی در فایل شرکت به کار می‌رود و چون به مزد هر
        نفر بسته است، با یک عدد مشترک قابل بیان نبود.
        """
        if getattr(self.params, "mission_base", "MONTHLY_RATE") == "PERSON_WAGE":
            return self.daily_base + self.seniority_daily
        return Decimal(self.params.mission_daily_rate or ZERO)

    @property
    def hourly_base(self) -> Decimal:
        hours = self.params.daily_work_hours or Decimal("7.33")
        return self.daily_base / hours

    @property
    def overtime_minutes(self) -> Decimal:
        """اضافه‌کاری **واقعیِ** ثبت‌شده، به دقیقه.

        دقیقه واحد اصلی است. ساعتِ ذخیره‌شده دو رقم اعشار دارد و ۲۷۴ دقیقه در
        آن ۴٫۵۷ می‌شود نه ۴٫۵۶۶…؛ روی نرخ ~۱٫۱ میلیون ریالیِ هر ساعت همین
        هزاران ریال خطا می‌دهد.
        """
        if not self.timesheet:
            return ZERO
        return Decimal(self.timesheet.overtime_minutes or 0)

    def recurring_or_manual(self, component) -> Decimal:
        """مبلغ یک قلم: اول از مزایای مستمر قرارداد، وگرنه از مبلغ دستی ماه.

        بعضی اعداد ماهانه نیستند. «مازاد ثابت» در فایل شرکت برای هر ۶۶ نفرِ
        مشترک بین تیر و مرداد **دقیقاً یکسان** بود — یعنی عددی سالانه است که
        سالی دو-سه بار عوض می‌شود، نه چیزی که هر ماه دستی وارد شود. جایش
        مزایای مستمر قرارداد است که تاریخ اعتبار هم دارد.

        ورودی دستیِ ماه همچنان کار می‌کند و **مقدم نیست**: اگر روی قرارداد
        عددی ثبت شده باشد همان ملاک است، وگرنه عدد ماه. این ترتیب عمدی است —
        وگرنه یک ورودی دستیِ جامانده از ماه قبل، عددِ قرارداد را بی‌صدا
        بی‌اثر می‌کرد.
        """
        recurring = self.contract_allowances.get(component.id)
        if recurring:
            return Decimal(recurring)
        manual = Decimal(self.manual_inputs.get(component.id, ZERO) or ZERO)
        if manual:
            return manual

        # قلمی که قاعده دارد، مبلغش را از همان قاعده می‌گیرد.
        #
        # لازم است چون «مابه‌التفاوت» از استخر مازاد **کم** می‌شود ولی
        # ترتیبش روی فیش بعد از اقلام زنجیره است. تا وقتی مبلغ دستی بود از
        # `manual_inputs` خوانده می‌شد؛ حالا که محاسبه می‌شود، اگر همین‌جا
        # صدا زده نشود استخر آن را صفر می‌بیند و روز مأموریت و ساعت
        # اضافه‌کاری برای همه بالا می‌رود.
        rule_key = getattr(component, "engine_rule_key", "")
        if rule_key:
            from apps.payroll.engine.rules import get_rule

            func = get_rule(rule_key)
            if func is not None:
                result = func(self, component)
                if result is not None:
                    return Decimal(result.amount)
        return ZERO

    @property
    def surplus(self):
        """زنجیرهٔ مازاد این پرسنل — یک بار ساخته و نگه داشته می‌شود.

        دو قاعده (اضافه‌کاری و حق مأموریت) به یک نتیجه نیاز دارند؛ اگر هرکدام
        جداگانه حساب می‌کرد، یک عدد در دو جا زندگی می‌کرد و ماه‌ها بعد که یکی
        عوض می‌شد دیگری بی‌سروصدا عقب می‌ماند.

        اینکه چه چیزی وارد استخر می‌شود **داده است نه کد**: هر قلم حقوقی
        می‌تواند نقش «افزودن به استخر» یا «کسر از استخر» بگیرد.
        """
        from apps.payroll.surplus import SurplusPlan

        if self._surplus is None:
            additions = deductions = ZERO
            for component in self.applicable_components:
                role = getattr(component, "allocation_role", "")
                if not role:
                    continue
                amount = self.recurring_or_manual(component)
                if not amount:
                    continue
                if role == "ADD":
                    additions += amount
                else:
                    deductions += amount
            self._surplus = SurplusPlan(
                real_minutes=self.overtime_minutes,
                additions=additions,
                deductions=deductions,
                hourly_base=self.overtime_hourly_base,
                factor=self.params.overtime_factor,
                mission_daily_base=self.mission_daily_base,
            )
        return self._surplus

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
