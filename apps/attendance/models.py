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

    # مرخصی استحقاقی به دقیقه نگهداری می‌شود چون فیش شرکت آن را به روز و ساعت و
    # دقیقه نشان می‌دهد و نگهداری اعشاریِ روز، خطای گرد کردن تولید می‌کند.
    # paid_leave_days همیشه از روی همین مقدار ساخته می‌شود، نه برعکس.
    leave_minutes = models.IntegerField("مرخصی استحقاقی (دقیقه)", default=0)
    paid_leave_days = models.DecimalField(
        "مرخصی استحقاقی (روز)", max_digits=6, decimal_places=2, default=0,
        help_text="خودکار از روی دقیقه محاسبه می‌شود",
    )
    sick_leave_days = models.DecimalField("مرخصی استعلاجی", max_digits=6, decimal_places=2, default=0)
    mission_days = models.DecimalField("مأموریت", max_digits=6, decimal_places=2, default=0)

    # اضافه‌کاری هم مثل مرخصی به دقیقه نگهداری می‌شود، چون ورودی‌اش سه‌تایی
    # (روز، ساعت، دقیقه) است و نگهداری اعشاریِ ساعت خطای گرد کردن تولید می‌کند.
    # overtime_hours همیشه از روی همین مقدار ساخته می‌شود، نه برعکس — موتور
    # محاسبه با ساعت کار می‌کند.
    overtime_minutes = models.IntegerField("اضافه‌کاری (دقیقه)", default=0)
    overtime_hours = models.DecimalField(
        "اضافه‌کاری (ساعت)", max_digits=6, decimal_places=2, default=0,
        help_text="خودکار از روی دقیقه محاسبه می‌شود — فقط برای نمایش",
    )
    # شب‌کاری و جمعه‌کاری از فرم کارکرد ماهانه برداشته شده‌اند (فیش‌های واقعی
    # شرکت چنین قلمی ندارند). ستون‌ها می‌مانند تا داده و فیش‌های گذشته سالم
    # بمانند و قاعده‌هایشان در موتور دست‌نخورده باقی می‌ماند.
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

    def value_of(self, item):
        """مقدار یک قلم کارکرد — چه ستون قدیمی باشد چه رکورد تازه.

        تنها راه خواندن اقلام کارکرد. بقیهٔ سامانه نباید بداند کدام قلم ستون
        دارد و کدام رکورد؛ همین یک تابع آن تفاوت را می‌پوشاند.
        """
        if item.source_field:
            return Decimal(str(getattr(self, item.source_field, 0) or 0))
        entry = next(
            (e for e in self.entries.all() if e.item_id == item.pk), None
        )
        return entry.value if entry else Decimal("0")

    def set_value(self, item, value):
        """ثبت مقدار یک قلم — روی ستون قدیمی یا رکورد تازه."""
        number = Decimal(str(value or 0))
        if item.source_field:
            setattr(self, item.source_field, number)
            return None
        entry, _ = TimesheetEntry.objects.update_or_create(
            timesheet=self, item=item, defaults={"value": number}
        )
        return entry

    @property
    def day_minutes(self) -> int:
        """طول یک روز کاری بر حسب دقیقه، از پارامتر قانونی همان دوره.

        هم برای مرخصی و هم برای اضافه‌کاری همین عدد مبناست. اگر نمایش با
        مقدار پیش‌فرض و ذخیره با مقدار پارامتر انجام شود، «۱ روز» واردشده
        دفعهٔ بعد «۱ روز و ۴۰ دقیقه» خوانده می‌شود.
        """
        from apps.attendance.leave import DEFAULT_DAY_MINUTES

        parameter = getattr(self.period, "legal_parameter", None) if self.period_id else None
        return parameter.leave_day_minutes if parameter else DEFAULT_DAY_MINUTES

    def save(self, *args, **kwargs):
        minutes_per_day = Decimal(self.day_minutes)
        self.paid_leave_days = (
            Decimal(self.leave_minutes or 0) / minutes_per_day
        ).quantize(Decimal("0.01"))
        self.overtime_hours = (
            Decimal(self.overtime_minutes or 0) / Decimal("60")
        ).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)

    @property
    def leave_display(self):
        from apps.attendance.leave import format_dhm

        return format_dhm(self.leave_minutes, self.day_minutes)

    @property
    def exact_overtime_hours(self) -> Decimal:
        """ساعت اضافه‌کاری بدون گرد کردن — همان که موتور باید ضرب کند.

        `overtime_hours` دو رقم اعشار دارد و برای نمایش است. موتور اگر از آن
        استفاده کند، ۲۷۴ دقیقه می‌شود ۴٫۵۷ ساعت به‌جای ۴٫۵۶۶۶…، و با نرخ‌های
        میلیونیِ هر ساعت، همان دو رقم چند هزار ریال خطا می‌سازد. در بک‌تست تیر
        ۱۴۰۵ همین یک مورد، ۹ فیش را از فایل جدا می‌کرد.

        دقیقه مبناست — همان قاعده‌ای که بالای این کلاس نوشته شده.
        """
        return Decimal(self.overtime_minutes or 0) / Decimal("60")

    @property
    def leave_parts(self):
        """(روز، ساعت، دقیقه) برای سه ورودی جدول کارکرد."""
        from apps.attendance.leave import split_dhm

        _, days, hours, minutes = split_dhm(self.leave_minutes, self.day_minutes)
        return {"d": days, "h": hours, "m": minutes}

    @property
    def overtime_parts(self):
        """(روز، ساعت، دقیقه) اضافه‌کاری — همان سه ورودیِ مرخصی، برای اضافه‌کاری."""
        from apps.attendance.leave import split_dhm

        _, days, hours, minutes = split_dhm(self.overtime_minutes, self.day_minutes)
        return {"d": days, "h": hours, "m": minutes}

    @property
    def overtime_display(self):
        from apps.attendance.leave import format_dhm

        return format_dhm(self.overtime_minutes, self.day_minutes)

    # کسورات کارکردی — سه موردی که واحدشان «روز» است و از کارکرد کم می‌شوند
    UNPAID_DAY_FIELDS = ["absence_days", "sick_leave_days", "unpaid_leave_days"]

    @property
    def unpaid_days(self) -> Decimal:
        """جمع روزهای بدون حقوق: غیبت + بیماری + مرخصی بدون حقوق."""
        return sum(
            (getattr(self, field) or Decimal("0") for field in self.UNPAID_DAY_FIELDS),
            Decimal("0"),
        )

    @property
    def paid_days(self) -> Decimal:
        """روز کارکرد قابل پرداخت = کارکرد اولیه − غیبت − بیماری − مرخصی بدون حقوق.

        `work_days` **کارکرد اولیه** است: کل روزهای اشتغال آن پرسنل در آن ماه،
        که از تاریخ استخدام/خاتمه/شروع مجدد پیش‌فرض می‌گیرد و دستی هم قابل
        اصلاح است. مرخصی استحقاقی و مأموریت داخل همین عدد هستند و کم نمی‌شوند
        چون پرداخت دارند؛ فقط سه قلم بی‌حقوق کسر می‌شوند.

        مثال سند: خاتمه ۱۶ مرداد ۱۴۰۵ → کارکرد اولیه ۱۵ روز؛ با ۱ روز غیبت،
        ۱ روز بیماری و ۱ روز مرخصی بدون حقوق → ۱۵ − ۳ = ۱۲ روز.
        """
        return max(self.work_days - self.unpaid_days, Decimal("0"))

    @property
    def is_complete(self):
        return self.status == self.Status.APPROVED


class LeaveRecord(models.Model):
    """یک مرخصی ثبت‌شده در کارتابل مرخصی.

    کارگزینی مرخصی را همین‌جا ثبت می‌کند و همان لحظه در کارکرد ماه اعمال
    می‌شود — بدون ورود دوباره در جدول کارکرد و بدون رفت‌وبرگشت بین کارگزینی و
    حقوق و دستمزد.

    **مبنا دقیقه است**، مثل بقیهٔ مرخصی‌های سامانه: مرخصی ساعتی و روزانه هر دو
    با یک واحد نگهداری می‌شوند و روزِ اعشاری فقط برای نمایش ساخته می‌شود.

    مرخصی‌ای که روی دو ماه بیفتد بین دوره‌ها به نسبت روزهای مشترک تقسیم
    می‌شود؛ در حالت رایج (مرخصی روزانه) این تقسیم دقیق است.
    """

    class Kind(models.TextChoices):
        ENTITLED = "ENTITLED", "استحقاقی"
        UNPAID = "UNPAID", "بدون حقوق"
        SICK = "SICK", "استعلاجی"

    class Status(models.TextChoices):
        REGISTERED = "REGISTERED", "ثبت‌شده"
        CANCELLED = "CANCELLED", "لغوشده"

    # هر نوع مرخصی به کدام ستون کارکرد می‌نشیند
    TIMESHEET_FIELD = {
        Kind.ENTITLED: "leave_minutes",
        Kind.UNPAID: "unpaid_leave_days",
        Kind.SICK: "sick_leave_days",
    }

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="leave_records", verbose_name="پرسنل"
    )
    kind = models.CharField("نوع مرخصی", max_length=10, choices=Kind.choices, default=Kind.ENTITLED)
    start_date = models.DateField("از تاریخ")
    end_date = models.DateField("تا تاریخ")
    minutes = models.PositiveIntegerField(
        "مدت (دقیقه)", default=0,
        help_text="مبنای ذخیره دقیقه است؛ روز و ساعت از روی همین ساخته می‌شوند",
    )

    status = models.CharField(
        "وضعیت", max_length=12, choices=Status.choices, default=Status.REGISTERED
    )
    reason = models.CharField("علت", max_length=200, blank=True)

    created_at = models.DateTimeField("زمان ثبت", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="leave_records", verbose_name="ثبت‌کننده",
    )

    class Meta:
        verbose_name = "مرخصی"
        verbose_name_plural = "کارتابل مرخصی"
        ordering = ["-start_date", "employee__personnel_code"]
        indexes = [models.Index(fields=["employee", "start_date", "end_date"])]

    def __str__(self):
        return f"{self.get_kind_display()} {self.employee.full_name} — {self.start_date}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "تاریخ پایان نمی‌تواند قبل از شروع باشد."})
        if not self.minutes:
            # خطای بدون فیلد: مدت در فرم به‌صورت سه ورودی روز/ساعت/دقیقه گرفته
            # می‌شود و فیلدی به نام `minutes` در فرم وجود ندارد که خطا را بگیرد.
            raise ValidationError("مدت مرخصی نمی‌تواند صفر باشد.")

    @property
    def is_active(self):
        return self.status == self.Status.REGISTERED

    @property
    def span_days(self) -> int:
        if not (self.start_date and self.end_date):
            return 0
        return (self.end_date - self.start_date).days + 1

    def minutes_in(self, start, end) -> int:
        """دقیقه‌های این مرخصی که داخل بازهٔ [start, end] می‌افتند.

        تقسیم به نسبت روزهای مشترک است. برای مرخصی روزانه — که مدتش مضربی از
        طول روز کاری است — این تقسیم دقیق درمی‌آید.
        """
        if not self.is_active or not self.span_days:
            return 0
        first = max(self.start_date, start)
        last = min(self.end_date, end)
        if last < first:
            return 0
        overlap = (last - first).days + 1
        if overlap >= self.span_days:
            return int(self.minutes)
        return int(round(self.minutes * overlap / self.span_days))

    def parts(self, day_minutes=None):
        """(روز، ساعت، دقیقه) برای نمایش."""
        from apps.attendance.leave import DEFAULT_DAY_MINUTES, split_dhm

        _, days, hours, mins = split_dhm(self.minutes, day_minutes or DEFAULT_DAY_MINUTES)
        return {"d": days, "h": hours, "m": mins}

    def display(self, day_minutes=None):
        from apps.attendance.leave import DEFAULT_DAY_MINUTES, format_dhm

        return format_dhm(self.minutes, day_minutes or DEFAULT_DAY_MINUTES)


class LeaveEntitlement(models.Model):
    """سهمیه مرخصی یک پرسنل در یک سال مالی.

    فقط دو عدد ورودی دارد: انتقالی از سال قبل و استحقاقی سال جاری. «مصرفی» و
    «مانده» هرگز ذخیره نمی‌شوند و همیشه از روی کارکرد ماه‌ها محاسبه می‌شوند —
    وگرنه با اصلاح کارکرد یک ماه، مانده از واقعیت جدا می‌افتد.
    """

    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE,
        related_name="leave_entitlements", verbose_name="پرسنل",
    )
    fiscal_year = models.ForeignKey(
        "payroll_config.FiscalYear", on_delete=models.PROTECT,
        related_name="leave_entitlements", verbose_name="سال مالی",
    )
    carried_over_minutes = models.IntegerField("انتقالی از سال قبل (دقیقه)", default=0)
    annual_minutes = models.IntegerField("استحقاقی سال (دقیقه)", default=0)

    # --- مانده‌گیری افتتاحیه، برای وقتی سامانه از وسط سال عملیاتی می‌شود
    #
    # «مصرفی» همیشه از جمع کارکرد ماه‌ها ساخته می‌شود، نه از عددی که یک بار
    # تایپ شده. ولی ماه‌هایی که پیش از راه‌اندازی سامانه گذشته‌اند کارکردی در
    # سامانه ندارند، و بدون این دو فیلد مانده مرخصی همه از اول سال صفر
    # می‌شود — یعنی عددی که روی فیش چاپ می‌شود غلط است.
    #
    # `opening_through_month` مرزِ همین موضوع است و وجودش اجباری است: بدون آن،
    # روزی که فروردین تا خرداد واقعاً وارد سامانه شوند، مصرفی‌شان **دو بار**
    # شمرده می‌شود — یک بار در عدد افتتاحیه و یک بار از کارکرد خودشان. با این
    # مرز، ماه‌های تا آن شماره از جمع کارکرد کنار گذاشته می‌شوند.
    #
    # وقتی آن ماه‌ها بار شدند، کافی است این مرز صفر شود تا سامانه دوباره همه
    # چیز را از کارکرد واقعی بسازد.
    opening_used_minutes = models.IntegerField(
        "مصرفی پیش از راه‌اندازی سامانه (دقیقه)", default=0,
        help_text="مرخصی استفاده‌شده از اول سال تا ماهی که سامانه عملیاتی شد",
    )
    opening_through_month = models.PositiveSmallIntegerField(
        "این عدد تا پایان کدام ماه است", default=0,
        help_text="۰ یعنی افتتاحیه‌ای در کار نیست و همه‌چیز از کارکرد ساخته می‌شود",
    )

    note = models.CharField("توضیح", max_length=200, blank=True)

    class Meta:
        verbose_name = "سهمیه مرخصی"
        verbose_name_plural = "سهمیه‌های مرخصی"
        unique_together = [("employee", "fiscal_year")]

    def __str__(self):
        return f"مرخصی {self.employee.full_name} — {self.fiscal_year.year}"

    @property
    def total_minutes(self):
        return self.carried_over_minutes + self.annual_minutes


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


class TimesheetItem(models.Model):
    """قلم کارکرد — یک ستون از جدول کارکرد ماهانه، به‌صورت داده نه کد.

    مسئله‌ای که این جدول حل می‌کند: تا امروز ستون‌های جدول کارکرد در مدل
    سخت‌کد شده بودند، پس افزودن «جمعه‌کاری» یا هر قلم تازه یعنی یک مهاجرت
    دیتابیس، یک تغییر در فرم، و یک قاعدهٔ تازه در موتور. حالا هر ستون یک سطر
    است و افزودن قلم تازه یعنی یک رکورد.

    **دادهٔ موجود جابه‌جا نشد.** ستون‌هایی که از قبل روی `Timesheet` بودند
    (کارکرد، غیبت، مرخصی، اضافه‌کاری، مأموریت، جمعه‌کاری…) همان‌جا می‌مانند و
    این جدول فقط با `source_field` به آن‌ها اشاره می‌کند. قلم‌های تازه در
    `TimesheetEntry` ذخیره می‌شوند. هر دو از یک راه خوانده می‌شوند
    (`Timesheet.value_of`)، پس بقیهٔ سامانه فرقشان را نمی‌فهمد.

    این تقسیم عمدی است: بازنویسی ستون‌های موجود یعنی دست بردن در چیزی که
    فیش‌های چند ماه رویش حساب شده‌اند، بی‌آنکه چیزی به کاربر اضافه کند.
    """

    class Unit(models.TextChoices):
        DAY = "DAY", "روز"
        HOUR = "HOUR", "ساعت"
        MINUTE = "MINUTE", "دقیقه"

    company = models.ForeignKey(
        "org.Company", on_delete=models.PROTECT,
        related_name="timesheet_items", verbose_name="شرکت",
    )
    code = models.CharField("کد", max_length=40)
    name = models.CharField("نام ستون", max_length=60)
    unit = models.CharField("واحد", max_length=8, choices=Unit.choices, default=Unit.HOUR)

    source_field = models.CharField(
        "ستون قدیمی", max_length=40, blank=True,
        help_text="اگر این قلم روی خود جدول کارکرد ستون دارد، نام همان فیلد. "
                  "خالی یعنی مقدارش در جدول مقادیر کارکرد ذخیره می‌شود.",
    )
    reduces_work_days = models.BooleanField(
        "از کارکرد قابل پرداخت کم می‌شود", default=False,
        help_text="مثل غیبت و مرخصی بدون حقوق. مرخصی استحقاقی و مأموریت کم نمی‌شوند.",
    )

    sequence = models.PositiveSmallIntegerField("ترتیب ستون", default=100)
    is_active = models.BooleanField("در جدول کارکرد نمایش داده شود", default=True)
    is_system = models.BooleanField(
        "سیستمی", default=False,
        help_text="اقلامی که موتور مستقیم به آن‌ها وابسته است و حذف نمی‌شوند",
    )
    description = models.CharField("توضیح", max_length=160, blank=True)

    class Meta:
        verbose_name = "قلم کارکرد"
        verbose_name_plural = "اقلام کارکرد"
        unique_together = [("company", "code")]
        ordering = ["sequence", "id"]

    def __str__(self):
        return self.name

    @property
    def unit_label(self) -> str:
        return self.get_unit_display()


class TimesheetEntry(models.Model):
    """مقدار یک قلم کارکردِ **تازه** برای یک پرسنل در یک ماه.

    فقط برای اقلامی که `source_field` ندارند؛ اقلام قدیمی همان ستون خودشان را
    روی `Timesheet` دارند و اینجا رکوردی نمی‌سازند.

    مقدار همیشه به کوچک‌ترین واحد ذخیره می‌شود — دقیقه برای ساعت و دقیقه،
    صدم‌روز برای روز — به همان دلیلی که مرخصی و اضافه‌کاری به دقیقه ذخیره
    می‌شوند: نگهداری اعشاری، خطای گرد کردن جمع می‌کند.
    """

    timesheet = models.ForeignKey(
        Timesheet, on_delete=models.CASCADE, related_name="entries", verbose_name="کارکرد"
    )
    item = models.ForeignKey(
        TimesheetItem, on_delete=models.PROTECT, related_name="entries", verbose_name="قلم"
    )
    value = models.DecimalField("مقدار", max_digits=10, decimal_places=2, default=0)

    class Meta:
        verbose_name = "مقدار قلم کارکرد"
        verbose_name_plural = "مقادیر اقلام کارکرد"
        unique_together = [("timesheet", "item")]

    def __str__(self):
        return f"{self.item.name}: {self.value}"
