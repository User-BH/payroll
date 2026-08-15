from apps.payroll.models import PayrollPeriod

# نگاشت نام مسیر به بخش منو. با این کار هیچ ویویی لازم نیست section را دستی
# بفرستد و صفحات زیرمجموعه (مثل جزئیات یک فیش) هم منوی درستشان روشن می‌ماند.
NAV_SECTIONS = {
    "dashboard": "dashboard",
    "employee_list": "employees",
    "employee_rows": "employees",
    "employee_detail": "employees",
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
