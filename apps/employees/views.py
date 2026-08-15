from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import can_edit_required, payroll_staff_required
from apps.employees.forms import (
    BankAccountForm,
    ContractForm,
    DependentForm,
    EmployeeForm,
    EmployeeImportForm,
)
from apps.employees.importer import build_template, import_employees
from apps.employees.models import Employee
from apps.org.models import Company
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


@can_edit_required
def employee_create(request):
    form = EmployeeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        employee = form.save(commit=False)
        employee.company = Company.objects.first()
        employee.save()
        messages.success(
            request,
            f"{employee.full_name} ثبت شد. حالا قرارداد او را تعریف کنید تا در محاسبه لحاظ شود.",
        )
        return redirect("contract_create", pk=employee.pk)
    return render(
        request, "employees/form.html", {"form": form, "title": "افزودن پرسنل"}
    )


@can_edit_required
def employee_edit(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    form = EmployeeForm(request.POST or None, instance=employee)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "اطلاعات پرسنل به‌روز شد.")
        return redirect("employee_detail", pk=employee.pk)
    return render(
        request,
        "employees/form.html",
        {"form": form, "title": f"ویرایش {employee.full_name}", "employee": employee},
    )


@can_edit_required
def contract_create(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    form = ContractForm(request.POST or None, employee=employee)
    if request.method == "POST" and form.is_valid():
        contract = form.save(commit=False)
        contract.employee = employee
        contract.save()
        messages.success(request, "قرارداد ثبت شد.")
        return redirect("employee_detail", pk=employee.pk)
    return render(
        request,
        "employees/contract_form.html",
        {"form": form, "employee": employee, "title": "قرارداد جدید"},
    )


@can_edit_required
def contract_edit(request, pk):
    from apps.employees.models import EmploymentContract

    contract = get_object_or_404(EmploymentContract.objects.select_related("employee"), pk=pk)
    form = ContractForm(request.POST or None, instance=contract, employee=contract.employee)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "قرارداد به‌روز شد.")
        return redirect("employee_detail", pk=contract.employee.pk)
    return render(
        request,
        "employees/contract_form.html",
        {"form": form, "employee": contract.employee, "title": "ویرایش قرارداد"},
    )


@can_edit_required
def bank_account_create(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    form = BankAccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        account = form.save(commit=False)
        account.employee = employee
        if account.is_default:
            employee.bank_accounts.update(is_default=False)
        account.save()
        messages.success(request, "حساب بانکی ثبت شد.")
        return redirect("employee_detail", pk=employee.pk)
    return render(
        request,
        "employees/simple_form.html",
        {"form": form, "employee": employee, "title": "افزودن حساب بانکی"},
    )


@can_edit_required
def dependent_create(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    form = DependentForm(request.POST or None, initial={"start_date": employee.hire_date})
    if request.method == "POST" and form.is_valid():
        dependent = form.save(commit=False)
        dependent.employee = employee
        dependent.save()
        messages.success(request, "فرد تحت تکفل ثبت شد.")
        return redirect("employee_detail", pk=employee.pk)
    return render(
        request,
        "employees/simple_form.html",
        {"form": form, "employee": employee, "title": "افزودن فرد تحت تکفل"},
    )


@can_edit_required
@require_POST
def employee_terminate(request, pk):
    """ثبت خروج پرسنل.

    سه کار با هم انجام می‌شود، چون جدا انجام دادنشان یعنی پرسنلِ خارج‌شده در
    محاسبه ماه بعد هم می‌آید: وضعیت خاتمه، تاریخ خروج، و بستن قرارداد فعال.
    """
    from apps.employees.models import EmploymentContract
    from apps.payroll.utils import parse_jalali_input

    employee = get_object_or_404(Employee, pk=pk)
    raw_date = (request.POST.get("termination_date") or "").strip()
    reason = (request.POST.get("termination_reason") or "").strip()

    date_value = parse_jalali_input(raw_date)
    if date_value is None:
        messages.error(request, "تاریخ خروج معتبر نیست.")
        return redirect("employee_detail", pk=employee.pk)

    employee.termination_date = date_value
    employee.termination_reason = reason
    employee.status = Employee.Status.TERMINATED
    employee.save(update_fields=["termination_date", "termination_reason", "status"])

    closed = 0
    for contract in employee.contracts.filter(status=EmploymentContract.Status.ACTIVE):
        contract.effective_to = date_value
        contract.status = EmploymentContract.Status.ENDED
        contract.save(update_fields=["effective_to", "status"])
        closed += 1

    messages.success(
        request,
        f"خروج {employee.full_name} ثبت شد و {closed} قرارداد فعال بسته شد. "
        "از دوره‌های بعدی در محاسبه نمی‌آید. "
        "توجه: تسویه‌حساب پایان کار هنوز در سامانه نیست و باید دستی انجام شود.",
    )
    return redirect("employee_detail", pk=employee.pk)


@can_edit_required
@require_POST
def employee_reactivate(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    employee.status = Employee.Status.ACTIVE
    employee.termination_date = None
    employee.termination_reason = ""
    employee.save(update_fields=["status", "termination_date", "termination_reason"])
    messages.success(
        request,
        f"{employee.full_name} دوباره فعال شد. برای ورود به چرخه حقوق باید "
        "قرارداد جدیدی برایش تعریف کنید.",
    )
    return redirect("employee_detail", pk=employee.pk)


@payroll_staff_required
def employee_import_template(request):
    response = HttpResponse(
        build_template(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="employees-template.xlsx"'
    return response


@can_edit_required
def employee_import(request):
    form = EmployeeImportForm(request.POST or None, request.FILES or None)
    result = None
    if request.method == "POST" and form.is_valid():
        try:
            result = import_employees(
                form.cleaned_data["file"],
                Company.objects.first(),
                create_contracts=form.cleaned_data["create_contracts"],
            )
        except Exception as exc:  # noqa: BLE001 — خطای فایل باید به کاربر نشان داده شود
            messages.error(request, f"فایل خوانده نشد: {exc}")
        else:
            if result["errors"]:
                messages.error(
                    request,
                    f"{len(result['errors'])} سطر ایراد دارد و هیچ رکوردی ثبت نشد. "
                    "ابتدا ایرادها را در فایل اصلاح کنید.",
                )
            else:
                messages.success(request, f"{result['created']} پرسنل با موفقیت وارد شد.")
                return redirect("employee_list")
    return render(request, "employees/import.html", {"form": form, "result": result})


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
