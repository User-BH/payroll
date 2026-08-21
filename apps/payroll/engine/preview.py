"""محاسبهٔ آزمایشی یک قلم، پیش از آنکه وارد فیش کسی شود.

قلمی که کاربر بدون کدنویسی می‌سازد باید **قبل از اجرای دوره** دیده شود، وگرنه
اولین باری که عددش را می‌بینید روی فیش ۱۴۶ نفر است.

نکتهٔ اصلی این فایل: پیش‌نمایش، فرمول را **دوباره پیاده نمی‌کند**. همان تابع
`parametric` موتور را با یک بستر نمونه صدا می‌زند. اگر روزی قاعده عوض شود،
پیش‌نمایش خودبه‌خود با آن عوض می‌شود؛ پیاده‌سازی دوم یعنی دو عددِ متفاوت که
هیچ‌کدام قابل اعتماد نیست.
"""

from dataclasses import dataclass, field
from decimal import Decimal

ZERO = Decimal("0")


@dataclass
class SampleContext:
    """کمینهٔ چیزی که قاعدهٔ پارامتری از بستر می‌خواند.

    عمداً `PayrollContext` واقعی ساخته نمی‌شود: آن به قرارداد، کارکرد و دوره
    نیاز دارد و ساختن نمونه‌شان در دیتابیس، برای یک پیش‌نمایش، هزینه و ریسک
    بی‌مورد است.
    """

    params: object
    paid_days: Decimal = Decimal("26")
    month_days: Decimal = Decimal("31")
    daily_base: Decimal = ZERO
    wage_basis_label: str = "دستمزد قرارداد"
    amounts: dict = field(default_factory=dict)

    @property
    def day_ratio(self) -> Decimal:
        if not self.month_days:
            return ZERO
        return self.paid_days / self.month_days

    def amount_of(self, code: str) -> Decimal:
        return self.amounts.get(code, ZERO)


def sample_for(company, params=None):
    """بستر نمونه از روی دادهٔ واقعی همان شرکت.

    مزد روزانه از میانگین قراردادهای فعال می‌آید، نه از عددی ساختگی: عددی که
    شبیه حقوق واقعی نباشد، پیش‌نمایش را بی‌فایده می‌کند.
    """
    from django.db.models import Avg

    from apps.employees.models import EmploymentContract
    from apps.payroll.models import PayrollPeriod
    from apps.payroll_config.models import LegalParameter

    if params is None:
        params = (
            LegalParameter.objects.filter(fiscal_year__company=company)
            .order_by("-effective_from")
            .first()
        )
    if params is None:
        return None

    period = (
        PayrollPeriod.objects.filter(company=company).order_by("-year", "-month").first()
    )
    month_days = (period.month_days if period else None) or params.monthly_days

    average = (
        EmploymentContract.objects.filter(
            employee__company=company,
            status=EmploymentContract.Status.ACTIVE,
            daily_wage__gt=0,
        ).aggregate(value=Avg("daily_wage"))["value"]
    )
    if average:
        daily_base = Decimal(average)
        basis = "دستمزد قرارداد"
    else:
        daily_base = params.min_daily_wage or ZERO
        basis = "حداقل دستمزد"

    return SampleContext(
        params=params,
        paid_days=Decimal(month_days) - Decimal("5"),  # یک ماه با پنج روز غیبت/مرخصی
        month_days=Decimal(month_days),
        daily_base=daily_base,
        wage_basis_label=basis,
    )


def explain_empty(component, sample) -> str:
    """چرا پیش‌نمایش عددی نداد.

    خالی ماندنِ بی‌توضیحِ کادر پیش‌نمایش بدترین حالت است: کاربر فکر می‌کند قلم
    درست است و تازه سر اجرای دوره می‌فهمد سطرش اصلاً نیامده.
    """
    if sample is None:
        return "برای این شرکت پارامتر قانونی سالی ثبت نشده؛ تا آن نباشد مبنایی برای محاسبه نیست."

    Base = component.BaseSource
    if component.base_source == Base.MIN_WAGE and not (sample.params.min_daily_wage or 0):
        return (
            "حداقل دستمزد روزانهٔ سال صفر است، پس این قلم روی فیش هم صفر می‌شود. "
            "از «تنظیمات سال مالی» مقدارش را ثبت کنید."
        )
    if component.base_source == Base.PERSON_WAGE and not sample.daily_base:
        return "نه قراردادی با حقوق پایه هست و نه حداقل دستمزد ثبت شده، پس مزد روزانه صفر است."
    if component.base_source == Base.FIXED and not component.fixed_amount:
        return "مبلغ ثابت صفر است."
    if component.base_source == Base.COMPONENT and not component.base_component_id:
        return "قلم مبنا انتخاب نشده است."
    return "با این تنظیمات، مبلغ صفر می‌شود و سطری روی فیش نمی‌آید."


def preview_component(component, sample):
    """اجرای همان قاعدهٔ موتور روی بستر نمونه — نتیجه یا `None`."""
    from apps.payroll.engine.rules import parametric

    if sample is None:
        return None
    if component.base_source == component.BaseSource.COMPONENT:
        # قلم مبنا هنوز محاسبه نشده است؛ برای نمونه، مبلغی قابل باور به آن
        # می‌دهیم تا نسبت درصدی قابل دیدن باشد.
        base = component.base_component
        if base is None:
            return None
        sample.amounts[base.code] = sample.daily_base * sample.paid_days
    try:
        return parametric(sample, component)
    except (TypeError, ValueError, ArithmeticError, AttributeError):
        # پیش‌نمایش هرگز نباید صفحهٔ ویرایش قلم را بشکند.
        return None
