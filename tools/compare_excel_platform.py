"""مقایسهٔ ریال‌به‌ریال خروجی سامانه با فیش‌های همان ماه در فایل اکسل شرکت.

    python tools/compare_excel_platform.py /path/to/1405.xlsx "تیر 1405"

پیش‌نیاز: همان ماه با `tools/load_excel_month.py` بارگذاری شده باشد.

اسکریپت دوره را محاسبه می‌کند و بعد برای هر پرسنل، هر قلم فیش را کنار ستون
متناظرش در اکسل می‌گذارد. خروجی سه بخش دارد:

  ۱) اقلامی که کامل می‌خوانند
  ۲) اقلامی که نمی‌خوانند، با اندازهٔ اختلاف و تعداد نفرات
  ۳) جمع‌های کل — ناخالص، بیمه، مالیات، خالص

مغایرت لزوماً باگ نیست؛ ممکن است سامانه عمداً روش دیگری داشته باشد. ولی هر
مغایرت باید **دلیل داشته باشد**، و این اسکریپت فهرست همان‌هاست.
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

from apps.employees.models import Employee  # noqa: E402
from apps.payroll.engine.runner import calculate_period  # noqa: E402
from apps.payroll.models import PayrollPeriod, Payslip  # noqa: E402

MONTH_NAMES = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
               "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]

# کد قلم سامانه → ستون اکسل
LINES = [
    ("BASE_SALARY", "حقوق قابل پرداخت"),
    ("SENIORITY", "سنوات قابل پرداخت"),
    ("DIFF", "مابه التفاوت پایه سنوات تجمیعی قابل پرداخت"),
    ("HOUSING", "حق مسكن قابل پرداخت"),
    ("CHILD", "حق اولاد قابل پرداخت"),
    ("MARRIAGE", "حق تاهل قابل پرداخت"),
    ("FOOD", "وجه بن قابل پرداخت"),
    (("OVERTIME", "OVERTIME_SURPLUS"), "مبلغ اضافه كاري کل"),
    ("PREV_CLAIM", "طلب ماه قبل"),
    ("LEAVE_PAY", "وجه مرخصی"),
    ("PHONE", "هزینه تلفن"),
    ("EID", "عیدی وپاداش قابل پرداخت"),
    ("SEVERANCE", "پایانکار قابل پرداخت"),
    # مأموریت ممکن است به چند قلم شکسته شده باشد (مثلاً ضریب متفاوت برای یک
    # واحد). ستون اکسل یکی است، پس همه با هم جمع می‌شوند.
    (("MISSION", "MISSION2", "MISSION_SALES", "MISSION_SURPLUS"), "مبلغ ماموریت"),
    ("COMM_1", "پورسانت یک قابل پرداخت"),
    ("COMM_2", "پورسانت قابل پرداخت دو"),
    ("COMM_3", "پورسانت قابل پرداخت سه"),
    ("LATE", "مبلغ کسر کار - دیر کرد"),
    ("STORE", "کسر انبار"),
    ("ADVANCE", "علی الحساب واریزی"),
    ("LOAN", "مبلغ قسط"),
    ("GOODS", "خرید از شرکت"),
    ("PREV_DEBT", "بدهی از ماه قبل"),
    ("OTHER_DEBT", "سایر بدهی"),
    ("SUPP_INS", "بیمه تکمیلی"),
    ("MEDICAL", "آزمایش وطب کار"),
    ("VEHICLE_FINE", "جرائم وخلافی خودروها"),
    ("INSURANCE_EMP", "سهم کارگر"),
    ("INCOME_TAX", "روند مالیات"),
    ("INSURANCE_EMPLOYER", "سهم کارفرما"),
    ("UNEMPLOYMENT", "بیمه بیکاری"),
]

TOTALS = [
    ("ناخالص", "gross_total", "جمع پرداختيها فیش"),
    ("ماخذ بیمه", "insurable_base", "ماخذ بیمه"),
    ("ماخذ مالیات", "taxable_base", "ماخذ مالیات"),
    ("جمع کسورات", "total_deductions", "جمع كسورات"),
    ("خالص پرداخت", "net_payable", "خالص پرداخت"),
]


def clean(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


def num(v):
    return D(str(v)) if isinstance(v, (int, float)) else D("0")


def fa(x):
    return f"{x:,.0f}"


def signed(x):
    return ("+" if x >= 0 else "") + f"{x:,.0f}"


# شیت و کلید پرسنلی از همان ماژول بارگذاری می‌آیند، نه نسخهٔ دوم اینجا: اگر
# مقایسه سطرها را جور دیگری بخواند یا کد پرسنلی را جور دیگری بسازد، اختلافی
# گزارش می‌کند که وجود ندارد — یا بدتر، اختلافی را نمی‌بیند که هست.
from tools.load_excel_month import (  # noqa: E402
    Sheet,
    build_key_map,
    personnel_code,
    resolve_sheets,
)


def main(path, title):
    sheets = [Sheet(path, name, exempt) for name, exempt in resolve_sheets(path, title)]
    build_key_map(sheets)
    month = MONTH_NAMES.index(title.split()[0]) + 1
    year = int(title.split()[1])
    period = PayrollPeriod.objects.get(year=year, month=month)
    period.status = PayrollPeriod.Status.DRAFT
    period.save(update_fields=["status"])
    result = calculate_period(period)
    print(f"محاسبهٔ {period.title}: {result.status}\n")

    slips = {
        s.employee.personnel_code: s
        for s in Payslip.objects.filter(period=period).select_related("employee")
        .prefetch_related("lines")
    }

    # آمار هر قلم
    stats = {}
    people = []
    rows = [(sheet, r) for sheet in sheets for r in sheet.rows]
    for sheet, r in rows:
        code = personnel_code(sheet, r)
        name = sheet.s("نام ونام خانوادگي", r)
        slip = slips.get(code)
        if slip is None:
            print(f"  ✗ فیشی برای {name} ({code}) ساخته نشد")
            continue
        amounts = {line.component_code: D(line.amount) for line in slip.lines.all()}
        row = {"name": name, "unit": sheet.s("واحد", r),
               "job": sheet.s("شغل", r), "diffs": {}}
        for lcode, column in LINES:
            codes = lcode if isinstance(lcode, tuple) else (lcode,)
            label = codes[0] if len(codes) == 1 else " + ".join(codes)
            excel = sheet.n(column, r)
            got = sum((amounts.get(c, D("0")) for c in codes), D("0"))
            stat = stats.setdefault(label, {"column": column, "ok": 0, "bad": 0,
                                            "delta": D("0"), "worst": None})
            if abs(got - excel) <= 1:
                stat["ok"] += 1
            else:
                stat["bad"] += 1
                stat["delta"] += got - excel
                row["diffs"][label] = (excel, got)
                if stat["worst"] is None or abs(got - excel) > abs(stat["worst"][2]):
                    stat["worst"] = (name, excel, got - excel)
        for label, field, column in TOTALS:
            excel = sheet.n(column, r)
            got = D(getattr(slip, field))
            # پرسنل «بدون بیمه»: فایل در ستون ماخذ بیمه صفر می‌نویسد، سامانه
            # عددِ نظری را نگه می‌دارد ولی او را از حق بیمه و از فایل تأمین
            # اجتماعی بیرون می‌گذارد و روی فیش هم «مشمول بیمه نیست» چاپ
            # می‌کند. نتیجه یکی است؛ فقط جای نگهداری عدد فرق می‌کند.
            if field == "insurable_base" and not slip.insurance_applies:
                got = D("0")
            stat = stats.setdefault(f"= {label}", {"column": column, "ok": 0, "bad": 0,
                                                   "delta": D("0"), "worst": None})
            if abs(got - excel) <= 1:
                stat["ok"] += 1
            else:
                stat["bad"] += 1
                stat["delta"] += got - excel
                row["diffs"][f"= {label}"] = (excel, got)
                if stat["worst"] is None or abs(got - excel) > abs(stat["worst"][2]):
                    stat["worst"] = (name, excel, got - excel)
        people.append(row)

    n = len(people)
    print(f"{'قلم':34}{'می‌خواند':>10}{'نمی‌خواند':>11}{'جمع اختلاف':>18}")
    print("-" * 74)
    clean_rows, broken = [], []
    for code, stat in stats.items():
        line = f"{code:34}{stat['ok']:>10}{stat['bad']:>11}{fa(stat['delta']):>18}"
        (clean_rows if stat["bad"] == 0 else broken).append((line, code, stat))

    for line, _, _ in clean_rows:
        print(line)
    if broken:
        print()
        for line, _, _ in broken:
            print(line)
        print("\nبدترین اختلاف هر قلم:")
        for _, code, stat in broken:
            name, excel, delta = stat["worst"]
            print(f"  {code:22} {name[:20]:22} اکسل {fa(excel):>16} · اختلاف {signed(delta):>16}")

    mismatched = [row for row in people if row["diffs"]]
    if mismatched:
        print()
        print(f"{len(mismatched)} نفر از {n} نفر مغایرت دارند:")
        for row in mismatched:
            print(f"  {row['name']} — {row['unit']} / {row['job']}")
            for label, (excel, got) in row["diffs"].items():
                print(f"      {label:34} اکسل {fa(excel):>18} · سامانه {fa(got):>18}"
                      f" · اختلاف {signed(got - excel):>16}")

    print(f"\n{n} نفر مقایسه شد · {len(clean_rows)} قلم کامل می‌خواند · {len(broken)} قلم نه")
    print(f"{n - len(mismatched)} فیش از {n} فیش ریال‌به‌ریال یکی است")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)
    main(sys.argv[1], sys.argv[2])
