from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """کاربر سامانه.

    دو خانواده کاربر داریم: کارکنان مالی که با سامانه کار می‌کنند، و پرسنلی که
    فقط به پرتال و فیش خودشان دسترسی دارند. تفکیک با فیلد role انجام می‌شود و
    اتصال به رکورد پرسنلی از سمت Employee.user برقرار است.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "مدیر سیستم"
        PAYROLL = "PAYROLL", "کارشناس حقوق و دستمزد"
        MANAGER = "MANAGER", "مدیر"
        EMPLOYEE = "EMPLOYEE", "کارمند"

    role = models.CharField("نقش", max_length=16, choices=Role.choices, default=Role.EMPLOYEE)
    mobile = models.CharField("موبایل", max_length=15, blank=True)
    job_title_label = models.CharField("عنوان نمایشی", max_length=80, blank=True)

    class Meta:
        verbose_name = "کاربر"
        verbose_name_plural = "کاربران"

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def initials(self):
        first = (self.first_name or self.username)[:1]
        last = (self.last_name or "")[:1]
        return f"{first}.{last}" if last else first

    @property
    def is_payroll_staff(self):
        """آیا اجازه ورود به بخش مالی سامانه را دارد؟"""
        return self.role in {self.Role.ADMIN, self.Role.PAYROLL, self.Role.MANAGER}

    @property
    def can_edit_payroll(self):
        """آیا اجازه تغییر داده و اجرای محاسبه را دارد؟"""
        return self.role in {self.Role.ADMIN, self.Role.PAYROLL}


class AuditLog(models.Model):
    """لاگ تغییرات موجودیت‌های مالی.

    برای دمو ساده نگه داشته شده؛ در فاز بعد جایش django-simple-history می‌آید.
    """

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_logs", verbose_name="کاربر",
    )
    action = models.CharField("عملیات", max_length=40)
    model_name = models.CharField("مدل", max_length=60)
    object_id = models.CharField("شناسه رکورد", max_length=40, blank=True)
    detail = models.JSONField("جزئیات", default=dict, blank=True)
    ip = models.GenericIPAddressField("آی‌پی", null=True, blank=True)
    created_at = models.DateTimeField("زمان", auto_now_add=True)

    class Meta:
        verbose_name = "لاگ تغییر"
        verbose_name_plural = "لاگ تغییرات"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["model_name", "object_id"])]

    def __str__(self):
        return f"{self.action} · {self.model_name}#{self.object_id}"
