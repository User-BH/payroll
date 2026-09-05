"""مدیریت وام و مساعده.

موتور محاسبه اقساط سررسیدشده را کسر می‌کند؛ اینجا وام ثبت و جدول اقساطش ساخته
می‌شود. اقساط در لحظه ثبت وام یک‌جا تولید می‌شوند تا سررسیدها از قبل مشخص و
قابل بازبینی باشند، نه اینکه هر ماه حدس زده شوند.
"""

from decimal import Decimal

from django import forms
from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from apps.org.current import active_company
from django.views.decorators.http import require_POST

from apps.accounts.decorators import can_edit_required, payroll_staff_required
from apps.employees.forms import BootstrapMixin
from apps.payroll.form_fields import JalaliDateField
from apps.employees.models import Employee
from apps.loans.models import Loan, LoanInstallment
from apps.payroll.utils import JALALI_MONTHS


class LoanForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Loan
        fields = [
            "employee", "loan_type", "title", "principal", "total_installments",
            "installment_amount", "grant_date", "first_year", "first_month", "notes",
        ]

    grant_date = JalaliDateField(label="تاریخ پرداخت", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(
            status=Employee.Status.ACTIVE
        ).order_by("personnel_code")
        self.fields["first_month"].widget = forms.Select(
            choices=list(enumerate(JALALI_MONTHS, start=1)), attrs={"class": "input"}
        )
        self.fields["installment_amount"].required = False
        self.fields["installment_amount"].help_text = (
            "خالی بگذارید تا از تقسیم مبلغ اصل بر تعداد اقساط محاسبه شود"
        )

    def clean(self):
        cleaned = super().clean()
        principal = cleaned.get("principal") or Decimal("0")
        count = cleaned.get("total_installments") or 0
        amount = cleaned.get("installment_amount")

        if count < 1:
            self.add_error("total_installments", "تعداد اقساط باید حداقل ۱ باشد.")
            return cleaned

        if not amount:
            amount = (principal / count).quantize(Decimal("1"))
            cleaned["installment_amount"] = amount

        if amount * count < principal:
            self.add_error(
                "installment_amount",
                f"جمع اقساط ({amount * count:,.0f}) از مبلغ وام ({principal:,.0f}) کمتر است.",
            )
        return cleaned


def _build_installments(loan):
    """ساخت جدول اقساط. قسط آخر مانده را جبران می‌کند تا جمع دقیقاً برابر اصل شود."""
    LoanInstallment.objects.filter(loan=loan).delete()
    year, month = loan.first_year, loan.first_month
    remaining = loan.principal
    rows = []
    for number in range(1, loan.total_installments + 1):
        is_last = number == loan.total_installments
        amount = remaining if is_last else min(loan.installment_amount, remaining)
        rows.append(
            LoanInstallment(
                loan=loan, number=number, due_year=year, due_month=month,
                amount=amount, status=LoanInstallment.Status.DUE,
            )
        )
        remaining -= amount
        month += 1
        if month > 12:
            month, year = 1, year + 1
    LoanInstallment.objects.bulk_create(rows)


@payroll_staff_required
def loan_list(request):
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    loans = (
        Loan.objects.filter(employee__company=active_company(request))
        .select_related("employee")
        .order_by("-id")
    )
    if query:
        loans = loans.filter(
            Q(employee__first_name__icontains=query)
            | Q(employee__last_name__icontains=query)
            | Q(employee__personnel_code__icontains=query)
        )
    if status:
        loans = loans.filter(status=status)

    totals = loans.aggregate(principal=Sum("principal"))
    rows = [{"loan": loan, "remaining": loan.remaining} for loan in loans]
    return render(
        request,
        "loans/list.html",
        {
            "rows": rows,
            "q": query,
            "status": status,
            "statuses": Loan.Status.choices,
            "total_principal": totals["principal"] or 0,
            "total_remaining": sum(r["remaining"] for r in rows),
        },
    )


@can_edit_required
def loan_create(request):
    form = LoanForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        loan = form.save()
        _build_installments(loan)
        messages.success(
            request,
            f"وام ثبت شد و {loan.total_installments} قسط از "
            f"{JALALI_MONTHS[loan.first_month - 1]} {loan.first_year} ساخته شد.",
        )
        return redirect("loan_detail", pk=loan.pk)
    return render(request, "loans/form.html", {"form": form, "title": "ثبت وام یا مساعده"})


@can_edit_required
def loan_edit(request, pk):
    loan = get_object_or_404(Loan, pk=pk)
    deducted = loan.installments.filter(status=LoanInstallment.Status.DEDUCTED).exists()
    form = LoanForm(request.POST or None, instance=loan)

    if request.method == "POST" and form.is_valid():
        if deducted:
            messages.error(
                request,
                "از این وام قسطی کسر شده و مبالغش قابل تغییر نیست. "
                "برای اصلاح، وام را معلق کنید و وام جدیدی ثبت کنید.",
            )
            return redirect("loan_detail", pk=loan.pk)
        loan = form.save()
        _build_installments(loan)
        messages.success(request, "وام و جدول اقساطش به‌روز شد.")
        return redirect("loan_detail", pk=loan.pk)

    return render(
        request,
        "loans/form.html",
        {"form": form, "loan": loan, "deducted": deducted, "title": "ویرایش وام"},
    )


@payroll_staff_required
def loan_detail(request, pk):
    loan = get_object_or_404(Loan.objects.select_related("employee"), pk=pk)
    installments = loan.installments.select_related(
        "payslip_line", "payslip_line__payslip", "payslip_line__payslip__period"
    ).order_by("number")
    return render(
        request,
        "loans/detail.html",
        {
            "loan": loan,
            "installments": installments,
            "paid": loan.paid_amount,
            "remaining": loan.remaining,
        },
    )


@can_edit_required
@require_POST
def loan_set_status(request, pk):
    loan = get_object_or_404(Loan, pk=pk)
    status = request.POST.get("status")
    if status not in dict(Loan.Status.choices):
        messages.error(request, "وضعیت نامعتبر است.")
        return redirect("loan_detail", pk=loan.pk)

    loan.status = status
    loan.save(update_fields=["status"])
    if status != Loan.Status.ACTIVE:
        # اقساط کسرنشده دیگر نباید در محاسبه بیایند
        loan.installments.filter(
            status__in=[LoanInstallment.Status.PENDING, LoanInstallment.Status.DUE]
        ).update(status=LoanInstallment.Status.SKIPPED)
        messages.info(request, "اقساط کسرنشده از چرخه محاسبه خارج شدند.")
    else:
        loan.installments.filter(status=LoanInstallment.Status.SKIPPED).update(
            status=LoanInstallment.Status.DUE
        )
        messages.success(request, "وام دوباره فعال شد و اقساطش به چرخه برگشتند.")
    return redirect("loan_detail", pk=loan.pk)
