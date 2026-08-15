from django import forms

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
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "hire_date": forms.DateInput(attrs={"type": "date"}),
            "address": forms.Textarea(attrs={"rows": 2}),
        }

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


class ContractForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = EmploymentContract
        fields = [
            "contract_number", "contract_type", "department", "cost_center",
            "job_title", "effective_from", "effective_to", "base_salary",
            "seniority_years", "weekly_hours", "is_insured", "is_taxable",
            "tax_exemption", "status", "notes",
        ]
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee = employee

    def clean(self):
        cleaned = super().clean()
        if self.employee and not self.instance.employee_id:
            self.instance.employee = self.employee
        # همپوشانی قراردادهای فعال در clean() مدل کنترل می‌شود
        self.instance.full_clean(exclude=["employee"])
        return cleaned


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
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


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
