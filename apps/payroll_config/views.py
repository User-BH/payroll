from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import can_edit_required, payroll_staff_required
from apps.org.models import Company
from apps.payroll_config.forms import (
    ComponentScopeForm,
    LegalParameterForm,
    SalaryComponentForm,
    TaxBracketFormSet,
)
from apps.payroll_config.models import (
    ComponentScope,
    FiscalYear,
    LegalParameter,
    SalaryComponent,
    TaxBracket,
)


@payroll_staff_required
def component_list(request):
    components = (
        SalaryComponent.objects.select_related("base_component")
        .prefetch_related("scopes")
        .order_by("sequence", "id")
    )
    groups = []
    for kind, label in SalaryComponent.Kind.choices:
        items = [c for c in components if c.kind == kind]
        if items:
            groups.append({"kind": kind, "label": label, "items": items})
    return render(
        request,
        "components/list.html",
        {"groups": groups, "total": components.count()},
    )


@can_edit_required
@require_POST
def component_toggle(request, pk):
    """فعال/غیرفعال کردن یک قلم — پاسخ HTMX فقط همان کارت است.

    توجه: تغییر این کلید روی دوره‌های قفل‌شده اثری ندارد، چون فیش‌ها snapshot
    خودشان را دارند.
    """
    component = get_object_or_404(SalaryComponent, pk=pk)
    component.is_active = not component.is_active
    component.save(update_fields=["is_active"])
    return render(request, "components/_item.html", {"component": component})


@can_edit_required
def component_create(request):
    company = Company.objects.first()
    form = SalaryComponentForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        component = form.save(commit=False)
        component.company = company
        component.save()
        messages.success(
            request,
            f"قلم «{component.name}» ساخته شد. برای محدود کردنش به یک واحد یا سمت، "
            "دامنه شمول تعریف کنید.",
        )
        return redirect("component_edit", pk=component.pk)
    return render(
        request,
        "components/form.html",
        {"form": form, "title": "افزودن قلم حقوقی"},
    )


@can_edit_required
def component_edit(request, pk):
    component = get_object_or_404(SalaryComponent, pk=pk)
    form = SalaryComponentForm(
        request.POST or None, instance=component, company=component.company
    )
    scope_form = ComponentScopeForm(company=component.company)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            "قلم به‌روز شد. توجه: دوره‌های قفل‌شده تغییر نمی‌کنند چون فیش‌هایشان "
            "snapshot خودشان را دارند.",
        )
        return redirect("component_list")

    return render(
        request,
        "components/form.html",
        {
            "form": form,
            "component": component,
            "scope_form": scope_form,
            "scopes": component.scopes.all(),
            "title": f"ویرایش {component.name}",
        },
    )


@can_edit_required
@require_POST
def component_scope_add(request, pk):
    component = get_object_or_404(SalaryComponent, pk=pk)
    form = ComponentScopeForm(request.POST, company=component.company)
    if form.is_valid():
        scope = form.save(commit=False)
        scope.component = component
        scope.save()
        messages.success(request, "دامنه شمول اضافه شد.")
    else:
        messages.error(request, form.errors.as_text())
    return redirect("component_edit", pk=component.pk)


@can_edit_required
@require_POST
def component_scope_delete(request, pk):
    scope = get_object_or_404(ComponentScope, pk=pk)
    component_pk = scope.component_id
    scope.delete()
    messages.info(request, "دامنه حذف شد. حالا این قلم به همه پرسنل تعلق می‌گیرد.")
    return redirect("component_edit", pk=component_pk)


@can_edit_required
def legal_parameter_edit(request, pk):
    params = get_object_or_404(LegalParameter.objects.select_related("fiscal_year"), pk=pk)
    form = LegalParameterForm(request.POST or None, instance=params)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            "پارامترهای سال ذخیره شد. دوره‌های محاسبه‌شده باید دوباره محاسبه شوند "
            "تا این مقادیر اعمال گردد.",
        )
        return redirect(f"/settings/fiscal/?year={params.fiscal_year_id}")
    return render(
        request,
        "settings/params_form.html",
        {"form": form, "params": params, "fiscal_year": params.fiscal_year},
    )


@can_edit_required
def tax_brackets_edit(request, pk):
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    queryset = TaxBracket.objects.filter(
        fiscal_year=fiscal_year, basis=TaxBracket.Basis.MONTHLY
    ).order_by("row_order")

    formset = TaxBracketFormSet(request.POST or None, queryset=queryset)
    if request.method == "POST" and formset.is_valid():
        brackets = formset.save(commit=False)
        for bracket in brackets:
            bracket.fiscal_year = fiscal_year
            bracket.basis = TaxBracket.Basis.MONTHLY
            bracket.save()
        for bracket in formset.deleted_objects:
            bracket.delete()
        messages.success(request, "پلکان مالیات ذخیره شد.")
        return redirect(f"/settings/fiscal/?year={fiscal_year.pk}")

    return render(
        request,
        "settings/brackets_form.html",
        {"formset": formset, "fiscal_year": fiscal_year},
    )


@payroll_staff_required
def fiscal_settings(request):
    year_id = request.GET.get("year")
    years = FiscalYear.objects.select_related("company").order_by("-year")
    fiscal_year = years.filter(pk=year_id).first() if year_id else years.first()

    params = None
    brackets = []
    if fiscal_year:
        params = (
            LegalParameter.objects.filter(fiscal_year=fiscal_year)
            .order_by("-effective_from")
            .first()
        )
        brackets = TaxBracket.objects.filter(
            fiscal_year=fiscal_year, basis=TaxBracket.Basis.MONTHLY
        ).order_by("row_order")

    return render(
        request,
        "settings/fiscal.html",
        {
            "years": years,
            "fiscal_year": fiscal_year,
            "params": params,
            "brackets": brackets,
        },
    )
