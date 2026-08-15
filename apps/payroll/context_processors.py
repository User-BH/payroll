from apps.payroll.models import PayrollPeriod

# نگاشت نام مسیر به بخش منو. با این کار هیچ ویویی لازم نیست section را دستی
# بفرستد و صفحات زیرمجموعه (مثل جزئیات یک فیش) هم منوی درستشان روشن می‌ماند.
NAV_SECTIONS = {
    "dashboard": "dashboard",
    "employee_list": "employees",
    "employee_rows": "employees",
    "employee_detail": "employees",
    "employee_create": "employees",
    "employee_edit": "employees",
    "employee_import": "employees",
    "contract_create": "employees",
    "contract_edit": "employees",
    "bank_account_create": "employees",
    "dependent_create": "employees",
    "period_create": "periods",
    "manual_inputs": "manual",
    "manual_input_save": "manual",
    "period_list": "periods",
    "period_detail": "periods",
    "period_calculate": "periods",
    "period_transition": "periods",
    "timesheet_grid": "timesheets",
    "timesheet_rows": "timesheets",
    "timesheet_save": "timesheets",
    "payslip_list": "payslips",
    "payslip_detail": "payslips",
    "payslip_print": "payslips",
    "dispute_list": "disputes",
    "dispute_resolve": "disputes",
    "component_list": "components",
    "component_toggle": "components",
    "reports": "reports",
    "report_insurance": "reports",
    "report_tax": "reports",
    "report_bank": "reports",
    "report_export": "reports",
    "fiscal_settings": "fiscal",
    "legal_parameter_edit": "fiscal",
    "tax_brackets_edit": "fiscal",
    "component_create": "components",
    "component_edit": "components",
    "component_scope_add": "components",
    "entitlement_list": "leave",
    "entitlement_save": "leave",
    "entitlement_fill_all": "leave",
    "portal_accounts": "portal_accounts",
    "portal_accounts_create": "portal_accounts",
    "portal_account_reset": "portal_accounts",
}


def current_period(request):
    """دوره جاری و بخش فعال منو، برای همه صفحات."""
    if not request.user.is_authenticated:
        return {}

    match = getattr(request, "resolver_match", None)
    section = NAV_SECTIONS.get(match.url_name) if match else None

    period = (
        PayrollPeriod.objects.select_related("company")
        .order_by("-year", "-month")
        .first()
    )
    return {"current_period": period, "section": section}
