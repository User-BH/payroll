from django.contrib import messages
from django.utils import timezone
from django.core.exceptions import ValidationError
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
    EmployeeCreateForm,
    EmployeeForm,
    EmployeeImportForm,
    SignatureForm,
)
from apps.employees.importer import build_template, import_employees
from apps.employees.models import Employee
from apps.employees.services import (
    create_initial_contract,
    missing_org_labels,
    org_defaults,
)
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
    """افزودن پرسنل — یک صفحه، یک بار ذخیره، پرسنلِ فعال.

    قبلاً بعد از ثبتِ اطلاعات هویتی، کاربر به فرم کاملِ قرارداد پرت می‌شد و تا
    پر نکردنِ آن، پرسنل «بدون قرارداد» می‌ماند. حالا فقط نوع قرارداد در همین
    صفحه پرسیده می‌شود و قرارداد فعال خودکار ساخته می‌شود.
    """
    from apps.attendance.services import default_work_days, open_period_for, set_initial_timesheet

    company = Company.objects.first()
    if company is None:
        messages.error(
            request,
            "هنوز هیچ شرکتی تعریف نشده است. ابتدا از «ساختار سازمانی» شرکت را بسازید "
            "(یا روی سرور دستور setup_operational را اجرا کنید).",
        )
        return redirect("employee_list")

    period = open_period_for(company)
    # کارکرد ماهانه عمداً پیش‌فرض ندارد: تاریخ استخدام هنوز وارد نشده، پس
    # عددِ «کل ماه» برای کسی که وسط ماه استخدام می‌شود غلط است. خالی بماند تا
    # بعد از ذخیره از روی همان تاریخ حساب شود.
    form = EmployeeCreateForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        employee = form.save(commit=False)
        employee.company = company
        employee.save()
        account = form.save_bank_account(employee)

        try:
            contract = create_initial_contract(
                employee, form.cleaned_data.get("contract_type")
            )
        except ValidationError as exc:
            contract = None
            messages.error(
                request,
                f"{employee.full_name} ثبت شد ولی قرارداد ساخته نشد: "
                f"{'؛ '.join(exc.messages)} — قرارداد را دستی تعریف کنید.",
            )
        else:
            if contract is None:
                missing = "، ".join(missing_org_labels(company)) if company else "شرکت"
                messages.warning(
                    request,
                    f"{employee.full_name} ثبت شد ولی قرارداد ساخته نشد چون {missing} "
                    "هنوز تعریف نشده است. ابتدا آن را در «ساختار سازمانی» بسازید، "
                    "سپس برای این پرسنل قرارداد تعریف کنید.",
                )

        # کارکرد بدون قرارداد در محاسبه معنایی ندارد، پس فقط وقتی ثبت می‌شود
        # که قرارداد ساخته شده باشد.
        timesheet = None
        if contract is not None:
            timesheet = set_initial_timesheet(
                employee, form.cleaned_data.get("monthly_work_days"), user=request.user
            )

        if contract is not None:
            note = (
                f" کارکرد {period.title} هم ثبت شد."
                if timesheet is not None and period is not None
                else ""
            )
            if account is not None:
                note += f" حساب {account.bank_name} ثبت شد."
            else:
                note += " حساب بانکی ثبت نشد — بدون آن، پرسنل در فایل پرداخت بانک نمی‌آید."
            messages.success(
                request,
                f"{employee.full_name} با قرارداد {contract.get_contract_type_display()} "
                f"ثبت و فعال شد.{note} "
                "مزد روزانه خالی است، پس فعلاً با حداقل دستمزد روزانهٔ سال حساب "
                "می‌شود — اگر مزد توافقی دارد، از دکمهٔ «ویرایش قرارداد» ثبتش کنید.",
            )
        return redirect("employee_detail", pk=employee.pk)

    return render(
        request,
        "employees/form.html",
        {
            "form": form,
            "title": "افزودن پرسنل",
            "open_period": period,
            "missing_org": missing_org_labels(company) if company else ["شرکت"],
        },
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
    department, cost_center, job_title = org_defaults(employee.company)
    form = ContractForm(
        request.POST or None,
        employee=employee,
        initial={
            "effective_from": employee.hire_date,
            "department": department,
            "cost_center": cost_center,
            "job_title": job_title,
        },
    )
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


@can_edit_required
@require_POST
def employee_signature_upload(request, pk):
    """ثبت تصویر امضای پرسنل از پنل.

    تا امروز فقط خودِ پرسنل می‌توانست از پرتال امضایش را بارگذاری کند. ولی
    امضاها روی کاغذِ پروندهٔ پرسنلی‌اند و واحد مالی آن‌ها را اسکن می‌کند — و
    کسی که پرتال ندارد یا با آن کار نمی‌کند، امضایش هیچ‌وقت روی فیش نمی‌نشست.

    همان فرم پرتال به کار می‌رود تا محدودیت حجم و نوع فایل یک جا بماند.
    """
    employee = get_object_or_404(Employee, pk=pk)
    form = SignatureForm(request.POST, request.FILES, instance=employee)
    if form.is_valid():
        form.save()
        messages.success(
            request,
            f"امضای {employee.full_name} ثبت شد. از این پس روی فیش‌هایی که "
            "خودش تأیید کند چاپ می‌شود.",
        )
    else:
        messages.error(request, " ".join(form.errors.get("signature", ["فایل معتبر نیست."])))
    return redirect("employee_detail", pk=employee.pk)


@can_edit_required
@require_POST
def employee_signature_clear(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    employee.signature = None
    employee.save(update_fields=["signature"])
    messages.success(request, f"امضای {employee.full_name} حذف شد.")
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
    from apps.attendance.services import get_or_create_timesheet, open_period_for

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

    # کارکرد ماهانهٔ دورهٔ باز — همان رکوردی که در جدول کارکرد دوره هم دیده
    # می‌شود؛ اینجا فقط برای همین یک نفر قابل ویرایش است.
    open_period = open_period_for(employee.company)
    timesheet = None
    if open_period is not None and employee.status == Employee.Status.ACTIVE:
        timesheet = get_or_create_timesheet(employee, open_period)

    # حقوق پایهٔ خالی یعنی «با حداقل دستمزد حساب کن» — پس باید بدانیم آن عدد
    # اصلاً پر شده است یا نه، وگرنه حقوق ثابت بی‌صدا صفر می‌شود.
    parameter = getattr(open_period, "legal_parameter", None) if open_period else None
    min_daily_wage = parameter.min_daily_wage if parameter else None

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
            "open_period": open_period,
            "timesheet": timesheet,
            "min_daily_wage": min_daily_wage,
            # سابقه ذخیره نمی‌شود؛ نسبت به پایان دورهٔ باز (یا امروز) حساب
            # می‌شود تا هیچ‌وقت کهنه نشود.
            "seniority_years": employee.seniority_years_at(
                open_period.end_date if open_period else timezone.localdate()
            ),
        },
    )
