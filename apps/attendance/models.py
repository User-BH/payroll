from decimal import Decimal

from django.db import models

from apps.employees.models import Employee, EmploymentContract


class Timesheet(models.Model):
    """کارکرد ماهانه یک پرسنل در یک دوره.

    این جدول ورودی اصلی موتور محاسبه است. در ماکاپ داشبورد، «۴ نفر باقی مانده»
    یعنی چهار پرسنل فعال هنوز رکورد تأییدشده در این جدول ندارند.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "پیش‌نویس"
        SUBMITTED = "SUBMITTED", "ارسال‌شده"
        APPROVED = "APPROVED", "تأییدشده"

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "ورود دستی"
        IMPORT = "IMPORT", "فایل اکسل"
        DEVICE = "DEVICE", "دستگاه حضور و غیاب"

    class ShiftType(models.TextChoices):
        NONE = "NONE", "بدون نوبت‌کاری"
        MORNING_EVENING = "MORNING_EVENING", "صبح و عصر"
        MORNING_NIGHT = "MORNING_NIGHT", "صبح و شب"
        ALL = "ALL", "صبح، عصر و شب"

    period = models.ForeignKey(
        "payroll.PayrollPeriod", on_delete=models.CASCADE,
        related_name="timesheets", verbose_name="دوره",
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="timesheets", verbose_name="پرسنل"
    )
    contract = models.ForeignKey(
        EmploymentContract, on_delete=models.PROTECT, null=True, blank=True,
        related_name="timesheets", verbose_name="قرارداد",
    )

    work_days = models.DecimalField("روز کارکرد", max_digits=6, decimal_places=2, default=Decimal("30"))
    absence_days = models.DecimalField("غیبت", max_digits=6, decimal_places=2, default=0)
    unpaid_leave_days = models.DecimalField("مرخصی بدون حقوق", max_digits=6, decimal_places=2, default=0)
    paid_leave_days = models.DecimalField("مرخصی استحقاقی", max_digits=6, decimal_places=2, default=0)
    sick_leave_days = models.DecimalField("مرخصی استعلاجی", max_digits=6, decimal_places=2, default=0)
    mission_days = models.DecimalField("مأموریت", max_digits=6, decimal_places=2, default=0)

    overtime_hours = models.DecimalField("اضافه‌کاری (ساعت)", max_digits=6, decimal_places=2, default=0)
    night_hours = models.DecimalField("شب‌کاری (ساعت)", max_digits=6, decimal_places=2, default=0)
    friday_hours = models.DecimalField("جمعه‌کاری (ساعت)", max_digits=6, decimal_places=2, default=0)
    holiday_hours = models.DecimalField("تعطیل‌کاری (ساعت)", max_digits=6, decimal_places=2, default=0)
    shift_type = models.CharField(
        "نوبت‌کاری", max_length=20, choices=ShiftType.choices, default=ShiftType.NONE
    )

    source = models.CharField("منبع", max_length=8, choices=Source.choices, default=Source.MANUAL)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.DRAFT)
    entered_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="entered_timesheets", verbose_name="ثبت‌کننده",
    )
    approved_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_timesheets", verbose_name="تأییدکننده",
    )
    approved_at = models.DateTimeField("زمان تأیید", null=True, blank=True)
    notes = models.CharField("توضیحات", max_length=200, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "کارکرد ماهانه"
        verbose_name_plural = "کارکرد ماهانه"
        unique_together = [("period", "employee")]
        ordering = ["employee__personnel_code"]
        indexes = [models.Index(fields=["period", "status"])]

    def __str__(self):
        return f"کارکرد {self.employee.full_name} — {self.period.title}"

    @property
    def paid_days(self) -> Decimal:
        """روزهای مشمول پرداخت = کارکرد + مرخصی استحقاقی + مأموریت.

        غیبت و مرخصی بدون حقوق کسر می‌شوند و در work_days لحاظ نشده‌اند.
        """
        return self.work_days + self.paid_leave_days + self.mission_days

    @property
    def is_complete(self):
        return self.status == self.Status.APPROVED


class TimesheetImport(models.Model):
    """لاگ ورود کارکرد از فایل اکسل — سطر به سطر، با خطاها."""

    period = models.ForeignKey(
        "payroll.PayrollPeriod", on_delete=models.CASCADE,
        related_name="timesheet_imports", verbose_name="دوره",
    )
    file_name = models.CharField("نام فایل", max_length=200)
    row_count = models.PositiveIntegerField("تعداد سطر", default=0)
    error_count = models.PositiveIntegerField("تعداد خطا", default=0)
    log = models.JSONField("گزارش", default=list, blank=True)
    imported_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="timesheet_imports", verbose_name="واردکننده",
    )
    created_at = models.DateTimeField("زمان", auto_now_add=True)

    class Meta:
        verbose_name = "ورود کارکرد از فایل"
        verbose_name_plural = "ورود کارکرد از فایل"
        ordering = ["-created_at"]
