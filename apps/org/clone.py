# -*- coding: utf-8 -*-
"""تکثیر پیکربندی یک شعبه روی شعبهٔ تازه.

«محاسبات و فیلدها دقیقاً مثل شعبهٔ تبریز» یعنی اقلام حقوقی، سال مالی،
پارامترهای قانونی و پله‌های مالیاتی همان‌ها باشند — ولی **کپی** شوند، نه به
اشتراک گذاشته شوند. اگر مشترک بودند، تغییر یک نرخ در یک شعبه بی‌صدا فیش شعبهٔ
دیگر را عوض می‌کرد.

چه چیزی کپی **نمی‌شود** و چرا:

    پرسنل و قرارداد    هر شعبه پرسنل خودش را دارد؛ همان چیزی که جدا بودنش خواسته شده
    دوره‌های حقوق      محاسبهٔ هر شعبه باید جداگانه وارد شود
    دامنه‌های شمول     به مرکز هزینه و پست ارجاع می‌دهند که هنوز در شعبهٔ تازه
                       وجود ندارند. `configure_1405` بعد از ورود پرسنل می‌سازدشان.
    ساختار سازمانی     چارت هر شعبه مال خودش است
"""

from django.db import transaction


@transaction.atomic
def clone_configuration(source, target) -> dict:
    """اقلام و پارامترهای `source` را روی `target` می‌سازد و آمار برمی‌گرداند.

    بی‌خطر برای اجرای دوباره: هرچه از قبل در مقصد باشد دست نمی‌خورد.
    """
    from apps.payroll_config.models import (
        FiscalYear, LegalParameter, SalaryComponent, TaxBracket,
    )

    stats = {"components": 0, "fiscal_years": 0, "parameters": 0, "brackets": 0}
    if source is None or target is None or source.pk == target.pk:
        return stats

    # ---------------------------------------------------------- اقلام حقوقی
    have = set(SalaryComponent.objects.filter(company=target).values_list("code", flat=True))
    skip = {"id", "company", "company_id", "absorbs", "adds"}
    for item in SalaryComponent.objects.filter(company=source):
        if item.code in have:
            continue
        fields = {
            f.name: getattr(item, f.name)
            for f in SalaryComponent._meta.fields
            if f.name not in skip
        }
        SalaryComponent.objects.create(company=target, **fields)
        stats["components"] += 1

    # رابطه‌ها **پس از** ساخت همه، و با کد نه با شناسه — شناسهٔ مقصد فرق دارد.
    new_by_code = {
        c.code: c for c in SalaryComponent.objects.filter(company=target)
    }
    for item in SalaryComponent.objects.filter(company=source).prefetch_related(
        "absorbs", "adds"
    ):
        twin = new_by_code.get(item.code)
        if twin is None:
            continue
        for name in ("absorbs", "adds"):
            wanted = [
                new_by_code[o.code]
                for o in getattr(item, name).all()
                if o.code in new_by_code
            ]
            if set(getattr(twin, name).all()) != set(wanted):
                getattr(twin, name).set(wanted)

    # --------------------------------------- سال مالی، پارامترها، پله‌های مالیات
    for year in FiscalYear.objects.filter(company=source):
        twin, created = FiscalYear.objects.get_or_create(
            company=target, year=year.year,
            defaults={"start_date": year.start_date, "end_date": year.end_date,
                      "is_closed": False},
        )
        if created:
            stats["fiscal_years"] += 1

        for params in LegalParameter.objects.filter(fiscal_year=year):
            if LegalParameter.objects.filter(
                fiscal_year=twin, effective_from=params.effective_from
            ).exists():
                continue
            fields = {
                f.name: getattr(params, f.name)
                for f in LegalParameter._meta.fields
                if f.name not in {"id", "fiscal_year", "fiscal_year_id"}
            }
            LegalParameter.objects.create(fiscal_year=twin, **fields)
            stats["parameters"] += 1

        for bracket in TaxBracket.objects.filter(fiscal_year=year):
            fields = {
                f.name: getattr(bracket, f.name)
                for f in TaxBracket._meta.fields
                if f.name not in {"id", "fiscal_year", "fiscal_year_id"}
            }
            if TaxBracket.objects.filter(fiscal_year=twin, **{
                k: v for k, v in fields.items() if k in ("row_order",)
            }).exists():
                continue
            TaxBracket.objects.create(fiscal_year=twin, **fields)
            stats["brackets"] += 1

    return stats
