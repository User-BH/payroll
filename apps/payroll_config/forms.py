from django import forms
from django.forms import modelformset_factory

from apps.employees.forms import BootstrapMixin
from apps.payroll.form_fields import JalaliDateField
from apps.payroll_config.models import (
    ComponentScope,
    LegalParameter,
    SalaryComponent,
    TaxBracket,
)


class LegalParameterForm(BootstrapMixin, forms.ModelForm):
    """پارامترهای قانونی سال — همه مبالغ به ریال."""

    class Meta:
        model = LegalParameter
        fields = [
            "effective_from", "effective_to",
            "min_daily_wage", "housing_allowance", "food_allowance",
            "child_allowance", "max_children", "seniority_daily",
            "ins_employee_rate", "ins_employer_rate", "unemployment_rate",
            "ins_ceiling_factor",
            "overtime_factor", "night_factor", "friday_factor", "holiday_factor",
            "monthly_days", "daily_work_hours", "leave_day_minutes",
            "rounding_unit", "deduct_insurance_from_tax_base",
        ]

    effective_from = JalaliDateField(label="شروع اعتبار")
    effective_to = JalaliDateField(label="پایان اعتبار", required=False)

    GROUPS = [
        ("اعتبار", ["effective_from", "effective_to"]),
        ("مزد و مزایای پایه", [
            "min_daily_wage", "housing_allowance", "food_allowance",
            "child_allowance", "max_children", "seniority_daily",
        ]),
        ("بیمه", [
            "ins_employee_rate", "ins_employer_rate", "unemployment_rate", "ins_ceiling_factor",
        ]),
        ("ضرایب کارکرد", [
            "overtime_factor", "night_factor", "friday_factor", "holiday_factor",
        ]),
        ("مبناهای زمانی و گرد کردن", [
            "monthly_days", "daily_work_hours", "leave_day_minutes",
            "rounding_unit", "deduct_insurance_from_tax_base",
        ]),
    ]

    def grouped(self):
        for title, names in self.GROUPS:
            yield title, [self[name] for name in names]

    def clean(self):
        cleaned = super().clean()
        rate_fields = [
            "ins_employee_rate", "ins_employer_rate", "unemployment_rate",
            "overtime_factor", "night_factor", "friday_factor", "holiday_factor",
        ]
        for name in rate_fields:
            value = cleaned.get(name)
            # نرخ‌ها اعشاری‌اند (۰٫۰۷ یعنی ۷٪). اگر کسی ۷ وارد کند یعنی ۷۰۰٪.
            if value is not None and value > 3:
                self.add_error(
                    name,
                    "نرخ باید اعشاری باشد، نه درصد. برای ۷ درصد عدد ۰٫۰۷ را وارد کنید.",
                )
        return cleaned


class TaxBracketForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = TaxBracket
        fields = ["row_order", "from_amount", "to_amount", "rate", "is_exemption"]


TaxBracketFormSet = modelformset_factory(
    TaxBracket, form=TaxBracketForm, extra=1, can_delete=True
)


class SalaryComponentForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = SalaryComponent
        fields = [
            "code", "name", "kind", "calc_type", "engine_rule_key",
            "base_component", "rate", "fixed_amount",
            "is_insurable", "is_taxable", "affects_eid", "affects_severance",
            "sequence", "gl_account", "color", "print_on_payslip",
            "is_active", "description",
        ]
        widgets = {"color": forms.TextInput(attrs={"type": "color"})}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        if company:
            queryset = SalaryComponent.objects.filter(company=company)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            self.fields["base_component"].queryset = queryset
        self.fields["engine_rule_key"].help_text = (
            "فقط وقتی «نحوه محاسبه» روی قاعده موتور است — نام قاعده در rules.py"
        )

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        queryset = SalaryComponent.objects.filter(company=self.company, code=code)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("این کد قبلاً برای قلم دیگری استفاده شده است.")
        return code

    def clean(self):
        cleaned = super().clean()
        calc_type = cleaned.get("calc_type")
        if calc_type == SalaryComponent.CalcType.ENGINE_RULE:
            from apps.payroll.engine.rules import RULES

            key = (cleaned.get("engine_rule_key") or "").strip()
            if not key:
                self.add_error("engine_rule_key", "برای قاعده موتور، کلید قاعده اجباری است.")
            elif key not in RULES:
                self.add_error(
                    "engine_rule_key",
                    "چنین قاعده‌ای در موتور ثبت نشده است. قواعد موجود: "
                    + "، ".join(sorted(RULES)),
                )
        if calc_type == SalaryComponent.CalcType.PERCENTAGE and not cleaned.get("base_component"):
            self.add_error("base_component", "برای قلم درصدی، انتخاب قلم مبنا اجباری است.")
        return cleaned


class ComponentScopeForm(BootstrapMixin, forms.ModelForm):
    """دامنه شمول — مقصد بسته به نوع دامنه از فهرست انتخاب می‌شود."""

    target = forms.ChoiceField(label="مقصد", required=False)

    class Meta:
        model = ComponentScope
        fields = ["scope_type"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.employees.models import EmploymentContract
        from apps.org.models import CostCenter, Department, JobTitle

        choices = [("", "—")]
        for department in Department.objects.filter(company=company):
            choices.append((f"DEPARTMENT:{department.pk}", f"واحد: {department.name}"))
        for cost_center in CostCenter.objects.filter(company=company):
            choices.append((f"COST_CENTER:{cost_center.pk}", f"مرکز هزینه: {cost_center.name}"))
        for job_title in JobTitle.objects.filter(company=company):
            choices.append((f"JOB_TITLE:{job_title.pk}", f"پست: {job_title.name}"))
        for value, label in EmploymentContract.ContractType.choices:
            choices.append((f"CONTRACT_TYPE:{value}", f"نوع قرارداد: {label}"))
        self.fields["target"].choices = choices
        self.fields["scope_type"].required = False
        self.fields["scope_type"].widget = forms.HiddenInput()

    def clean(self):
        cleaned = super().clean()
        target = cleaned.get("target") or ""
        if not target:
            raise forms.ValidationError("مقصد دامنه را انتخاب کنید.")
        scope_type, _, scope_id = target.partition(":")
        cleaned["scope_type"] = scope_type
        self.instance.scope_type = scope_type
        self.instance.scope_id = scope_id
        return cleaned
