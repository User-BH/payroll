from decimal import Decimal

from django import forms

from apps.payroll.form_fields import JalaliDateField

from apps.employees.banks import BANK_CHOICES, iban_checksum_ok, normalize_iban
from apps.org.models import CostCenter, JobTitle
from apps.employees.models import (
    BankAccount,
    Dependent,
    Employee,
    EmploymentContract,
    is_valid_national_id,
)


class BootstrapMixin:
    """کلاس ظاهری یکسان برای همه ورودی‌ها."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                continue
            css = widget.attrs.get("class", "")
            widget.attrs["class"] = (css + " input").strip()


class EmployeeForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "personnel_code", "first_name", "last_name", "father_name",
            "national_id", "id_number", "birth_date", "gender", "marital_status",
            "insurance_number", "mobile", "email", "address", "postal_code",
            "hire_date", "termination_date", "rehire_date", "status",
            "is_insurance_exempt", "insurance_exempt_reason", "prior_service_months",
        ]
        widgets = {"address": forms.Textarea(attrs={"rows": 2})}

    birth_date = JalaliDateField(label="تاریخ تولد", required=False)
    hire_date = JalaliDateField(label="تاریخ استخدام")
    # این دو تاریخ فقط ثبت اطلاعات نیستند: کارکرد اولیهٔ هر ماه از روی همین‌ها
    # حساب می‌شود، پس در فرم ویرایش پرسنل در دسترس‌اند.
    termination_date = JalaliDateField(label="تاریخ خاتمه کار", required=False)
    rehire_date = JalaliDateField(label="تاریخ شروع به کار مجدد", required=False)

    def clean(self):
        cleaned = super().clean()
        hire = cleaned.get("hire_date")
        termination = cleaned.get("termination_date")
        rehire = cleaned.get("rehire_date")
        if termination and hire and termination <= hire:
            self.add_error("termination_date", "تاریخ خاتمه کار باید بعد از تاریخ استخدام باشد.")
        if rehire and not termination:
            self.add_error(
                "rehire_date",
                "شروع به کار مجدد بدون تاریخ خاتمه کار معنا ندارد.",
            )
        if rehire and termination and rehire < termination:
            self.add_error("rehire_date", "شروع به کار مجدد باید بعد از خاتمه کار باشد.")
        return cleaned

    # فیلدهایی که در قالب، پنل جداگانه دارند (در فرم ویرایش هیچ‌کدام)
    EXTRA_FIELDS = []
    BANK_FIELDS = []

    def identity_fields(self):
        return [field for field in self if field.name not in self.EXTRA_FIELDS]

    def contract_fields(self):
        return [self[name] for name in self.EXTRA_FIELDS]

    def bank_fields(self):
        return [self[name] for name in self.BANK_FIELDS]

    def clean_national_id(self):
        """چک‌سام فقط وقتی بررسی می‌شود که مقدار **عوض شده** باشد.

        پرسنلی که از اکسل وارد شده‌اند کد ملی ندارند و سامانه برایشان کد
        جایگزین ساخته که چک‌سامش نمی‌خواند. با اعتبارسنجی بی‌قید، ویرایشِ
        موبایل یا مزدِ همان پرسنل هم رد می‌شد — روی فیلدی که کاربر اصلاً دست
        نزده بود. عملاً یعنی هیچ‌کدام از آن‌ها قابل ویرایش نبودند.

        اگر کاربر عدد را عوض کند، همچنان باید معتبر باشد.
        """
        value = (self.cleaned_data.get("national_id") or "").strip()
        unchanged = self.instance.pk and value == (self.instance.national_id or "")
        if value and not unchanged and not is_valid_national_id(value):
            raise forms.ValidationError("کد ملی معتبر نیست (رقم کنترلی نادرست است).")
        return value

    def clean_personnel_code(self):
        code = (self.cleaned_data.get("personnel_code") or "").strip()
        qs = Employee.objects.filter(personnel_code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("این کد پرسنلی قبلاً ثبت شده است.")
        return code


class EmployeeCreateForm(EmployeeForm):
    """فرم افزودن پرسنل.

    عمداً فقط **نوع قرارداد** را می‌پرسد، نه ریز جزئیات قرارداد را: پرسنل باید
    با یک بار پر کردن همین صفحه فعال شود تا بشود رویش کلیک کرد، ویرایشش کرد و
    خروجش را ثبت کرد. بقیهٔ فیلدهای قرارداد (واحد، مزد روزانه، …) پیش‌فرض
    می‌گیرند و در «ویرایش قرارداد» تکمیل می‌شوند.
    """

    contract_type = forms.ChoiceField(
        label="نوع قرارداد",
        choices=EmploymentContract.ContractType.choices,
        initial=EmploymentContract.ContractType.PERMANENT,
        help_text="قرارداد فعال با همین نوع و از تاریخ استخدام ساخته می‌شود",
    )
    # مرکز هزینه و پست، پیش‌تر پرسیده نمی‌شدند و «اولین ردیفِ ساختار سازمانی»
    # پیش‌فرض می‌شد. نتیجه این بود که هر پرسنل تازه در واحدِ اشتباه می‌نشست و
    # تا وقتی کسی یادش می‌ماند به «ویرایش قرارداد» برود، همان‌جا می‌ماند — و
    # دامنهٔ شمول اقلام حقوقی هم دقیقاً روی همین دو می‌نشیند، یعنی فیشش غلط
    # درمی‌آمد بی‌آنکه خطایی دیده شود.
    cost_center = forms.ModelChoiceField(
        label="مرکز هزینه", queryset=CostCenter.objects.none(),
        help_text="دامنهٔ شمول اقلام حقوقی روی همین تعیین می‌شود",
    )
    job_title = forms.ModelChoiceField(
        label="پست سازمانی", queryset=JobTitle.objects.none(),
    )
    daily_wage = forms.DecimalField(
        label="مزد روزانه (ریال)", required=False, min_value=0,
        max_digits=18, decimal_places=0,
        help_text="خالی بگذارید تا حداقل دستمزد همان سال مالی ثبت شود",
    )
    monthly_work_days = forms.DecimalField(
        label="کارکرد ماهانه (روز)",
        required=False,
        min_value=0,
        max_value=31,
        max_digits=6,
        decimal_places=2,
        help_text="خالی بگذارید تا از تاریخ استخدام حساب شود — برای استخدام وسط ماه همین درست است",
    )

    # حساب بانکی همین‌جا پرسیده می‌شود، نه در یک صفحهٔ جداگانه: رفتن به بخش
    # دیگر برای دو فیلد، کار ساده را چندمرحله‌ای می‌کند.
    bank_name = forms.ChoiceField(
        label="بانک",
        choices=BANK_CHOICES,
        initial=BankAccount.DEFAULT_BANK,
        required=False,
    )
    account_number = forms.CharField(
        label="شماره حساب",
        max_length=30,
        required=False,
        help_text="پرداخت بر مبنای شماره حساب انجام می‌شود",
    )
    iban = forms.CharField(
        label="شماره شبا",
        max_length=40,
        required=False,
        help_text="اختیاری — اگر پر شود، روی فیش حقوقی چاپ می‌شود",
    )

    # این فیلدها در قالب، پنل جداگانهٔ خودشان را دارند
    EXTRA_FIELDS = [
        "contract_type", "cost_center", "job_title", "daily_wage", "monthly_work_days",
    ]
    BANK_FIELDS = ["bank_name", "account_number", "iban"]

    class Meta(EmployeeForm.Meta):
        pass

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        # فهرست‌ها به شرکت محدود می‌شوند و الفبایی مرتب — نه به ترتیب ساخت،
        # که برای کاربر بی‌معناست.
        self.fields["cost_center"].queryset = CostCenter.objects.filter(
            company=company, is_active=True
        ).order_by("name")
        self.fields["job_title"].queryset = JobTitle.objects.filter(
            company=company, is_active=True
        ).order_by("name")

    def identity_fields(self):
        skip = set(self.EXTRA_FIELDS) | set(self.BANK_FIELDS)
        return [field for field in self if field.name not in skip]

    def bank_fields(self):
        return [self[name] for name in self.BANK_FIELDS]

    def clean_iban(self):
        return clean_iban_value(self.cleaned_data.get("iban"))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("iban") and not cleaned.get("account_number"):
            self.add_error(
                "account_number",
                "برای ثبت شبا، شماره حساب هم لازم است — پرداخت بر مبنای شماره حساب انجام می‌شود.",
            )
        return cleaned

    def save_bank_account(self, employee):
        """حساب بانکی را از همین فرم می‌سازد. بدون شماره حساب، حسابی ساخته نمی‌شود."""
        account_number = (self.cleaned_data.get("account_number") or "").strip()
        if not account_number:
            return None
        return BankAccount.objects.create(
            employee=employee,
            bank_name=self.cleaned_data.get("bank_name") or BankAccount.DEFAULT_BANK,
            account_number=account_number,
            iban=self.cleaned_data.get("iban") or "",
            is_default=True,
        )


class ContractForm(BootstrapMixin, forms.ModelForm):
    # «مازاد ثابت» کنار مزد روزانه می‌نشیند چون از همان جنس است: عددی که سالی
    # دو-سه بار عوض می‌شود، نه چیزی که هر ماه وارد شود. در فایل شرکت، این عدد
    # بین تیر و مرداد برای هر ۶۶ نفرِ مشترک دقیقاً یکسان بود.
    #
    # پشت صحنه یک «مزایای مستمر قرارداد» روی قلم SURPLUS_FIXED ساخته می‌شود،
    # پس تاریخ اعتبار هم دارد و فیشِ ماه‌های گذشته با تغییرش عوض نمی‌شود.
    fixed_surplus = forms.DecimalField(
        label="مازاد ثابت (ریال)", required=False, min_value=0,
        max_digits=18, decimal_places=0,
        help_text="عددی سالانه — در گروه پشتیبانی به مأموریت و اضافه‌کاری تبدیل "
                  "می‌شود و در گروه فروش به پورسانت اضافه می‌شود",
    )

    class Meta:
        model = EmploymentContract
        # «واحد سازمانی» پرسیده نمی‌شود — از مرکز هزینه ساخته می‌شود. روی کل
        # دیتابیس این دو یک‌به‌یک بودند، پس پرسیدنِ دوباره‌اش فقط یک انتخاب
        # اضافه بود که هیچ‌وقت با مرکز هزینه فرق نمی‌کرد.
        fields = [
            "contract_number", "contract_type", "cost_center",
            "job_title", "effective_from", "effective_to", "daily_wage",
            "weekly_hours", "is_insured", "is_taxable",
            "tax_exemption", "status", "notes",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    SURPLUS_CODE = "SURPLUS_FIXED"

    def _surplus_component(self):
        from apps.payroll_config.models import SalaryComponent

        company = getattr(self.instance, "employee", None)
        company = company.company if company else None
        return SalaryComponent.objects.filter(
            company=company, code=self.SURPLUS_CODE
        ).first()

    def _surplus_allowance(self):
        component = self._surplus_component()
        if component is None or not self.instance.pk:
            return None
        return self.instance.allowances.filter(component=component).first()

    def save_fixed_surplus(self, contract):
        """مازاد ثابت را به‌صورت مزایای مستمر قرارداد ذخیره می‌کند."""
        component = self._surplus_component()
        if component is None:
            return
        amount = self.cleaned_data.get("fixed_surplus") or 0
        if not amount:
            contract.allowances.filter(component=component).delete()
            return
        contract.allowances.update_or_create(
            component=component,
            defaults={
                "amount": amount,
                "effective_from": contract.effective_from,
                "effective_to": None,
            },
        )

    effective_from = JalaliDateField(label="شروع اعتبار")
    effective_to = JalaliDateField(label="پایان اعتبار", required=False)

    def __init__(self, *args, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee = employee or (self.instance.employee if self.instance.pk else None)
        # پرسنل باید **پیش از** اعتبارسنجی روی instance بنشیند، نه در clean().
        # جنگو خودش در _post_clean متد full_clean مدل را صدا می‌زند؛ اگر آن‌جا
        # employee_id خالی باشد، کنترل همپوشانی قراردادها بی‌صدا رد می‌شود.
        if self.employee and not self.instance.employee_id:
            self.instance.employee = self.employee

        # مقدار فعلی مازاد ثابت از مزایای مستمر قرارداد خوانده می‌شود
        # واحد از مرکز هزینه پر می‌شود، چون مدل هنوز الزامی می‌داندش
        allowance = self._surplus_allowance()
        if allowance is not None and not self.is_bound:
            self.fields["fixed_surplus"].initial = allowance.amount

        # مزد روزانه روی مدل `default=0` دارد و صفر معنای روشنی دارد: «مزد
        # اختصاصی ندارد، از حداقل دستمزد سال استفاده کن». پس اجباری نیست —
        # ستارهٔ قرمز کنارش کاربر را وادار می‌کرد عددی بنویسد که ندارد.
        self.fields["daily_wage"].required = False

    def clean_daily_wage(self):
        return self.cleaned_data.get("daily_wage") or Decimal("0")

    def clean(self):
        """واحد را از مرکز هزینه پر می‌کند، پیش از اعتبارسنجی مدل.

        ستون `department` روی مدل هنوز الزامی است (فیش‌های صادرشده به آن اشاره
        دارند)، ولی دیگر از کاربر پرسیده نمی‌شود. اگر اینجا پر نشود،
        `full_clean` مدل با «این فیلد الزامی است» رد می‌کند — روی فیلدی که
        اصلاً در فرم نیست، یعنی خطایی که کاربر جایی نمی‌بیندش.
        """
        cleaned = super().clean()
        cost_center = cleaned.get("cost_center")
        if cost_center is not None:
            from apps.employees.services import department_for

            department = department_for(cost_center)
            if department is not None:
                self.instance.department = department
        return cleaned


def clean_iban_value(value):
    """شبا را تمیز و کنترل می‌کند. خالی مجاز است."""
    iban = normalize_iban(value)
    if not iban:
        return ""
    if len(iban) != 26 or not iban.startswith("IR"):
        raise forms.ValidationError(
            "شماره شبا باید IR به‌همراه ۲۴ رقم باشد (فاصله و خط تیره اشکالی ندارد)."
        )
    if not iban_checksum_ok(iban):
        raise forms.ValidationError(
            "شماره شبا معتبر نیست (رقم کنترلی نمی‌خواند) — دوباره از روی کارت یا اپ بانک بررسی کنید."
        )
    return iban


class BankAccountForm(BootstrapMixin, forms.ModelForm):
    """کد بانک عمداً در فرم نیست — از روی نام بانک پر می‌شود."""

    class Meta:
        model = BankAccount
        fields = ["bank_name", "account_number", "iban", "is_default", "is_active"]

    def clean_iban(self):
        return clean_iban_value(self.cleaned_data.get("iban"))


class DependentForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Dependent
        fields = [
            "relation", "first_name", "last_name", "national_id", "birth_date",
            "child_allowance_eligible", "is_insured", "start_date", "end_date",
        ]

    birth_date = JalaliDateField(label="تاریخ تولد", required=False)
    start_date = JalaliDateField(label="شروع تکفل")
    end_date = JalaliDateField(label="پایان تکفل", required=False)


class SignatureForm(forms.ModelForm):
    """بارگذاری امضا توسط خود پرسنل در پرتال."""

    MAX_BYTES = 2 * 1024 * 1024

    class Meta:
        model = Employee
        fields = ["signature"]
        labels = {"signature": "تصویر امضا"}

    def clean_signature(self):
        image = self.cleaned_data.get("signature")
        if image and getattr(image, "size", 0) > self.MAX_BYTES:
            raise forms.ValidationError("حجم تصویر باید کمتر از ۲ مگابایت باشد.")
        return image


class EmployeeImportForm(forms.Form):
    file = forms.FileField(
        label="فایل اکسل پرسنل",
        help_text="فقط xlsx — ابتدا فایل الگو را دانلود کنید",
    )
    create_contracts = forms.BooleanField(
        label="ساخت قرارداد همزمان با پرسنل", required=False, initial=True
    )
