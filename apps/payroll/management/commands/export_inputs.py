# -*- coding: utf-8 -*-
"""خروجی گرفتن از مبالغ دستی و مزایای مستمر، برای انتقال به سرور.

    python manage.py export_inputs --year 1405 --out inputs-1405.json
    python manage.py export_inputs --year 1405 --month 5 --out mordad.json

فایل خروجی **متنی و خواندنی** است؛ پیش از اجرا روی سرور می‌شود بازش کرد و
دید چه چیزی در آن است. عمداً JSON است نه dump دیتابیس: dump شناسه‌های عددی
دارد و شناسهٔ لوکال با سرور یکی نیست، پس هر بار خطر نشستنِ عدد روی پرسنل
اشتباه هست. اینجا هویت‌ها **کد پرسنلی و کد قلم** است.

جفتش `import_inputs` است که به‌طور پیش‌فرض فقط گزارش می‌دهد.
"""

import json
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.employees.models import ContractAllowance
from apps.payroll.models import PayrollInput, PayrollPeriod


class Command(BaseCommand):
    help = "خروجی مبالغ دستی و مزایای مستمر برای انتقال به سرور"

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--month", type=int)
        parser.add_argument("--out", required=True, help="مسیر فایل خروجی")
        parser.add_argument(
            "--no-allowances", action="store_true",
            help="فقط مبالغ دستی؛ مزایای مستمر قرارداد را نگیر",
        )

    def handle(self, *args, **options):
        periods = PayrollPeriod.objects.filter(year=options["year"])
        if options.get("month"):
            periods = periods.filter(month=options["month"])
        periods = list(periods.order_by("month"))
        if not periods:
            self.stderr.write("دوره‌ای با این مشخصات نیست.")
            return

        inputs = []
        for row in (
            PayrollInput.objects.filter(period__in=periods)
            .select_related("period", "employee", "component")
            .order_by("period__month", "employee__personnel_code")
        ):
            inputs.append({
                "year": row.period.year,
                "month": row.period.month,
                "personnel_code": row.employee.personnel_code,
                "employee": row.employee.full_name,
                "component": row.component.code,
                "amount": str(row.amount),
            })

        allowances = []
        if not options["no_allowances"]:
            for row in (
                ContractAllowance.objects.select_related(
                    "contract__employee", "component"
                ).order_by("contract__employee__personnel_code")
            ):
                allowances.append({
                    "personnel_code": row.contract.employee.personnel_code,
                    "employee": row.contract.employee.full_name,
                    "component": row.component.code,
                    "amount": str(row.amount),
                    "effective_from": row.effective_from.isoformat(),
                    "effective_to": (
                        row.effective_to.isoformat() if row.effective_to else None
                    ),
                })

        payload = {
            "note": "برای import_inputs — هویت‌ها کد پرسنلی و کد قلم است، نه شناسهٔ عددی",
            "year": options["year"],
            "months": [p.month for p in periods],
            "inputs": inputs,
            "allowances": allowances,
        }
        with open(options["out"], "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)

        total = sum(Decimal(r["amount"]) for r in inputs)
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(inputs)} مبلغ دستی ({total:,} ریال) و "
                f"{len(allowances)} مزایای مستمر در «{options['out']}» نوشته شد."
            )
        )
