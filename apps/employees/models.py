from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from apps.employees.banks import BANK_CHOICES, code_for as bank_code_for, normalize_iban
from apps.org.models import Company, CostCenter, Department, JobTitle

national_id_validator = RegexValidator(r"^\d{10}$", "کد ملی باید دقیقاً ۱۰ رقم باشد.")
iban_validator = RegexValidator(r"^IR\d{24}$", "شماره شبا باید با IR شروع شود و ۲۶ کاراکتر باشد.")


def is_valid_national_id(value: str) -> bool:
    """اعتبارسنجی چک‌سام کد ملی ایران."""
    if not value or not value.isdigit() or len(value) != 10:
        return False
    if value == value[0] * 10:
        return False
    check = int(value[9])
    total = sum(int(value[i]) * (10 - i) for i in range(9))
    remainder = total % 11
    return check == remainder if remainder < 2 else check == 11 - remainder


class Employee(models.Model):
    """پرسنل.

    توجه: این مدل عمداً هیچ اطلاعات شغلی یا مالی ندارد. واحد، مرکز هزینه، پست و
    مزد روزانه همگی روی EmploymentContract هستند چون همه در طول زمان عوض می‌شوند
    و تاریخِ تغییرشان باید ثبت بماند.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "فعال"
        SUSPENDED = "SUSPENDED", "معلق"
        TERMINATED = "TERMINATED", "خاتمه‌یافته"

    class Gender(models.TextChoices):
        MALE = "M", "مرد"
        FEMALE = "F", "زن"

    class MaritalStatus(models.TextChoices):
        SINGLE = "SINGLE", "مجرد"
        MARRIED = "MARRIED", "متأهل"

    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="employees", verbose_name="شرکت"
    )
    user = models.OneToOneField(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="employee", verbose_name="کاربر پرتال",
    )

    personnel_code = models.CharField("کد پرسنلی", max_length=20)
    first_name = models.CharField("نام", max_length=60)
    last_name = models.CharField("نام خانوادگی", max_length=80)
    father_name = models.CharField("نام پدر", max_length=60, blank=True)
    national_id = models.CharField(
        "کد ملی", max_length=10, unique=True, validators=[national_id_validator]
    )
    id_number = models.CharField("شماره شناسنامه", max_length=20, blank=True)
    birth_date = models.DateField("تاریخ تولد", null=True, blank=True)
    gender = models.CharField("جنسیت", max_length=1, choices=Gender.choices, default=Gender.MALE)
    marital_status = models.CharField(
        "وضعیت تأهل", max_length=10, choices=MaritalStatus.choices, default=MaritalStatus.SINGLE
    )
    insurance_number = models.CharField("شماره بیمه", max_length=15, blank=True)

    mobile = models.CharField("موبایل", max_length=15, blank=True)
    email = models.EmailField("ایمیل", blank=True)
    address = models.TextField("نشانی", blank=True)
    postal_code = models.CharField("کد پستی", max_length=10, blank=True)

    # امضای اسکن‌شده پرسنل. فقط پس از تأیید فیش توسط خودش روی فیش چاپ می‌شود،
    # پس نقش «امضای دریافت‌کننده» را ایفا می‌کند نه یک تصویر تزئینی.
    signature = models.ImageField(
        "تصویر امضا", upload_to="signatures/", blank=True, null=True,
        help_text="تصویر امضا با زمینه روشن — روی فیش تأییدشده چاپ می‌شود",
    )

    # کسی که بیمهٔ تأمین اجتماعی برایش کسر نمی‌شود. علتش یکی نیست: ممکن است
    # بازنشسته باشد، یا خودش نخواهد بیمه شود، یا هر دلیل دیگری. پس اسم این
    # کلید «بازنشسته» نیست — چیزی که موتور لازم دارد بدانَد فقط همین است که
    # بیمه دارد یا نه، و علتش جداگانه ثبت می‌شود.
    #
    # این یک آیتم کنترلی در موتور محاسبه است، نه یادداشتی در پرونده: تصمیمش در
    # PayrollContext.insurance_applies گرفته می‌شود و همهٔ مسیرها (سه قاعدهٔ
    # بیمه، گزارش بیمه، جمع ماه، خروجی تأمین اجتماعی) از همان یک نقطه می‌آیند.
    is_insurance_exempt = models.BooleanField(
        "بدون بیمه", default=False,
        help_text="حق بیمه برایش محاسبه نمی‌شود و در لیست تأمین اجتماعی نمی‌آید",
    )
    # سابقهٔ کارِ پیش از این استخدام. روی **شخص** است نه قرارداد، چون ویژگی
    # خودِ اوست: اگر خارج شود و برگردد، همان سابقه با او می‌ماند.
    #
    # سابقهٔ کل هیچ‌وقت ذخیره نمی‌شود؛ در موتور و نسبت به **دورهٔ حقوقی** حساب
    # می‌شود. عددِ ذخیره‌شده هر سال کهنه می‌شد و کسی به‌روزش نمی‌کرد — در
    # دیتابیس عملیاتی یک نفر ۳ سال ثبت شده بود در حالی که ۴ سال سر کار بود.
    prior_service_months = models.PositiveSmallIntegerField(
        "سابقهٔ قبلی (ماه)", default=0,
        help_text="سابقهٔ پیش از این استخدام — در همین کارگاه یا جای دیگر. "
                  "به سابقهٔ محاسبه‌شده از تاریخ استخدام اضافه می‌شود.",
    )
    insurance_exempt_reason = models.CharField(
        "علت نداشتن بیمه", max_length=120, blank=True,
        help_text="مثلاً «بازنشسته» یا «انصراف کتبی» — روی پرونده می‌ماند تا بعداً معلوم باشد چرا",
    )

    # این سه تاریخ با هم «بازهٔ اشتغال» را می‌سازند و کارکرد اولیهٔ هر ماه از
    # روی همان حساب می‌شود — نه از روی طول کامل ماه.
    hire_date = models.DateField("تاریخ استخدام")
    termination_date = models.DateField(
        "تاریخ خاتمه کار", null=True, blank=True,
        help_text="از این تاریخ به بعد کارکرد ندارد؛ خودِ این روز جزو کارکرد نیست",
    )
    rehire_date = models.DateField(
        "تاریخ شروع به کار مجدد", null=True, blank=True,
        help_text="اگر پس از خاتمه دوباره مشغول به کار شده — از این تاریخ دوباره کارکرد دارد",
    )
    termination_reason = models.CharField("علت خروج", max_length=120, blank=True)
    status = models.CharField("وضعیت", max_length=12, choices=Status.choices, default=Status.ACTIVE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "پرسنل"
        verbose_name_plural = "پرسنل"
        unique_together = [("company", "personnel_code")]
        ordering = ["personnel_code"]
        indexes = [models.Index(fields=["status", "last_name"])]

    def __str__(self):
        return f"{self.full_name} ({self.personnel_code})"

    def clean(self):
        """چک‌سام کد ملی — فقط روی مقدارِ **تازه یا عوض‌شده**.

        پرسنلی که از فایل اکسل وارد شده‌اند کد ملی واقعی ندارند و سامانه
        برایشان کد جایگزین ساخته. اگر این بررسی بی‌قید اجرا شود، ویرایشِ
        موبایل یا مزدِ همان پرسنل هم رد می‌شود — روی فیلدی که کاربر اصلاً دست
        نزده. یعنی عملاً هیچ‌کدامشان قابل ویرایش نمی‌مانند.

        مقدارِ ذخیره‌شده هرچه باشد پذیرفته می‌شود؛ به‌محض اینکه کسی عوضش کند،
        باید معتبر باشد.
        """
        if not self.national_id or is_valid_national_id(self.national_id):
            return
        if self.pk:
            stored = (
                type(self).objects.filter(pk=self.pk)
                .values_list("national_id", flat=True)
                .first()
            )
            if stored == self.national_id:
                return
        raise ValidationError({"national_id": "کد ملی معتبر نیست (چک‌سام نادرست)."})

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def initials(self):
        return f"{self.first_name[:1]}.{self.last_name[:1]}"

    def employment_spans(self):
        """بازه‌های اشتغال به شکل (شروع، پایانِ ناشمول).

        پایان `None` یعنی هنوز ادامه دارد. «تاریخ خاتمه کار» خودش جزو کارکرد
        نیست — سند صریح است: «از آن تاریخ به بعد شخص دیگر کارکرد ندارد». پس
        خاتمهٔ ۱۶ مرداد یعنی آخرین روز کارکرد ۱۵ مرداد.
        """
        if not self.hire_date:
            return []
        spans = []
        if self.termination_date:
            if self.termination_date > self.hire_date:
                spans.append((self.hire_date, self.termination_date))
            if self.rehire_date:
                spans.append((max(self.rehire_date, self.termination_date), None))
        else:
            spans.append((self.hire_date, None))
        return spans

    def employed_days_in(self, start, end) -> int:
        """تعداد روزهای اشتغال در بازهٔ [start, end] — کارکرد اولیهٔ آن دوره.

        مبنای «روز کارکرد» هر ماه است: کسی که وسط ماه آمده یا رفته، کارکرد
        اولیه‌اش کمتر از طول ماه است و نباید ۳۰ یا ۳۱ روز پیش‌فرض بگیرد.
        """
        if not (start and end) or end < start:
            return 0
        total = 0
        for span_start, span_end in self.employment_spans():
            first = max(span_start, start)
            # span_end ناشمول است، پس یک روز عقب می‌آید
            last = end if span_end is None else min(span_end - timedelta(days=1), end)
            if last >= first:
                total += (last - first).days + 1
        return total

    def is_employed_on(self, on_date) -> bool:
        return any(
            span_start <= on_date and (span_end is None or on_date < span_end)
            for span_start, span_end in self.employment_spans()
        )

    def contract_on(self, on_date):
        """قرارداد معتبر در یک تاریخ مشخص. قلب اصلِ «همه‌چیز تاریخ‌دار»."""
        return (
            self.contracts.filter(
                status=EmploymentContract.Status.ACTIVE,
                effective_from__lte=on_date,
            )
            .filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=on_date))
            .select_related("department", "cost_center", "job_title")
            .first()
        )

    def dependents_on(self, on_date):
        """افراد تحت تکفلِ معتبر در تاریخ مشخص."""
        return self.dependents.filter(start_date__lte=on_date).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=on_date)
        )

    def children_count_on(self, on_date):
        return self.dependents_on(on_date).filter(child_allowance_eligible=True).count()

    @property
    def default_bank_account(self):
        return self.bank_accounts.filter(is_default=True, is_active=True).first()


    def seniority_months_at(self, on_date) -> int:
        """سابقهٔ کل به ماه، تا یک تاریخ مشخص — نه «امروز».

        «امروز» غلط است: محاسبهٔ دوبارهٔ یک ماه قدیمی نباید سابقهٔ امروز را در
        فیش دیروز بنشاند.
        """
        if not self.hire_date or not on_date or on_date < self.hire_date:
            return int(self.prior_service_months or 0)
        months = (on_date.year - self.hire_date.year) * 12 + (
            on_date.month - self.hire_date.month
        )
        if on_date.day < self.hire_date.day:
            months -= 1
        return max(0, months) + int(self.prior_service_months or 0)

    def seniority_years_at(self, on_date) -> int:
        return self.seniority_months_at(on_date) // 12


class Dependent(models.Model):
    """افراد تحت تکفل.

    تاریخ‌دار است چون فرزندی که به سن قانونی می‌رسد یا همسری که جدا می‌شود،
    حق اولاد را از تاریخ مشخصی تغییر می‌دهد — و فیش‌های قبلی نباید عوض شوند.
    """

    class Relation(models.TextChoices):
        SPOUSE = "SPOUSE", "همسر"
        CHILD = "CHILD", "فرزند"
        PARENT = "PARENT", "والدین"

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="dependents", verbose_name="پرسنل"
    )
    relation = models.CharField("نسبت", max_length=10, choices=Relation.choices)
    first_name = models.CharField("نام", max_length=60)
    last_name = models.CharField("نام خانوادگی", max_length=80, blank=True)
    national_id = models.CharField("کد ملی", max_length=10, blank=True)
    birth_date = models.DateField("تاریخ تولد", null=True, blank=True)
    child_allowance_eligible = models.BooleanField("مشمول حق اولاد", default=False)
    is_insured = models.BooleanField("تحت پوشش بیمه", default=True)
    start_date = models.DateField("شروع تکفل")
    end_date = models.DateField("پایان تکفل", null=True, blank=True)

    class Meta:
        verbose_name = "فرد تحت تکفل"
        verbose_name_plural = "افراد تحت تکفل"

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.get_relation_display()})"


class BankAccount(models.Model):
    """حساب بانکی پرسنل.

    پرداخت این شرکت از طریق بانک رسالت و بر مبنای **شماره حساب** انجام می‌شود،
    نه شبا. پس شماره حساب اجباری و شبا اختیاری است.
    """

    DEFAULT_BANK = "رسالت"

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="bank_accounts", verbose_name="پرسنل"
    )
    # انتخاب از فهرست، نه متن آزاد: نام‌های متفاوت برای یک بانک («ملی» و
    # «بانک ملی ایران») فایل پرداخت و گزارش‌ها را دوتکه می‌کند. مقدار ذخیره‌شده
    # همان نام کوتاه است تا دادهٔ قبلی سر جایش بماند.
    bank_name = models.CharField(
        "بانک", max_length=60, default=DEFAULT_BANK, choices=BANK_CHOICES
    )
    bank_code = models.CharField(
        "کد بانک", max_length=10, blank=True,
        help_text="خودکار از روی نام بانک پر می‌شود",
    )
    account_number = models.CharField("شماره حساب", max_length=30)
    card_number = models.CharField("شماره کارت", max_length=20, blank=True)
    iban = models.CharField(
        "شماره شبا", max_length=26, blank=True, validators=[iban_validator],
        help_text="اختیاری — پرداخت بر مبنای شماره حساب انجام می‌شود",
    )
    is_default = models.BooleanField("حساب پیش‌فرض", default=True)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "حساب بانکی"
        verbose_name_plural = "حساب‌های بانکی"

    def __str__(self):
        return f"{self.bank_name} — {self.account_number}"

    def save(self, *args, **kwargs):
        self.iban = normalize_iban(self.iban)
        if not self.bank_code:
            self.bank_code = bank_code_for(self.bank_name)
        super().save(*args, **kwargs)


class EmploymentContract(models.Model):
    """قرارداد استخدامی — موجودیت تاریخ‌دارِ اصلی سامانه.

    هر ترفیع، تغییر واحد یا افزایش حقوق یک قرارداد جدید با effective_from جدید
    است، نه ویرایش قرارداد قبلی.
    """

    class ContractType(models.TextChoices):
        PERMANENT = "PERMANENT", "دائم"
        TEMPORARY = "TEMPORARY", "موقت"
        HOURLY = "HOURLY", "ساعتی"
        DAILY = "DAILY", "روزمزد"
        TRIAL = "TRIAL", "آزمایشی"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "پیش‌نویس"
        ACTIVE = "ACTIVE", "فعال"
        ENDED = "ENDED", "پایان‌یافته"

    class TaxExemption(models.TextChoices):
        NONE = "NONE", "بدون معافیت خاص"
        FREE_ZONE = "FREE_ZONE", "مناطق آزاد"
        DISABLED = "DISABLED", "معلولین"

    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="contracts", verbose_name="پرسنل"
    )
    contract_number = models.CharField("شماره قرارداد", max_length=30, blank=True)
    contract_type = models.CharField(
        "نوع قرارداد", max_length=12, choices=ContractType.choices, default=ContractType.PERMANENT
    )

    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="contracts", verbose_name="واحد"
    )
    cost_center = models.ForeignKey(
        CostCenter, on_delete=models.PROTECT, related_name="contracts", verbose_name="مرکز هزینه"
    )
    job_title = models.ForeignKey(
        JobTitle, on_delete=models.PROTECT, related_name="contracts", verbose_name="پست سازمانی"
    )

    effective_from = models.DateField("شروع اعتبار")
    effective_to = models.DateField(
        "پایان اعتبار", null=True, blank=True, help_text="خالی یعنی قرارداد جاری"
    )

    # مبنای مزد **روزانه** است، نه ماهانه. سه دلیل:
    #
    # ۱) فایل واقعی شرکت همین است: مزد روزانه ثبت می‌شود و حقوق ماهانه از روی
    #    آن ساخته می‌شود، نه برعکس.
    # ۲) نگهداری ماهانه یعنی مزد روزانه باید هر ماه با تقسیم بر طول همان ماه
    #    ساخته شود — و همان قرارداد در مرداد (۳۱ روزه) و مهر (۳۰ روزه) دو مزد
    #    روزانهٔ متفاوت می‌داد.
    # ۳) تقسیم، کسر متناوب می‌سازد؛ عددِ ثبت‌شده نمی‌سازد. با مزد روزانهٔ صحیح،
    #    هر سطر فیش با ماشین‌حساب دقیقاً درمی‌آید.
    #
    # صفر یعنی «این پرسنل مزد اختصاصی ندارد» و مبنا حداقل دستمزد همان سال
    # می‌شود — تصمیمش در `PayrollContext.daily_base` است، یک جا.
    # پایهٔ سنوات **تجمیعی** روزانه — انباشتهٔ سال‌های خدمت این شخص.
    #
    # با «پایه سنوات روزانه»ی سال (که برای همه یکی است) فرق دارد و مابه‌التفاوتِ
    # همین دو، سطرِ «مابه التفاوت» فیش را می‌سازد:
    #
    #     مابه‌التفاوت = (تجمیعی روزانه − سنوات روزانهٔ سال) × کارکرد قابل پرداخت
    #
    # عددی سالانه است و در فایل شرکت بین تیر و مرداد برای هیچ‌کس عوض نشد، پس
    # جایش روی قرارداد است نه در مبالغ دستیِ ماهانه. تا پیش از این، جوابِ
    # اکسل هر ماه دستی وارد می‌شد — یعنی سامانه آن را حساب نمی‌کرد، فقط
    # عبورش می‌داد.
    cumulative_seniority_daily = models.DecimalField(
        "پایه سنوات تجمیعی روزانه", max_digits=18, decimal_places=0, default=Decimal("0"),
        help_text="انباشتهٔ سال‌های خدمت. مابه‌التفاوت با پایه سنوات سال، روی فیش می‌آید.",
    )
    daily_wage = models.DecimalField(
        "مزد روزانه (ریال)", max_digits=18, decimal_places=0, default=Decimal("0"),
        help_text="خالی یا صفر یعنی از «حداقل دستمزد روزانه» سال مالی استفاده شود",
    )
    weekly_hours = models.DecimalField("ساعت کار هفتگی", max_digits=5, decimal_places=2, default=Decimal("44"))

    is_insured = models.BooleanField("مشمول بیمه", default=True)
    is_taxable = models.BooleanField("مشمول مالیات", default=True)
    tax_exemption = models.CharField(
        "معافیت مالیاتی", max_length=12, choices=TaxExemption.choices, default=TaxExemption.NONE
    )

    status = models.CharField("وضعیت", max_length=8, choices=Status.choices, default=Status.ACTIVE)
    signed_date = models.DateField("تاریخ امضا", null=True, blank=True)
    notes = models.TextField("توضیحات", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "قرارداد"
        verbose_name_plural = "قراردادها"
        ordering = ["-effective_from"]
        indexes = [models.Index(fields=["employee", "effective_from", "effective_to"])]

    def __str__(self):
        return f"{self.employee.full_name} — از {self.effective_from}"

    def clean(self):
        """جلوگیری از همپوشانی قراردادهای فعال یک پرسنل.

        در PostgreSQL این یک EXCLUDE constraint یک‌خطی بود؛ MySQL چنین امکانی
        ندارد، پس اینجا و در سرویس ایجاد قرارداد (با select_for_update) تضمین
        می‌شود. این تنها جای مدل است که MySQL هزینه دارد.
        """
        if self.effective_to and self.effective_from and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "پایان اعتبار نمی‌تواند قبل از شروع باشد."})

        # بدون تاریخ شروع، پرس‌وجوی همپوشانی معنا ندارد و با None در فیلتر،
        # جنگو ValueError می‌دهد و صفحه با خطای ۵۰۰ می‌خوابد. نبودِ این تاریخ را
        # اعتبارسنجی خودِ فیلد گزارش می‌کند.
        if not self.effective_from:
            return

        if not self.employee_id or self.status != self.Status.ACTIVE:
            return

        overlapping = EmploymentContract.objects.filter(
            employee_id=self.employee_id, status=self.Status.ACTIVE
        ).exclude(pk=self.pk)
        overlapping = overlapping.filter(
            models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=self.effective_from)
        )
        if self.effective_to:
            overlapping = overlapping.filter(effective_from__lte=self.effective_to)

        if overlapping.exists():
            raise ValidationError(
                "این پرسنل در همین بازه قرارداد فعال دیگری دارد. "
                "ابتدا قرارداد قبلی را پایان دهید."
            )

    def hourly_base(self, daily_work_hours: Decimal) -> Decimal:
        """مزد ساعتی = مزد روزانه ÷ ساعات کار روزانه (معمولاً ۷٫۳۳)."""
        if not daily_work_hours:
            return Decimal("0")
        return self.daily_wage / Decimal(daily_work_hours)


class ContractAllowance(models.Model):
    """مزایای مستمر مختص یک قرارداد.

    مثال: «فوق‌العاده شغل این کارمند ۵٬۰۰۰٬۰۰۰ ریال است» — بدون اینکه قلم
    حقوقی جدیدی برای کل شرکت ساخته شود.
    """

    contract = models.ForeignKey(
        EmploymentContract, on_delete=models.CASCADE,
        related_name="allowances", verbose_name="قرارداد",
    )
    component = models.ForeignKey(
        "payroll_config.SalaryComponent", on_delete=models.PROTECT,
        related_name="contract_allowances", verbose_name="قلم حقوقی",
    )
    amount = models.DecimalField("مبلغ (ریال)", max_digits=18, decimal_places=0, default=Decimal("0"))
    effective_from = models.DateField("شروع اعتبار")
    effective_to = models.DateField("پایان اعتبار", null=True, blank=True)

    class Meta:
        verbose_name = "مزایای مستمر قرارداد"
        verbose_name_plural = "مزایای مستمر قرارداد"

    def __str__(self):
        return f"{self.component} — {self.amount}"
