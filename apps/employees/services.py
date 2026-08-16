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


def create_initial_contract(employee, contract_type, effective_from=None):
    """قرارداد اولیهٔ پرسنل تازه‌افزوده‌شده.

    فقط «نوع قرارداد» از کاربر پرسیده می‌شود؛ بقیهٔ فیلدها پیش‌فرض می‌گیرند تا
    پرسنل بلافاصله فعال و قابل مشاهده باشد. حقوق پایه عمداً صفر می‌ماند —
    عددِ حدسی به‌جای عددِ واقعی، اشتباهی است که تا فیش حقوقی پنهان می‌ماند،
    ولی صفر در همان صفحهٔ پرسنل با هشدار دیده می‌شود.

    اگر ساختار سازمانی هنوز تعریف نشده باشد None برمی‌گرداند و پرسنل بدون
    قرارداد ثبت می‌شود (به‌جای اینکه کل ثبت شکست بخورد).
    """
    department, cost_center, job_title = org_defaults(employee.company)
    if not (department and cost_center and job_title):
        return None

    contract = EmploymentContract(
        employee=employee,
        contract_type=contract_type or EmploymentContract.ContractType.PERMANENT,
        department=department,
        cost_center=cost_center,
        job_title=job_title,
        effective_from=effective_from or employee.hire_date,
        base_salary=Decimal("0"),
        status=EmploymentContract.Status.ACTIVE,
    )
    contract.full_clean(exclude=["employee"])
    contract.save()
    return contract
