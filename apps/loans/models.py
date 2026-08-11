from decimal import Decimal

from django.db import models

from apps.employees.models import Employee


class Loan(models.Model):
    """وام یا مساعده."""

    class LoanType(models.TextChoices):
        LOAN = "LOAN", "وام"
        ADVANCE = "ADVANCE", "مساعده"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "جاری"
        SETTLED = "SETTLED", "تسویه‌شده"
        SUSPENDED = "SUSPENDED", "معلق"
        CANCELLED = "CANCELLED", "لغوشده"

    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="loans", verbose_name="پرسنل"
    )
    loan_type = models.CharField(
        "نوع", max_length=8, choices=LoanType.choices, default=LoanType.LOAN
    )
    title = models.CharField("عنوان", max_length=100, blank=True)
    principal = models.DecimalField("مبلغ اصل (ریال)", max_digits=18, decimal_places=0)
    total_installments = models.PositiveSmallIntegerField("تعداد اقساط", default=1)
    installment_amount = models.DecimalField("مبلغ هر قسط", max_digits=18, decimal_places=0)
    grant_date = models.DateField("تاریخ پرداخت", null=True, blank=True)
    first_year = models.PositiveSmallIntegerField("سال اولین قسط")
    first_month = models.PositiveSmallIntegerField("ماه اولین قسط")
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    notes = models.CharField("توضیحات", max_length=200, blank=True)

    class Meta:
        verbose_name = "وام و مساعده"
        verbose_name_plural = "وام و مساعده"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.get_loan_type_display()} {self.employee.full_name}"

    @property
    def paid_amount(self) -> Decimal:
        agg = self.installments.filter(status=LoanInstallment.Status.DEDUCTED).aggregate(
            total=models.Sum("amount")
        )
        return agg["total"] or Decimal("0")

    @property
    def remaining(self) -> Decimal:
        return self.principal - self.paid_amount


class LoanInstallment(models.Model):
    """قسط.

    هر قسط باید بداند دقیقاً در کدام سطر کدام فیش کسر شده — به همین دلیل
    payslip_line نگه داشته می‌شود، نه فقط یک پرچم «پرداخت شد».
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "سررسید نشده"
        DUE = "DUE", "سررسید"
        DEDUCTED = "DEDUCTED", "کسر شده"
        SKIPPED = "SKIPPED", "رد شده"
        WAIVED = "WAIVED", "بخشیده شده"

    loan = models.ForeignKey(
        Loan, on_delete=models.CASCADE, related_name="installments", verbose_name="وام"
    )
    number = models.PositiveSmallIntegerField("شماره قسط")
    due_year = models.PositiveSmallIntegerField("سال سررسید")
    due_month = models.PositiveSmallIntegerField("ماه سررسید")
    amount = models.DecimalField("مبلغ", max_digits=18, decimal_places=0)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.PENDING)
    payslip_line = models.ForeignKey(
        "payroll.PayslipLine", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="loan_installments", verbose_name="سطر کسر",
    )
    deducted_at = models.DateTimeField("زمان کسر", null=True, blank=True)

    class Meta:
        verbose_name = "قسط"
        verbose_name_plural = "اقساط"
        ordering = ["loan", "number"]
        unique_together = [("loan", "number")]
        indexes = [models.Index(fields=["due_year", "due_month", "status"])]

    def __str__(self):
        return f"قسط {self.number} — {self.amount}"
