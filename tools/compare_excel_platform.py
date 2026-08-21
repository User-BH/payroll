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
    ("OVERTIME", "مبلغ اضافه كاري کل"),
    # مأموریت ممکن است به چند قلم شکسته شده باشد (مثلاً ضریب متفاوت برای یک
    # واحد). ستون اکسل یکی است، پس همه با هم جمع می‌شوند.
    (("MISSION", "MISSION_SALES"), "مبلغ ماموریت"),
    ("COMM_1", "پورسانت یک قابل پرداخت"),
    ("COMM_2", "پورسانت قابل پرداخت دو"),
    ("COMM_3", "پورسانت قابل پرداخت سه"),
    ("LATE", "مبلغ کسر کار - دیر کرد"),
    ("STORE", "کسر انبار"),
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


class Sheet:
    def __init__(self, path, title):
        self.ws = openpyxl.load_workbook(path, data_only=True)[title]
        self.index = {}
        for c in range(1, self.ws.max_column + 1):
            head = clean(self.ws.cell(1, c).value)
            if head:
                self.index.setdefault(head, c)
        self.rows = [
            r for r in range(3, self.ws.max_row + 1)
            if self.ws.cell(r, self.index["نام ونام خانوادگي"]).value
        ]

    def n(self, key, row):
        c = self.index.get(key)
        return num(self.ws.cell(row, c).value) if c else D("0")

    def s(self, key, row):
        c = self.index.get(key)
        return clean(self.ws.cell(row, c).value) if c else ""


def main(path, title):
    sheet = Sheet(path, title)
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
    for r in sheet.rows:
        code = sheet.s("شماره پرسنلی", r) or f"X{r:03d}"
        name = sheet.s("نام ونام خانوادگي", r)
        slip = slips.get(code)
        if slip is None:
            print(f"  ✗ فیشی برای {name} ({code}) ساخته نشد")
            continue
        amounts = {line.component_code: D(line.amount) for line in slip.lines.all()}
        row = {"name": name, "unit": sheet.s("واحد", r), "diffs": {}}
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
            stat = stats.setdefault(f"= {label}", {"column": column, "ok": 0, "bad": 0,
                                                   "delta": D("0"), "worst": None})
            if abs(got - excel) <= 1:
                stat["ok"] += 1
            else:
                stat["bad"] += 1
                stat["delta"] += got - excel
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

    print(f"\n{n} نفر مقایسه شد · {len(clean_rows)} قلم کامل می‌خواند · {len(broken)} قلم نه")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)
    main(sys.argv[1], sys.argv[2])
