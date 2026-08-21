"""بررسی سلامت پیکربندی اقلام — پیش از آنکه فیش خالی صادر شود.

انگیزهٔ این فایل یک باگ واقعی است: «حق مسکن» و «وجه بن» روی فیش نمی‌آمدند، در
حالی که مبلغشان در پارامترهای سال ثبت شده بود. علتش این بود که آن دو قلم به
«مبلغ ثابت» وصل بودند با مبلغ صفر، و قاعدهٔ مبلغ ثابت وقتی مبلغ صفر است هیچ
سطری تولید نمی‌کند — یعنی قلم بی‌سروصدا غیب می‌شد.

**سکوت، بدترین رفتار ممکن است.** قلمی که فعال است ولی هیچ‌وقت عددی تولید
نمی‌کند باید قبل از اجرای دوره دیده شود، با دلیلش، و با راه حلش. این فایل تنها
جای این تشخیص است تا هر قلم تازه‌ای هم خودبه‌خود پوشش بگیرد.
"""

from decimal import Decimal

ZERO = Decimal("0")

# قلمی که پیکربندی‌اش ایراد دارد و باید درست شود.
BROKEN = "BROKEN"
# قلمی که سالم است ولی امروز مصداقی ندارد — مثل پورسانت فروش وقتی هنوز کسی در
# فروش نیست. اطلاع‌دادنی است، نه خرابی.
UNREACHABLE = "UNREACHABLE"


def _rule_warning(component, params):
    """قلم وصل‌شده به قاعدهٔ موتور: آیا پارامتر سالش پر است؟

    هر قاعده از یک فیلد پارامتر سال می‌خواند؛ اگر آن صفر باشد قاعده عددی
    نمی‌سازد. نگاشت زیر همان وابستگی است، صریح نوشته‌شده.
    """
    from apps.payroll.engine.rules import RULES

    key = component.engine_rule_key
    if not key:
        return "کلید قاعده خالی است، پس موتور نمی‌داند این قلم را چطور حساب کند."
    if key not in RULES:
        return f"قاعده‌ای با کلید «{key}» در موتور ثبت نشده است."

    needs = {
        "housing_allowance": ("housing_allowance", "حق مسکن ماهانه"),
        "food_allowance": ("food_allowance", "بن کارگری ماهانه"),
        "child_allowance": ("child_allowance", "حق اولاد هر فرزند"),
        "seniority": ("seniority_daily", "پایه سنوات روزانه"),
    }
    if key in needs:
        field, label = needs[key]
        if not (getattr(params, field, None) or ZERO):
            return (
                f"«{label}» در پارامترهای سال صفر است، پس این قلم روی هیچ فیشی "
                "نمی‌آید. از «تنظیمات سال مالی» مقدارش را ثبت کنید."
            )
    return ""


def _parametric_warning(component):
    from apps.payroll_config.models import SalaryComponent

    base = component.base_source
    Base = SalaryComponent.BaseSource
    if not base or not component.quantity_source:
        return "مبنا یا مقدار قاعدهٔ پارامتری انتخاب نشده است."
    if base == Base.FIXED and not component.fixed_amount:
        return "مبنای «مبلغ ثابت» است ولی مبلغش صفر است."
    if base == Base.COMPONENT and not component.base_component_id:
        return "مبنای «قلم دیگر» است ولی قلم مبنا انتخاب نشده است."
    return ""


def _scope_warning(component, contracts):
    """قلمی که دامنه شمولش به هیچ قرارداد فعالی نمی‌خورد.

    این هم یک باگ واقعی است: روی دیتابیس عملیاتی، «حق تاهل» به نوع قرارداد
    «موقت» محدود شده بود در حالی که همهٔ پرسنل قرارداد «دائم» داشتند. نتیجه
    این بود که کاربر تیک «متأهل» را می‌زد و هیچ اتفاقی نمی‌افتاد — بدون هیچ
    پیامی، هیچ‌جا.

    دامنه شمول تنها جایی است که یک قلمِ کاملاً درست هم می‌تواند به هیچ‌کس
    نرسد، پس باید جداگانه دیده شود.
    """
    scopes = list(component.scopes.all())
    if not scopes:
        return ""
    if any(component.applies_to(c) for c in contracts):
        return ""
    targets = "، ".join(f"«{s.target_label()}»" for s in scopes)
    return (
        f"دامنه شمولش ({targets}) است و هیچ‌کدام از {len(contracts)} قرارداد "
        "فعال چنین مشخصه‌ای ندارند."
    )


def _active_contracts(company):
    from apps.employees.models import Employee, EmploymentContract

    return list(
        EmploymentContract.objects.filter(
            employee__company=company,
            employee__status=Employee.Status.ACTIVE,
            status=EmploymentContract.Status.ACTIVE,
        ).select_related("employee")
    )


def component_warnings(company, params=None):
    """اقلام فعالی که با پیکربندی امروز هیچ عددی تولید نمی‌کنند.

    خروجی: فهرست دیکشنری با `component` و `reason`. خالی بودنش یعنی هر قلم
    فعال، دست‌کم یک راه برای رسیدن به عدد دارد.
    """
    from apps.payroll_config.models import LegalParameter, SalaryComponent

    if params is None:
        params = (
            LegalParameter.objects.filter(fiscal_year__company=company)
            .order_by("-effective_from")
            .first()
        )

    from apps.payroll.engine.runner import ROUNDING_COMPONENT_CODE

    warnings = []
    components = (
        SalaryComponent.objects.filter(company=company, is_active=True)
        .exclude(kind=SalaryComponent.Kind.INFO)
        # «تعدیل گرد کردن» عمداً صفر است تا وقتی واحد گرد کردن ۱ باشد؛ هشدارش
        # هر ماه تکرار می‌شد و بقیهٔ هشدارها را بی‌ارزش می‌کرد.
        .exclude(code=ROUNDING_COMPONENT_CODE)
        .prefetch_related("scopes")
        .order_by("sequence", "id")
    )
    contracts = _active_contracts(company)
    Calc = SalaryComponent.CalcType
    for component in components:
        reason = ""
        if component.calc_type == Calc.FIXED and not component.fixed_amount:
            reason = (
                "«مبلغ ثابت» است ولی مبلغش صفر است، پس سطری روی فیش نمی‌آید. "
                "یا مبلغ را وارد کنید یا نحوهٔ محاسبه‌اش را عوض کنید."
            )
        elif component.calc_type == Calc.PERCENTAGE and not component.base_component_id:
            reason = "«درصدی از قلم دیگر» است ولی قلم مبنا انتخاب نشده است."
        elif component.calc_type == Calc.PERCENTAGE and not component.rate:
            reason = "«درصدی از قلم دیگر» است ولی نرخش صفر است."
        elif component.calc_type == Calc.PARAMETRIC:
            reason = _parametric_warning(component)
        elif component.calc_type == Calc.ENGINE_RULE and params is not None:
            reason = _rule_warning(component, params)
        elif component.calc_type == Calc.ENGINE_RULE and params is None:
            reason = "برای این سال پارامتر قانونی ثبت نشده است."

        # دامنه شمول مستقل از نحوهٔ محاسبه است: قلمی که فرمولش هم درست باشد
        # می‌تواند به هیچ‌کس نرسد. دو ایراد جدا هستند و **هر دو با هم** گزارش
        # می‌شوند — وگرنه کاربر اولی را درست می‌کند، دوباره محاسبه می‌گیرد، و
        # تازه می‌فهمد ایراد دومی هم بوده. یک بار دیدن بهتر از دو بار است.
        scope_note = _scope_warning(component, contracts) if contracts else ""

        if reason:
            if scope_note:
                reason = f"{reason} ضمناً {scope_note}"
            warnings.append({"component": component, "reason": reason, "kind": BROKEN})
        elif scope_note:
            # سالم است ولی امروز مصداقی ندارد — مثل پورسانت فروش وقتی هنوز
            # کسی در فروش نیست. جدا دسته‌بندی می‌شود تا هشدار واقعی زیر
            # اطلاعیه‌ها گم نشود.
            warnings.append(
                {"component": component, "reason": scope_note, "kind": UNREACHABLE}
            )
    return warnings
