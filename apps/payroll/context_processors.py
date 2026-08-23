"""متغیرهای مشترک همهٔ صفحه‌ها: دورهٔ جاری و ساختار منو.

نگاشت مسیر به منو در `apps/payroll/navigation.py` است، نه اینجا: منو دو چیز
لازم دارد (بخش فعال و زبانه‌های همان بخش) و هر دو از یک جا می‌آیند تا نتوانند
با هم ناهماهنگ شوند.
"""

from apps.payroll import navigation
from apps.payroll.models import PayrollPeriod


def current_period(request):
    # سال جلالی امروز — برای امضای سازنده در پای سایدبار. پیش از بررسی ورود
    # ساخته می‌شود تا صفحهٔ ورود هم داشته باشدش.
    import jdatetime

    from apps.org.models import Company

    # نام شرکت تا امروز در قالب‌ها سخت‌کد بود («تامین کالا باختر» در سربرگ،
    # صفحهٔ ورود و فیش). یعنی همان کدی که چندشرکتی طراحی شده، روی صفحه اسم
    # یک شرکت را چاپ می‌کرد. حالا از دیتابیس می‌آید.
    #
    # پیش از بررسی ورود ساخته می‌شود چون صفحهٔ ورود هم نام شرکت را نشان
    # می‌دهد و آن‌جا هنوز کاربری در کار نیست.
    common = {
        "jalali_year": jdatetime.date.today().year,
        "company": Company.objects.filter(is_active=True).first(),
    }

    if not request.user.is_authenticated:
        return common

    period = (
        PayrollPeriod.objects.select_related("company")
        .order_by("-year", "-month")
        .first()
    )
    return {**common, "current_period": period, **navigation.build(request, period)}
