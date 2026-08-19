"""اجرای آزمایشی — «اگر این را عوض کنم، چه می‌شود؟»

کارشناس حقوق و دستمزد در اکسل عادت دارد عددی را عوض کند، اثرش را روی کل ستون
ببیند، و اگر خوشش نیامد `Ctrl+Z` بزند. اینجا همان کار ممکن است، ولی با یک
تفاوت مهم: **هیچ چیزی ذخیره نمی‌شود.** نه فیشی، نه پارامتری، نه سطری.

دو قاعده‌ای که این فایل را قابل اعتماد می‌کند:

۱. **پیاده‌سازی دوم وجود ندارد.** شبیه‌سازی همان `compute_lines` موتور را صدا
   می‌زند و همان ورودی‌ها را از `gather_period_inputs` می‌گیرد. اگر عددی که
   کاربر پیش از تصمیم می‌بیند با عددی که بعد از تأیید در فیش می‌نشیند فرق
   داشته باشد، کل این صفحه بی‌ارزش است.

۲. **بدون تغییر، باید عیناً همان اعداد فیش‌های ذخیره‌شده دربیاید.** این
   آزمون پذیرش این فایل است و در `probe` بررسی می‌شود.

تغییرها دو دسته‌اند و هر دو فقط در حافظه اعمال می‌شوند:

    params_overrides     {"min_daily_wage": "6000000", ...}
    component_overrides  {component_id: {"rate": "0.3", "fixed_amount": "…"}}
"""

from decimal import Decimal, InvalidOperation

from apps.payroll.utils import quantize_rial

ZERO = Decimal("0")

# فیلدهای قلم که در اجرای آزمایشی قابل تغییرند. عمداً محدود: نوع قلم و کلید
# قاعده‌اش تغییر نمی‌کند، چون آن دیگر «همین قلم با عدد دیگر» نیست.
COMPONENT_FIELDS = {"rate", "fixed_amount"}

# پارامترهای سالی که در اجرای آزمایشی قابل تغییرند، با برچسب فارسی و واحدشان.
# عمداً فهرست بسته است: پارامتری که اثرش روی محاسبه روشن نیست، در این صفحه
# جایی ندارد.
TESTABLE_PARAMS = [
    ("min_daily_wage", "حداقل دستمزد روزانه", "ریال"),
    ("housing_allowance", "حق مسکن ماهانه", "ریال"),
    ("food_allowance", "بن کارگری ماهانه", "ریال"),
    ("child_allowance", "حق اولاد هر فرزند", "ریال"),
    ("seniority_daily", "پایه سنوات روزانه", "ریال"),
    ("ins_employee_rate", "نرخ بیمه سهم کارگر", "ضریب (۰٫۰۷ = ۷٪)"),
    ("ins_employer_rate", "نرخ بیمه سهم کارفرما", "ضریب (۰٫۲۰ = ۲۰٪)"),
    ("unemployment_rate", "نرخ بیمه بیکاری", "ضریب (۰٫۰۳ = ۳٪)"),
    ("overtime_factor", "ضریب اضافه‌کاری", "ضریب (۱٫۴)"),
    ("ins_ceiling_factor", "ضریب سقف بیمه", "ضریب"),
    ("rounding_unit", "واحد گرد کردن خالص", "ریال"),
]
PARAM_LABELS = {key: label for key, label, _ in TESTABLE_PARAMS}


def _decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("٬", "").strip())
    except (InvalidOperation, ValueError):
        return None


class SimulatedParams:
    """پارامترهای دوره با روکشِ تغییرهای آزمایشی.

    روی `EffectiveParams` سوار می‌شود (که خودش سالانه + ماهانه را لایه کرده)،
    پس ترتیب خواندن می‌شود: **آزمایشی → ماهانه → سالانه**.
    """

    def __init__(self, base, overrides=None):
        self._base = base
        self._overrides = {}
        for key, value in (overrides or {}).items():
            number = _decimal(value)
            if number is not None:
                self._overrides[key] = number

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._base, name)

    # این دو، مشتقِ حداقل دستمزدند و باید روکش را ببینند، نه مقدار پایه را.
    @property
    def min_monthly_wage(self):
        return self.min_daily_wage * self.monthly_days

    @property
    def insurance_ceiling(self):
        return self.min_monthly_wage * self.ins_ceiling_factor

    def as_snapshot(self):
        data = self._base.as_snapshot()
        data.update({key: str(value) for key, value in self._overrides.items()})
        return data


def _apply_component_overrides(components, overrides):
    """کپیِ درون‌حافظه‌ای اقلام با مقادیر تازه.

    خودِ نمونه‌های queryset دستکاری می‌شوند ولی هرگز `save()` نمی‌شوند؛ همان
    شیء بعد از پایان درخواست دور ریخته می‌شود.
    """
    if not overrides:
        return components, {}
    changed = {}
    for component in components:
        patch = overrides.get(str(component.pk)) or overrides.get(component.pk)
        if not patch:
            continue
        for field, value in patch.items():
            if field not in COMPONENT_FIELDS:
                continue
            number = _decimal(value)
            if number is None:
                continue
            before = getattr(component, field)
            if before == number:
                continue
            setattr(component, field, number)
            changed[component.code] = {
                "name": component.name, "field": field,
                "before": before, "after": number,
            }
    return components, changed


def simulate_period(period, params_overrides=None, component_overrides=None):
    """محاسبهٔ کل دوره با تغییرهای فرضی — بدون ذخیره.

    خروجی: `{"cells": {(employee_id, code): amount}, "totals": {...},
    "changes": [...]}`؛ برگهٔ محاسبه با همین کلیدها ستون تفاوت را می‌سازد.
    """
    from apps.payroll.engine.context import PayrollContext
    from apps.payroll.engine.runner import (
        compute_lines,
        gather_period_inputs,
        resolve_effective_params,
        resolve_legal_parameter,
    )
    from apps.payroll.models import CommissionAllocation

    legal_parameter = resolve_legal_parameter(period)
    params = SimulatedParams(
        resolve_effective_params(period, legal_parameter), params_overrides
    )

    data = gather_period_inputs(period, params, include_deducted=True)
    components, component_changes = _apply_component_overrides(
        data["components"], component_overrides
    )

    # تخصیص پورسانتِ **موجود** خوانده می‌شود، نه ساخته: ساختنش می‌نویسد و
    # اجرای آزمایشی حق نوشتن ندارد.
    allocations = {
        item.employee_id: item
        for item in CommissionAllocation.objects.filter(period=period)
    }

    cells, totals, employees = {}, {}, {}
    for contract in data["contracts"]:
        employee = contract.employee
        ctx = PayrollContext(
            period=period,
            employee=employee,
            contract=contract,
            timesheet=data["timesheets"].get(employee.pk),
            params=params,
            children_count=employee.children_count_on(period.end_date),
            manual_inputs=data["manual_inputs"].get(employee.pk, {}),
            contract_allowances=data["allowances"].get(contract.pk, {}),
            due_installments=data["installments"].get(employee.pk, []),
            allocation=allocations.get(employee.pk),
        )
        pending, employer_extra, _ = compute_lines(ctx, components)
        employees[employee.pk] = {
            "gross": quantize_rial(ctx.gross),
            "deductions": quantize_rial(ctx.total_deductions),
            "net": quantize_rial(ctx.net_payable),
            "employer_cost": quantize_rial(ctx.gross + employer_extra),
        }
        for component, result in pending:
            # همان عددی که اگر ذخیره می‌شد در فیش می‌نشست: مبلغ‌ها گرد شده و
            # اقلامِ روز/ساعت با مقدارشان، نه با مبلغ صفرشان.
            if component.display_unit in ("DAY", "HOUR"):
                value = result.quantity
            else:
                value = quantize_rial(result.amount)
            cells[(employee.pk, component.code)] = value
            totals[component.code] = totals.get(component.code, ZERO) + quantize_rial(
                result.amount
            )

    return {
        "cells": cells,
        "totals": totals,
        "employees": employees,
        "component_changes": list(component_changes.values()),
        "params_overrides": {
            key: value for key, value in (params_overrides or {}).items() if _decimal(value)
        },
    }
