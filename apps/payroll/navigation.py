"""ساختار منو: پنج ورودی اصلی، و زبانه‌های هر بخش.

پیش از این منو ۱۷ ورودی داشت و شش تای آن‌ها ماه‌محور بودند — یعنی کاربر برای
هر کار باید یک بار از منو رد می‌شد و **دوباره دوره را انتخاب می‌کرد**. کار
ماهانه در عمل این‌طور نیست: یک ماه را باز می‌کنی و همه‌چیزش را همان‌جا انجام
می‌دهی، مثل شیت ماهانهٔ اکسل.

پس منو پنج ورودی شد و هر ورودی زبانه‌های خودش را بالای صفحه دارد. تودرتویی
فقط یک لایه است و آن یک لایه هم دیده می‌شود، نه اینکه در منو پنهان باشد.

`SECTIONS` تنها جای این نگاشت است: هر نام مسیر به یک بخش و یک زبانه. صفحه‌ای
که اینجا نیامده باشد، منوی روشنی ندارد — پس اضافه کردن صفحهٔ تازه یعنی یک
سطر اینجا.
"""

# نام مسیر → (بخش منو، کلید زبانه)
SECTIONS = {
    # ---------------------------------------------------------- داشبورد
    "dashboard": ("dashboard", ""),

    # ------------------------------------------------------------ پرسنل
    "employee_list": ("employees", "list"),
    "employee_rows": ("employees", "list"),
    "employee_detail": ("employees", "list"),
    "employee_create": ("employees", "list"),
    "employee_edit": ("employees", "list"),
    "employee_import": ("employees", "list"),
    "contract_create": ("employees", "list"),
    "contract_edit": ("employees", "list"),
    "bank_account_create": ("employees", "list"),
    "dependent_create": ("employees", "list"),
    "employee_timesheet_save": ("employees", "list"),
    "employee_terminate": ("employees", "list"),
    "employee_reactivate": ("employees", "list"),
    "loan_list": ("employees", "loans"),
    "loan_create": ("employees", "loans"),
    "loan_detail": ("employees", "loans"),
    "loan_edit": ("employees", "loans"),
    "loan_set_status": ("employees", "loans"),
    "leave_desk": ("employees", "leave_desk"),
    "leave_record_create": ("employees", "leave_desk"),
    "leave_record_edit": ("employees", "leave_desk"),
    "leave_record_cancel": ("employees", "leave_desk"),
    "leave_sync_period": ("employees", "leave_desk"),
    "entitlement_list": ("employees", "entitlements"),
    "entitlement_save": ("employees", "entitlements"),
    "entitlement_fill_all": ("employees", "entitlements"),
    "dispute_list": ("employees", "disputes"),
    "dispute_resolve": ("employees", "disputes"),

    # ------------------------------------------------------------- دوره
    "period_list": ("periods", "list"),
    "period_create": ("periods", "list"),
    "period_detail": ("periods", "detail"),
    "period_calculate": ("periods", "detail"),
    "period_transition": ("periods", "detail"),
    "timesheet_grid": ("periods", "timesheets"),
    "timesheet_rows": ("periods", "timesheets"),
    "timesheet_save": ("periods", "timesheets"),
    "timesheet_import": ("periods", "timesheets"),
    "timesheet_approve_all": ("periods", "timesheets"),
    "manual_inputs": ("periods", "manual"),
    "manual_input_save": ("periods", "manual"),
    "monthly_parameters": ("periods", "monthly"),
    "monthly_parameters_save": ("periods", "monthly"),
    "commission_allocations": ("periods", "commission"),
    "commission_allocations_save": ("periods", "commission"),
    "period_sheet": ("periods", "sheet"),
    "period_sheet_export": ("periods", "sheet"),
    "payslip_list": ("periods", "payslips"),
    "payslip_detail": ("periods", "payslips"),
    "payslip_print": ("periods", "payslips"),
    "payslip_batch_print": ("periods", "payslips"),
    "export_center": ("periods", "exports"),
    "export_generate": ("periods", "exports"),
    "export_download": ("periods", "exports"),
    "export_update_status": ("periods", "exports"),

    # --------------------------------------------------------- گزارش‌ها
    "reports": ("reports", "list"),
    "report_insurance": ("reports", "list"),
    "report_tax": ("reports", "list"),
    "report_bank": ("reports", "list"),
    "report_org": ("reports", "list"),
    "report_export": ("reports", "list"),

    # ---------------------------------------------------------- تنظیمات
    "settings_home": ("settings", "home"),
    "component_list": ("settings", "components"),
    "component_create": ("settings", "components"),
    "component_edit": ("settings", "components"),
    "component_toggle": ("settings", "components"),
    "component_scope_add": ("settings", "components"),
    "component_scope_delete": ("settings", "components"),
    "timesheet_items": ("settings", "timesheet_items"),
    "timesheet_item_toggle": ("settings", "timesheet_items"),
    "fiscal_settings": ("settings", "fiscal"),
    "legal_parameter_edit": ("settings", "fiscal"),
    "tax_brackets_edit": ("settings", "fiscal"),
    "org_settings": ("settings", "org"),
    "company_edit": ("settings", "org"),
    "org_item_create": ("settings", "org"),
    "org_item_edit": ("settings", "org"),
    "org_item_delete": ("settings", "org"),
    "staff_users": ("settings", "users"),
    "staff_user_create": ("settings", "users"),
    "staff_user_edit": ("settings", "users"),
    "portal_accounts": ("settings", "portal"),
    "portal_accounts_create": ("settings", "portal"),
    "portal_account_reset": ("settings", "portal"),
}

# مسیرهایی که پارامتر `pk` آن‌ها **شناسهٔ دوره** است. بقیهٔ مسیرهای بخش دوره
# (مثل جزئیات یک فیش) pk دیگری دارند و زبانه‌هایشان باید از دورهٔ خودِ آن
# رکورد بیاید، نه از این عدد.
PERIOD_PK_ROUTES = {
    "period_detail", "period_calculate", "period_transition",
    "timesheet_grid", "timesheet_rows", "timesheet_save", "timesheet_import",
    "timesheet_approve_all", "manual_inputs", "manual_input_save",
    "monthly_parameters", "monthly_parameters_save",
    "commission_allocations", "commission_allocations_save",
    "period_sheet", "period_sheet_export", "payslip_list", "payslip_batch_print",
    "export_center", "export_generate", "export_update_status",
}


def _tabs_for(section, period, user):
    """زبانه‌های یک بخش — (کلید، عنوان، نام مسیر، آرگومان‌ها)."""
    can_edit = getattr(user, "can_edit_payroll", False)

    if section == "employees":
        tabs = [
            ("list", "فهرست پرسنل", "employee_list", []),
            ("loans", "وام و اقساط", "loan_list", []),
            ("leave_desk", "کارتابل مرخصی", "leave_desk", []),
            ("entitlements", "سهمیه مرخصی", "entitlement_list", []),
            ("disputes", "اعتراض‌ها", "dispute_list", []),
        ]
        return tabs

    if section == "periods":
        if period is None:
            return [("list", "دوره‌ها", "period_list", [])]
        args = [period.pk]
        return [
            ("list", "همه دوره‌ها", "period_list", []),
            ("detail", "خلاصه دوره", "period_detail", args),
            ("timesheets", "کارکرد ماهانه", "timesheet_grid", args),
            ("manual", "مبالغ دستی", "manual_inputs", args),
            ("monthly", "آیتم‌های ماهانه", "monthly_parameters", args),
            ("commission", "تخصیص پورسانت", "commission_allocations", args),
            ("sheet", "برگه محاسبه", "period_sheet", args),
            ("payslips", "فیش‌ها", "payslip_list", args),
            ("exports", "خروجی‌های قانونی", "export_center", args),
        ]

    if section == "settings":
        tabs = [
            ("home", "همه تنظیمات", "settings_home", []),
            ("components", "اقلام حقوقی", "component_list", []),
            ("timesheet_items", "اقلام کارکرد", "timesheet_items", []),
            ("fiscal", "سال مالی و مالیات", "fiscal_settings", []),
            ("org", "شرکت و چارت", "org_settings", []),
        ]
        if can_edit:
            tabs += [
                ("users", "کاربران سامانه", "staff_users", []),
                ("portal", "حساب‌های پرتال", "portal_accounts", []),
            ]
        return tabs

    return []


def build(request, latest_period):
    """بخش فعال، زبانهٔ فعال و فهرست زبانه‌های همان بخش."""
    match = getattr(request, "resolver_match", None)
    name = match.url_name if match else None
    section, tab = SECTIONS.get(name, (None, ""))

    period = latest_period
    if section == "periods" and match is not None:
        if name in PERIOD_PK_ROUTES and "pk" in match.kwargs:
            from apps.payroll.models import PayrollPeriod

            period = (
                PayrollPeriod.objects.filter(pk=match.kwargs["pk"]).first() or latest_period
            )
        elif name in ("payslip_detail", "payslip_print") and "pk" in match.kwargs:
            from apps.payroll.models import Payslip

            payslip = (
                Payslip.objects.filter(pk=match.kwargs["pk"])
                .select_related("period")
                .first()
            )
            period = payslip.period if payslip else latest_period

    return {
        "section": section,
        "tab": tab,
        "tabs": _tabs_for(section, period, request.user),
        "tab_period": period,
    }
