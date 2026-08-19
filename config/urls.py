from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from apps.accounts import portal_admin
from apps.accounts import views as accounts_views
from apps.attendance import entitlement_views
from apps.attendance import leave_views
from apps.attendance import views as attendance_views
from apps.employees import views as employees_views
from apps.loans import views as loans_views
from apps.org import views as org_views
from apps.payroll import views as payroll_views
from apps.payroll_config import views as config_views
from apps.portal import views as portal_views

urlpatterns = [
    path("admin/", admin.site.urls),
    # ---- احراز هویت کارکنان مالی
    path("login/", accounts_views.staff_login, name="login"),
    path("logout/", accounts_views.logout_view, name="logout"),
    # ---- داشبورد
    path("", payroll_views.dashboard, name="dashboard"),
    # ---- پرسنل
    path("employees/", employees_views.employee_list, name="employee_list"),
    path("employees/rows/", employees_views.employee_rows, name="employee_rows"),
    path("employees/new/", employees_views.employee_create, name="employee_create"),
    path("employees/import/", employees_views.employee_import, name="employee_import"),
    path(
        "employees/import/template/",
        employees_views.employee_import_template,
        name="employee_import_template",
    ),
    path("employees/<int:pk>/", employees_views.employee_detail, name="employee_detail"),
    path("employees/<int:pk>/edit/", employees_views.employee_edit, name="employee_edit"),
    path("employees/<int:pk>/contract/new/", employees_views.contract_create, name="contract_create"),
    path("employees/<int:pk>/bank/new/", employees_views.bank_account_create, name="bank_account_create"),
    path("employees/<int:pk>/dependent/new/", employees_views.dependent_create, name="dependent_create"),
    path(
        "employees/<int:pk>/timesheet/",
        attendance_views.employee_timesheet_save,
        name="employee_timesheet_save",
    ),
    path("employees/<int:pk>/terminate/", employees_views.employee_terminate, name="employee_terminate"),
    path("employees/<int:pk>/reactivate/", employees_views.employee_reactivate, name="employee_reactivate"),
    path("contracts/<int:pk>/edit/", employees_views.contract_edit, name="contract_edit"),
    # ---- دوره‌های حقوقی
    path("periods/", payroll_views.period_list, name="period_list"),
    path("periods/new/", payroll_views.period_create, name="period_create"),
    path(
        "periods/<int:pk>/monthly/",
        payroll_views.monthly_parameters,
        name="monthly_parameters",
    ),
    path(
        "periods/<int:pk>/monthly/save/",
        payroll_views.monthly_parameters_save,
        name="monthly_parameters_save",
    ),
    path(
        "periods/<int:pk>/commission/",
        payroll_views.commission_allocations,
        name="commission_allocations",
    ),
    path(
        "periods/<int:pk>/commission/save/",
        payroll_views.commission_allocations_save,
        name="commission_allocations_save",
    ),
    path("periods/<int:pk>/manual/", payroll_views.manual_inputs, name="manual_inputs"),
    path("periods/<int:pk>/manual/save/", payroll_views.manual_input_save, name="manual_input_save"),
    path("periods/<int:pk>/", payroll_views.period_detail, name="period_detail"),
    path("periods/<int:pk>/calculate/", payroll_views.period_calculate, name="period_calculate"),
    path(
        "periods/<int:pk>/transition/<str:action>/",
        payroll_views.period_transition,
        name="period_transition",
    ),
    # ---- کارکرد ماهانه
    path("periods/<int:pk>/timesheets/", attendance_views.timesheet_grid, name="timesheet_grid"),
    path("periods/<int:pk>/timesheets/rows/", attendance_views.timesheet_rows, name="timesheet_rows"),
    path("timesheets/<int:pk>/save/", attendance_views.timesheet_save, name="timesheet_save"),
    path("settings/timesheet-items/", attendance_views.timesheet_items, name="timesheet_items"),
    path(
        "settings/timesheet-items/<int:pk>/toggle/",
        attendance_views.timesheet_item_toggle,
        name="timesheet_item_toggle",
    ),
    path("periods/<int:pk>/timesheets/import/", attendance_views.timesheet_import, name="timesheet_import"),
    path(
        "periods/<int:pk>/timesheets/template/",
        attendance_views.timesheet_import_template,
        name="timesheet_import_template",
    ),
    path(
        "periods/<int:pk>/timesheets/approve-all/",
        attendance_views.timesheet_approve_all,
        name="timesheet_approve_all",
    ),
    # ---- وام و اقساط
    path("loans/", loans_views.loan_list, name="loan_list"),
    path("loans/new/", loans_views.loan_create, name="loan_create"),
    path("loans/<int:pk>/", loans_views.loan_detail, name="loan_detail"),
    path("loans/<int:pk>/edit/", loans_views.loan_edit, name="loan_edit"),
    path("loans/<int:pk>/status/", loans_views.loan_set_status, name="loan_set_status"),
    # ---- شرکت و ساختار سازمانی
    path("org/", org_views.org_settings, name="org_settings"),
    path("org/company/", org_views.company_edit, name="company_edit"),
    path("org/<str:kind>/new/", org_views.org_item_form, name="org_item_create"),
    path("org/<str:kind>/<int:pk>/edit/", org_views.org_item_form, name="org_item_edit"),
    path("org/<str:kind>/<int:pk>/delete/", org_views.org_item_delete, name="org_item_delete"),
    # ---- فیش حقوقی
    path("periods/<int:pk>/sheet/", payroll_views.period_sheet, name="period_sheet"),
    path("periods/<int:pk>/sheet/export/", payroll_views.period_sheet_export, name="period_sheet_export"),
    path("periods/<int:pk>/payslips/", payroll_views.payslip_list, name="payslip_list"),
    path("payslips/<int:pk>/", payroll_views.payslip_detail, name="payslip_detail"),
    path("payslips/<int:pk>/print/", payroll_views.payslip_print, name="payslip_print"),
    path(
        "periods/<int:pk>/payslips/print/",
        payroll_views.payslip_batch_print,
        name="payslip_batch_print",
    ),
    # ---- اعتراض‌های پرسنل
    path("disputes/", payroll_views.dispute_list, name="dispute_list"),
    path("disputes/<int:pk>/resolve/", payroll_views.dispute_resolve, name="dispute_resolve"),
    # ---- پیکربندی
    path("settings/", config_views.settings_home, name="settings_home"),
    path("components/", config_views.component_list, name="component_list"),
    path("components/new/", config_views.component_create, name="component_create"),
    path("components/<int:pk>/edit/", config_views.component_edit, name="component_edit"),
    path("components/<int:pk>/toggle/", config_views.component_toggle, name="component_toggle"),
    path("components/<int:pk>/scope/add/", config_views.component_scope_add, name="component_scope_add"),
    path("scopes/<int:pk>/delete/", config_views.component_scope_delete, name="component_scope_delete"),
    path("settings/fiscal/", config_views.fiscal_settings, name="fiscal_settings"),
    path("settings/params/<int:pk>/edit/", config_views.legal_parameter_edit, name="legal_parameter_edit"),
    path("settings/brackets/<int:pk>/edit/", config_views.tax_brackets_edit, name="tax_brackets_edit"),
    # ---- کارتابل مرخصی
    path("leave/desk/", leave_views.leave_desk, name="leave_desk"),
    path("leave/desk/new/", leave_views.leave_record_form, name="leave_record_create"),
    path("leave/desk/<int:pk>/edit/", leave_views.leave_record_form, name="leave_record_edit"),
    path("leave/desk/<int:pk>/cancel/", leave_views.leave_record_cancel, name="leave_record_cancel"),
    path("leave/desk/sync/<int:pk>/", leave_views.leave_sync_period, name="leave_sync_period"),
    # ---- سهمیه مرخصی
    path("leave/entitlements/", entitlement_views.entitlement_list, name="entitlement_list"),
    path("leave/entitlements/save/", entitlement_views.entitlement_save, name="entitlement_save"),
    path("leave/entitlements/fill/", entitlement_views.entitlement_fill_all, name="entitlement_fill_all"),
    # ---- حساب‌های پرتال
    path("portal-accounts/", portal_admin.portal_accounts, name="portal_accounts"),
    path("portal-accounts/create/", portal_admin.portal_accounts_create, name="portal_accounts_create"),
    path("portal-accounts/export/", portal_admin.portal_accounts_export, name="portal_accounts_export"),
    path("portal-accounts/<int:pk>/reset/", portal_admin.portal_account_reset, name="portal_account_reset"),
    path("password/change/", portal_admin.password_change, name="password_change"),
    # ---- کاربران سامانه
    path("users/", portal_admin.staff_users, name="staff_users"),
    path("users/new/", portal_admin.staff_user_form, name="staff_user_create"),
    path("users/<int:pk>/edit/", portal_admin.staff_user_form, name="staff_user_edit"),
    path("users/<int:pk>/toggle/", portal_admin.staff_user_toggle, name="staff_user_toggle"),
    # ---- گزارش‌ها
    path("reports/", payroll_views.reports, name="reports"),
    path("reports/<int:pk>/insurance/", payroll_views.report_insurance, name="report_insurance"),
    path("reports/<int:pk>/tax/", payroll_views.report_tax, name="report_tax"),
    path("reports/<int:pk>/bank/", payroll_views.report_bank, name="report_bank"),
    path("reports/<int:pk>/org/", payroll_views.report_org, name="report_org"),
    path("reports/<int:pk>/export/<str:kind>/", payroll_views.report_export, name="report_export"),
    # ---- خروجی‌های قانونی
    path("periods/<int:pk>/exports/", payroll_views.export_center, name="export_center"),
    path("periods/<int:pk>/exports/<str:kind>/generate/", payroll_views.export_generate, name="export_generate"),
    path("exports/<int:pk>/download/", payroll_views.export_download, name="export_download"),
    path("exports/<int:pk>/status/", payroll_views.export_update_status, name="export_update_status"),
    # ---- پرتال کارکنان
    path("portal/login/", portal_views.portal_login, name="portal_login"),
    path("portal/logout/", portal_views.portal_logout, name="portal_logout"),
    path("portal/", portal_views.portal_home, name="portal_home"),
    path("portal/payslip/<int:pk>/", portal_views.portal_payslip, name="portal_payslip"),
    path("portal/payslip/<int:pk>/ack/", portal_views.portal_payslip_ack, name="portal_payslip_ack"),
    path("portal/signature/", portal_views.portal_signature, name="portal_signature"),
]

# فایل‌های آپلودی (امضا) در حالت توسعه. روی سرور nginx آن‌ها را سرو می‌کند.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
