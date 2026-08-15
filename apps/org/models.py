from django.db import models


class Company(models.Model):
    """شرکت. مدل از ابتدا چندشرکتی است تا اگر شعبه یا شرکت دوم اضافه شد،
    نیازی به مهاجرت داده نباشد."""

    name = models.CharField("نام", max_length=120)
    legal_name = models.CharField("نام حقوقی", max_length=200, blank=True)
    national_id = models.CharField("شناسه ملی", max_length=11, blank=True)
    economic_code = models.CharField("کد اقتصادی", max_length=20, blank=True)
    registration_number = models.CharField("شماره ثبت", max_length=20, blank=True)
    insurance_workshop_code = models.CharField("کد کارگاه تأمین اجتماعی", max_length=20, blank=True)
    tax_file_number = models.CharField("شماره پرونده مالیاتی", max_length=20, blank=True)
    address = models.TextField("نشانی", blank=True)
    phone = models.CharField("تلفن", max_length=30, blank=True)
    is_active = models.BooleanField("فعال", default=True)

    # --- تنظیمات فایل پرداخت بانک
    # هر بانک فرمت خودش را می‌خواهد. به‌جای hard-code کردن فرمت یک بانک، ستون‌ها
    # و جداکننده از اینجا خوانده می‌شوند تا تطبیق با بانک بدون تغییر کد ممکن باشد.
    bank_file_columns = models.CharField(
        "ستون‌های فایل بانک", max_length=200, default="row,account,amount",
        help_text="با کاما جدا کنید. مقادیر مجاز: "
                  "row, personnel_code, national_id, name, account, iban, amount, description",
    )
    bank_file_delimiter = models.CharField(
        "جداکننده", max_length=5, default=",",
        help_text="مثلاً , یا ; یا | — برای tab بنویسید \\t",
    )
    bank_file_include_header = models.BooleanField("سطر عنوان داشته باشد", default=False)
    bank_file_extension = models.CharField("پسوند فایل", max_length=8, default="txt")
    bank_file_encoding = models.CharField(
        "کدگذاری فایل", max_length=20, default="utf-8-sig",
        help_text="utf-8-sig برای اکسل فارسی · cp1256 برای سامانه‌های قدیمی",
    )

    class Meta:
        verbose_name = "شرکت"
        verbose_name_plural = "شرکت‌ها"

    def __str__(self):
        return self.name


class Branch(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="branches", verbose_name="شرکت"
    )
    name = models.CharField("نام شعبه", max_length=100)
    code = models.CharField("کد", max_length=20, blank=True)
    insurance_branch_code = models.CharField("کد شعبه بیمه", max_length=20, blank=True)
    address = models.TextField("نشانی", blank=True)

    class Meta:
        verbose_name = "شعبه"
        verbose_name_plural = "شعب"
        unique_together = [("company", "name")]

    def __str__(self):
        return self.name


class Department(models.Model):
    """واحد سازمانی. سلسله‌مراتبی است (parent) تا چارت واقعی قابل بیان باشد."""

    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="departments", verbose_name="شرکت"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="children", verbose_name="واحد بالادست",
    )
    name = models.CharField("نام واحد", max_length=100)
    code = models.CharField("کد", max_length=20, blank=True)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "واحد سازمانی"
        verbose_name_plural = "واحدهای سازمانی"
        unique_together = [("company", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class CostCenter(models.Model):
    """مرکز هزینه. دامنه شمول اقلام حقوقی معمولاً بر همین مبنا تعریف می‌شود."""

    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="cost_centers", verbose_name="شرکت"
    )
    name = models.CharField("نام مرکز هزینه", max_length=100)
    code = models.CharField("کد", max_length=20, blank=True)
    gl_account = models.CharField("کد حساب دفتر کل", max_length=30, blank=True)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "مرکز هزینه"
        verbose_name_plural = "مراکز هزینه"
        unique_together = [("company", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class JobTitle(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="job_titles", verbose_name="شرکت"
    )
    name = models.CharField("عنوان شغلی", max_length=100)
    code = models.CharField("کد", max_length=20, blank=True)
    job_group = models.PositiveSmallIntegerField(
        "گروه شغلی", null=True, blank=True,
        help_text="بر اساس طرح طبقه‌بندی مشاغل",
    )
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "پست سازمانی"
        verbose_name_plural = "پست‌های سازمانی"
        unique_together = [("company", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name
