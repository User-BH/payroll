from django.core.exceptions import ValidationError
from django.db import models

MAX_DEPTH = 12  # سد بی‌نهایت‌گردی؛ چارت واقعی هرگز به این عمق نمی‌رسد


class OrgNode(models.Model):
    """رفتار مشترک گره‌های چارت سازمانی.

    چارت شرکت یک درخت است: **سازمان → مرکز هزینه → واحد → پرسنل**. هر گره کد
    خودش را دارد و کد کاملش از زنجیرهٔ پدرانش ساخته می‌شود، پس تجمیع گزارش روی
    هر سطح فقط یعنی «همهٔ گره‌های زیر این گره».

    بالادستِ هر گره از `org_parent` خوانده می‌شود نه از یک فیلد ثابت: واحد ممکن
    است زیر واحد دیگری باشد و اگر نبود، زیر مرکز هزینه‌اش می‌نشیند. همین یک
    نقطه باعث می‌شود بقیهٔ متدها برای هر دو مدل یکی بمانند.
    """

    class Meta:
        abstract = True

    @property
    def org_parent(self):
        raise NotImplementedError

    def path(self):
        """از ریشه تا خودِ گره.

        حلقه (پدرِ خودش، یا دو گره پدرِ هم) درخت را به چرخهٔ بی‌پایان تبدیل
        می‌کند؛ `seen` جلویش را می‌گیرد تا یک دادهٔ خراب کل صفحه را قفل نکند.
        """
        chain, node, seen = [], self, set()
        while node is not None and len(chain) < MAX_DEPTH:
            key = (type(node).__name__, node.pk)
            if key in seen:
                break
            seen.add(key)
            chain.append(node)
            node = node.org_parent
        return list(reversed(chain))

    @property
    def depth(self) -> int:
        """فاصله از ریشه — ۰ برای گرهٔ بی‌پدر."""
        return len(self.path()) - 1

    @property
    def full_code(self) -> str:
        """کد کامل: کد همهٔ پدران تا خود گره، با خط تیره."""
        return "-".join(node.code for node in self.path() if node.code)

    @property
    def full_path(self) -> str:
        return " › ".join(node.name for node in self.path())

    def clean(self):
        """جلوگیری از حلقه: بالا رفتن از پدرها نباید دوباره به خودِ گره برسد.

        `path()` روی دادهٔ حلقه‌دار فقط زنجیره را کوتاه می‌کند و خطا نمی‌دهد، پس
        اینجا صریح بالا می‌رویم و دنبال خودمان می‌گردیم. حلقه در چارت یعنی گره
        از درخت بیرون می‌افتد و هزینه‌اش در هیچ گزارشی جمع نمی‌شود — خطایی که
        فقط وقتی کشف می‌شود که جمع‌ها نخوانند.
        """
        super().clean()
        if not self.pk:
            return
        node, seen = self.org_parent, set()
        while node is not None:
            key = (type(node).__name__, node.pk)
            if key == (type(self).__name__, self.pk):
                raise ValidationError(
                    "این انتخاب حلقه می‌سازد؛ گره نمی‌تواند زیرمجموعهٔ خودش باشد."
                )
            if key in seen:
                break
            seen.add(key)
            node = node.org_parent

    @classmethod
    def node_models(cls):
        """همهٔ مدل‌هایی که در یک فضای کد مشترک‌اند.

        کد مرکز هزینه و کد واحد در یک فضا زندگی می‌کنند، وگرنه «۱۰-۵۰» می‌تواند
        هم‌زمان مسیر دو گره باشد و کدِ کامل دیگر گره را مشخص نمی‌کند.
        """
        return (CostCenter, Department)

    @classmethod
    def used_codes(cls, company_id, exclude=None):
        used = set()
        for model in cls.node_models():
            query = model.objects.filter(company_id=company_id)
            if exclude is not None and isinstance(exclude, model):
                query = query.exclude(pk=exclude.pk)
            used.update(query.values_list("code", flat=True))
        used.discard("")
        return used

    @classmethod
    def code_owner(cls, company_id, code, exclude=None):
        """گره‌ای که این کد را گرفته است — برای پیام خطای روشن."""
        for model in cls.node_models():
            query = model.objects.filter(company_id=company_id, code=code)
            if exclude is not None and isinstance(exclude, model):
                query = query.exclude(pk=exclude.pk)
            owner = query.first()
            if owner is not None:
                return owner
        return None

    def assign_code(self):
        """کد خالی را با اولین عدد دو رقمی آزاد در همان شرکت پر می‌کند.

        کد اجباری است چون بند ۸ سند «کد مستقل برای هر گره» می‌خواهد، ولی
        اجباری کردن ورودی یعنی کاربر باید برای دادهٔ موجود هم کد بسازد. پس
        خالی‌ها خودکار پر می‌شوند و هر وقت کاربر کد واقعی سازمان را داشت،
        جایش می‌گذارد.
        """
        if self.code:
            return
        used = self.used_codes(self.company_id, exclude=self)
        number = 10
        while f"{number:02d}" in used:  # پله‌های ده‌تایی، تا جا برای گره بعدی بماند
            number += 10
        self.code = f"{number:02d}"

    def save(self, *args, **kwargs):
        self.assign_code()
        super().save(*args, **kwargs)


class Company(models.Model):
    """شرکت. مدل از ابتدا چندشرکتی است تا اگر شعبه یا شرکت دوم اضافه شد،
    نیازی به مهاجرت داده نباشد."""

    name = models.CharField("نام", max_length=120)
    legal_name = models.CharField("نام حقوقی", max_length=200, blank=True)
    # زیرنویس سربرگ فیش. تا امروز در قالب سخت‌کد شده بود، یعنی فیشِ هر شرکتِ
    # دیگری هم «پخش مواد غذایی…» چاپ می‌کرد.
    activity = models.CharField(
        "زمینه فعالیت", max_length=120, blank=True,
        help_text="زیر نام شرکت روی سربرگ فیش چاپ می‌شود",
    )
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

    @property
    def display_name(self) -> str:
        """نامی که روی فیش و سربرگ چاپ می‌شود.

        `name` نامِ **شعبه** است («تبریز»، «اردبیل») و در سوییچ شعبه دیده
        می‌شود. ولی روی فیش حقوقی باید نام شرکت بیاید، نه نام شهر — کارمند
        فیشی می‌گیرد که فرستنده‌اش باید معلوم باشد.

        تا وقتی `legal_name` خالی است همان نام شعبه چاپ می‌شود، پس شرکتی که
        یک شعبه دارد چیزی را از دست نمی‌دهد.
        """
        return self.legal_name or self.name


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


class Department(OrgNode):
    """واحد سازمانی. سلسله‌مراتبی است (parent) تا چارت واقعی قابل بیان باشد."""

    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="departments", verbose_name="شرکت"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="children", verbose_name="واحد بالادست",
    )
    cost_center = models.ForeignKey(
        "CostCenter", on_delete=models.PROTECT, null=True, blank=True,
        related_name="departments", verbose_name="مرکز هزینه",
        help_text="فقط برای واحدهای سطح اول؛ واحد زیرمجموعه، مرکز هزینه را از واحد بالادست به ارث می‌برد",
    )
    name = models.CharField("نام واحد", max_length=100)
    code = models.CharField("کد", max_length=20, blank=True)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "واحد سازمانی"
        verbose_name_plural = "واحدهای سازمانی"
        unique_together = [("company", "name"), ("company", "code")]
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def org_parent(self):
        """واحد بالادست، وگرنه مرکز هزینه — دو سطح مختلف از یک درخت."""
        return self.parent or self.cost_center

    @property
    def effective_cost_center(self):
        """مرکز هزینهٔ مؤثر: مالِ خودش یا به ارث رسیده از واحد بالادست."""
        for node in reversed(self.path()):
            if isinstance(node, CostCenter):
                return node
            if isinstance(node, Department) and node.cost_center_id:
                return node.cost_center
        return None


class CostCenter(OrgNode):
    """مرکز هزینه. دامنه شمول اقلام حقوقی معمولاً بر همین مبنا تعریف می‌شود."""

    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="cost_centers", verbose_name="شرکت"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="children", verbose_name="مرکز هزینه بالادست",
    )
    name = models.CharField("نام مرکز هزینه", max_length=100)
    code = models.CharField("کد", max_length=20, blank=True)
    gl_account = models.CharField("کد حساب دفتر کل", max_length=30, blank=True)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "مرکز هزینه"
        verbose_name_plural = "مراکز هزینه"
        unique_together = [("company", "name"), ("company", "code")]
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def org_parent(self):
        return self.parent


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
