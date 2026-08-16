from django import forms

from apps.payroll.form_fields import JalaliDateField

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
            "hire_date", "status",
        ]
        widgets = {"address": forms.Textarea(attrs={"rows": 2})}

    birth_date = JalaliDateField(label="تاریخ تولد", required=False)
    hire_date = JalaliDateField(label="تاریخ استخدام")

    # فیلدهایی که در قالب، پنل جداگانه دارند (در فرم ویرایش هیچ‌کدام)
    EXTRA_FIELDS = []

    def identity_fields(self):
        return [field for field in self if field.name not in self.EXTRA_FIELDS]

    def contract_fields(self):
        return [self[name] for name in self.EXTRA_FIELDS]

    def clean_national_id(self):
        value = (self.cleaned_data.get("national_id") or "").strip()
        if value and not is_valid_national_id(value):
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
    خروجش را ثبت کرد. بقیهٔ فیلدهای قرارداد (واحد، حقوق پایه، …) پیش‌فرض
    می‌گیرند و در «ویرایش قرارداد» تکمیل می‌شوند.
    """

    contract_type = forms.ChoiceField(
        label="نوع قرارداد",
        choices=EmploymentContract.ContractType.choices,
        initial=EmploymentContract.ContractType.PERMANENT,
        help_text="قرارداد فعال با همین نوع و از تاریخ استخدام ساخته می‌شود",
    )
    monthly_work_days = forms.DecimalField(
        label="کارکرد ماهانه (روز)",
        required=False,
        min_value=0,
        max_value=31,
        max_digits=6,
        decimal_places=2,
        help_text="اختیاری — اگر دورهٔ بازی وجود داشته باشد، کارکرد این ماه با همین عدد ثبت می‌شود",
    )

    # این دو فیلد در قالب، پنل جداگانهٔ خودشان را دارند
    EXTRA_FIELDS = ["contract_type", "monthly_work_days"]

    class Meta(EmployeeForm.Meta):
        pass


class ContractForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = EmploymentContract
        fields = [
            "contract_number", "contract_type", "department", "cost_center",
            "job_title", "effective_from", "effective_to", "base_salary",
            "seniority_years", "weekly_hours", "is_insured", "is_taxable",
            "tax_exemption", "status", "notes",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

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


class BankAccountForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ["bank_name", "bank_code", "account_number", "iban", "is_default", "is_active"]


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
