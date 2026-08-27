# -*- coding: utf-8 -*-
"""نشاندن خروجیِ `export_inputs` روی این دیتابیس.

    python manage.py import_inputs inputs-1405.json              فقط گزارش
    python manage.py import_inputs inputs-1405.json --apply      پر کردن جاهای خالی
    python manage.py import_inputs inputs-1405.json --apply --overwrite

**به‌طور پیش‌فرض هیچ عددی را که از قبل اینجا هست عوض نمی‌کند.** فقط جاهای
خالی را پر می‌کند و اختلاف‌ها را گزارش می‌دهد تا خودتان تصمیم بگیرید — چون
دیتابیس مقصد ممکن است ویرایش‌هایی داشته باشد که مبدأ ندارد، و بی‌صدا
برگرداندنشان بدترین حالت است. برای عوض کردنِ اختلاف‌ها `--overwrite` لازم
است، صریح و جداگانه.

هیچ‌وقت چیزی حذف نمی‌کند.

هویت‌ها کد پرسنلی و کد قلم‌اند، نه شناسهٔ عددی — شناسهٔ لوکال با سرور یکی
نیست و نشستنِ عدد روی پرسنلِ اشتباه، خطایی است که تا فیش کسی غلط نشود دیده
نمی‌شود.
"""

import json
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.employees.models import ContractAllowance, Employee, EmploymentContract
from apps.payroll.models import PayrollInput, PayrollPeriod
from apps.payroll_config.models import SalaryComponent


class Command(BaseCommand):
    help = "نشاندن خروجی export_inputs روی این دیتابیس"

    def add_arguments(self, parser):
        parser.add_argument("path", help="فایل JSON خروجیِ export_inputs")
        parser.add_argument("--apply", action="store_true", help="واقعاً بنویس")
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="اختلاف‌ها را هم با مقدار فایل جایگزین کن",
        )
        parser.add_argument(
            "--no-allowances", action="store_true", help="مزایای مستمر را رد کن"
        )

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        with open(options["path"], encoding="utf-8") as fh:
            payload = json.load(fh)

        self.stdout.write(
            "فایل: سال {} · ماه‌های {} · {} مبلغ دستی · {} مزایای مستمر".format(
                payload.get("year"),
                payload.get("months"),
                len(payload.get("inputs", [])),
                len(payload.get("allowances", [])),
            )
        )

        add, same, differ, skipped = self._inputs(payload, options)
        if not options["no_allowances"]:
            self._allowances(payload, options)

        self.stdout.write("")
        self.stdout.write(
            "مبالغ دستی — نبود: {} · یکسان: {} · متفاوت: {} · نشد: {}".format(
                len(add), same, len(differ), len(skipped)
            )
        )
        for line in differ:
            self.stdout.write(self.style.WARNING("   متفاوت  " + line))
        for line in skipped:
            self.stdout.write(self.style.ERROR("   نشد     " + line))
        for line in add[:40]:
            self.stdout.write("   افزوده  " + line)
        if len(add) > 40:
            self.stdout.write("   … و {} ردیف دیگر".format(len(add) - 40))

        if not options["apply"]:
            self.stdout.write("")
            self.stdout.write("چیزی نوشته نشد. برای نوشتن --apply.")
            return
        if differ and not options["overwrite"]:
            self.stdout.write("")
            self.stdout.write(
                "ردیف‌های «متفاوت» دست‌نخورده ماندند. برای جایگزینی --overwrite."
            )
        self.stdout.write("حالا دوره‌ها را دوباره محاسبه کنید.")

    # ------------------------------------------------------------------

    def _inputs(self, payload, options):
        rows = payload.get("inputs", [])
        add, differ, skipped = [], [], []
        same = 0
        writes = []

        periods, employees, components = {}, {}, {}

        def period_of(year, month):
            key = (year, month)
            if key not in periods:
                periods[key] = PayrollPeriod.objects.filter(
                    year=year, month=month
                ).first()
            return periods[key]

        def employee_of(code):
            if code not in employees:
                employees[code] = Employee.objects.filter(
                    personnel_code=code
                ).first()
            return employees[code]

        def component_of(code):
            if code not in components:
                components[code] = SalaryComponent.objects.filter(code=code).first()
            return components[code]

        for row in rows:
            amount = Decimal(row["amount"])
            label = "{}/{:02d} · {} · {} · {:,}".format(
                row["year"], row["month"], row["employee"], row["component"], amount
            )
            period = period_of(row["year"], row["month"])
            employee = employee_of(row["personnel_code"])
            component = component_of(row["component"])
            if period is None:
                skipped.append(label + " — این دوره در سامانه نیست")
                continue
            if employee is None:
                skipped.append(
                    label + " — پرسنل {} نیست".format(row["personnel_code"])
                )
                continue
            if component is None:
                skipped.append(label + " — قلم {} نیست".format(row["component"]))
                continue

            existing = PayrollInput.objects.filter(
                period=period, employee=employee, component=component
            ).first()
            if existing is None:
                add.append(label)
                writes.append((period, employee, component, amount, False))
            elif existing.amount == amount:
                same += 1
            else:
                differ.append(
                    "{}/{:02d} · {} · {} · اینجا {:,} ← فایل {:,}".format(
                        row["year"], row["month"], row["employee"],
                        row["component"], existing.amount, amount,
                    )
                )
                writes.append((period, employee, component, amount, True))

        if options["apply"]:
            with transaction.atomic():
                for period, employee, component, amount, is_diff in writes:
                    if is_diff and not options["overwrite"]:
                        continue
                    PayrollInput.objects.update_or_create(
                        period=period,
                        employee=employee,
                        component=component,
                        defaults={"amount": amount},
                    )
        return add, same, differ, skipped

    # ------------------------------------------------------------------

    def _allowances(self, payload, options):
        rows = payload.get("allowances", [])
        if not rows:
            return
        added = same = differ = skipped = 0
        writes = []
        for row in rows:
            employee = Employee.objects.filter(
                personnel_code=row["personnel_code"]
            ).first()
            component = SalaryComponent.objects.filter(
                code=row["component"]
            ).first()
            if employee is None or component is None:
                skipped += 1
                continue
            # قرارداد فعالِ همان پرسنل — مزایای مستمر به قرارداد می‌چسبد نه به
            # پرسنل، و شناسهٔ قرارداد بین دو دیتابیس یکی نیست.
            contract = (
                EmploymentContract.objects.filter(
                    employee=employee, status=EmploymentContract.Status.ACTIVE
                )
                .order_by("-effective_from")
                .first()
            )
            if contract is None:
                skipped += 1
                continue
            existing = ContractAllowance.objects.filter(
                contract=contract, component=component
            ).first()
            amount = Decimal(row["amount"])
            if existing is None:
                added += 1
                writes.append((contract, component, row, amount, False))
            elif existing.amount == amount:
                same += 1
            else:
                differ += 1
                writes.append((contract, component, row, amount, True))

        self.stdout.write(
            "مزایای مستمر — نبود: {} · یکسان: {} · متفاوت: {} · نشد: {}".format(
                added, same, differ, skipped
            )
        )
        if not options["apply"]:
            return
        with transaction.atomic():
            for contract, component, row, amount, is_diff in writes:
                if is_diff and not options["overwrite"]:
                    continue
                ContractAllowance.objects.update_or_create(
                    contract=contract,
                    component=component,
                    defaults={
                        "amount": amount,
                        "effective_from": date.fromisoformat(row["effective_from"]),
                        "effective_to": (
                            date.fromisoformat(row["effective_to"])
                            if row["effective_to"]
                            else None
                        ),
                    },
                )
