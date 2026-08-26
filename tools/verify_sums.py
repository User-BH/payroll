"""کنترل جمع‌های افقی و عمودی سامانه در برابر فایل اکسل.

    python tools/verify_sums.py "1405.xlsx" "تیر 1405"

دو چیز جدا را می‌سنجد:

**افقی** — درون هر فیش: آیا جمع سطرهای مزایا برابر ناخالص است، جمع کسور برابر
جمع کسورات، و ناخالص منهای کسور برابر خالص؟ این آزمونِ خودِ سامانه است و به
اکسل کاری ندارد؛ اگر نخواند، فیش با خودش جور نیست.

**عمودی** — جمع ستون‌ها: جمع هر قلم روی همهٔ پرسنل، در برابر جمع همان ستون در
اکسل. اینجاست که معلوم می‌شود اختلاف یک نفر در کل ماه چقدر وزن دارد.
"""

import os
import re
import sys
from decimal import Decimal as D

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import openpyxl  # noqa: E402

from apps.payroll.models import PayrollPeriod, Payslip  # noqa: E402
from apps.payroll_config.models import SalaryComponent  # noqa: E402
from tools.compare_excel_platform import LINES, MONTH_NAMES  # noqa: E402
from tools.load_excel_month import Sheet, build_key_map, resolve_sheets  # noqa: E402


def fa(value):
    return f"{value:,.0f}"


def main(path, title):
    sheets = [Sheet(path, name, exempt) for name, exempt in resolve_sheets(path, title)]
    build_key_map(sheets)
    month = MONTH_NAMES.index(title.split()[0]) + 1
    year = int(title.split()[1])
    period = PayrollPeriod.objects.get(year=year, month=month)
    # فقط کسانی که در فایلِ همین ماه هستند، وگرنه جمع عمودی با اکسل جور
    # درنمی‌آید بی‌آنکه معلوم باشد چرا — و علتش هم اشتباهِ محاسبه نیست.
    from tools.load_excel_month import personnel_code

    in_file = {personnel_code(sheet, row) for sheet in sheets for row in sheet.rows}
    everyone = list(
        Payslip.objects.filter(period=period)
        .select_related("employee").prefetch_related("lines")
    )
    slips = [s for s in everyone if s.employee.personnel_code in in_file]
    extra = [s for s in everyone if s.employee.personnel_code not in in_file]
    if extra:
        print("فیش‌هایی که در فایل این ماه سطری ندارند و از جمع کنار گذاشته شدند:")
        for slip in extra:
            print(f"   - {slip.employee.full_name}: ناخالص {fa(slip.gross_total)}")
        print()

    # ---------------------------------------------------------------- افقی
    print(f"=== جمع افقی — درون هر فیش ({len(slips)} فیش)\n")
    bad = []
    for slip in slips:
        lines = list(slip.lines.all())
        earnings = sum(
            (D(line.amount) for line in lines
             if line.kind == SalaryComponent.Kind.EARNING), D(0)
        )
        deductions = sum(
            (D(line.amount) for line in lines
             if line.kind == SalaryComponent.Kind.DEDUCTION), D(0)
        )
        problems = []
        if earnings != D(slip.gross_total):
            problems.append(f"جمع مزایا {fa(earnings)} ≠ ناخالص {fa(slip.gross_total)}")
        if deductions != D(slip.total_deductions):
            problems.append(
                f"جمع کسور {fa(deductions)} ≠ جمع کسورات {fa(slip.total_deductions)}"
            )
        if D(slip.gross_total) - D(slip.total_deductions) != D(slip.net_payable):
            problems.append("ناخالص − کسورات ≠ خالص")
        if problems:
            bad.append((slip.employee.full_name, problems))

    if bad:
        for name, problems in bad[:10]:
            print(f"  ✗ {name}: " + " · ".join(problems))
        print(f"\n  {len(bad)} فیش با خودش جور نیست")
    else:
        print("  ✓ هر فیش با خودش جور است: جمع مزایا = ناخالص،"
              " جمع کسور = کسورات، و ناخالص − کسورات = خالص")

    # --------------------------------------------------------------- عمودی
    print(f"\n=== جمع عمودی — ستون‌به‌ستون در برابر اکسل\n")
    book = openpyxl.load_workbook(path, data_only=True)
    totals = {}
    for sheet in sheets:
        ws = book[sheet.title]
        for row in sheet.rows:
            for codes, column in LINES:
                key = codes if isinstance(codes, tuple) else (codes,)
                totals.setdefault(key, [D(0), D(0), column])
                totals[key][0] += sheet.n(column, row)

    amounts = {}
    for slip in slips:
        for line in slip.lines.all():
            amounts[line.component_code] = amounts.get(line.component_code, D(0)) + D(line.amount)
    for key, box in totals.items():
        box[1] = sum((amounts.get(code, D(0)) for code in key), D(0))

    width = max(len(" + ".join(k)) for k in totals)
    print(f"{'قلم':{width}}{'اکسل':>20}{'سامانه':>20}{'اختلاف':>18}")
    print("-" * (width + 58))
    clean = 0
    for key, (excel, got, column) in sorted(totals.items(), key=lambda x: -abs(x[1][1] - x[1][0])):
        label = " + ".join(key)
        diff = got - excel
        if abs(diff) <= 1:
            clean += 1
            continue
        print(f"{label:{width}}{fa(excel):>20}{fa(got):>20}{('+' if diff > 0 else '') + fa(diff):>18}")
    print(f"\n  {clean} قلم از {len(totals)} قلم، جمع عمودی‌شان دقیقاً یکی است")

    # جمع‌های کل
    print("\n=== جمع کل دوره\n")
    grand = {"AW": D(0), "BW": D(0), "BX": D(0)}
    for sheet in sheets:
        for row in sheet.rows:
            grand["AW"] += sheet.n("جمع پرداختيها فیش", row)
            grand["BW"] += sheet.n("جمع كسورات", row)
            grand["BX"] += sheet.n("خالص پرداخت", row)
    ours = {
        "AW": sum((D(s.gross_total) for s in slips), D(0)),
        "BW": sum((D(s.total_deductions) for s in slips), D(0)),
        "BX": sum((D(s.net_payable) for s in slips), D(0)),
    }
    for key, label in (("AW", "ناخالص"), ("BW", "جمع کسورات"), ("BX", "خالص پرداخت")):
        diff = ours[key] - grand[key]
        mark = "✓" if abs(diff) <= 1 else "✗"
        print(f"  {mark} {label:14}{fa(grand[key]):>22}{fa(ours[key]):>22}"
              f"{('+' if diff > 0 else '') + fa(diff):>18}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)
    main(sys.argv[1], sys.argv[2])
