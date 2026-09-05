# -*- coding: utf-8 -*-
"""نشاندن خروجی `export_config` روی این دیتابیس.

    python manage.py import_config config.json            فقط گزارش
    python manage.py import_config config.json --apply

**هیچ‌وقت چیزی حذف نمی‌کند.** قلمی که در مقصد هست و در فایل نیست، دست‌نخورده
می‌ماند و فقط گزارش می‌شود.

هویت‌ها نام و کدند نه شناسهٔ عددی. **دامنه‌های شمول با نامِ مقصد** بازسازی
می‌شوند نه با شناسه: شناسهٔ مرکز هزینهٔ «فروش» در لوکال و سرور یکی نیست، و
نشستنِ دامنه روی مرکز هزینهٔ اشتباه یعنی قلمی به گروهی برسد که نباید — خطایی
که تا غلط شدن فیش کسی دیده نمی‌شود.

اگر مقصدِ یک دامنه در این دیتابیس نباشد، آن دامنه **ساخته نمی‌شود** و صریحاً
گزارش می‌شود؛ چون قلمِ بی‌دامنه به **همهٔ** پرسنل تعلق می‌گیرد و ساکت گذشتن از
آن بدترین حالت است.
"""

import json
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.org.models import Company
from apps.payroll_config.models import (
    ComponentScope,
    FiscalYear,
    LegalParameter,
    SalaryComponent,
    TaxBracket,
)

COMPANY_FIELDS = [
    "legal_name", "activity", "national_id", "economic_code",
    "registration_number", "insurance_workshop_code", "tax_file_number",
    "address", "phone", "is_active",
]
COMPONENT_SKIP = {
    "id", "company", "company_id", "base_component", "base_component_id",
    "timesheet_item", "timesheet_item_id",
}
PARAM_SKIP = {"id", "fiscal_year", "fiscal_year_id"}


def cast(model, name, value):
    """مقدار JSON را به نوعی که فیلد می‌خواهد برمی‌گرداند."""
    if value is None:
        return None
    kind = model._meta.get_field(name).get_internal_type()
    if kind == "DecimalField":
        return Decimal(str(value))
    if kind == "DateField" and isinstance(value, str):
        return date.fromisoformat(value)
    return value


class Command(BaseCommand):
    help = "نشاندن خروجی export_config روی این دیتابیس"

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--apply", action="store_true", help="واقعاً بنویس")

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        with open(options["path"], encoding="utf-8") as fh:
            payload = json.load(fh)

        self.notes = []
        self.problems = []
        self.stats = {
            "companies": 0, "components": 0, "updated": 0,
            "scopes": 0, "years": 0, "params": 0, "brackets": 0,
        }

        # اجرای آزمایشی همان مسیرِ اجرای واقعی را می‌رود و بعد برمی‌گردد،
        # وگرنه گزارش و نتیجه دو پیاده‌سازی جدا می‌شدند و می‌توانستند فرق کنند.
        with transaction.atomic():
            for spec in payload.get("companies", []):
                self._company(spec)
            if not options["apply"]:
                transaction.set_rollback(True)

        for line in self.notes:
            self.stdout.write("   " + line)
        if self.problems:
            self.stdout.write("")
            for line in self.problems:
                self.stdout.write(self.style.ERROR("   ! " + line))

        self.stdout.write("")
        self.stdout.write(
            "شعبه {companies} · قلم تازه {components} · قلم به‌روزشده {updated}"
            " · دامنه {scopes} · سال مالی {years} · پارامتر {params}"
            " · پلهٔ مالیات {brackets}".format(**self.stats)
        )
        if options["apply"]:
            self.stdout.write(self.style.SUCCESS("اعمال شد."))
            self.stdout.write("حالا دوره‌ها را دوباره محاسبه کنید: manage.py recalculate")
        else:
            self.stdout.write("")
            self.stdout.write("چیزی نوشته نشد. برای نوشتن --apply.")

    # ------------------------------------------------------------------

    def _company(self, spec):
        name = spec["name"]
        company = Company.objects.filter(name=name).first()
        if company is None:
            company = Company(name=name)
            self.stats["companies"] += 1
            self.notes.append("شعبهٔ تازه: " + name)
        for field in COMPANY_FIELDS:
            if field in spec:
                setattr(company, field, spec[field])
        company.save()

        self._components(company, spec.get("components", []))
        for year in spec.get("fiscal_years", []):
            self._year(company, year)

    # ------------------------------------------------------------------

    def _components(self, company, specs):
        existing = {
            c.code: c for c in SalaryComponent.objects.filter(company=company)
        }

        # گام اول خودِ اقلام؛ رابطه‌ها بعد، چون به همدیگر ارجاع می‌دهند و
        # قلمی که هنوز ساخته نشده نمی‌تواند مرجع باشد.
        for spec in specs:
            code = spec["code"]
            component = existing.get(code)
            fresh = component is None
            if fresh:
                component = SalaryComponent(company=company, code=code)
            changed = []
            for field in SalaryComponent._meta.fields:
                if field.name in COMPONENT_SKIP or field.name not in spec:
                    continue
                want = cast(SalaryComponent, field.name, spec[field.name])
                if getattr(component, field.name) != want:
                    changed.append(field.name)
                    setattr(component, field.name, want)
            component.save()
            existing[code] = component
            if fresh:
                self.stats["components"] += 1
                self.notes.append(
                    "{} · قلم تازه: {} ({})".format(company.name, spec["name"], code)
                )
            elif changed:
                self.stats["updated"] += 1
                self.notes.append(
                    "{} · {}: {}".format(
                        company.name, spec["name"], "، ".join(changed)
                    )
                )

        by_code = {
            c.code: c for c in SalaryComponent.objects.filter(company=company)
        }
        for spec in specs:
            component = by_code.get(spec["code"])
            if component is None:
                continue
            base = spec.get("base_component")
            if base and base in by_code:
                if component.base_component_id != by_code[base].pk:
                    component.base_component = by_code[base]
                    component.save(update_fields=["base_component"])
            for rel in ("absorbs", "adds"):
                wanted = [by_code[c] for c in spec.get(rel, []) if c in by_code]
                if set(getattr(component, rel).all()) != set(wanted):
                    getattr(component, rel).set(wanted)
            self._scopes(company, component, spec.get("scopes", []))

        extra = set(by_code) - {s["code"] for s in specs}
        if extra:
            self.notes.append(
                "{} · در مقصد هست و در فایل نیست (دست نخورد): {}".format(
                    company.name, "، ".join(sorted(extra))
                )
            )

    # ------------------------------------------------------------------

    def _resolve(self, company, kind, label):
        """مقصدِ یک دامنه را **با نام** پیدا می‌کند، نه با شناسه."""
        from apps.org.models import CostCenter, Department, JobTitle

        if kind == ComponentScope.ScopeType.ALL:
            return ""
        if kind == ComponentScope.ScopeType.CONTRACT_TYPE:
            return label  # خودِ مقدارِ انتخاب است، نه شناسه
        model = {
            ComponentScope.ScopeType.DEPARTMENT: Department,
            ComponentScope.ScopeType.COST_CENTER: CostCenter,
            ComponentScope.ScopeType.JOB_TITLE: JobTitle,
        }.get(kind)
        if model is None:
            return None
        found = model.objects.filter(company=company, name=label).first()
        return str(found.pk) if found else None

    def _scopes(self, company, component, specs):
        wanted = set()
        for spec in specs:
            kind = spec["type"]
            if kind == ComponentScope.ScopeType.CONTRACT_TYPE:
                raw = spec.get("id")
            else:
                raw = spec.get("label") or spec.get("id")
            target = self._resolve(company, kind, raw)
            if target is None:
                self.problems.append(
                    "{} · «{}»: مقصدِ دامنه «{}» در این دیتابیس نیست — دامنه "
                    "ساخته نشد و این قلم فعلاً به **همه** تعلق می‌گیرد. پس از "
                    "ورود پرسنل، دوباره اجرا کنید.".format(
                        company.name, component.name, raw
                    )
                )
                continue
            wanted.add((kind, target))

        current = {(s.scope_type, s.scope_id) for s in component.scopes.all()}
        if wanted == current:
            return
        component.scopes.all().delete()
        for kind, target in wanted:
            ComponentScope.objects.create(
                component=component, scope_type=kind, scope_id=target
            )
        self.stats["scopes"] += len(wanted)
        self.notes.append(
            "{} · دامنهٔ «{}» به‌روز شد ({} مقصد)".format(
                company.name, component.name, len(wanted)
            )
        )

    # ------------------------------------------------------------------

    def _year(self, company, spec):
        year, created = FiscalYear.objects.get_or_create(
            company=company,
            year=spec["year"],
            defaults={
                "start_date": cast(FiscalYear, "start_date", spec["start_date"]),
                "end_date": cast(FiscalYear, "end_date", spec["end_date"]),
                "is_closed": spec.get("is_closed", False),
            },
        )
        if created:
            self.stats["years"] += 1
            self.notes.append(
                "{} · سال مالی تازه: {}".format(company.name, spec["year"])
            )

        for item in spec.get("parameters", []):
            eff = cast(LegalParameter, "effective_from", item["effective_from"])
            row = LegalParameter.objects.filter(
                fiscal_year=year, effective_from=eff
            ).first()
            fresh = row is None
            if fresh:
                row = LegalParameter(fiscal_year=year)
            changed = []
            for field in LegalParameter._meta.fields:
                if field.name in PARAM_SKIP or field.name not in item:
                    continue
                want = cast(LegalParameter, field.name, item[field.name])
                if getattr(row, field.name, None) != want:
                    changed.append(field.name)
                    setattr(row, field.name, want)
            row.save()
            if fresh:
                self.stats["params"] += 1
                self.notes.append(
                    "{} · پارامترهای {} ساخته شد".format(company.name, eff)
                )
            elif changed:
                self.notes.append(
                    "{} · پارامترهای {}: {}".format(
                        company.name, eff, "، ".join(changed)
                    )
                )

        for item in spec.get("tax_brackets", []):
            row = TaxBracket.objects.filter(
                fiscal_year=year, row_order=item["row_order"]
            ).first()
            fresh = row is None
            if fresh:
                row = TaxBracket(fiscal_year=year)
            for field in TaxBracket._meta.fields:
                if field.name in PARAM_SKIP or field.name not in item:
                    continue
                setattr(row, field.name, cast(TaxBracket, field.name, item[field.name]))
            row.save()
            if fresh:
                self.stats["brackets"] += 1
