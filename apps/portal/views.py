from django.contrib.auth import authenticate, login, logout
from django.shortcuts import get_object_or_404, redirect, render

from apps.employees.models import Employee
from apps.payroll.models import Payslip, PayslipView
from apps.payroll_config.models import SalaryComponent


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def portal_login(request):
    """ورود پرسنل با کد پرسنلی.

    نام کاربری پرتال همان کد پرسنلی است؛ نگاشت آن به User در زمان ایجاد
    حساب انجام می‌شود.
    """
    if request.user.is_authenticated and hasattr(request.user, "employee"):
        return redirect("portal_home")

    error = None
    personnel_code = ""
    if request.method == "POST":
        personnel_code = request.POST.get("personnel_code", "").strip()
        password = request.POST.get("password", "")
        employee = Employee.objects.filter(personnel_code=personnel_code).first()
        username = employee.user.username if employee and employee.user else personnel_code
        user = authenticate(request, username=username, password=password)
        if user is None:
            error = "کد پرسنلی یا رمز عبور نادرست است."
        elif not hasattr(user, "employee"):
            error = "این حساب به پرونده پرسنلی متصل نیست. با واحد مالی تماس بگیرید."
        else:
            login(request, user)
            return redirect("portal_home")

    return render(
        request,
        "portal/login.html",
        {"error": error, "personnel_code": personnel_code},
    )


def portal_logout(request):
    logout(request)
    return redirect("portal_login")


def portal_home(request):
    if not request.user.is_authenticated:
        return redirect("portal_login")
    employee = getattr(request.user, "employee", None)
    if employee is None:
        return redirect("portal_login")

    payslips = (
        Payslip.objects.filter(employee=employee)
        .select_related("period")
        .order_by("-period__year", "-period__month")
    )
    # فیش‌ها فقط بعد از تأیید دوره برای پرسنل قابل مشاهده‌اند
    visible = [p for p in payslips if p.period.status in {"APPROVED", "LOCKED", "PAID"}]

    return render(
        request,
        "portal/home.html",
        {
            "employee": employee,
            "payslips": visible,
            "latest": visible[0] if visible else None,
            "contract": employee.contract_on(employee.hire_date) or employee.contracts.first(),
        },
    )


def portal_payslip(request, pk):
    if not request.user.is_authenticated:
        return redirect("portal_login")
    employee = getattr(request.user, "employee", None)
    if employee is None:
        return redirect("portal_login")

    # کنترل دسترسی در سطح رکورد: کارمند فقط فیش خودش را می‌بیند
    payslip = get_object_or_404(
        Payslip.objects.select_related("period", "employee", "department"),
        pk=pk,
        employee=employee,
    )
    if payslip.period.status not in {"APPROVED", "LOCKED", "PAID"}:
        return redirect("portal_home")

    PayslipView.objects.create(payslip=payslip, user=request.user, ip=_client_ip(request))

    lines = payslip.lines.all().order_by("sequence", "id")
    return render(
        request,
        "portal/payslip.html",
        {
            "payslip": payslip,
            "employee": employee,
            "earnings": [l for l in lines if l.kind == SalaryComponent.Kind.EARNING],
            "deductions": [l for l in lines if l.kind == SalaryComponent.Kind.DEDUCTION],
        },
    )
