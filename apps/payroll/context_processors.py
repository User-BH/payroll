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

    from apps.org.current import active_company, companies, organization_name

    # نام شرکت تا امروز در قالب‌ها سخت‌کد بود («تامین کالا باختر» در سربرگ،
    # صفحهٔ ورود و فیش). یعنی همان کدی که چندشرکتی طراحی شده، روی صفحه اسم
    # یک شرکت را چاپ می‌کرد. حالا از دیتابیس می‌آید.
    #
    # پیش از بررسی ورود ساخته می‌شود چون صفحهٔ ورود هم نام شرکت را نشان
    # می‌دهد و آن‌جا هنوز کاربری در کار نیست.
    common = {
        "jalali_year": jdatetime.date.today().year,
        "company": active_company(request),
        # نام کل مجموعه — **مستقل از شعبهٔ انتخاب‌شده**.
        #
        # سربرگ و عنوان صفحه نام سازمان را می‌گویند نه نام شهر، و با سوییچ
        # شعبه نباید تکان بخورند. نام شعبه جای خودش را دارد: سوییچ.
        "organization": organization_name(),
    }

    if not request.user.is_authenticated:
        return common

    # فهرست شعبه‌ها فقط وقتی به قالب می‌رود که بیش از یکی باشد — سوییچی که
    # همیشه یک گزینه دارد، فضای هدر را بی‌دلیل می‌گیرد.
    branches = list(companies())
    common["branches"] = branches if len(branches) > 1 else []

    # دورهٔ جاریِ همین شعبه — وگرنه منو و نوار بالا دورهٔ شعبهٔ دیگر را
    # نشان می‌دهند و کاربر روی دادهٔ اشتباه کار می‌کند.
    period = (
        PayrollPeriod.objects.filter(company=common["company"])
        .select_related("company")
        .order_by("-year", "-month")
        .first()
    )
    return {**common, "current_period": period, **navigation.build(request, period)}
