from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.employees.models import Employee, EmploymentContract
from apps.org.models import Company, CostCenter, Department
from apps.payroll_config.models import FiscalYear, LegalParameter, SalaryComponent

JALALI_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]


class PayrollPeriod(models.Model):
    """دوره حقوقی — یک ماشین حالت.

    عبور از هر حالت به بعدی برگشت‌پذیر است، به‌جز LOCKED که برگشت‌ناپذیر است و
    از آن به بعد فقط فیش اصلاحی صادر می‌شود.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "پیش‌نویس"
        TIMESHEET_LOCKED = "TIMESHEET_LOCKED", "کارکرد قفل‌شده"
        CALCULATED = "CALCULATED", "محاسبه‌شده"
        APPROVED = "APPROVED", "تأییدشده"
        LOCKED = "LOCKED", "قفل‌شده"
        PAID = "PAID", "پرداخت‌شده"

    # ترتیب پیشروی حالت‌ها
    FLOW = [
        Status.DRAFT,
        Status.TIMESHEET_LOCKED,
        Status.CALCULATED,
        Status.APPROVED,
        Status.LOCKED,
        Status.PAID,
    ]

    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="periods", verbose_name="شرکت"
    )
    fiscal_year = models.ForeignKey(
        FiscalYear, on_delete=models.PROTECT, related_name="periods", verbose_name="سال مالی"
    )
    year = models.PositiveSmallIntegerField("سال (جلالی)")
    month = models.PositiveSmallIntegerField("ماه")

    start_date = models.DateField("شروع دوره")
    end_date = models.DateField("پایان دوره")
    payment_date = models.DateField("تاریخ پرداخت", null=True, blank=True)

    status = models.CharField("وضعیت", max_length=20, choices=Status.choices, default=Status.DRAFT)
    legal_parameter = models.ForeignKey(
        LegalParameter, on_delete=models.PROTECT, null=True, blank=True,
        related_name="periods", verbose_name="پارامتر اعمال‌شده",
    )

    # جمع‌های ذخیره‌شده برای کارت‌های داشبورد (بعد از هر محاسبه به‌روز می‌شوند)
    total_gross = models.DecimalField("ناخالص کل", max_digits=20, decimal_places=0, default=0)
    total_net = models.DecimalField("خالص کل", max_digits=20, decimal_places=0, default=0)
    total_deductions = models.DecimalField("جمع کسور", max_digits=20, decimal_places=0, default=0)
    total_employer_cost = models.DecimalField("هزینه کارفرما", max_digits=20, decimal_places=0, default=0)
    employee_count = models.PositiveIntegerField("تعداد پرسنل", default=0)

    calculated_at = models.DateTimeField("زمان محاسبه", null=True, blank=True)
    approved_at = models.DateTimeField("زمان تأیید", null=True, blank=True)
    locked_at = models.DateTimeField("زمان قفل", null=True, blank=True)
    locked_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="locked_periods", verbose_name="قفل‌کننده",
    )
    notes = models.TextField("توضیحات", blank=True)

    class Meta:
        verbose_name = "دوره حقوقی"
        verbose_name_plural = "دوره‌های حقوقی"
        unique_together = [("company", "year", "month")]
        ordering = ["-year", "-month"]

    def __str__(self):
        return self.title

    @property
    def title(self):
        from apps.payroll.utils import fa_digits

        name = JALALI_MONTHS[self.month - 1] if 1 <= self.month <= 12 else str(self.month)
        return f"{name} {fa_digits(self.year)}"

    @property
    def month_name(self):
        return JALALI_MONTHS[self.month - 1] if 1 <= self.month <= 12 else str(self.month)

    @property
    def month_days(self):
        """روزهای واقعی ماه جلالی این دوره — ۳۱ در شش‌ماههٔ اول، ۳۰ در دوم،
        و اسفند ۲۹ (در سال کبیسه ۳۰).

        از خودِ بازهٔ دوره خوانده می‌شود، نه از یک عدد ثابت در پارامترهای
        قانونی: مزد روزانه و تسهیم مزایای ثابت باید بر طول همان ماه تقسیم
        شوند، وگرنه کارکرد ناقصِ یک ماه ۳۱ روزه با نسبت اشتباه حساب می‌شود.
        عددِ «روز کارکرد» هر پرسنل جداگانه و دستی وارد می‌شود؛ این فقط مخرج
        محاسبه و مقدار پیش‌فرض ورودی است.
        """
        if self.start_date and self.end_date:
            return Decimal((self.end_date - self.start_date).days + 1)
        return None

    @property
    def is_locked(self):
        return self.status in {self.Status.LOCKED, self.Status.PAID}

    @property
    def is_editable(self):
        """آیا کارکرد و داده‌های دوره هنوز قابل تغییرند؟"""
        return self.status == self.Status.DRAFT

    @property
    def can_calculate(self):
        return self.status in {
            self.Status.DRAFT,
            self.Status.TIMESHEET_LOCKED,
            self.Status.CALCULATED,
        }

    @property
    def next_status(self):
        try:
            index = self.FLOW.index(self.Status(self.status))
        except ValueError:
            return None
        return self.FLOW[index + 1] if index + 1 < len(self.FLOW) else None

    @property
    def previous_status(self):
        """برگشت فقط تا قبل از قفل مجاز است."""
        if self.status in {self.Status.LOCKED, self.Status.PAID, self.Status.DRAFT}:
            return None
        index = self.FLOW.index(self.Status(self.status))
        return self.FLOW[index - 1]

    @property
    def status_tone(self):
        return {
            self.Status.DRAFT: "wait",
            self.Status.TIMESHEET_LOCKED: "wait",
            self.Status.CALCULATED: "info",
            self.Status.APPROVED: "ok",
            self.Status.LOCKED: "lock",
            self.Status.PAID: "ok",
        }.get(self.status, "wait")


class PayrollRun(models.Model):
    """لاگ یک بار اجرای محاسبه.

    جدا از دوره است چون محاسبه ممکن است چندین بار اجرا شود و باید بدانیم کدام
    اجرا کدام فیش را ساخته و با کدام نسخه از موتور.
    """

    class Status(models.TextChoices):
        RUNNING = "RUNNING", "در حال اجرا"
        SUCCESS = "SUCCESS", "موفق"
        FAILED = "FAILED", "ناموفق"

    period = models.ForeignKey(
        PayrollPeriod, on_delete=models.CASCADE, related_name="runs", verbose_name="دوره"
    )
    started_at = models.DateTimeField("شروع", auto_now_add=True)
    finished_at = models.DateTimeField("پایان", null=True, blank=True)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.RUNNING)
    engine_version = models.CharField("نسخه موتور", max_length=20, blank=True)
    run_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payroll_runs", verbose_name="اجراکننده",
    )
    success_count = models.PositiveIntegerField("موفق", default=0)
    error_count = models.PositiveIntegerField("خطا", default=0)
    error_detail = models.JSONField("جزئیات خطا", default=list, blank=True)

    class Meta:
        verbose_name = "اجرای محاسبه"
        verbose_name_plural = "اجراهای محاسبه"
        ordering = ["-started_at"]

    def __str__(self):
        return f"اجرای {self.period} — {self.get_status_display()}"

    @property
    def duration_seconds(self):
        if not self.finished_at:
            return None
        return (self.finished_at - self.started_at).total_seconds()


class PayrollInput(models.Model):
    """مبالغ متغیرِ ورودی دستی برای یک دوره — مثل پورسانت فروش.

    اقلامی که calc_type آن‌ها MANUAL است مقدارشان را از اینجا می‌گیرند.
    """

    period = models.ForeignKey(
        PayrollPeriod, on_delete=models.CASCADE, related_name="inputs", verbose_name="دوره"
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="payroll_inputs", verbose_name="پرسنل"
    )
    component = models.ForeignKey(
        SalaryComponent, on_delete=models.PROTECT, related_name="inputs", verbose_name="قلم حقوقی"
    )
    amount = models.DecimalField("مبلغ (ریال)", max_digits=18, decimal_places=0, default=0)
    note = models.CharField("توضیح", max_length=160, blank=True)

    class Meta:
        verbose_name = "ورودی دستی دوره"
        verbose_name_plural = "ورودی‌های دستی دوره"
        unique_together = [("period", "employee", "component")]

    def __str__(self):
        return f"{self.employee} — {self.component}: {self.amount}"


class Payslip(models.Model):
    """فیش حقوقی.

    بعد از قفل دوره هرگز تغییر نمی‌کند و باید به‌تنهایی — بدون اتکا به هیچ جدول
    دیگری — قابل بازخوانی و قابل دفاع باشد. به همین دلیل نام واحد، شبا و کل
    پارامترهای قانونی داخل خودش کپی می‌شوند.
    """

    class Status(models.TextChoices):
        CALCULATED = "CALCULATED", "محاسبه‌شده"
        APPROVED = "APPROVED", "تأییدشده"
        PAID = "PAID", "پرداخت‌شده"
        CANCELLED = "CANCELLED", "ابطال‌شده"

    period = models.ForeignKey(
        PayrollPeriod, on_delete=models.CASCADE, related_name="payslips", verbose_name="دوره"
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="payslips", verbose_name="پرسنل"
    )
    contract = models.ForeignKey(
        EmploymentContract, on_delete=models.PROTECT, related_name="payslips", verbose_name="قرارداد"
    )
    run = models.ForeignKey(
        PayrollRun, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payslips", verbose_name="اجرای محاسبه",
    )

    # --- کپی‌های لحظه محاسبه (snapshot، نه تکرار داده)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="payslips", verbose_name="واحد"
    )
    cost_center = models.ForeignKey(
        CostCenter, on_delete=models.PROTECT, related_name="payslips", verbose_name="مرکز هزینه"
    )
    iban_snapshot = models.CharField("شبا در لحظه پرداخت", max_length=26, blank=True)
    account_snapshot = models.CharField("شماره حساب در لحظه پرداخت", max_length=30, blank=True)
    bank_snapshot = models.CharField("بانک عامل", max_length=60, blank=True)
    # وضعیت بیمه هم مثل بقیهٔ مبناها در لحظهٔ محاسبه عکس‌برداری می‌شود: اگر
    # بعداً تیک «بازنشسته» یک پرسنل عوض شود، لیست بیمه‌ای که قبلاً به تأمین
    # اجتماعی فرستاده شده نباید با آن تغییر کند.
    insurance_applies = models.BooleanField(
        "مشمول بیمه", default=True,
        help_text="در لحظه محاسبه ثبت می‌شود؛ پرسنل بازنشسته و قرارداد غیرمشمول، False",
    )
    params_snapshot = models.JSONField("تصویر پارامترهای قانونی", default=dict, blank=True)
    leave_snapshot = models.JSONField(
        "تصویر مانده مرخصی", default=dict, blank=True,
        help_text="انتقالی، استحقاقی، مصرفی ماه، مصرفی از اول سال و مانده — در لحظه محاسبه",
    )

    # --- ارقام
    work_days = models.DecimalField("روز کارکرد", max_digits=6, decimal_places=2, default=0)
    gross_total = models.DecimalField("ناخالص کل", max_digits=18, decimal_places=0, default=0)
    insurable_base = models.DecimalField("مبنای بیمه", max_digits=18, decimal_places=0, default=0)
    taxable_base = models.DecimalField("مبنای مالیات", max_digits=18, decimal_places=0, default=0)
    total_deductions = models.DecimalField("جمع کسور", max_digits=18, decimal_places=0, default=0)
    net_payable = models.DecimalField("خالص پرداختی", max_digits=18, decimal_places=0, default=0)
    tax_amount = models.DecimalField("مالیات", max_digits=18, decimal_places=0, default=0)
    ins_employee = models.DecimalField("بیمه سهم کارگر", max_digits=18, decimal_places=0, default=0)
    ins_employer = models.DecimalField("بیمه سهم کارفرما", max_digits=18, decimal_places=0, default=0)
    employer_total_cost = models.DecimalField(
        "کل هزینه کارفرما", max_digits=18, decimal_places=0, default=0
    )

    status = models.CharField(
        "وضعیت", max_length=12, choices=Status.choices, default=Status.CALCULATED
    )
    is_corrective = models.BooleanField("فیش اصلاحی", default=False)
    revision = models.PositiveSmallIntegerField(
        "شماره اصلاح",
        default=0,
        help_text="۰ = فیش اصلی دوره، ۱ به بعد = فیش‌های اصلاحی",
    )
    original_payslip = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="corrections", verbose_name="فیش اصلی",
    )

    calc_hash = models.CharField("اثر انگشت محاسبه", max_length=64, blank=True)
    calculated_at = models.DateTimeField("زمان محاسبه", auto_now_add=True)
    paid_at = models.DateTimeField("زمان پرداخت", null=True, blank=True)
    payment_reference = models.CharField("مرجع پرداخت", max_length=60, blank=True)

    # ---- گردش مشاهده و تأیید توسط پرسنل
    # جایگزین امضای دستی پای فیش کاغذی. مسیر:
    #   در انتظار → دیده شد → (تأیید | اعتراض) → بررسی‌شده
    class Ack(models.TextChoices):
        PENDING = "PENDING", "در انتظار مشاهده"
        VIEWED = "VIEWED", "دیده شد"
        ACCEPTED = "ACCEPTED", "تأیید شد"
        DISPUTED = "DISPUTED", "اعتراض ثبت شد"
        RESOLVED = "RESOLVED", "بررسی و پاسخ داده شد"

    ack_status = models.CharField(
        "وضعیت تأیید پرسنل", max_length=10, choices=Ack.choices, default=Ack.PENDING
    )
    first_viewed_at = models.DateTimeField("اولین مشاهده", null=True, blank=True)
    acknowledged_at = models.DateTimeField("زمان تأیید", null=True, blank=True)
    dispute_reason = models.TextField("علت اعتراض", blank=True)
    disputed_at = models.DateTimeField("زمان ثبت اعتراض", null=True, blank=True)
    review_note = models.TextField("پاسخ واحد مالی", blank=True)
    reviewed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_payslips", verbose_name="بررسی‌کننده",
    )
    reviewed_at = models.DateTimeField("زمان بررسی", null=True, blank=True)

    class Meta:
        verbose_name = "فیش حقوقی"
        verbose_name_plural = "فیش‌های حقوقی"
        ordering = ["employee__personnel_code"]
        indexes = [models.Index(fields=["period", "employee"])]
        constraints = [
            # روی هر دوره برای هر پرسنل فقط یک فیش اصلی (revision=0) و پس از آن
            # فیش‌های اصلاحی شماره‌دار.
            #
            # نسخه اول این قید به‌صورت UniqueConstraint با condition نوشته شده
            # بود؛ MySQL ایندکس شرطی (partial index) ندارد و جنگو چنین قیدی را
            # روی MySQL بی‌صدا نادیده می‌گیرد (هشدار models.W038). یعنی دقیقاً
            # همان جایی که نباید، امکان ثبت دو فیش تکراری باز می‌ماند. با یک
            # ستون عددی، قید روی هر دیتابیسی واقعی است.
            models.UniqueConstraint(
                fields=["period", "employee", "revision"],
                name="unique_payslip_per_period_employee",
            )
        ]

    def __str__(self):
        return f"فیش {self.employee.full_name} — {self.period.title}"

    def save(self, *args, **kwargs):
        """لایه اول محافظت از فیش قفل‌شده.

        لایه دوم باید یک تریگر BEFORE UPDATE در دیتابیس باشد؛ اتکا به منطق UI
        کافی نیست.
        """
        if self.pk and not kwargs.pop("force_locked_write", False):
            current = Payslip.objects.filter(pk=self.pk).values_list("period__status", flat=True).first()
            if current in {PayrollPeriod.Status.LOCKED, PayrollPeriod.Status.PAID}:
                raise ValidationError("این فیش در دوره قفل‌شده است و قابل تغییر نیست.")
        super().save(*args, **kwargs)

    @property
    def earnings(self):
        return [line for line in self.lines.all() if line.kind == SalaryComponent.Kind.EARNING]

    @property
    def deductions(self):
        return [line for line in self.lines.all() if line.kind == SalaryComponent.Kind.DEDUCTION]

    @property
    def employer_costs(self):
        return [line for line in self.lines.all() if line.kind == SalaryComponent.Kind.EMPLOYER_COST]

    @property
    def ack_tone(self):
        return {
            self.Ack.PENDING: "muted",
            self.Ack.VIEWED: "info",
            self.Ack.ACCEPTED: "ok",
            self.Ack.DISPUTED: "wait",
            self.Ack.RESOLVED: "lock",
        }.get(self.ack_status, "muted")

    @property
    def awaiting_employee_action(self):
        """دیده شده ولی هنوز تأیید یا اعتراض نکرده."""
        return self.ack_status == self.Ack.VIEWED

    def save_ack(self, fields):
        """ذخیره فیلدهای گردش تأیید.

        عمداً از save() مدل رد می‌شود: فیش قفل‌شده تغییرناپذیر است، ولی مشاهده و
        تأیید و اعتراض پرسنل دقیقاً بعد از قفل شدن دوره اتفاق می‌افتد. این فیلدها
        هیچ‌کدام روی ارقام فیش اثر ندارند.
        """
        super().save(update_fields=fields)

    def mark_viewed(self):
        if self.ack_status == self.Ack.PENDING:
            self.ack_status = self.Ack.VIEWED
            self.first_viewed_at = timezone.now()
            self.save_ack(["ack_status", "first_viewed_at"])


class PayslipLine(models.Model):
    """یک سطر از فیش.

    فیلدهای component_code و component_name کپی‌اند: اگر سال بعد نام قلم عوض شود
    یا غیرفعال شود، فیش قدیمی باید همان چیزی را نشان دهد که آن روز چاپ شد.
    """

    payslip = models.ForeignKey(
        Payslip, on_delete=models.CASCADE, related_name="lines", verbose_name="فیش"
    )
    component = models.ForeignKey(
        SalaryComponent, on_delete=models.PROTECT, null=True, blank=True,
        related_name="payslip_lines", verbose_name="قلم حقوقی",
    )
    component_code = models.CharField("کد قلم", max_length=40)
    component_name = models.CharField("نام قلم", max_length=80)
    kind = models.CharField("نوع", max_length=16, choices=SalaryComponent.Kind.choices)
    sequence = models.PositiveSmallIntegerField("ترتیب", default=100)

    base_amount = models.DecimalField("مبنا", max_digits=18, decimal_places=0, default=0)
    quantity = models.DecimalField("تعداد / ساعت", max_digits=10, decimal_places=2, default=0)
    rate = models.DecimalField("ضریب / نرخ", max_digits=9, decimal_places=4, default=0)
    amount = models.DecimalField("مبلغ", max_digits=18, decimal_places=0, default=0)

    is_insurable = models.BooleanField("مشمول بیمه", default=False)
    is_taxable = models.BooleanField("مشمول مالیات", default=False)
    explanation = models.CharField(
        "توضیح محاسبه", max_length=255, blank=True,
        help_text="مثال: اضافه‌کاری: ۱۲ ساعت × (۸۵٬۰۰۰٬۰۰۰ ÷ ۳۰ ÷ ۷٫۳۳) × ۱٫۴",
    )

    class Meta:
        verbose_name = "سطر فیش"
        verbose_name_plural = "سطرهای فیش"
        ordering = ["sequence", "id"]
        indexes = [models.Index(fields=["payslip", "sequence"])]

    def __str__(self):
        return f"{self.component_name}: {self.amount}"


class PayrollExport(models.Model):
    """رکورد یک خروجی قانونی.

    فایل به‌تنهایی کافی نیست: باید بدانیم چه چیزی، کِی، با چه جمعی تولید شد و
    آیا ارسال شده یا نه. شش ماه بعد که سازمان سؤال کند، همین رکورد جواب است.
    """

    class Kind(models.TextChoices):
        INSURANCE = "INSURANCE", "لیست بیمه (DSK)"
        TAX = "TAX", "لیست مالیات"
        BANK = "BANK", "فایل پرداخت بانک"

    class Status(models.TextChoices):
        GENERATED = "GENERATED", "تولید شده"
        SUBMITTED = "SUBMITTED", "ارسال شده"
        ACCEPTED = "ACCEPTED", "پذیرفته شده"
        REJECTED = "REJECTED", "رد شده"

    period = models.ForeignKey(
        PayrollPeriod, on_delete=models.CASCADE, related_name="exports", verbose_name="دوره"
    )
    kind = models.CharField("نوع خروجی", max_length=12, choices=Kind.choices)
    file = models.FileField("فایل", upload_to="exports/%Y/%m/")
    file_name = models.CharField("نام فایل", max_length=160)

    record_count = models.PositiveIntegerField("تعداد رکورد", default=0)
    total_amount = models.DecimalField("جمع مبلغ", max_digits=20, decimal_places=0, default=0)
    summary = models.JSONField("خلاصه ارقام", default=dict, blank=True)

    status = models.CharField(
        "وضعیت", max_length=10, choices=Status.choices, default=Status.GENERATED
    )
    tracking_code = models.CharField("کد رهگیری", max_length=60, blank=True)
    submitted_at = models.DateTimeField("زمان ارسال", null=True, blank=True)
    note = models.CharField("توضیح", max_length=250, blank=True)

    generated_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payroll_exports", verbose_name="تولیدکننده",
    )
    generated_at = models.DateTimeField("زمان تولید", auto_now_add=True)

    class Meta:
        verbose_name = "خروجی قانونی"
        verbose_name_plural = "خروجی‌های قانونی"
        ordering = ["-generated_at"]
        indexes = [models.Index(fields=["period", "kind"])]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.period.title}"

    @property
    def status_tone(self):
        return {
            self.Status.GENERATED: "muted",
            self.Status.SUBMITTED: "info",
            self.Status.ACCEPTED: "ok",
            self.Status.REJECTED: "wait",
        }.get(self.status, "muted")


class PayslipView(models.Model):
    """لاگ مشاهده فیش در پرتال — چه کسی، کِی، از کجا."""

    payslip = models.ForeignKey(
        Payslip, on_delete=models.CASCADE, related_name="views", verbose_name="فیش"
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True,
        related_name="payslip_views", verbose_name="کاربر",
    )
    viewed_at = models.DateTimeField("زمان مشاهده", auto_now_add=True)
    ip = models.GenericIPAddressField("آی‌پی", null=True, blank=True)

    class Meta:
        verbose_name = "مشاهده فیش"
        verbose_name_plural = "مشاهدات فیش"
        ordering = ["-viewed_at"]
