"""سرویس‌های پرسنل — کارهایی که بیش از یک مدل را با هم درگیر می‌کنند.

دلیل جدا بودن از views: ساخت «قرارداد اولیه» هم از فرم افزودن پرسنل صدا زده
می‌شود و هم می‌تواند از دستورهای مدیریتی صدا زده شود؛ منطقش نباید داخل view
بماند.
"""

from decimal import Decimal

from apps.employees.models import EmploymentContract
from apps.org.models import CostCenter, Department, JobTitle


def org_defaults(company):
    """اولین واحد، مرکز هزینه و پست سازمانیِ فعالِ شرکت.

    قرارداد بدون این سه نمی‌تواند ساخته شود (هر سه در مدل الزامی‌اند). در فرم
    افزودن پرسنل این‌ها پرسیده نمی‌شوند، پس مقدار پیش‌فرض از ساختار سازمانی
    برداشته می‌شود و کاربر بعداً در «ویرایش قرارداد» اصلاحش می‌کند.
    """
    department = Department.objects.filter(company=company, is_active=True).order_by("pk").first()
    cost_center = CostCenter.objects.filter(company=company, is_active=True).order_by("pk").first()
    job_title = JobTitle.objects.filter(company=company, is_active=True).order_by("pk").first()
    return department, cost_center, job_title


def _starting_wage(employee, daily_wage):
    """مزد روزانهٔ قرارداد تازه.

    موتور محاسبه از قبل می‌دانست که مزدِ صفر یعنی «با حداقل دستمزد حساب کن»،
    ولی صفحهٔ پرسنل همان صفر را نشان می‌داد و کاربر فکر می‌کرد مزدی ثبت نشده.
    حالا همان لحظهٔ ساخت، عددِ واقعیِ سال مالی نوشته می‌شود تا آنچه روی صفحه
    دیده می‌شود همان باشد که در محاسبه به کار می‌رود.

    فقط هنگام **ساخت** — ویرایش بعدی دست کاربر است و اگر صفرش کند، صفر
    می‌ماند.
    """
    if daily_wage:
        return Decimal(daily_wage)

    from apps.payroll_config.models import LegalParameter

    params = (
        LegalParameter.objects.filter(fiscal_year__company=employee.company)
        .order_by("-effective_from")
        .first()
    )
    return Decimal(getattr(params, "min_daily_wage", 0) or 0)


def missing_org_labels(company):
    """نام آن بخش‌هایی از ساختار سازمانی که هنوز تعریف نشده‌اند."""
    department, cost_center, job_title = org_defaults(company)
    missing = []
    if department is None:
        missing.append("واحد سازمانی")
    if cost_center is None:
        missing.append("مرکز هزینه")
    if job_title is None:
        missing.append("پست سازمانی")
    return missing


def department_for(cost_center):
    """واحد سازمانیِ متناظر یک مرکز هزینه.

    مدل هنوز «واحد» را الزامی می‌داند ولی در عمل مقدارش با مرکز هزینه یکی
    است، پس دیگر از کاربر پرسیده نمی‌شود: اول واحدی که به همین مرکز هزینه وصل
    است، وگرنه هم‌نامش، وگرنه هر واحدی که باشد تا قرارداد ساخته شود.
    """
    if cost_center is None:
        return None
    linked = Department.objects.filter(
        company=cost_center.company, cost_center=cost_center, is_active=True
    ).order_by("name").first()
    if linked:
        return linked
    same_name = Department.objects.filter(
        company=cost_center.company, name=cost_center.name, is_active=True
    ).first()
    if same_name:
        return same_name
    return Department.objects.filter(
        company=cost_center.company, is_active=True
    ).order_by("name").first()


def create_initial_contract(
    employee, contract_type, effective_from=None,
    cost_center=None, job_title=None, daily_wage=None,
):
    """قرارداد اولیهٔ پرسنل تازه‌افزوده‌شده.

    فقط «نوع قرارداد» از کاربر پرسیده می‌شود؛ بقیهٔ فیلدها پیش‌فرض می‌گیرند تا
    پرسنل بلافاصله فعال و قابل مشاهده باشد. مزد روزانه عمداً صفر می‌ماند —
    عددِ حدسی به‌جای عددِ واقعی، اشتباهی است که تا فیش حقوقی پنهان می‌ماند،
    ولی صفر در همان صفحهٔ پرسنل با هشدار دیده می‌شود.

    اگر ساختار سازمانی هنوز تعریف نشده باشد None برمی‌گرداند و پرسنل بدون
    قرارداد ثبت می‌شود (به‌جای اینکه کل ثبت شکست بخورد).
    """
    if cost_center is None or job_title is None:
        fallback_dept, fallback_cc, fallback_job = org_defaults(employee.company)
        cost_center = cost_center or fallback_cc
        job_title = job_title or fallback_job
    department = department_for(cost_center)
    if not (department and cost_center and job_title):
        return None

    contract = EmploymentContract(
        employee=employee,
        contract_type=contract_type or EmploymentContract.ContractType.PERMANENT,
        department=department,
        cost_center=cost_center,
        job_title=job_title,
        effective_from=effective_from or employee.hire_date,
        daily_wage=_starting_wage(employee, daily_wage),
        status=EmploymentContract.Status.ACTIVE,
    )
    contract.full_clean(exclude=["employee"])
    contract.save()
    return contract
