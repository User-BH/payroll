from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from apps.accounts.decorators import payroll_staff_required
from apps.employees.models import Employee
from apps.payroll.models import Payslip


def _filtered_employees(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    employees = Employee.objects.select_related("company").prefetch_related("contracts")
    if query:
        employees = employees.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(personnel_code__icontains=query)
            | Q(national_id__icontains=query)
        )
    if status:
        employees = employees.filter(status=status)
    return employees.order_by("personnel_code"), query, status


def _page(request, queryset):
    paginator = Paginator(queryset, 25)
    return paginator.get_page(request.GET.get("page") or 1)


def _decorate(page_obj):
    """قرارداد جاری هر پرسنل را برای نمایش ضمیمه می‌کند."""
    rows = []
    for employee in page_obj:
        contract = employee.contracts.filter(status="ACTIVE").order_by("-effective_from").first()
        rows.append({"employee": employee, "contract": contract})
    return rows


@payroll_staff_required
def employee_list(request):
    employees, query, status = _filtered_employees(request)
    page_obj = _page(request, employees)
    return render(
        request,
        "employees/list.html",
        {
            "rows": _decorate(page_obj),
            "page_obj": page_obj,
            "q": query,
            "status": status,
            "total": employees.count(),
            "statuses": Employee.Status.choices,
        },
    )


@payroll_staff_required
def employee_rows(request):
    """پاسخ HTMX برای جستجوی زنده — فقط بدنه جدول برمی‌گردد."""
    employees, query, status = _filtered_employees(request)
    page_obj = _page(request, employees)
    return render(
        request,
        "employees/_rows.html",
        {
            "rows": _decorate(page_obj),
            "page_obj": page_obj,
            "q": query,
            "status": status,
            "total": employees.count(),
        },
    )


@payroll_staff_required
def employee_detail(request, pk):
    employee = get_object_or_404(
        Employee.objects.select_related("company"), pk=pk
    )
    contracts = employee.contracts.select_related(
        "department", "cost_center", "job_title"
    ).order_by("-effective_from")
    payslips = (
        Payslip.objects.filter(employee=employee)
        .select_related("period")
        .order_by("-period__year", "-period__month")[:12]
    )
    return render(
        request,
        "employees/detail.html",
        {
            "employee": employee,
            "contracts": contracts,
            "current_contract": contracts.filter(status="ACTIVE").first(),
            "dependents": employee.dependents.all(),
            "bank_accounts": employee.bank_accounts.all(),
            "payslips": payslips,
            "loans": employee.loans.all(),
        },
    )
