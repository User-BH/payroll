"""صفحهٔ فرمول‌ها — آنچه موتور **واقعاً** انجام می‌دهد.

هیچ متنی اینجا دربارهٔ محاسبه نوشته نشده. توضیح هر قلم از دو جای زنده می‌آید:

  ۱) **مستند خودِ قاعده** در موتور (`func.__doc__`). اگر فردا فرمولی عوض شود و
     مستندش با آن عوض شود، این صفحه هم عوض می‌شود.
  ۲) **توضیح یک سطر واقعی فیش** — همان رشته‌ای که خودِ قاعده هنگام محاسبه
     ساخته و در `PayslipLine.explanation` نشسته است. این دیگر توصیف نیست،
     ردِ پای همان اجرا است.

اگر اینجا فرمول را دوباره می‌نوشتیم، اولین باری که موتور عوض می‌شد این صفحه
دروغ می‌گفت — و کسی که به آن اعتماد کرده بود، دیرتر از همه می‌فهمید.

سمتِ اکسل تصویر ثابتی است در `excel_reference.py`، چون فایل شرکت روی سرور
نیست. تفاوتِ این دو، همان چیزی است که باید دیده شود.
"""

import inspect

from apps.payroll.engine.rules import RULES, get_rule
from apps.payroll.models import PayslipLine
from apps.payroll_config.models import SalaryComponent

try:
    from apps.payroll.excel_reference import EXCEL_FORMULAS, SOURCE
except ImportError:  # نگاشت هنوز ساخته نشده
    EXCEL_FORMULAS, SOURCE = {}, ""


def _doc(func) -> str:
    """مستند قاعده، بدون تورفتگیِ کد."""
    return inspect.cleandoc(func.__doc__ or "").strip()


def _how(component) -> tuple:
    """(عنوان روش، شرح) — از پیکربندی خودِ قلم."""
    kind = component.calc_type
    if kind == SalaryComponent.CalcType.ENGINE_RULE:
        func = get_rule(component.engine_rule_key)
        if func is None:
            return "قاعدهٔ موتور", f"قاعده‌ای با کلید «{component.engine_rule_key}» ثبت نشده است."
        return f"قاعدهٔ موتور · {component.engine_rule_key}", _doc(func)
    if kind == SalaryComponent.CalcType.PARAMETRIC:
        return "قاعدهٔ پارامتری", component.formula_label()
    if kind == SalaryComponent.CalcType.PERCENTAGE:
        base = component.base_component.name if component.base_component else "—"
        return "درصدی از قلم دیگر", f"{component.rate * 100}٪ از «{base}»"
    if kind == SalaryComponent.CalcType.FIXED:
        return "مبلغ ثابت", f"{component.fixed_amount:,.0f} ریال در هر دوره"
    return "ورود دستی", "مبلغش هر دوره در «مبالغ دستی» وارد می‌شود و محاسبه‌ای ندارد."


def _samples(codes, limit=2):
    """توضیحِ چند سطر واقعی از تازه‌ترین فیش‌ها.

    این‌ها را قاعده هنگام محاسبه نوشته است، پس اگر فرمول عوض شود بدون اینکه
    کسی این صفحه را دست بزند، همین‌جا عوض می‌شوند.
    """
    rows = (
        PayslipLine.objects.filter(component_code__in=codes)
        .exclude(explanation="")
        .select_related("payslip__employee", "payslip__period")
        .order_by("-payslip__period__year", "-payslip__period__month", "-id")[:limit]
    )
    return [
        {
            "who": row.payslip.employee.full_name,
            "period": row.payslip.period.title,
            "amount": row.amount,
            "text": row.explanation,
        }
        for row in rows
    ]


def build(company):
    """فهرست اقلام با روش محاسبه، نمونهٔ زنده، و فرمول اکسل کنارش."""
    components = list(
        SalaryComponent.objects.filter(company=company, is_active=True)
        .select_related("base_component")
        .prefetch_related("scopes", "absorbs")
        .order_by("kind", "sequence")
    )
    from apps.payroll_config.models import annotate_config_labels

    annotate_config_labels(components)

    groups, matched, missing = {}, 0, []
    for component in components:
        how, detail = _how(component)
        excel = EXCEL_FORMULAS.get(component.code)
        if excel:
            matched += 1
        elif component.kind != SalaryComponent.Kind.INFO:
            missing.append(component)
        groups.setdefault(component.get_kind_display(), []).append({
            "component": component,
            "how": how,
            "detail": detail,
            "samples": _samples([component.code]),
            "excel": excel,
            "scopes": [scope.target_label() for scope in component.scopes.all()],
            "absorbs": [item.name for item in component.absorbs.all()],
        })

    return {
        "groups": groups,
        "excel_source": SOURCE,
        "excel_matched": matched,
        "excel_missing": missing,
        "rule_count": len(RULES),
    }
