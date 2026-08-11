from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import can_edit_required, payroll_staff_required
from apps.payroll_config.models import FiscalYear, LegalParameter, SalaryComponent, TaxBracket


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
