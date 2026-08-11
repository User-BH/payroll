from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def payroll_staff_required(view):
    """فقط کاربران بخش مالی. پرسنل عادی به پرتال خودشان هدایت می‌شوند."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect(f"/login/?next={request.path}")
        if not user.is_payroll_staff:
            return redirect("portal_home")
        return view(request, *args, **kwargs)

    return wrapper


def can_edit_required(view):
    """عملیات تغییردهنده: فقط مدیر سیستم و کارشناس حقوق و دستمزد."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect(f"/login/?next={request.path}")
        if not user.can_edit_payroll:
            messages.error(request, "شما اجازه انجام این عملیات را ندارید.")
            return redirect("dashboard")
        return view(request, *args, **kwargs)

    return wrapper
