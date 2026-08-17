"""اجراکننده محاسبه.

ترتیب اجرا عمدی است و سه پاس دارد:
  ۱) مزایا      → ناخالص، مبنای بیمه و مبنای مالیات ساخته می‌شوند
  ۲) کسور       → بیمه و مالیات روی مبناهای کامل‌شده محاسبه می‌شوند
  ۳) هزینه کارفرما

اگر بیمه و مالیات با مزایا در یک پاس محاسبه می‌شدند، ترتیب اقلام روی نتیجه اثر
می‌گذاشت — و این دقیقاً همان خطایی است که در سامانه‌های حقوق دیر کشف می‌شود.
"""

import hashlib
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.attendance.leave import compute_balance
from apps.attendance.models import Timesheet
from apps.employees.models import ContractAllowance, EmploymentContract
from apps.loans.models import Loan, LoanInstallment
from apps.payroll.engine import rules as rules_module
from apps.payroll.engine.context import ZERO, LineResult, PayrollContext
from apps.payroll.engine.rules import get_rule
from apps.payroll.models import (
    PayrollInput,
    PayrollPeriod,
    PayrollRun,
    Payslip,
    PayslipLine,
)
from apps.payroll.utils import fa_money, fa_number, floor_to_unit, quantize_rial
from apps.payroll_config.models import LegalParameter, SalaryComponent

ROUNDING_COMPONENT_CODE = "ROUNDING_ADJ"


class CalculationError(Exception):
    pass


def resolve_legal_parameter(period) -> LegalParameter:
    """پارامتر قانونی معتبر در پایان دوره."""
    params = (
        LegalParameter.objects.filter(
            fiscal_year=period.fiscal_year, effective_from__lte=period.end_date
        )
        .order_by("-effective_from")
        .first()
    )
    if not params:
        raise CalculationError(
            f"برای سال مالی {period.fiscal_year.year} پارامتر قانونی تعریف نشده است."
        )
    return params


def _rule_for(component):
    """انتخاب قاعده بر اساس نحوه محاسبه قلم."""
    if component.calc_type == SalaryComponent.CalcType.ENGINE_RULE:
        return get_rule(component.engine_rule_key)
    if component.calc_type == SalaryComponent.CalcType.FIXED:
        return rules_module.fixed_amount
    if component.calc_type == SalaryComponent.CalcType.PERCENTAGE:
        return rules_module.percentage_of
    if component.calc_type == SalaryComponent.CalcType.MANUAL:
        if component.kind == SalaryComponent.Kind.DEDUCTION:
            return rules_module.deduction_manual
        return rules_module.manual_input
    return None


def _hash_context(ctx: PayrollContext) -> str:
    parts = [
        str(ctx.employee.pk),
        str(ctx.contract.pk),
        str(ctx.paid_days),
        str(ctx.gross),
        str(ctx.total_deductions),
        str(ctx.params.pk),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def calculate_payslip(ctx: PayrollContext, components, run=None) -> Payslip:
    """محاسبه و ثبت فیش یک پرسنل. باید داخل transaction صدا زده شود."""
    by_kind = {
        SalaryComponent.Kind.EARNING: [],
        SalaryComponent.Kind.DEDUCTION: [],
        SalaryComponent.Kind.EMPLOYER_COST: [],
    }
    for component in components:
        if component.code == ROUNDING_COMPONENT_CODE:
            continue
        if component.kind in by_kind and component.applies_to(ctx.contract):
            by_kind[component.kind].append(component)

    # بدون بیمه (قرارداد غیرمشمول، یا پرسنل بازنشسته):
    # نه کسر سهم کارگر، نه هزینه بیمه کارفرما
    if not ctx.insurance_applies:
        by_kind[SalaryComponent.Kind.DEDUCTION] = [
            c
            for c in by_kind[SalaryComponent.Kind.DEDUCTION]
            if c.engine_rule_key != "insurance_employee"
        ]
        by_kind[SalaryComponent.Kind.EMPLOYER_COST] = [
            c
            for c in by_kind[SalaryComponent.Kind.EMPLOYER_COST]
            if c.engine_rule_key
            not in {"insurance_employer", "unemployment_insurance"}
        ]

    pending = []
    loan_line_position = None

    def run_pass(kind):
        nonlocal loan_line_position
        for component in by_kind[kind]:
            func = _rule_for(component)
            if func is None:
                continue
            result = func(ctx, component)
            if result is None or result.amount == ZERO:
                continue
            ctx.register(component, result)
            if component.engine_rule_key == "loan_installment":
                loan_line_position = len(pending)
            pending.append((component, result))

    run_pass(SalaryComponent.Kind.EARNING)
    run_pass(SalaryComponent.Kind.DEDUCTION)
    run_pass(SalaryComponent.Kind.EMPLOYER_COST)

    # گرد کردن خالص پرداختی. اختلاف به‌صورت یک سطر شفاف ثبت می‌شود تا جمع
    # سطرهای فیش همیشه دقیقاً برابر خالص باشد.
    net = ctx.net_payable
    unit = ctx.params.rounding_unit or 1
    rounded_net = floor_to_unit(net, unit)
    diff = quantize_rial(net - rounded_net)
    if diff > 0:
        adjustment = next(
            (c for c in components if c.code == ROUNDING_COMPONENT_CODE), None
        )
        if adjustment:
            result = LineResult(
                amount=diff,
                base_amount=quantize_rial(net),
                quantity=Decimal("1"),
                rate=ZERO,
                explanation=(
                    f"تعدیل گرد کردن: خالص {fa_money(net)} به {fa_money(rounded_net)} "
                    f"ریال گرد شد (واحد {fa_number(unit)} ریال)"
                ),
            )
            ctx.register(adjustment, result)
            pending.append((adjustment, result))

    employer_extra = sum(
        (
            result.amount
            for component, result in pending
            if component.kind == SalaryComponent.Kind.EMPLOYER_COST
        ),
        ZERO,
    )

    payslip = Payslip.objects.create(
        period=ctx.period,
        employee=ctx.employee,
        contract=ctx.contract,
        run=run,
        department=ctx.contract.department,
        cost_center=ctx.contract.cost_center,
        iban_snapshot=getattr(ctx.employee.default_bank_account, "iban", "") or "",
        account_snapshot=getattr(ctx.employee.default_bank_account, "account_number", "") or "",
        bank_snapshot=getattr(ctx.employee.default_bank_account, "bank_name", "") or "",
        insurance_applies=ctx.insurance_applies,
        # طول ماه از تقویم دوره می‌آید نه از پارامتر ثابت، پس باید داخل
        # snapshot ثبت شود وگرنه فیش قفل‌شده مخرج محاسبه‌اش را از دست می‌دهد.
        params_snapshot={**ctx.params.as_snapshot(), "month_days": str(ctx.month_days)},
        leave_snapshot=compute_balance(
            ctx.employee, ctx.period, ctx.params.leave_day_minutes
        ).as_snapshot(),
        work_days=ctx.paid_days,
        gross_total=quantize_rial(ctx.gross),
        insurable_base=quantize_rial(ctx.insurable_base),
        taxable_base=quantize_rial(ctx.taxable_base),
        total_deductions=quantize_rial(ctx.total_deductions),
        net_payable=quantize_rial(ctx.net_payable),
        tax_amount=quantize_rial(ctx.amount_of("INCOME_TAX")),
        ins_employee=quantize_rial(ctx.amount_of("INSURANCE_EMP")),
        ins_employer=quantize_rial(ctx.amount_of("INSURANCE_EMPLOYER")),
        employer_total_cost=quantize_rial(ctx.gross + employer_extra),
        calc_hash=_hash_context(ctx),
    )

    PayslipLine.objects.bulk_create(
        [
            PayslipLine(
                payslip=payslip,
                component=component,
                component_code=component.code,
                component_name=component.name,
                kind=component.kind,
                sequence=component.sequence,
                base_amount=result.base_amount,
                quantity=result.quantity,
                rate=result.rate,
                amount=result.amount,
                is_insurable=component.is_insurable,
                is_taxable=component.is_taxable,
                explanation=result.explanation[:255],
            )
            for component, result in pending
        ]
    )

    # اتصال اقساط به سطری که کسرشان کرده — تا بعداً قابل ردیابی باشد
    if loan_line_position is not None and ctx.due_installments:
        component, _ = pending[loan_line_position]
        loan_line = payslip.lines.filter(component_code=component.code).first()
        if loan_line:
            now = timezone.now()
            for installment in ctx.due_installments:
                installment.status = LoanInstallment.Status.DEDUCTED
                installment.payslip_line = loan_line
                installment.deducted_at = now
            LoanInstallment.objects.bulk_update(
                ctx.due_installments, ["status", "payslip_line", "deducted_at"]
            )

    return payslip


@transaction.atomic
def calculate_period(period: PayrollPeriod, user=None) -> PayrollRun:
    """محاسبه کل دوره — یا همه یا هیچ.

    اگر فیش نفر نودم خطا داد، ۸۹ فیش قبلی هم نباید بمانند؛ وگرنه دوره در حالت
    نیمه‌محاسبه گیر می‌کند.
    """
    if period.is_locked:
        raise CalculationError("دوره قفل شده است و قابل محاسبه مجدد نیست.")

    params = resolve_legal_parameter(period)

    run = PayrollRun.objects.create(
        period=period,
        run_by=user,
        engine_version=getattr(settings, "PAYROLL_ENGINE_VERSION", "1.0.0"),
    )

    # پاک کردن نتیجه اجرای قبلی و برگرداندن اقساط به حالت سررسید
    LoanInstallment.objects.filter(
        due_year=period.year,
        due_month=period.month,
        status=LoanInstallment.Status.DEDUCTED,
    ).update(status=LoanInstallment.Status.DUE, payslip_line=None, deducted_at=None)
    Payslip.objects.filter(period=period, revision=0).delete()

    components = list(
        SalaryComponent.objects.filter(company=period.company, is_active=True)
        .select_related("base_component")
        .prefetch_related("scopes")
        .order_by("sequence", "id")
    )

    timesheets = {
        ts.employee_id: ts for ts in Timesheet.objects.filter(period=period)
    }

    manual_inputs = {}
    for item in PayrollInput.objects.filter(period=period):
        manual_inputs.setdefault(item.employee_id, {})[item.component_id] = item.amount

    allowances = {}
    allowance_qs = ContractAllowance.objects.filter(
        effective_from__lte=period.end_date
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=period.start_date))
    for allowance in allowance_qs:
        allowances.setdefault(allowance.contract_id, {})[
            allowance.component_id
        ] = allowance.amount

    installments = {}
    due_qs = LoanInstallment.objects.filter(
        due_year=period.year,
        due_month=period.month,
        status__in=[LoanInstallment.Status.PENDING, LoanInstallment.Status.DUE],
        loan__status=Loan.Status.ACTIVE,
    ).select_related("loan")
    for installment in due_qs:
        installments.setdefault(installment.loan.employee_id, []).append(installment)

    contracts = (
        EmploymentContract.objects.filter(
            status=EmploymentContract.Status.ACTIVE,
            effective_from__lte=period.end_date,
            employee__company=period.company,
            employee__status="ACTIVE",
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=period.start_date))
        .select_related("employee", "department", "cost_center", "job_title")
        .order_by("employee__personnel_code")
    )

    success = 0
    errors = []
    for contract in contracts:
        employee = contract.employee
        try:
            ctx = PayrollContext(
                period=period,
                employee=employee,
                contract=contract,
                timesheet=timesheets.get(employee.pk),
                params=params,
                children_count=employee.children_count_on(period.end_date),
                manual_inputs=manual_inputs.get(employee.pk, {}),
                contract_allowances=allowances.get(contract.pk, {}),
                due_installments=installments.get(employee.pk, []),
            )
            calculate_payslip(ctx, components, run=run)
            success += 1
        except Exception as exc:  # noqa: BLE001 — خطا در لاگ اجرا ثبت می‌شود
            errors.append(
                {
                    "personnel_code": employee.personnel_code,
                    "name": employee.full_name,
                    "error": str(exc),
                }
            )

    if errors:
        # transaction.atomic خودش rollback می‌کند؛ لاگ اجرا هم برمی‌گردد،
        # به همین دلیل پیام خطا از طریق استثنا به لایه ویو می‌رسد.
        raise CalculationError(
            f"محاسبه با {len(errors)} خطا متوقف شد و هیچ فیشی ثبت نشد. "
            f"اولین خطا — {errors[0]['name']}: {errors[0]['error']}"
        )

    _finalize_period(period, params, run, success)
    return run


def _finalize_period(period, params, run, success):
    totals = Payslip.objects.filter(period=period).aggregate(
        gross=Sum("gross_total"),
        net=Sum("net_payable"),
        deductions=Sum("total_deductions"),
        employer=Sum("employer_total_cost"),
    )
    period.total_gross = totals["gross"] or 0
    period.total_net = totals["net"] or 0
    period.total_deductions = totals["deductions"] or 0
    period.total_employer_cost = totals["employer"] or 0
    period.employee_count = success
    period.calculated_at = timezone.now()
    period.legal_parameter = params
    if period.status in {
        PayrollPeriod.Status.DRAFT,
        PayrollPeriod.Status.TIMESHEET_LOCKED,
    }:
        period.status = PayrollPeriod.Status.CALCULATED
    period.save()

    run.status = PayrollRun.Status.SUCCESS
    run.finished_at = timezone.now()
    run.success_count = success
    run.error_count = 0
    run.save()
