"""متغیرهای مشترک همهٔ صفحه‌ها: دورهٔ جاری و ساختار منو.

نگاشت مسیر به منو در `apps/payroll/navigation.py` است، نه اینجا: منو دو چیز
لازم دارد (بخش فعال و زبانه‌های همان بخش) و هر دو از یک جا می‌آیند تا نتوانند
با هم ناهماهنگ شوند.
"""

from apps.payroll import navigation
from apps.payroll.models import PayrollPeriod


def current_period(request):
    if not request.user.is_authenticated:
        return {}

    period = (
        PayrollPeriod.objects.select_related("company")
        .order_by("-year", "-month")
        .first()
    )
    return {"current_period": period, **navigation.build(request, period)}
