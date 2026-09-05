# -*- coding: utf-8 -*-
"""شعبهٔ فعالِ این نشست.

مدل از اول چندشرکتی بود ولی ویوها همه‌جا `Company.objects.first()` صدا
می‌زدند — یعنی شرکت دوم ساخته می‌شد و هیچ‌کس نمی‌دیدش. اینجا آن انتخاب یک
جای واحد شد.

انتخاب در **نشست** نگه داشته می‌شود نه روی کاربر: یک حسابدار ممکن است در دو
پنجره دو شعبه را باز کند، و ذخیره‌اش روی کاربر یعنی پنجرهٔ دیگر هم بی‌خبر
جابه‌جا شود.

اگر شناسهٔ ذخیره‌شده دیگر معتبر نباشد (شعبه پاک یا غیرفعال شده) بی‌سروصدا به
اولین شعبهٔ فعال برمی‌گردد، نه خطا — کاربری که لینک قدیمی باز می‌کند نباید با
صفحهٔ خطا روبه‌رو شود.
"""

SESSION_KEY = "active_company_id"


def companies():
    """شعبه‌های فعال، به ترتیب نام — فقط برای نمایش در سوییچ."""
    from apps.org.models import Company

    return Company.objects.filter(is_active=True).order_by("name")


def active_company(request=None):
    """شعبه‌ای که کاربر الان روی آن کار می‌کند."""
    from apps.org.models import Company

    if request is not None:
        pk = getattr(request, "session", {}).get(SESSION_KEY)
        if pk:
            found = Company.objects.filter(pk=pk, is_active=True).first()
            if found is not None:
                return found
    # بازگشتِ پیش‌فرض **قدیمی‌ترین** شعبه است، نه اولین الفبایی: «اردبیل»
    # الفبایی پیش از «تامین کالا باختر» می‌آید و مرتب‌سازیِ نامی یعنی ساختن
    # شعبهٔ دوم، شعبهٔ پیش‌فرضِ همه‌جا را بی‌صدا عوض کند.
    return (
        Company.objects.filter(is_active=True).order_by("pk").first()
        or Company.objects.order_by("pk").first()
    )


def set_active_company(request, company) -> None:
    request.session[SESSION_KEY] = company.pk


def organization_name() -> str:
    """نام کل مجموعه، مستقل از شعبه‌ای که کاربر انتخاب کرده.

    شعبه‌ها اسم شهرند («تبریز»، «اردبیل») ولی سربرگ و فیش باید نام سازمان را
    بگویند. `legal_name` قدیمی‌ترین شعبه ملاک است — همان شعبه‌ای که بقیه از
    رویش ساخته شده‌اند و `legal_name` را از او به ارث برده‌اند.

    اگر هیچ شعبه‌ای `legal_name` نداشته باشد، نامِ خودِ قدیمی‌ترین شعبه
    برمی‌گردد؛ پس شرکتی که تک‌شعبه است هیچ‌چیز را از دست نمی‌دهد.
    """
    from apps.org.models import Company

    first = Company.objects.order_by("pk").first()
    if first is None:
        return ""
    return first.legal_name or first.name
