"""قواعد محاسبه.

تصمیم معماری: منطق محاسبه در کد است، نه در دیتابیس. هر قاعده یک تابع خالص با
یک کلید ثابت است؛ دیتابیس فقط می‌گوید کدام قاعده، با چه ضریبی، با چه ترتیبی، و
مشمول بیمه/مالیات هست یا نه.

دلیل: باگ در حقوق و دستمزد مسئولیت قانونی و مالی دارد. کد قطعی و تست‌پذیر خیلی
ارزشمندتر از انعطافِ فرمول‌نویسی داخل دیتابیس (و eval کردن آن) است.
"""

from decimal import Decimal

from apps.payroll.engine.context import ZERO, LineResult, PayrollContext
from apps.payroll.utils import fa_money, fa_number

RULES = {}


def rule(key: str, label: str = ""):
    def decorator(func):
        func.rule_key = key
        func.rule_label = label or key
        RULES[key] = func
        return func

    return decorator


def get_rule(key: str):
    return RULES.get(key)


# ==================================================================== مزایا


@rule("base_salary", "حقوق پایه")
def base_salary(ctx: PayrollContext, component):
    days = ctx.paid_days
    daily = ctx.daily_base
    amount = daily * days
    return LineResult(
        amount=amount,
        base_amount=ctx.contract.base_salary,
        quantity=days,
        rate=Decimal("1"),
        explanation=(
            f"حقوق پایه: {fa_number(days)} روز × {fa_money(daily)} ریال مزد روزانه"
        ),
    ).rounded()


@rule("seniority", "پایه سنوات")
def seniority(ctx: PayrollContext, component):
    if ctx.contract.seniority_years < 1:
        return None
    daily = ctx.params.seniority_daily
    days = ctx.paid_days
    return LineResult(
        amount=daily * days,
        base_amount=daily,
        quantity=days,
        rate=Decimal("1"),
        explanation=(
            f"پایه سنوات: {fa_number(days)} روز × {fa_money(daily)} ریال "
            f"(سابقه {fa_number(ctx.contract.seniority_years)} سال)"
        ),
    ).rounded()


@rule("housing_allowance", "حق مسکن")
def housing_allowance(ctx: PayrollContext, component):
    monthly = ctx.params.housing_allowance
    return _prorated(ctx, monthly, "حق مسکن")


@rule("food_allowance", "بن کارگری")
def food_allowance(ctx: PayrollContext, component):
    monthly = ctx.params.food_allowance
    return _prorated(ctx, monthly, "بن کارگری")


def _prorated(ctx: PayrollContext, monthly_amount: Decimal, label: str):
    """مزایای ثابت ماهانه که به نسبت روز کارکرد تسهیم می‌شوند."""
    ratio = ctx.day_ratio
    amount = monthly_amount * ratio
    return LineResult(
        amount=amount,
        base_amount=monthly_amount,
        quantity=ctx.paid_days,
        rate=ratio,
        explanation=(
            f"{label}: {fa_money(monthly_amount)} ریال × "
            f"{fa_number(ctx.paid_days)} ÷ {fa_number(ctx.month_days)} روز"
        ),
    ).rounded()


@rule("child_allowance", "حق اولاد")
def child_allowance(ctx: PayrollContext, component):
    count = ctx.children_count
    if count <= 0:
        return None
    max_children = ctx.params.max_children or 0
    effective = min(count, max_children) if max_children else count
    per_child = ctx.params.child_allowance
    ratio = ctx.day_ratio
    amount = per_child * effective * ratio
    note = ""
    if max_children and count > max_children:
        note = f" (از {fa_number(count)} فرزند، {fa_number(max_children)} فرزند مشمول)"
    return LineResult(
        amount=amount,
        base_amount=per_child,
        quantity=Decimal(effective),
        rate=ratio,
        explanation=(
            f"حق اولاد: {fa_number(effective)} فرزند × {fa_money(per_child)} ریال × "
            f"{fa_number(ctx.paid_days)} ÷ {fa_number(ctx.month_days)} روز{note}"
        ),
    ).rounded()


def _hourly_rule(ctx: PayrollContext, hours: Decimal, factor: Decimal, label: str):
    if not hours or hours <= 0:
        return None
    hourly = ctx.hourly_base
    amount = hourly * factor * hours
    return LineResult(
        amount=amount,
        base_amount=hourly,
        quantity=hours,
        rate=factor,
        explanation=(
            f"{label}: {fa_number(hours, 2)} ساعت × {fa_money(hourly)} ریال "
            f"مزد ساعتی × {fa_number(factor, 3)}"
        ),
    ).rounded()


@rule("overtime", "اضافه‌کاری")
def overtime(ctx: PayrollContext, component):
    if not ctx.timesheet:
        return None
    return _hourly_rule(
        ctx, ctx.timesheet.overtime_hours, ctx.params.overtime_factor, "اضافه‌کاری"
    )


@rule("night_work", "شب‌کاری")
def night_work(ctx: PayrollContext, component):
    if not ctx.timesheet:
        return None
    return _hourly_rule(ctx, ctx.timesheet.night_hours, ctx.params.night_factor, "شب‌کاری")


@rule("friday_work", "جمعه‌کاری")
def friday_work(ctx: PayrollContext, component):
    if not ctx.timesheet:
        return None
    return _hourly_rule(ctx, ctx.timesheet.friday_hours, ctx.params.friday_factor, "جمعه‌کاری")


@rule("holiday_work", "تعطیل‌کاری")
def holiday_work(ctx: PayrollContext, component):
    if not ctx.timesheet:
        return None
    return _hourly_rule(ctx, ctx.timesheet.holiday_hours, ctx.params.holiday_factor, "تعطیل‌کاری")


@rule("shift_work", "نوبت‌کاری")
def shift_work(ctx: PayrollContext, component):
    if not ctx.timesheet:
        return None
    shift = ctx.timesheet.shift_type
    rates = ctx.params.shift_rates or {}
    raw = rates.get(shift)
    if not raw:
        return None
    factor = Decimal(str(raw))
    base = ctx.amount_of("BASE_SALARY")
    amount = base * factor
    return LineResult(
        amount=amount,
        base_amount=base,
        quantity=Decimal("1"),
        rate=factor,
        explanation=(
            f"نوبت‌کاری ({ctx.timesheet.get_shift_type_display()}): "
            f"{fa_money(base)} ریال × {fa_number(factor * 100, 2)}٪"
        ),
    ).rounded()


@rule("contract_allowance", "مزایای مستمر قرارداد")
def contract_allowance(ctx: PayrollContext, component):
    monthly = ctx.contract_allowances.get(component.id)
    if not monthly:
        return None
    return _prorated(ctx, Decimal(monthly), component.name)


@rule("manual_input", "ورود دستی دوره")
def manual_input(ctx: PayrollContext, component):
    """اقلامی مثل پورسانت فروش که مبلغشان از بیرون موتور می‌آید."""
    amount = ctx.manual_inputs.get(component.id)
    if not amount:
        return None
    return LineResult(
        amount=Decimal(amount),
        base_amount=Decimal(amount),
        quantity=Decimal("1"),
        rate=Decimal("1"),
        explanation=f"{component.name}: مبلغ ثبت‌شده برای دوره {ctx.period.title}",
    ).rounded()


@rule("percentage_of", "درصدی از قلم دیگر")
def percentage_of(ctx: PayrollContext, component):
    if not component.base_component_id:
        return None
    base = ctx.amount_of(component.base_component.code)
    if not base:
        return None
    factor = component.rate
    return LineResult(
        amount=base * factor,
        base_amount=base,
        quantity=Decimal("1"),
        rate=factor,
        explanation=(
            f"{component.name}: {fa_number(factor * 100, 2)}٪ از "
            f"{component.base_component.name} ({fa_money(base)} ریال)"
        ),
    ).rounded()


@rule("fixed_amount", "مبلغ ثابت")
def fixed_amount(ctx: PayrollContext, component):
    if not component.fixed_amount:
        return None
    return LineResult(
        amount=component.fixed_amount,
        base_amount=component.fixed_amount,
        quantity=Decimal("1"),
        rate=Decimal("1"),
        explanation=f"{component.name}: مبلغ ثابت ماهانه",
    ).rounded()


# ==================================================================== کسور


@rule("insurance_employee", "بیمه سهم کارگر")
def insurance_employee(ctx: PayrollContext, component):
    base = ctx.capped_insurable
    rate = ctx.params.ins_employee_rate
    ceiling = ctx.params.insurance_ceiling
    capped_note = ""
    if ceiling and ctx.insurable_base > ceiling:
        capped_note = (
            f" — مبنا از {fa_money(ctx.insurable_base)} به سقف قانونی "
            f"{fa_money(ceiling)} محدود شد"
        )
    return LineResult(
        amount=base * rate,
        base_amount=base,
        quantity=Decimal("1"),
        rate=rate,
        explanation=(
            f"بیمه سهم کارگر: {fa_money(base)} ریال × "
            f"{fa_number(rate * 100, 2)}٪{capped_note}"
        ),
    ).rounded()


@rule("income_tax", "مالیات بر درآمد حقوق")
def income_tax(ctx: PayrollContext, component):
    """مالیات پلکانی.

    نکته‌ای که باید با حسابدار شرکت تأیید شود: آیا بیمه سهم کارگر از درآمد مشمول
    مالیات کسر می‌شود؟ اینجا با پرچم deduct_insurance_from_tax_base کنترل می‌شود.
    """
    from apps.payroll_config.models import TaxBracket

    taxable = ctx.taxable_base
    ins_note = ""
    if ctx.params.deduct_insurance_from_tax_base:
        ins = ctx.amount_of("INSURANCE_EMP")
        taxable -= ins
        if ins:
            ins_note = f" (پس از کسر بیمه سهم کارگر {fa_money(ins)})"

    if taxable <= 0:
        return None

    brackets = list(
        TaxBracket.objects.filter(
            fiscal_year=ctx.period.fiscal_year, basis=TaxBracket.Basis.MONTHLY
        ).order_by("row_order")
    )
    if not brackets:
        return None

    total = ZERO
    applied = []
    for bracket in brackets:
        lower = bracket.from_amount
        if taxable <= lower:
            break
        upper = bracket.to_amount if bracket.to_amount is not None else taxable
        portion = min(taxable, upper) - lower
        if portion <= 0:
            continue
        if bracket.rate > 0:
            total += portion * bracket.rate
            applied.append(f"{fa_money(portion)}×{fa_number(bracket.rate * 100, 0)}٪")

    if total <= 0:
        return None

    detail = " + ".join(applied)
    return LineResult(
        amount=total,
        base_amount=taxable,
        quantity=Decimal("1"),
        rate=(total / taxable) if taxable else ZERO,
        explanation=(
            f"مالیات پلکانی بر مبنای {fa_money(taxable)} ریال{ins_note}: {detail}"
        ),
    ).rounded()


@rule("loan_installment", "اقساط وام و مساعده")
def loan_installment(ctx: PayrollContext, component):
    if not ctx.due_installments:
        return None
    total = sum((item.amount for item in ctx.due_installments), ZERO)
    if total <= 0:
        return None
    count = len(ctx.due_installments)
    titles = "، ".join(
        f"{item.loan.get_loan_type_display()} قسط {fa_number(item.number)}"
        for item in ctx.due_installments[:3]
    )
    more = f" و {fa_number(count - 3)} مورد دیگر" if count > 3 else ""
    return LineResult(
        amount=total,
        base_amount=total,
        quantity=Decimal(count),
        rate=Decimal("1"),
        explanation=f"کسر اقساط سررسیدشده: {titles}{more}",
    ).rounded()


@rule("deduction_manual", "کسور دستی")
def deduction_manual(ctx: PayrollContext, component):
    amount = ctx.manual_inputs.get(component.id)
    if not amount:
        return None
    return LineResult(
        amount=Decimal(amount),
        base_amount=Decimal(amount),
        quantity=Decimal("1"),
        rate=Decimal("1"),
        explanation=f"{component.name}: مبلغ ثبت‌شده برای دوره {ctx.period.title}",
    ).rounded()


# ============================================================ هزینه کارفرما


@rule("insurance_employer", "بیمه سهم کارفرما")
def insurance_employer(ctx: PayrollContext, component):
    base = ctx.capped_insurable
    rate = ctx.params.ins_employer_rate
    return LineResult(
        amount=base * rate,
        base_amount=base,
        quantity=Decimal("1"),
        rate=rate,
        explanation=(
            f"بیمه سهم کارفرما: {fa_money(base)} ریال × {fa_number(rate * 100, 2)}٪"
        ),
    ).rounded()


@rule("unemployment_insurance", "بیمه بیکاری")
def unemployment_insurance(ctx: PayrollContext, component):
    base = ctx.capped_insurable
    rate = ctx.params.unemployment_rate
    return LineResult(
        amount=base * rate,
        base_amount=base,
        quantity=Decimal("1"),
        rate=rate,
        explanation=(
            f"بیمه بیکاری (سهم کارفرما): {fa_money(base)} ریال × "
            f"{fa_number(rate * 100, 2)}٪"
        ),
    ).rounded()
