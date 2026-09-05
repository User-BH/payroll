# -*- coding: utf-8 -*-
"""بیرون کشیدن **همهٔ تنظیمات محاسباتی** به یک فایل JSON.

    python manage.py export_config --out config.json

تنظیمات این سامانه بین کد و دیتابیس پخش‌اند: `configure_1405` بخشی را
می‌سازد، ولی تصمیم‌هایی مثل ضریب پایه سنوات ماهانه، تیک تبدیل خودکار پورسانت،
نام شعبه‌ها و دامنه‌های شمول در دیتابیس زندگی می‌کنند. برای همین سروری که
فقط `git pull` و `configure_1405` می‌گیرد، عقب می‌ماند.

این فایل آن شکاف را می‌بندد: هرچه در دیتابیس تنظیم است بیرون می‌آید و
`import_config` روی مقصد می‌نشاندش.

**داده‌ی حقوقی در این فایل نیست** — نه پرسنل، نه کارکرد، نه فیش، نه مبلغ
دستی. فقط پیکربندی. پس برخلاف دامپ دیتابیس، فرستادنش بی‌خطر است.

هویت‌ها نام و کدند نه شناسهٔ عددی: شناسهٔ لوکال با سرور یکی نیست و نشستنِ
تنظیم روی قلمِ اشتباه، خطایی است که تا غلط شدن فیش کسی دیده نمی‌شود.
"""

import json
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.org.models import Company
from apps.payroll_config.models import (
    FiscalYear, LegalParameter, SalaryComponent, TaxBracket,
)

COMPANY_FIELDS = [
    "name", "legal_name", "activity", "national_id", "economic_code",
    "registration_number", "insurance_workshop_code", "tax_file_number",
    "address", "phone", "is_active",
]
COMPONENT_SKIP = {"id", "company", "company_id", "base_component",
                  "base_component_id", "timesheet_item", "timesheet_item_id"}
PARAM_SKIP = {"id", "fiscal_year", "fiscal_year_id"}


def plain(value):
    """Decimal و date را به چیزی تبدیل می‌کند که JSON بفهمد و برگشتش دقیق باشد."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


class Command(BaseCommand):
    help = "بیرون کشیدن تنظیمات محاسباتی به JSON"

    def add_arguments(self, parser):
        parser.add_argument("--out", default="config.json")
        parser.add_argument("--company", default="", help="فقط یک شعبه")

    def handle(self, *args, **options):
        companies = Company.objects.order_by("pk")
        if options["company"]:
            companies = companies.filter(name=options["company"])
            if not companies:
                self.stderr.write(f"شعبهٔ «{options['company']}» نیست.")
                return

        payload = {"version": 1, "companies": []}
        for company in companies:
            payload["companies"].append(self._company(company))

        with open(options["out"], "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)

        n_comp = sum(len(c["components"]) for c in payload["companies"])
        n_scope = sum(
            len(x["scopes"]) for c in payload["companies"] for x in c["components"]
        )
        self.stdout.write(self.style.SUCCESS(
            f"{len(payload['companies'])} شعبه · {n_comp} قلم حقوقی · "
            f"{n_scope} دامنه شمول در «{options['out']}» نوشته شد."
        ))

    # ------------------------------------------------------------------

    def _company(self, company):
        return {
            **{f: plain(getattr(company, f)) for f in COMPANY_FIELDS},
            "components": [
                self._component(c)
                for c in SalaryComponent.objects.filter(company=company)
                .prefetch_related("scopes", "absorbs", "adds")
                .order_by("code")
            ],
            "fiscal_years": [
                self._year(y)
                for y in FiscalYear.objects.filter(company=company).order_by("year")
            ],
        }

    def _component(self, c):
        return {
            **{
                f.name: plain(getattr(c, f.name))
                for f in SalaryComponent._meta.fields
                if f.name not in COMPONENT_SKIP
            },
            # رابطه‌ها با **کد** می‌روند نه شناسه — شناسهٔ مقصد فرق دارد.
            "base_component": c.base_component.code if c.base_component else None,
            "absorbs": sorted(x.code for x in c.absorbs.all()),
            "adds": sorted(x.code for x in c.adds.all()),
            "scopes": sorted(
                (
                    {"type": s.scope_type, "id": s.scope_id,
                     "label": s.target_label()}
                    for s in c.scopes.all()
                ),
                key=lambda d: (d["type"], d["id"]),
            ),
        }

    def _year(self, y):
        return {
            "year": y.year,
            "start_date": plain(y.start_date),
            "end_date": plain(y.end_date),
            "is_closed": y.is_closed,
            "parameters": [
                {f.name: plain(getattr(p, f.name))
                 for f in LegalParameter._meta.fields if f.name not in PARAM_SKIP}
                for p in LegalParameter.objects.filter(fiscal_year=y)
                .order_by("effective_from")
            ],
            "tax_brackets": [
                {f.name: plain(getattr(b, f.name))
                 for f in TaxBracket._meta.fields if f.name not in PARAM_SKIP}
                for b in TaxBracket.objects.filter(fiscal_year=y).order_by("row_order")
            ],
        }
