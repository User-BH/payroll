from decimal import Decimal

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
            "child_allowance", "max_children", "marriage_allowance", "seniority_daily",
            "ins_employee_rate", "ins_employer_rate", "unemployment_rate",
            "ins_ceiling_factor",
            "overtime_factor", "night_factor", "friday_factor", "holiday_factor",
            "monthly_days", "daily_work_hours", "monthly_work_hours", "leave_day_minutes",
            "overtime_base", "mission_base",
            "rounding_unit", "deduct_insurance_from_tax_base",
        ]

    effective_from = JalaliDateField(label="شروع اعتبار")
    effective_to = JalaliDateField(label="پایان اعتبار", required=False)

    GROUPS = [
        ("اعتبار", ["effective_from", "effective_to"]),
        ("مزد و مزایای پایه", [
            "min_daily_wage", "housing_allowance", "food_allowance",
            "child_allowance", "max_children", "marriage_allowance", "seniority_daily",
        ]),
        ("بیمه", [
            "ins_employee_rate", "ins_employer_rate", "unemployment_rate", "ins_ceiling_factor",
        ]),
        ("ضرایب کارکرد", [
            "overtime_factor", "night_factor", "friday_factor", "holiday_factor",
        ]),
        ("مبناهای زمانی و گرد کردن", [
            "monthly_days", "daily_work_hours", "monthly_work_hours", "leave_day_minutes",
            "overtime_base", "mission_base",
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
            "base_source", "quantity_source", "base_component", "timesheet_item",
            "rate", "fixed_amount",
            "display_unit", "is_insurable", "is_taxable",
            "affects_eid", "affects_severance",
            "sequence", "gl_account", "color", "print_on_payslip",
            "is_active", "description",
        ]
        widgets = {"color": forms.TextInput(attrs={"type": "color"})}

    GROUPS = [
        ("شناسه و نوع", ["code", "name", "kind", "sequence"]),
        ("نحوه محاسبه", [
            "calc_type", "base_source", "quantity_source", "base_component",
            "timesheet_item", "rate", "fixed_amount", "engine_rule_key",
        ]),
        ("رفتار در فیش و گزارش", [
            "display_unit", "is_insurable", "is_taxable",
            "affects_eid", "affects_severance", "print_on_payslip",
        ]),
        ("نمایش و سایر", ["gl_account", "color", "is_active", "description"]),
    ]

    def grouped(self):
        for title, names in self.GROUPS:
            yield title, [self[name] for name in names]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        if company:
            queryset = SalaryComponent.objects.filter(company=company)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            self.fields["base_component"].queryset = queryset
            # فقط اقلام کارکردِ فعال؛ قلمی که در جدول کارکرد نیست همیشه صفر
            # می‌ماند و سطر حقوقی‌اش بی‌سروصدا نمی‌آید.
            from apps.attendance.models import TimesheetItem

            self.fields["timesheet_item"].queryset = TimesheetItem.objects.filter(
                company=company, is_active=True
            )
        self.fields["engine_rule_key"].help_text = (
            "فقط وقتی «نحوه محاسبه» روی قاعده موتور است — نام قاعده در rules.py"
        )
        self.fields["calc_type"].help_text = (
            "«قاعده پارامتری» بدون کدنویسی ساخته می‌شود: مبنا × مقدار × ضریب"
        )
        # هر دو روی مدل `default=0` دارند، پس خالی گذاشتنشان یعنی صفر — نه
        # «فیلد لازم است». بدون این، ساختن یک قلم پارامتریِ ساده هم به پر کردن
        # دو خانهٔ بی‌ربط گیر می‌کرد.
        for name in ("rate", "fixed_amount"):
            self.fields[name].required = False
        self.fields["rate"].help_text = "ضریب فرمول؛ خالی یا ۱ یعنی بدون ضریب"
        self.fields["base_component"].help_text = (
            "وقتی مبنا «مبلغ یک قلم دیگر» است — آن قلم باید ترتیب کوچک‌تری داشته باشد"
        )
        self.fields["timesheet_item"].help_text = (
            "وقتی مقدار «یک قلم جدول کارکرد» است — همان ستونی که اپراتور پر می‌کند"
        )

    def clean_rate(self):
        return self.cleaned_data.get("rate") or Decimal("0")

    def clean_fixed_amount(self):
        return self.cleaned_data.get("fixed_amount") or Decimal("0")

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

        if calc_type == SalaryComponent.CalcType.PARAMETRIC:
            self._clean_parametric(cleaned)

        # قلمی که به قلم دیگری بسته است باید **بعد از** آن محاسبه شود، وگرنه
        # موقع محاسبه مبنایش هنوز صفر است و سطر بی‌سروصدا صفر می‌شود.
        base = cleaned.get("base_component")
        sequence = cleaned.get("sequence")
        if base is not None and sequence is not None and base.sequence >= sequence:
            self.add_error(
                "sequence",
                f"ترتیب باید بزرگ‌تر از ترتیب «{base.name}» ({base.sequence}) باشد، "
                "وگرنه قلم مبنا هنوز محاسبه نشده و این قلم صفر می‌شود.",
            )
        return cleaned

    def _clean_parametric(self, cleaned):
        """قاعدهٔ پارامتری فقط وقتی معنا دارد که هر سه جزئش کامل باشند."""
        base_source = cleaned.get("base_source")
        if not base_source:
            self.add_error("base_source", "برای قاعده پارامتری، مبنای محاسبه اجباری است.")
        if not cleaned.get("quantity_source"):
            self.add_error("quantity_source", "برای قاعده پارامتری، مقدار اجباری است.")
        if base_source == SalaryComponent.BaseSource.FIXED and not cleaned.get("fixed_amount"):
            self.add_error("fixed_amount", "مبنای «مبلغ ثابت» بدون مبلغ، همیشه صفر می‌شود.")
        if base_source == SalaryComponent.BaseSource.COMPONENT and not cleaned.get("base_component"):
            self.add_error("base_component", "مبنای «مبلغ یک قلم دیگر» بدون انتخاب قلم، معنا ندارد.")
        if (
            cleaned.get("quantity_source") == SalaryComponent.QuantitySource.TIMESHEET_ITEM
            and not cleaned.get("timesheet_item")
        ):
            self.add_error(
                "timesheet_item",
                "مقدار «یک قلم جدول کارکرد» بدون انتخاب آن قلم، همیشه صفر می‌شود.",
            )


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
