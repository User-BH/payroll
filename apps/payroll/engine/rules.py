"""قواعد محاسبه.

تصمیم معماری: منطق محاسبه در کد است، نه در دیتابیس. هر قاعده یک تابع خالص با
یک کلید ثابت است؛ دیتابیس فقط می‌گوید کدام قاعده، با چه ضریبی، با چه ترتیبی، و
مشمول بیمه/مالیات هست یا نه.

دلیل: باگ در حقوق و دستمزد مسئولیت قانونی و مالی دارد. کد قطعی و تست‌پذیر خیلی
ارزشمندتر از انعطافِ فرمول‌نویسی داخل دیتابیس (و eval کردن آن) است.
"""

from decimal import Decimal

from apps.payroll.engine.context import ZERO, LineResult, PayrollContext
from apps.payroll.utils import fa_money, fa_number, fa_wage

RULES = {}


def rule(key: str, label: str = "", manual_input: str = ""):
    """ثبت یک قاعده در موتور.

    `manual_input` وقتی پر است یعنی این قاعده مبلغی را می‌خواند که اپراتور هر
    دوره وارد می‌کند، و متنش می‌گوید آن عدد **چه معنایی دارد**. صفحهٔ «مبالغ
    دستی» از همین نشانه می‌فهمد که باید این قلم را هم نشان بدهد و بالای جدول
    چه توضیحی بدهد.

    دو چیزِ متفاوت را از هم جدا می‌کند:

    - عددی که **خودِ مبلغ** است (پورسانت، کسور موردی)
    - عددی که **به محاسبهٔ خودکار اضافه می‌شود** (حق مأموریت، که پایه‌اش از
      روز مأموریت می‌آید)

    بدون این تفکیک، اپراتور مبلغ مأموریت را در خانه‌ای می‌نوشت که فقط
    «اضافه» است و مأموریت دو بار پرداخت می‌شد.
    """

    def decorator(func):
        func.rule_key = key
        func.rule_label = label or key
        func.manual_input_note = manual_input
        RULES[key] = func
        return func

    return decorator


def get_rule(key: str):
    return RULES.get(key)


def manual_input_note(key: str) -> str:
    """اگر این قاعده ورودی دستی می‌خواهد، توضیحِ معنای آن عدد؛ وگرنه رشتهٔ خالی."""
    func = RULES.get(key)
    return getattr(func, "manual_input_note", "") if func else ""


# ==================================================================== مزایا


@rule("base_salary", "حقوق پایه")
def base_salary(ctx: PayrollContext, component):
    """حقوق ثابت = روز کارکرد قابل پرداخت × مزد روزانه.

    مزد روزانه یا از دستمزد واقعیِ قرارداد می‌آید یا — اگر قرارداد عددی
    نداشته باشد — از حداقل دستمزد همان سال. توضیح سطر می‌گوید کدام، تا روی
    فیش پیدا باشد با کدام مبنا حساب شده است.
    """
    days = ctx.paid_days
    daily = ctx.daily_base
    unpaid = ctx.unpaid_days
    unpaid_note = (
        f" (کارکرد اولیه {fa_number(ctx.initial_days, 2)} روز − "
        f"{fa_number(unpaid, 2)} روز بدون حقوق)"
        if unpaid
        else ""
    )
    return LineResult(
        amount=daily * days,
        base_amount=daily,
        quantity=days,
        rate=Decimal("1"),
        explanation=(
            f"حقوق ثابت: {fa_number(days, 2)} روز × {fa_wage(daily)} ریال مزد روزانه "
            f"بر مبنای {ctx.wage_basis_label}{unpaid_note}"
        ),
    ).rounded()


@rule("seniority", "پایه سنوات")
def seniority(ctx: PayrollContext, component):
    if ctx.seniority_years < 1:
        return None
    daily = ctx.params.seniority_daily
    days = ctx.paid_days
    return LineResult(
        amount=daily * days,
        base_amount=daily,
        quantity=days,
        rate=Decimal("1"),
        explanation=(
            f"پایه سنوات: {fa_number(days, 2)} روز × {fa_wage(daily)} ریال "
            f"(سابقه {fa_number(ctx.seniority_years)} سال)"
        ),
    ).rounded()


@rule("housing_allowance", "حق مسکن")
def housing_allowance(ctx: PayrollContext, component):
    monthly = ctx.params.housing_allowance
    return _prorated(ctx, monthly, "حق مسکن")


@rule("food_allowance", "بن کارگری")
def food_allowance(ctx: PayrollContext, component):
    monthly = ctx.params.food_allowance
    return _prorated(ctx, monthly, "بن کارگری")


def _prorated(ctx: PayrollContext, monthly_amount: Decimal, label: str):
    """مزایای ثابت ماهانه که به نسبت روز کارکرد تسهیم می‌شوند."""
    ratio = ctx.day_ratio
    amount = monthly_amount * ratio
    return LineResult(
        amount=amount,
        base_amount=monthly_amount,
        quantity=ctx.paid_days,
        rate=ratio,
        explanation=(
            f"{label}: {fa_money(monthly_amount)} ریال × "
            f"{fa_number(ctx.paid_days, 2)} ÷ {fa_number(ctx.month_days, 2)} روز"
        ),
    ).rounded()


@rule("marriage_allowance", "حق تأهل")
def marriage_allowance(ctx: PayrollContext, component):
    """حق تأهل — فقط برای متأهل‌ها، به نسبت روز کارکرد.

    برخلاف حق اولاد، این قلم **قانونی نیست**: سیاست شرکت است و مبلغش در
    پارامترهای سال ثبت می‌شود. پس اگر شرکتی چنین قلمی ندارد، مبلغ را صفر
    می‌گذارد و سطر اصلاً روی فیش نمی‌آید.

    در فایل ۱۴۰۵ شرکت، این قلم مشمول بیمه و مالیات هر دو است (از ماخذ بیمه
    فقط ماموریت و حق اولاد کم می‌شوند، نه حق تأهل) — و شمولش داده است، نه
    کد: روی خودِ قلم تنظیم می‌شود.
    """
    from apps.employees.models import Employee

    married = getattr(ctx.employee, "marital_status", None) == Employee.MaritalStatus.MARRIED
    if not married:
        return None
    monthly = Decimal(ctx.params.marriage_allowance or ZERO)
    if not monthly:
        return None
    return _prorated(ctx, monthly, "حق تأهل")


@rule("child_allowance", "حق اولاد")
def child_allowance(ctx: PayrollContext, component):
    count = ctx.children_count
    if count <= 0:
        return None
    max_children = ctx.params.max_children or 0
    effective = min(count, max_children) if max_children else count
    per_child = ctx.params.child_allowance
    ratio = ctx.day_ratio
    amount = per_child * effective * ratio
    note = ""
    if max_children and count > max_children:
        note = f" (از {fa_number(count)} فرزند، {fa_number(max_children)} فرزند مشمول)"
    return LineResult(
        amount=amount,
        base_amount=per_child,
        quantity=Decimal(effective),
        rate=ratio,
        explanation=(
            f"حق اولاد: {fa_number(effective)} فرزند × {fa_money(per_child)} ریال × "
            f"{fa_number(ctx.paid_days, 2)} ÷ {fa_number(ctx.month_days, 2)} روز{note}"
        ),
    ).rounded()


def _hourly_rule(ctx: PayrollContext, hours: Decimal, factor: Decimal, label: str):
    if not hours or hours <= 0:
        return None
    hourly = ctx.hourly_base
    amount = hourly * factor * hours
    return LineResult(
        amount=amount,
        base_amount=hourly,
        quantity=hours,
        rate=factor,
        explanation=(
            f"{label}: {fa_number(hours, 2)} ساعت × {fa_wage(hourly)} ریال "
            f"مزد ساعتی × {fa_number(factor, 3)}"
        ),
    ).rounded()


@rule("overtime", "اضافه‌کاری")
def overtime(ctx: PayrollContext, component):
    """اضافه‌کاری = ساعت‌های جدول کارکرد + مبلغ منتقل‌شده از پورسانت.

    مبنای ساعتی اگر برای همان ماه ثبت شده باشد از آن می‌آید، وگرنه از مزد
    ساعتی خود پرسنل. مبلغ منتقل‌شده از پورسانت در `commission.py` و با رعایت
    سقف ساعت همان ماه حساب شده و اینجا فقط به سطر اضافه می‌شود.
    """
    hours = ctx.timesheet.exact_overtime_hours if ctx.timesheet else ZERO
    monthly_rate = Decimal(ctx.params.overtime_hourly_rate or ZERO)

    # مبنای ساعتیِ ماه، **مبلغ نهایی هر ساعت** است و ضریب روی آن اعمال نمی‌شود:
    # همان عددی است که هر ماه تصویب می‌شود. اگر ضریب هم می‌خورد، «ساعت معادلِ»
    # مبلغ منتقل‌شده از پورسانت با سقف ساعت نمی‌خواند و سقف بی‌معنا می‌شد.
    if monthly_rate:
        hourly, factor, basis = monthly_rate, Decimal("1"), "مبنای ساعتی این ماه"
    else:
        hourly, factor = ctx.overtime_hourly_base, ctx.params.overtime_factor
        basis = (
            "مبنای ساعتی ماهانه"
            if getattr(ctx.params, "overtime_base", "") == "MONTHLY_BASE"
            else "مزد ساعتی"
        )

    # مبلغِ اعلامیِ مدیریت، اگر ثبت شده باشد، **کل مبلغ اضافه‌کاری** است و
    # جای محاسبه را می‌گیرد — نه اینکه رویش اضافه شود. روال شرکت این است که
    # ساعت اعلام می‌شود و روبه‌رویش مبلغ نوشته می‌شود، و آن مبلغ لزوماً از
    # ضربِ ساعت در مبنای سال درنمی‌آید.
    #
    # ساعت همچنان روی فیش می‌نشیند، چون سطر فیش باید بگوید بابت چند ساعت.
    declared = getattr(ctx.timesheet, "overtime_amount", None) if ctx.timesheet else None
    parts = []
    if declared is not None:
        amount = Decimal(declared)
        hour_note = f" برای {fa_number(hours, 2)} ساعت" if hours and hours > 0 else ""
        parts.append(f"اضافه‌کاری: مبلغ اعلامی{hour_note}")
    else:
        amount = hourly * factor * hours if hours and hours > 0 else ZERO
        if hours and hours > 0:
            rate_note = "" if monthly_rate else f" × {fa_number(factor, 3)}"
            parts.append(
                f"اضافه‌کاری: {fa_number(hours, 2)} ساعت × {fa_wage(hourly)} ریال "
                f"{basis}{rate_note}"
            )

    transferred = ctx.commission_to_overtime
    if transferred:
        amount += transferred
        hours = hours + ctx.commission_overtime_hours
        parts.append(
            f"به‌علاوهٔ {fa_money(transferred)} ریال منتقل‌شده از پورسانت "
            f"({fa_number(ctx.commission_overtime_hours, 2)} ساعت)"
        )

    # با مبلغ اعلامی، صفر هم معنادار است («این ماه اضافه‌کاری ندارد») ولی
    # سطرِ صفر روی فیش چیزی اضافه نمی‌کند، پس مثل قبل حذف می‌شود.
    if amount <= ZERO:
        return None
    return LineResult(
        amount=amount,
        base_amount=(amount / hours) if (declared is not None and hours) else hourly,
        quantity=hours,
        rate=Decimal("1") if declared is not None else factor,
        explanation=" — ".join(parts),
    ).rounded()


@rule("mission_allowance", "حق مأموریت",
      manual_input="این عدد به‌علاوهٔ محاسبهٔ خودکار روی روز مأموریت است، نه به‌جای آن. "
                   "برای مأموریت عادی خالی بگذارید و روزها را در جدول کارکرد ثبت کنید.")
def mission_allowance(ctx: PayrollContext, component):
    """حق مأموریت = روزهای مأموریت جدول کارکرد + مبلغ منتقل‌شده از پورسانت.

    مبنای روزانه «آیتم محاسباتی ماهانه» است و هر ماه جداگانه ثبت می‌شود؛ اگر
    ثبت نشده باشد فقط مبلغ دستیِ همان قلم (اگر باشد) می‌ماند.

    **ضریب قلم** در همین فرمول ضرب می‌شود، چون در فایل ۱۴۰۵ شرکت مأموریتِ واحد
    فروش ضریب ۲ می‌خورَد و بقیه ضریب ۱ (هر پنج ماه، هر ۳۳ نفر، بدون استثنا).
    با همین، آن تفاوت به‌جای کد شدن، با دو قلم مأموریت و دامنه شمول بیان
    می‌شود: یکی با ضریب ۲ محدود به مرکز هزینهٔ فروش، یکی با ضریب ۱ برای بقیه.

    ضریب خالی یا صفر یعنی ۱، پس اقلام موجود عوض نمی‌شوند.

    **ضریب فقط روی روزهای جدول کارکرد اثر دارد**، نه روی مبلغ منتقل‌شده از
    پورسانت: آن یکی از قبل مبلغ ریالیِ نهایی است و ضرب دوباره‌اش یعنی دوبار
    حساب کردن. (در فایل اکسل، تبدیل پورسانت به مأموریت خودش با همین ضریب
    بازی می‌کند — بخش ۵ سند EXCEL-1405 — که هنوز به سامانه نیامده.)
    """
    rate = ctx.mission_daily_base
    days = (ctx.timesheet.mission_days if ctx.timesheet else ZERO) or ZERO
    factor = component.rate if component.rate else Decimal("1")
    basis = (
        "مزد روزانه + پایه سنوات"
        if getattr(ctx.params, "mission_base", "") == "PERSON_WAGE"
        else "مبنای روزانهٔ این ماه"
    )

    amount = rate * days * factor
    parts = []
    if amount:
        factor_note = f" × ضریب {fa_number(factor, 3)}" if factor != 1 else ""
        parts.append(
            f"حق مأموریت: {fa_number(days, 2)} روز × {fa_wage(rate)} ریال "
            f"{basis}{factor_note}"
        )

    transferred = ctx.commission_to_mission
    if transferred:
        amount += transferred
        days = days + ctx.commission_mission_days
        parts.append(
            f"به‌علاوهٔ {fa_money(transferred)} ریال منتقل‌شده از پورسانت "
            f"({fa_number(ctx.commission_mission_days, 2)} روز)"
        )

    # مبلغ دستیِ ثبت‌شده روی همین قلم هم اگر باشد اضافه می‌شود
    manual = ctx.manual_inputs.get(component.id)
    if manual:
        amount += Decimal(manual)
        parts.append(f"به‌علاوهٔ {fa_money(manual)} ریال مبلغ دستی")

    if amount <= ZERO:
        return None
    return LineResult(
        amount=amount,
        base_amount=rate,
        quantity=days,
        rate=Decimal("1"),
        explanation=" — ".join(parts),
    ).rounded()


@rule("night_work", "شب‌کاری")
def night_work(ctx: PayrollContext, component):
    if not ctx.timesheet:
        return None
    return _hourly_rule(ctx, ctx.timesheet.night_hours, ctx.params.night_factor, "شب‌کاری")


@rule("friday_work", "جمعه‌کاری")
def friday_work(ctx: PayrollContext, component):
    if not ctx.timesheet:
        return None
    return _hourly_rule(ctx, ctx.timesheet.friday_hours, ctx.params.friday_factor, "جمعه‌کاری")


@rule("holiday_work", "تعطیل‌کاری")
def holiday_work(ctx: PayrollContext, component):
    if not ctx.timesheet:
        return None
    return _hourly_rule(ctx, ctx.timesheet.holiday_hours, ctx.params.holiday_factor, "تعطیل‌کاری")


@rule("shift_work", "نوبت‌کاری")
def shift_work(ctx: PayrollContext, component):
    if not ctx.timesheet:
        return None
    shift = ctx.timesheet.shift_type
    rates = ctx.params.shift_rates or {}
    raw = rates.get(shift)
    if not raw:
        return None
    factor = Decimal(str(raw))
    base = ctx.amount_of("BASE_SALARY")
    amount = base * factor
    return LineResult(
        amount=amount,
        base_amount=base,
        quantity=Decimal("1"),
        rate=factor,
        explanation=(
            f"نوبت‌کاری ({ctx.timesheet.get_shift_type_display()}): "
            f"{fa_money(base)} ریال × {fa_number(factor * 100, 2)}٪"
        ),
    ).rounded()


@rule("contract_allowance", "مزایای مستمر قرارداد")
def contract_allowance(ctx: PayrollContext, component):
    monthly = ctx.contract_allowances.get(component.id)
    if not monthly:
        return None
    return _prorated(ctx, Decimal(monthly), component.name)


@rule("manual_input", "ورود دستی دوره",
      manual_input="عددی که وارد می‌کنید خودِ مبلغ این قلم است.")
def manual_input(ctx: PayrollContext, component):
    """اقلامی مثل پورسانت فروش که مبلغشان از بیرون موتور می‌آید.

    اگر قلم «پورسانت» باشد و بخشی از آن به حق مأموریت یا اضافه‌کاری منتقل شده
    باشد، فقط **مانده** روی این سطر می‌نشیند — وگرنه همان مبلغ دو بار پرداخت
    می‌شد. توضیح سطر می‌گوید چه مقدار کجا رفته است.
    """
    amount = Decimal(ctx.manual_inputs.get(component.id) or ZERO)
    if not amount:
        return None

    if component.is_commission and ctx.commission_transferred:
        share = ctx.commission_share(amount)
        if share <= ZERO:
            return None
        return LineResult(
            amount=share,
            base_amount=amount,
            quantity=Decimal("1"),
            rate=Decimal("1"),
            explanation=(
                f"{component.name}: از {fa_money(amount)} ریال، "
                f"{fa_money(amount - share)} ریال به حق مأموریت/اضافه‌کاری منتقل شد "
                f"و {fa_money(share)} ریال مانده"
            ),
        ).rounded()

    return LineResult(
        amount=amount,
        base_amount=amount,
        quantity=Decimal("1"),
        rate=Decimal("1"),
        explanation=f"{component.name}: مبلغ ثبت‌شده برای دوره {ctx.period.title}",
    ).rounded()


@rule("percentage_of", "درصدی از قلم دیگر")
def percentage_of(ctx: PayrollContext, component):
    if not component.base_component_id:
        return None
    base = ctx.amount_of(component.base_component.code)
    if not base:
        return None
    factor = component.rate
    return LineResult(
        amount=base * factor,
        base_amount=base,
        quantity=Decimal("1"),
        rate=factor,
        explanation=(
            f"{component.name}: {fa_number(factor * 100, 2)}٪ از "
            f"{component.base_component.name} ({fa_money(base)} ریال)"
        ),
    ).rounded()


@rule("parametric", "قاعده پارامتری")
def parametric(ctx: PayrollContext, component):
    """قلمی که کاربر بدون کدنویسی ساخته است — بند ۳ سند.

        مبلغ = مبنا × مقدار × ضریب

    مبنا یکی از چهار چیز است (حداقل دستمزد، مزد خود پرسنل، مبلغ ثابت، مبلغ قلم
    دیگر) و مقدار یکی از سه حالت (روز کارکرد، نسبت کارکرد به ماه، ثابت). با
    همین ترکیب، شکل همهٔ قواعد دست‌نویسِ موجود قابل بیان است.

    عمداً «زبان فرمول» نیست: هر ترکیب ممکن اینجا از پیش تست‌شده و قابل ممیزی
    است، و هر عدد توضیح خودش را با همان اجزا می‌سازد.
    """
    from apps.payroll_config.models import SalaryComponent

    base_kind = component.base_source
    Base = SalaryComponent.BaseSource
    Quantity = SalaryComponent.QuantitySource

    if base_kind == Base.MIN_WAGE:
        base = ctx.params.min_daily_wage or ZERO
        base_label = "حداقل دستمزد روزانه"
    elif base_kind == Base.PERSON_WAGE:
        base = ctx.daily_base
        base_label = f"مزد روزانه ({ctx.wage_basis_label})"
    elif base_kind == Base.FIXED:
        base = component.fixed_amount or ZERO
        base_label = "مبلغ ثابت"
    elif base_kind == Base.COMPONENT:
        if not component.base_component_id:
            return None
        base = ctx.amount_of(component.base_component.code)
        base_label = component.base_component.name
    else:
        return None

    if not base:
        return None

    if component.quantity_source == Quantity.TIMESHEET_ITEM:
        # مقدار از جدول کارکرد می‌آید، به واحد خودِ همان قلم (روز/ساعت/دقیقه).
        # با همین، افزودن «جمعه‌کاری» یا هر قلم کارکرد تازه هیچ کد جدیدی لازم
        # ندارد: یک ستون در کارکرد، یک قلم پارامتری، تمام.
        item = component.timesheet_item
        if item is None or ctx.timesheet is None:
            return None
        quantity = ctx.timesheet.value_of(item)
        quantity_text = f"{fa_number(quantity, 2)} {item.unit_label} {item.name}"
    elif component.quantity_source == Quantity.PAID_DAYS:
        quantity = ctx.paid_days
        quantity_text = f"{fa_number(quantity, 2)} روز کارکرد"
    elif component.quantity_source == Quantity.DAY_RATIO:
        quantity = ctx.day_ratio
        quantity_text = (
            f"{fa_number(ctx.paid_days, 2)} ÷ {fa_number(ctx.month_days, 2)} روز ماه"
        )
    else:
        quantity = Decimal("1")
        quantity_text = ""

    factor = component.rate if component.rate else Decimal("1")

    pieces = [f"{fa_wage(base)} ریال {base_label}"]
    if quantity_text:
        pieces.append(quantity_text)
    if factor != 1:
        pieces.append(f"ضریب {fa_number(factor, 4)}")

    return LineResult(
        amount=base * quantity * factor,
        base_amount=base,
        quantity=quantity,
        rate=factor,
        explanation=f"{component.name}: " + " × ".join(pieces),
    ).rounded()


@rule("commission_net", "پورسانت پس از جذب",
      manual_input="عددی که وارد می‌کنید پورسانت خام است، پیش از کسر.")
def commission_net(ctx: PayrollContext, component):
    """پورسانت خام منهای اقلامی که در آن جذب می‌شوند.

    از فایل ۱۴۰۵ شرکت، برای گروه فروش (روی ۵۵ نفر-ماه ریال‌به‌ریال تأیید شد):

        پورسانت قابل پرداخت = پورسانت خام
                            − (مبلغ مأموریت + مابه‌التفاوت سنوات + ذخیره پورسانت)

    منطقش این است که بستهٔ توافقی فروشنده ثابت است: وقتی سنوات انباشته بالا
    می‌رود یا مأموریت بیشتری ثبت می‌شود، از سهم پورسانت خودش برداشته می‌شود نه
    اینکه به جمع اضافه شود.

    **چرا جذب، نه کسور؟** کسور از خالص کم می‌شود و ماخذ بیمه و مالیات را دست
    نمی‌زند. جذب، خودِ ناخالص را کم می‌کند. همین تفاوت است که این مکانیزم را
    لازم کرده.

    اقلامِ جذب‌شونده داده‌اند نه کد (`SalaryComponent.absorbs`)، پس اگر فردا
    قلم تازه‌ای اضافه شد، یک انتخاب در فرم کافی است.

    نتیجه می‌تواند **منفی** شود و عمداً صفر نمی‌شود: در فایل شرکت هم می‌شود
    (اردیبهشت، علی قاسمی: ۹۸۰٬۸۴۳− ریال). صفر کردنش یعنی پنهان کردن اینکه
    جذب از خودِ پورسانت بیشتر بوده.
    """
    raw = Decimal(ctx.manual_inputs.get(component.id, ZERO) or ZERO)

    # «مازاد ثابت» در فرمول فروشِ فایل به پورسانت خام **اضافه** می‌شود:
    #     پورسانت قابل پرداخت = (پورسانت خام + مازاد ثابت) − (جذب‌شونده‌ها)
    # تا وقتی مازاد ثابت ورودی ماهانه بود، بارگذار آن را با پورسانت خام یک‌جا
    # وارد می‌کرد. حالا که روی قرارداد نشسته، همین‌جا خوانده می‌شود.
    surplus_add = ZERO
    for other in ctx.applicable_components:
        if getattr(other, "allocation_role", "") == "ADD":
            surplus_add += ctx.recurring_or_manual(other)
    raw += surplus_add

    absorbed = ZERO
    pieces = []
    for other in component.absorbs.all():
        # قلمی که سطر ساخته، از سطرش خوانده می‌شود؛ قلمی که فقط ورودی دستی
        # است (مثل ذخیره پورسانت که روی فیش نمی‌آید) از همان ورودی.
        amount = ctx.amount_of(other.code)
        if not amount:
            amount = Decimal(ctx.manual_inputs.get(other.id, ZERO) or ZERO)
        if amount:
            absorbed += amount
            pieces.append(f"{other.name} {fa_money(amount)}")

    if not raw and not absorbed:
        return None

    note = f" − ({' + '.join(pieces)})" if pieces else ""
    add_note = f" (شامل {fa_money(surplus_add)} ریال مازاد ثابت)" if surplus_add else ""
    return LineResult(
        amount=raw - absorbed,
        base_amount=raw,
        quantity=Decimal("1"),
        rate=Decimal("1"),
        explanation=f"{component.name}: {fa_money(raw)} ریال{add_note}{note}",
    ).rounded()


def _surplus_note(plan) -> str:
    """توضیح مشترک دو قلمِ زنجیره — تا هر دو سطر یک روایت بگویند."""
    parts = [f"استخر مازاد {fa_money(plan.pool)} ریال"]
    if plan.real_minutes:
        parts.append(
            f"شامل {fa_number(plan.real_minutes / Decimal('60'), 2)} ساعت "
            f"اضافه‌کاری واقعی ({fa_money(plan.real_amount)} ریال)"
        )
    if plan.additions:
        parts.append(f"به‌علاوهٔ {fa_money(plan.additions)} ریال مازاد")
    if plan.deductions:
        parts.append(f"منهای {fa_money(plan.deductions)} ریال کسر از استخر")
    return "؛ ".join(parts)


@rule("mission_surplus", "حق مأموریت از استخر مازاد")
def mission_surplus(ctx: PayrollContext, component):
    """روز مأموریت را **حساب می‌کند**، نه اینکه از جدول کارکرد بخواند.

    گام اول زنجیرهٔ مازاد: بزرگ‌ترین واحد اول پر می‌شود. توضیح کامل زنجیره در
    `apps/payroll/surplus.py` است.

    این قلم جایگزین «حق مأموریت» عادی است، نه اضافه بر آن — باید با دامنه
    شمول به همان واحدی محدود شود که زنجیره دارد، و قلم مأموریت عادی به بقیه.
    """
    plan = ctx.surplus
    days = plan.mission_days
    if not days:
        return None
    rate = plan.mission_daily_base
    return LineResult(
        amount=rate * days,
        base_amount=rate,
        quantity=days,
        rate=Decimal("1"),
        explanation=(
            f"حق مأموریت از زنجیرهٔ مازاد: {fa_number(days)} روز × "
            f"{fa_wage(rate)} ریال (مزد روزانه + پایه سنوات) — {_surplus_note(plan)}"
        ),
    ).rounded()


@rule("overtime_surplus", "اضافه‌کاری از استخر مازاد")
def overtime_surplus(ctx: PayrollContext, component):
    """ساعت و دقیقهٔ اضافه‌کاری را از ماندهٔ استخر می‌سازد.

    گام دوم و سوم زنجیره. عددی که روی فیش می‌نشیند دیگر ساعتِ کارکرد نیست:
    ساعتِ **قابل پرداخت** است، بعد از اینکه روزهای مأموریت سهمشان را برداشتند.

    ماندهٔ گرد کردن (`residue`) عمداً جبران نمی‌شود — در فایل شرکت هم نمی‌شود —
    ولی در توضیح سطر نوشته می‌شود تا حسابدار ببیندش.
    """
    # مبلغ اعلامیِ مدیریت اینجا هم مقدم است. اگر کسی مبلغ نوشته باشد، همان
    # کل اضافه‌کاری اوست و زنجیره برای این سطر دور زده می‌شود.
    #
    # روز مأموریتِ زنجیره سر جایش می‌ماند: آن گام جداگانه‌ای است و مبلغی که
    # برای اضافه‌کاری اعلام شده دربارهٔ مأموریت چیزی نمی‌گوید.
    declared = getattr(ctx.timesheet, "overtime_amount", None) if ctx.timesheet else None
    if declared is not None:
        amount = Decimal(declared)
        if amount <= ZERO:
            return None
        return LineResult(
            amount=amount,
            base_amount=amount,
            quantity=ctx.overtime_minutes / Decimal("60"),
            rate=Decimal("1"),
            explanation="اضافه‌کاری: مبلغ اعلامی — جای محاسبهٔ زنجیرهٔ مازاد را گرفت",
        ).rounded()

    plan = ctx.surplus
    hours, minutes = plan.overtime_hours, plan.overtime_extra_minutes
    if not hours and not minutes:
        return None

    amount = plan.money_for(hours=hours, minutes=minutes)
    time_note = []
    if hours:
        time_note.append(f"{fa_number(hours)} ساعت")
    if minutes:
        time_note.append(f"{fa_number(minutes)} دقیقه")
    residue_note = (
        f" — باقی‌ماندهٔ گرد کردن {fa_money(abs(plan.residue))} ریال "
        f"{'اضافه پرداخت' if plan.residue < ZERO else 'پرداخت‌نشده'}"
        if plan.residue
        else ""
    )
    return LineResult(
        amount=amount,
        base_amount=plan.hour_rate,
        quantity=plan.overtime_minutes / Decimal("60"),
        rate=Decimal("1"),
        explanation=(
            f"اضافه‌کاری از زنجیرهٔ مازاد: {' و '.join(time_note)} × "
            f"{fa_wage(plan.hour_rate)} ریال هر ساعت — {_surplus_note(plan)}"
            f"{residue_note}"
        ),
    ).rounded()


@rule("fixed_amount", "مبلغ ثابت")
def fixed_amount(ctx: PayrollContext, component):
    if not component.fixed_amount:
        return None
    return LineResult(
        amount=component.fixed_amount,
        base_amount=component.fixed_amount,
        quantity=Decimal("1"),
        rate=Decimal("1"),
        explanation=f"{component.name}: مبلغ ثابت ماهانه",
    ).rounded()


# ==================================================================== کسور


@rule("insurance_employee", "بیمه سهم کارگر")
def insurance_employee(ctx: PayrollContext, component):
    if not ctx.insurance_applies:
        return None
    base = ctx.capped_insurable
    rate = ctx.params.ins_employee_rate
    ceiling = ctx.params.insurance_ceiling
    capped_note = ""
    if ceiling and ctx.insurable_base > ceiling:
        capped_note = (
            f" — مبنا از {fa_money(ctx.insurable_base)} به سقف قانونی "
            f"{fa_money(ceiling)} محدود شد"
        )
    return LineResult(
        amount=base * rate,
        base_amount=base,
        quantity=Decimal("1"),
        rate=rate,
        explanation=(
            f"بیمه سهم کارگر: {fa_money(base)} ریال × "
            f"{fa_number(rate * 100, 2)}٪{capped_note}"
        ),
    ).rounded()


@rule("income_tax", "مالیات بر درآمد حقوق")
def income_tax(ctx: PayrollContext, component):
    """مالیات پلکانی.

    نکته‌ای که باید با حسابدار شرکت تأیید شود: آیا بیمه سهم کارگر از درآمد مشمول
    مالیات کسر می‌شود؟ اینجا با پرچم deduct_insurance_from_tax_base کنترل می‌شود.
    """
    from apps.payroll_config.models import TaxBracket

    taxable = ctx.taxable_after_insurance
    ins_note = ""
    if ctx.params.deduct_insurance_from_tax_base:
        ins = ctx.amount_of("INSURANCE_EMP")
        if ins:
            ins_note = f" (پس از کسر بیمه سهم کارگر {fa_money(ins)})"

    if taxable <= 0:
        return None

    brackets = list(
        TaxBracket.objects.filter(
            fiscal_year=ctx.period.fiscal_year, basis=TaxBracket.Basis.MONTHLY
        ).order_by("row_order")
    )
    if not brackets:
        return None

    total = ZERO
    applied = []
    for bracket in brackets:
        lower = bracket.from_amount
        if taxable <= lower:
            break
        upper = bracket.to_amount if bracket.to_amount is not None else taxable
        portion = min(taxable, upper) - lower
        if portion <= 0:
            continue
        if bracket.rate > 0:
            total += portion * bracket.rate
            applied.append(f"{fa_money(portion)}×{fa_number(bracket.rate * 100, 0)}٪")

    if total <= 0:
        return None

    detail = " + ".join(applied)
    return LineResult(
        amount=total,
        base_amount=taxable,
        quantity=Decimal("1"),
        rate=(total / taxable) if taxable else ZERO,
        explanation=(
            f"مالیات پلکانی بر مبنای {fa_money(taxable)} ریال{ins_note}: {detail}"
        ),
    ).rounded()


@rule("loan_installment", "اقساط وام و مساعده")
def loan_installment(ctx: PayrollContext, component):
    if not ctx.due_installments:
        return None
    total = sum((item.amount for item in ctx.due_installments), ZERO)
    if total <= 0:
        return None
    count = len(ctx.due_installments)
    titles = "، ".join(
        f"{item.loan.get_loan_type_display()} قسط {fa_number(item.number)}"
        for item in ctx.due_installments[:3]
    )
    more = f" و {fa_number(count - 3)} مورد دیگر" if count > 3 else ""
    return LineResult(
        amount=total,
        base_amount=total,
        quantity=Decimal(count),
        rate=Decimal("1"),
        explanation=f"کسر اقساط سررسیدشده: {titles}{more}",
    ).rounded()


@rule("deduction_manual", "کسور دستی",
      manual_input="عددی که وارد می‌کنید خودِ مبلغ کسور این دوره است.")
def deduction_manual(ctx: PayrollContext, component):
    amount = ctx.manual_inputs.get(component.id)
    if not amount:
        return None
    return LineResult(
        amount=Decimal(amount),
        base_amount=Decimal(amount),
        quantity=Decimal("1"),
        rate=Decimal("1"),
        explanation=f"{component.name}: مبلغ ثبت‌شده برای دوره {ctx.period.title}",
    ).rounded()


# ================================================== کسورات کارکردی (فقط روز)


def _day_only_rule(days: Decimal, label: str):
    """سطر «فقط روز» — بدون مبلغ ریالی.

    اثر مالی این اقلام قبلاً با کم شدن از روز کارکرد اعمال شده است؛ اگر مبلغ
    ریالی هم می‌گذاشتیم، دو بار کسر می‌شد. سطر می‌ماند چون روی فیش باید دیده
    شود که چند روز غیبت یا بیماری بوده است.
    """
    if not days or days <= 0:
        return None
    return LineResult(
        amount=ZERO,
        base_amount=ZERO,
        quantity=days,
        rate=ZERO,
        explanation=f"{label}: {fa_number(days, 2)} روز — از روز کارکرد کسر شده است",
    )


@rule("absence_days", "غیبت (روز)")
def absence_days(ctx: PayrollContext, component):
    if not ctx.timesheet:
        return None
    return _day_only_rule(ctx.timesheet.absence_days, "غیبت")


@rule("sick_days", "بیماری (روز)")
def sick_days(ctx: PayrollContext, component):
    if not ctx.timesheet:
        return None
    return _day_only_rule(ctx.timesheet.sick_leave_days, "بیماری")


@rule("unpaid_leave_days", "مرخصی بدون حقوق (روز)")
def unpaid_leave_days(ctx: PayrollContext, component):
    if not ctx.timesheet:
        return None
    return _day_only_rule(ctx.timesheet.unpaid_leave_days, "مرخصی بدون حقوق")


# ============================================================ هزینه کارفرما


@rule("insurance_employer", "بیمه سهم کارفرما")
def insurance_employer(ctx: PayrollContext, component):
    if not ctx.insurance_applies:
        return None
    base = ctx.capped_insurable
    rate = ctx.params.ins_employer_rate
    return LineResult(
        amount=base * rate,
        base_amount=base,
        quantity=Decimal("1"),
        rate=rate,
        explanation=(
            f"بیمه سهم کارفرما: {fa_money(base)} ریال × {fa_number(rate * 100, 2)}٪"
        ),
    ).rounded()


@rule("unemployment_insurance", "بیمه بیکاری")
def unemployment_insurance(ctx: PayrollContext, component):
    if not ctx.insurance_applies:
        return None
    base = ctx.capped_insurable
    rate = ctx.params.unemployment_rate
    return LineResult(
        amount=base * rate,
        base_amount=base,
        quantity=Decimal("1"),
        rate=rate,
        explanation=(
            f"بیمه بیکاری (سهم کارفرما): {fa_money(base)} ریال × "
            f"{fa_number(rate * 100, 2)}٪"
        ),
    ).rounded()


# ================================================================== اطلاعی
# «مبنای محاسبه»هایی که عدد پرداختی نیستند ولی هر حسابداری اول سراغشان می‌رود.
# در فایل اکسل شرکت این‌ها ستون‌های پشت‌صحنه بودند (ماخذ بیمه، ماخذ مالیات،
# جمع مزد و سنوات روزانه…) و چون سطر نداشتند، هر بار باید از فرمول سلول
# بیرون کشیده می‌شدند. اینجا هر کدام یک قلمِ اسم‌دارند.
#
# سه قاعدهٔ ثابت دربارهٔ اقلام اطلاعی:
#   ۱. بعد از هر سه پاس دیگر اجرا می‌شوند، پس عددشان نهایی است.
#   ۲. در هیچ جمعی وارد نمی‌شوند — نه ناخالص، نه کسور، نه مبنای بیمه و مالیات.
#   ۳. عددشان از همان جایی می‌آید که محاسبهٔ واقعی از آن آمده، نه از فرمول دوم.


def _info(label: str, amount, explanation: str, quantity=None, rate=None, money=True):
    """یک سطر اطلاعی. `money=False` برای مقدارهایی مثل روز که نباید گرد شوند."""
    result = LineResult(
        amount=amount,
        base_amount=amount,
        quantity=quantity if quantity is not None else Decimal("1"),
        rate=rate if rate is not None else ZERO,
        explanation=explanation,
    )
    return result.rounded() if money else result


@rule("info_insurance_base", "ماخذ بیمه")
def info_insurance_base(ctx: PayrollContext, component):
    """همان مبنایی که سه قلم بیمه روی آن حساب شده‌اند."""
    if not ctx.insurance_applies:
        return _info(
            component.name, ZERO,
            "این پرسنل در این دوره مشمول بیمه نیست، پس ماخذ بیمه ندارد.",
        )
    base = ctx.capped_insurable
    ceiling = ctx.params.insurance_ceiling
    note = ""
    if ceiling and ctx.insurable_base > ceiling:
        note = (
            f" — از {fa_money(ctx.insurable_base)} به سقف قانونی "
            f"{fa_money(ceiling)} محدود شد"
        )
    return _info(
        component.name, base,
        f"ماخذ بیمه: جمع اقلام مشمول بیمه = {fa_money(base)} ریال{note}",
    )


@rule("info_tax_base", "ماخذ مالیات")
def info_tax_base(ctx: PayrollContext, component):
    """درآمد مشمول مالیات — دقیقاً عددی که پلکان مالیات روی آن نشسته."""
    base = ctx.taxable_after_insurance
    note = ""
    if ctx.params.deduct_insurance_from_tax_base and ctx.amount_of("INSURANCE_EMP"):
        note = f" پس از کسر بیمه سهم کارگر {fa_money(ctx.amount_of('INSURANCE_EMP'))}"
    return _info(
        component.name, max(base, ZERO),
        f"ماخذ مالیات: جمع اقلام مشمول مالیات{note} = {fa_money(max(base, ZERO))} ریال",
    )


@rule("info_daily_wage", "مزد روزانه")
def info_daily_wage(ctx: PayrollContext, component):
    return _info(
        component.name, ctx.daily_base,
        f"مزد روزانه بر مبنای {ctx.wage_basis_label}: {fa_wage(ctx.daily_base)} ریال",
    )


@rule("info_hourly_wage", "مزد ساعتی")
def info_hourly_wage(ctx: PayrollContext, component):
    hours = ctx.params.daily_work_hours or Decimal("7.33")
    return _info(
        component.name, ctx.hourly_base,
        f"مزد ساعتی: {fa_wage(ctx.daily_base)} ÷ {fa_number(hours, 2)} ساعت کار روزانه "
        f"= {fa_wage(ctx.hourly_base)} ریال",
    )


@rule("info_gross", "جمع ناخالص")
def info_gross(ctx: PayrollContext, component):
    return _info(
        component.name, ctx.gross,
        f"جمع همهٔ مزایای این فیش = {fa_money(ctx.gross)} ریال",
    )


@rule("info_employer_cost", "کل هزینه کارفرما")
def info_employer_cost(ctx: PayrollContext, component):
    """ناخالص + هر قلمی که نوعش «هزینه کارفرما» است.

    جمع از `ctx.employer_cost` می‌آید که هنگام ثبت هر سطر پر شده، نه از حدس زدن
    روی کد اقلام: هر قلم هزینهٔ کارفرمای تازه‌ای هم خودبه‌خود اینجا می‌آید.
    """
    total = ctx.gross + ctx.employer_cost
    return _info(
        component.name, total,
        f"ناخالص {fa_money(ctx.gross)} + هزینه کارفرما {fa_money(ctx.employer_cost)} "
        f"= {fa_money(total)} ریال",
    )


@rule("info_paid_days", "روز کارکرد قابل پرداخت")
def info_paid_days(ctx: PayrollContext, component):
    return _info(
        component.name, ctx.paid_days,
        f"کارکرد اولیه {fa_number(ctx.initial_days, 2)} − روزهای بی‌حقوق "
        f"{fa_number(ctx.unpaid_days, 2)} = {fa_number(ctx.paid_days, 2)} روز",
        quantity=ctx.paid_days,
        money=False,
    )
