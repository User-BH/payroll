from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render


def staff_login(request):
    """ورود کارکنان بخش مالی."""
    if request.user.is_authenticated and request.user.is_payroll_staff:
        return redirect("dashboard")

    error = None
    username = ""
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is None:
            error = "نام کاربری یا رمز عبور نادرست است."
        elif not user.is_payroll_staff:
            error = "این حساب دسترسی به بخش مالی ندارد. از پرتال کارکنان وارد شوید."
        else:
            login(request, user)
            return redirect(request.GET.get("next") or "dashboard")

    return render(request, "accounts/login.html", {"error": error, "username": username})


def logout_view(request):
    logout(request)
    messages.info(request, "از سامانه خارج شدید.")
    return redirect("login")
