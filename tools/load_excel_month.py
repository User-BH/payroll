"""بارگذاری یک ماهِ فایل اکسل شرکت در سامانه، برای مقایسهٔ ریال‌به‌ریال.

    python tools/load_excel_month.py /path/to/1405.xlsx "تیر 1405"

چرا این اسکریپت هست: بهترین آزمونِ یک سامانهٔ حقوق این است که همان ورودی‌هایی
که حسابدار در اکسل وارد می‌کند به سامانه داده شود و خروجی‌ها کنار هم گذاشته
شوند. تفاوت‌ها همان فهرست کارهای باقی‌مانده است.

**فقط ورودی‌ها بارگذاری می‌شوند، نه جواب‌ها.** مزد روزانه، کارکرد، ساعت
اضافه‌کاری، روز مأموریت، پورسانت خام و کسورات وارد می‌شوند؛ حقوق ثابت، بیمه،
مالیات و خالص را خودِ موتور می‌سازد. تنها استثنا آنجاست که سامانه هنوز قاعده‌اش
را ندارد (مابه‌التفاوت پایه سنوات تجمیعی) — آن یکی به‌صورت «مبلغ دستی» وارد
می‌شود، دقیقاً همان کاری که اپراتور امروز می‌کند.

اسکریپت idempotent است: دوباره اجرا کردنش همان نتیجه را می‌دهد.
"""

import os
import re
import sys
from decimal import Decimal as D

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import jdatetime  # noqa: E402
import openpyxl  # noqa: E402

from apps.attendance.models import Timesheet  # noqa: E402
from apps.employees.models import Dependent, Employee, EmploymentContract  # noqa: E402
from apps.org.models import Company, CostCenter, Department, JobTitle  # noqa: E402
from apps.payroll.models import MonthlyParameter, PayrollInput, PayrollPeriod  # noqa: E402
from apps.payroll_config.models import LegalParameter, SalaryComponent  # noqa: E402

MONTH_NAMES = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
               "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def num(value):
    return D(str(value)) if isinstance(value, (int, float)) else D("0")


def jalali(text):
    """«۱۳۹۵/۰۹/۰۱» → تاریخ میلادی."""
    parts = re.findall(r"\d+", clean(text))
    if len(parts) != 3:
        return None
    y, m, d = (int(x) for x in parts)
    return jdatetime.date(y, m, d).togregorian()


class Sheet:
    def __init__(self, path, title):
        book = openpyxl.load_workbook(path, data_only=True)
        self.ws = book[title]
        self.title = title
        self.index = {}
        for c in range(1, self.ws.max_column + 1):
            head = clean(self.ws.cell(1, c).value)
            if head:
                self.index.setdefault(head, c)
        self.rows = [
            r for r in range(3, self.ws.max_row + 1)
            if self.ws.cell(r, self.index["نام ونام خانوادگي"]).value
        ]

    def get(self, key, row):
        c = self.index.get(key)
        return self.ws.cell(row, c).value if c else None

    def n(self, key, row):
        return num(self.get(key, row))

    def s(self, key, row):
        return clean(self.get(key, row))


# ---------------------------------------------------------------- ساختار سازمانی

def ensure_org(company, sheet):
    """واحد و پست سازمانی را از خود فایل می‌سازد.

    مرکز هزینه در فایل تیر خالی است، پس واحد هم‌نام مرکز هزینه گرفته می‌شود —
    گزارش‌های سازمانی بدون مرکز هزینه معنا ندارند.
    """
    units = sorted({sheet.s("واحد", r) for r in sheet.rows if sheet.s("واحد", r)})
    titles = sorted({sheet.s("شغل", r) for r in sheet.rows if sheet.s("شغل", r)})

    centers, departments = {}, {}
    for name in units:
        center, _ = CostCenter.objects.get_or_create(company=company, name=name)
        centers[name] = center
        dept, _ = Department.objects.get_or_create(
            company=company, name=name, defaults={"cost_center": center}
        )
        if dept.cost_center_id != center.pk:
            dept.cost_center = center
            dept.save(update_fields=["cost_center"])
        departments[name] = dept

    jobs = {}
    for name in titles:
        jobs[name], _ = JobTitle.objects.get_or_create(company=company, name=name)
    return departments, centers, jobs


# ---------------------------------------------------------------- پارامترهای سال

def ensure_params(sheet, fiscal_year):
    """مبالغ سال را از خود فایل برمی‌دارد، نه از حدس."""
    row = sheet.rows[0]
    params = LegalParameter.objects.filter(fiscal_year=fiscal_year).first()
    params.min_daily_wage = sheet.n("حداقل دستمزد 1405", row)
    params.housing_allowance = sheet.n("حق مسکن", row)
    params.food_allowance = sheet.n("وجه بن", row)
    params.seniority_daily = sheet.n("پایه سنوات روزانه", row) or D("166667")

    # حق اولاد و حق تأهل باید از سطری خوانده شوند که واقعاً دارندشان
    for r in sheet.rows:
        if sheet.n("تعداد اولاد", r):
            params.child_allowance = sheet.n("حق اولاد", r) / sheet.n("تعداد اولاد", r)
            break
    for r in sheet.rows:
        if sheet.n("حق تاهل", r):
            params.marriage_allowance = sheet.n("حق تاهل", r)
            break
    params.save()
    return params


# ---------------------------------------------------------------- پرسنل

def load_people(company, sheet, departments, centers, jobs, period):
    created = updated = 0
    for r in sheet.rows:
        full = sheet.s("نام ونام خانوادگي", r)
        first, _, last = full.partition(" ")
        code = sheet.s("شماره پرسنلی", r) or f"X{r:03d}"
        hire = jalali(sheet.get("تاریخ شروع بکار", r))
        gender = "F" if "خانم" in sheet.s("آقا / خانم", r) else "M"
        married = "متاهل" in sheet.s("وضعیت تاهل", r)

        # hire_date باید در defaults باشد: get_or_create همان لحظه INSERT می‌زند
        # و این فیلد روی مدل اجباری است.
        employee, is_new = Employee.objects.get_or_create(
            company=company, personnel_code=code,
            defaults={
                "first_name": first,
                "last_name": last.strip() or first,
                "hire_date": hire,
                # فایل کد ملی ندارد و این فیلد در مدل یکتاست. کد پرسنلیِ
                # صفرپرشده گذاشته می‌شود: یکتا هست و آشکارا کد ملی واقعی نیست،
                # پس کسی اشتباهی جایی از آن استفاده نمی‌کند.
                "national_id": code.rjust(10, "0")[:10],
            },
        )
        employee.first_name = first
        employee.last_name = last.strip() or first
        employee.gender = gender
        employee.marital_status = "MARRIED" if married else "SINGLE"
        employee.hire_date = hire
        employee.status = Employee.Status.ACTIVE
        employee.save()
        created += is_new
        updated += not is_new

        # فرزندان: فقط تعدادشان در فایل هست، پس همان تعداد رکورد ساخته می‌شود
        want = int(sheet.n("تعداد اولاد", r))
        have = employee.dependents.filter(relation=Dependent.Relation.CHILD).count()
        for i in range(have, want):
            Dependent.objects.create(
                employee=employee, first_name=f"فرزند {i + 1}", last_name=employee.last_name,
                relation=Dependent.Relation.CHILD, start_date=hire, child_allowance_eligible=True,
            )
        if have > want:
            for extra in employee.dependents.filter(
                relation=Dependent.Relation.CHILD
            ).order_by("-pk")[: have - want]:
                extra.delete()

        unit = sheet.s("واحد", r)
        job = sheet.s("شغل", r)
        years = max(0, (period.end_date - hire).days // 365) if hire else 0
        contract, _ = EmploymentContract.objects.get_or_create(
            employee=employee,
            defaults={
                "effective_from": hire,
                "status": EmploymentContract.Status.ACTIVE,
                "department": departments[unit],
                "cost_center": centers[unit],
                "job_title": jobs[job],
            },
        )
        contract.contract_type = EmploymentContract.ContractType.PERMANENT
        contract.department = departments[unit]
        contract.cost_center = centers[unit]
        contract.job_title = jobs[job]
        contract.effective_from = hire
        contract.daily_wage = sheet.n("مزدروزانه", r)
        contract.seniority_years = years
        contract.status = EmploymentContract.Status.ACTIVE
        contract.save()
    return created, updated


# ---------------------------------------------------------------- کارکرد

def load_timesheets(sheet, period, params):
    day_minutes = params.leave_day_minutes or 440
    for r in sheet.rows:
        code = sheet.s("شماره پرسنلی", r) or f"X{r:03d}"
        employee = Employee.objects.get(company=period.company, personnel_code=code)
        contract = employee.contracts.filter(status="ACTIVE").first()
        timesheet, _ = Timesheet.objects.get_or_create(
            period=period, employee=employee, defaults={"contract": contract}
        )
        timesheet.contract = contract
        timesheet.work_days = sheet.n("کارکرد واقعی ماهانه", r)
        timesheet.absence_days = sheet.n("غیبت", r)
        timesheet.unpaid_leave_days = sheet.n("بدون حقوق", r)
        timesheet.sick_leave_days = sheet.n("بیماری", r)
        timesheet.mission_days = sheet.n("مدت ماموریت", r)
        # اضافه‌کاری: ستون **عادی** خوانده می‌شود نه «واقعی».
        #
        # این دو یکی نیستند و تفاوتشان ساختاری است: برای گروه فروش
        # «عادی = واقعی»، ولی برای گروه پشتیبانی «عادی = محاسبه اضافه کار» —
        # یعنی ساعتی که از زنجیرهٔ مازاد بیرون می‌آید، نه ساعتی که کار کرده.
        # ستون «عادی» همان است که پول رویش حساب می‌شود، پس ورودی درست همان است.
        timesheet.overtime_minutes = int(
            sheet.n("اضافه کاری عادی ساعت", r) * 60 + sheet.n("اضافه کاری عادی دقیقه", r)
        )
        timesheet.status = Timesheet.Status.APPROVED
        timesheet.save()


# ---------------------------------------------------------------- مبالغ دستی

# ستون اکسل → کد قلم حقوقی. فقط چیزهایی که سامانه قاعده‌ای برایشان ندارد.
MANUAL = {
    "مابه التفاوت پایه سنوات تجمیعی قابل پرداخت": "DIFF",
    "پورسانت یک": "COMM_1",
    "پورسانت دو": "COMM_2",
    "پورسانت سه": "COMM_3",
    "طلب ماه قبل": "PREV_CLAIM",
    "وجه مرخصی": "LEAVE_PAY",
    "علی الحساب واریزی": "ADVANCE",
    "خرید از شرکت": "GOODS",
    "بدهی از ماه قبل": "PREV_DEBT",
    "بدهی متفرقه": "OTHER_DEBT",
    "بیمه تکمیلی": "SUPP_INS",
    "جرائم وخلافی خودروها": "VEHICLE_FINE",
    "آزمایش وطب کار": "MEDICAL",
    "مبلغ کسر کار - دیر کرد": "LATE",
}


def load_manual(sheet, period):
    codes = {c.code: c for c in SalaryComponent.objects.filter(company=period.company)}
    written = skipped = 0
    for r in sheet.rows:
        pcode = sheet.s("شماره پرسنلی", r) or f"X{r:03d}"
        employee = Employee.objects.get(company=period.company, personnel_code=pcode)
        for column, code in MANUAL.items():
            component = codes.get(code)
            if component is None:
                skipped += 1
                continue
            value = sheet.n(column, r)
            if not value:
                PayrollInput.objects.filter(
                    period=period, employee=employee, component=component
                ).delete()
                continue
            PayrollInput.objects.update_or_create(
                period=period, employee=employee, component=component,
                defaults={"amount": value},
            )
            written += 1
    return written, skipped


def main(path, title):
    company = Company.objects.first()
    sheet = Sheet(path, title)
    month = MONTH_NAMES.index(title.split()[0]) + 1
    year = int(title.split()[1])

    fiscal = company.fiscal_years.get(year=year)
    period = PayrollPeriod.objects.filter(company=company, year=year, month=month).first()
    if period is None:
        from apps.payroll.utils import jalali_month_range

        start, end = jalali_month_range(year, month)
        period = PayrollPeriod.objects.create(
            company=company, fiscal_year=fiscal, year=year, month=month,
            start_date=start, end_date=end, status=PayrollPeriod.Status.DRAFT,
        )
    period.status = PayrollPeriod.Status.DRAFT
    period.save()

    params = ensure_params(sheet, fiscal)
    departments, centers, jobs = ensure_org(company, sheet)
    created, updated = load_people(company, sheet, departments, centers, jobs, period)
    load_timesheets(sheet, period, params)
    written, skipped = load_manual(sheet, period)

    print(f"دوره      : {period.title}  ({period.month_days} روز)")
    print(f"پرسنل     : {created} تازه · {updated} به‌روز")
    print(f"کارکرد    : {Timesheet.objects.filter(period=period).count()} سطر")
    print(f"مبالغ دستی: {written} مقدار" + (f" · {skipped} قلمِ نبود" if skipped else ""))
    print(f"پارامترها : حداقل {params.min_daily_wage:,.0f} · مسکن {params.housing_allowance:,.0f}"
          f" · بن {params.food_allowance:,.0f} · اولاد {params.child_allowance:,.0f}"
          f" · تأهل {params.marriage_allowance:,.0f} · سنوات روزانه {params.seniority_daily:,.0f}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)
    main(sys.argv[1], sys.argv[2])
