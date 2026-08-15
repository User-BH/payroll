"""مدیریت ساختار سازمانی و اطلاعات شرکت."""

from django import forms
from django.contrib import messages
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import can_edit_required, payroll_staff_required
from apps.employees.forms import BootstrapMixin
from apps.org.models import Company, CostCenter, Department, JobTitle


class CompanyForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            "name", "legal_name", "national_id", "economic_code",
            "registration_number", "insurance_workshop_code", "tax_file_number",
            "address", "phone",
            "bank_file_columns", "bank_file_delimiter", "bank_file_include_header",
            "bank_file_extension", "bank_file_encoding",
        ]
        widgets = {"address": forms.Textarea(attrs={"rows": 2})}

    GROUPS = [
        ("مشخصات", ["name", "legal_name", "national_id", "economic_code",
                    "registration_number", "phone", "address"]),
        ("کدهای رسمی", ["insurance_workshop_code", "tax_file_number"]),
        ("فرمت فایل پرداخت بانک", ["bank_file_columns", "bank_file_delimiter",
                                   "bank_file_include_header", "bank_file_extension",
                                   "bank_file_encoding"]),
    ]

    def grouped(self):
        for title, names in self.GROUPS:
            yield title, [self[name] for name in names]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["insurance_workshop_code"].help_text = "روی لیست بیمه چاپ می‌شود"
        self.fields["tax_file_number"].help_text = "روی لیست مالیات چاپ می‌شود"

    def clean_bank_file_columns(self):
        from apps.payroll.exports.generators import BANK_TOKENS

        raw = (self.cleaned_data.get("bank_file_columns") or "").strip()
        columns = [c.strip() for c in raw.split(",") if c.strip()]
        if not columns:
            raise forms.ValidationError("حداقل یک ستون لازم است.")
        unknown = [c for c in columns if c not in BANK_TOKENS]
        if unknown:
            raise forms.ValidationError(
                "ستون ناشناخته: " + "، ".join(unknown)
                + " — مقادیر مجاز: " + "، ".join(BANK_TOKENS)
            )
        return ",".join(columns)


class _OrgFormBase(BootstrapMixin, forms.ModelForm):
    """پایه مشترک فرم‌های ساختار سازمانی."""


def _simple_form(model, extra_fields=()):
    # ساخت با modelform_factory، نه با ست کردن Meta.model بعد از تعریف کلاس:
    # متاکلاس ModelForm در لحظه تعریف کلاس اجرا می‌شود و تغییر بعدی Meta
    # نادیده گرفته می‌شود (خطای «ModelForm has no model class specified»).
    return forms.models.modelform_factory(
        model, form=_OrgFormBase, fields=["name", "code", *extra_fields, "is_active"]
    )


DepartmentForm = _simple_form(Department)
CostCenterForm = _simple_form(CostCenter, ["gl_account"])
JobTitleForm = _simple_form(JobTitle, ["job_group"])

KINDS = {
    "department": (Department, DepartmentForm, "واحد سازمانی"),
    "cost-center": (CostCenter, CostCenterForm, "مرکز هزینه"),
    "job-title": (JobTitle, JobTitleForm, "پست سازمانی"),
}


@payroll_staff_required
def org_settings(request):
    company = Company.objects.first()
    return render(
        request,
        "org/settings.html",
        {
            "company": company,
            "departments": Department.objects.filter(company=company).order_by("name"),
            "cost_centers": CostCenter.objects.filter(company=company).order_by("name"),
            "job_titles": JobTitle.objects.filter(company=company).order_by("name"),
        },
    )


@can_edit_required
def company_edit(request):
    company = Company.objects.first()
    if company is None:
        messages.error(request, "شرکتی تعریف نشده است. ابتدا setup_operational را اجرا کنید.")
        return redirect("org_settings")

    form = CompanyForm(request.POST or None, instance=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "اطلاعات شرکت به‌روز شد.")
        return redirect("org_settings")
    return render(request, "org/company_form.html", {"form": form, "company": company})


@can_edit_required
def org_item_form(request, kind, pk=None):
    if kind not in KINDS:
        messages.error(request, "نوع نامعتبر است.")
        return redirect("org_settings")

    model, form_class, label = KINDS[kind]
    instance = get_object_or_404(model, pk=pk) if pk else None
    form = form_class(request.POST or None, instance=instance)

    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        if instance is None:
            item.company = Company.objects.first()
        item.save()
        messages.success(request, f"«{item.name}» ذخیره شد.")
        return redirect("org_settings")

    return render(
        request,
        "org/item_form.html",
        {
            "form": form,
            "kind": kind,
            "label": label,
            "instance": instance,
            "title": f"{'ویرایش' if instance else 'افزودن'} {label}",
        },
    )


@can_edit_required
@require_POST
def org_item_delete(request, kind, pk):
    if kind not in KINDS:
        return redirect("org_settings")
    model, _, label = KINDS[kind]
    item = get_object_or_404(model, pk=pk)
    name = item.name
    try:
        item.delete()
    except ProtectedError:
        # قراردادها با PROTECT بسته‌اند؛ حذف نباید تاریخچه را خراب کند
        item.is_active = False
        item.save(update_fields=["is_active"])
        messages.warning(
            request,
            f"«{name}» در قراردادها استفاده شده و حذف نشد، ولی غیرفعال شد "
            "و دیگر در فرم‌های جدید نمی‌آید.",
        )
    else:
        messages.success(request, f"«{name}» حذف شد.")
    return redirect("org_settings")
