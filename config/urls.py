from django.contrib import admin
from django.urls import path

from apps.accounts import views as accounts_views
from apps.attendance import views as attendance_views
from apps.employees import views as employees_views
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
    path("contracts/<int:pk>/edit/", employees_views.contract_edit, name="contract_edit"),
    # ---- دوره‌های حقوقی
    path("periods/", payroll_views.period_list, name="period_list"),
    path("periods/new/", payroll_views.period_create, name="period_create"),
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
    # ---- فیش حقوقی
    path("periods/<int:pk>/payslips/", payroll_views.payslip_list, name="payslip_list"),
    path("payslips/<int:pk>/", payroll_views.payslip_detail, name="payslip_detail"),
    path("payslips/<int:pk>/print/", payroll_views.payslip_print, name="payslip_print"),
    # ---- اعتراض‌های پرسنل
    path("disputes/", payroll_views.dispute_list, name="dispute_list"),
    path("disputes/<int:pk>/resolve/", payroll_views.dispute_resolve, name="dispute_resolve"),
    # ---- پیکربندی
    path("components/", config_views.component_list, name="component_list"),
    path("components/<int:pk>/toggle/", config_views.component_toggle, name="component_toggle"),
    path("settings/fiscal/", config_views.fiscal_settings, name="fiscal_settings"),
    # ---- گزارش‌ها
    path("reports/", payroll_views.reports, name="reports"),
    path("reports/<int:pk>/insurance/", payroll_views.report_insurance, name="report_insurance"),
    path("reports/<int:pk>/tax/", payroll_views.report_tax, name="report_tax"),
    path("reports/<int:pk>/bank/", payroll_views.report_bank, name="report_bank"),
    path("reports/<int:pk>/export/<str:kind>/", payroll_views.report_export, name="report_export"),
    # ---- پرتال کارکنان
    path("portal/login/", portal_views.portal_login, name="portal_login"),
    path("portal/logout/", portal_views.portal_logout, name="portal_logout"),
    path("portal/", portal_views.portal_home, name="portal_home"),
    path("portal/payslip/<int:pk>/", portal_views.portal_payslip, name="portal_payslip"),
    path("portal/payslip/<int:pk>/ack/", portal_views.portal_payslip_ack, name="portal_payslip_ack"),
]
