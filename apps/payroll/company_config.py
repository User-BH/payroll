"""پیکربندی شرکت مطابق فایل «حقوق دستمزد تیر ۱۴۰۵».

چرا این فایل هست: پیکربندیِ تأییدشدهٔ بک‌تست تا امروز فقط **در یک دیتابیس**
زندگی می‌کرد. `setup_operational` اقلام پایه را می‌سازد ولی زنجیرهٔ مازاد،
جذب پورسانت و گروه راننده استجاری را نه — یعنی هرکس دیتابیس تازه‌ای می‌ساخت،
همان اعدادی را که سند BACKTEST وعده داده بود نمی‌گرفت. دیتابیس سرور هم دقیقاً
همین کم را داشت.

اینجا آن پیکربندی، **یک بار و قابل تکرار**، نوشته شده است. هیچ فرمولی کد
نمی‌شود؛ فقط اقلام و دامنه‌هایی ساخته می‌شوند که موتور از قبل بلد است.

سه گروه پرداخت در فایل تیر ۱۴۰۵ — و رنگ سطر در اکسل دقیقاً همین‌هاست:

    سفید  · واحد «فروش»            → مأموریت دستی با ضریب ۲، پورسانت با جذب
    زرد   · واحد «پشتیبانی»         → زنجیرهٔ مازاد: مأموریت و اضافه‌کاری خروجی‌اند
    سبز   · شغل «راننده استجاری»    → بدون زنجیره؛ عیدی و پایانکار و وجه مرخصی ماهانه

شیت «تیر بدون بیمه» گروه چهارم نیست: همان دو گروه اول و دوم است، فقط ماخذ
بیمه‌اش صفر است — که با تیک «بدون بیمه» روی خودِ پرسنل بیان می‌شود، نه با قلم.
"""

from decimal import Decimal

from apps.employees.models import EmploymentContract
from apps.org.models import CostCenter, JobTitle
from apps.payroll_config.models import ComponentScope, LegalParameter, SalaryComponent

SALES_UNIT = "فروش"
SUPPORT_UNIT = "پشتیبانی"
RENTAL_DRIVER = "راننده استجاری"

GREEN, AMBER, GREY = "#3E8E5B", "#B57B14", "#8A8175"

# اقلامی که فقط به گروه راننده استجاری تعلق دارند
DRIVER_ONLY_CODES = {"EID", "SEVERANCE"}

# (کد، نام، نوع، نحوه محاسبه، قاعده، ترتیب، مشمول بیمه، مشمول مالیات، چاپ، رنگ)
#
# مشمولیت از دو ستون خودِ فایل می‌آید و نه از حدس:
#     ماخذ بیمه   = جمع پرداختی‌ها − (مبلغ ماموریت + حق اولاد)
#     ماخذ مالیات = جمع پرداختی‌ها − مبلغ ماموریت
# پس هر قلم پرداختی مشمول هر دو است، مگر مأموریت (هیچ‌کدام) و اولاد (فقط مالیات).
NEW_COMPONENTS = [
    # --- زنجیرهٔ مازاد، گروه پشتیبانی -------------------------------------
    # این دو ورودی‌اند و روی فیش سطر ندارند: مبلغشان به روز مأموریت و ساعت
    # اضافه‌کاری تبدیل می‌شود و اگر «مزایا» بودند، یک بار به شکل خودشان و یک
    # بار به شکل تبدیل‌شده در ناخالص می‌نشستند. «اطلاعی» یعنی در هیچ جمعی نیست.
    ("SURPLUS_FIXED", "مازاد ثابت", "INFO", "MANUAL", "", 570, False, False, False, GREY),
    ("SURPLUS_OT", "مازاد پرداختی ماهانه", "INFO", "MANUAL", "", 571, False, False, False, GREY),
    ("OVERTIME_SURPLUS", "اضافه کار", "EARNING", "ENGINE_RULE", "overtime_surplus",
     71, True, True, True, GREEN),
    ("MISSION_SURPLUS", "حق ماموریت", "EARNING", "ENGINE_RULE", "mission_surplus",
     82, False, False, True, AMBER),
    # --- گروه راننده استجاری ---------------------------------------------
    # این سه در فایل فرمول دارند (T×۵ و T×۲٫۵ و مرخصی استحقاقی) ولی فقط برای
    # یک نفر. تا وقتی قاعده‌شان به موتور نیامده، مثل مابه‌التفاوت به‌صورت مبلغ
    # دستی وارد می‌شوند — همان کاری که اپراتور امروز می‌کند.
    ("EID", "عیدی و پاداش", "EARNING", "ENGINE_RULE", "eid_monthly",
     101, True, True, True, GREEN),
    ("SEVERANCE", "پایانکار", "EARNING", "ENGINE_RULE", "severance_monthly",
     102, True, True, True, GREEN),
    # --- دو قلمِ فرمول پورسانت که تا امروز مدل نشده بودند ------------------
    # ستون «کسر مازاد پرداختی فروش» در فرمول فایل از پورسانت کم می‌شود. در
    # فایل ۱۴۰۵ برای همهٔ سطرهای فروش صفر است، ولی نبودنش یعنی فرمول سامانه
    # با فرمول فایل یکی نیست و روزی که ناصفر شود، بی‌صدا از قلم می‌افتد.
    ("SALES_SURPLUS_DEDUCT", "کسر مازاد پرداختی فروش", "INFO", "MANUAL", "",
     572, False, False, False, GREY),
    # کف صفرِ پورسانت مبلغی را پرداخت‌نشده می‌گذارد؛ این سطر همان را پیدا
    # نگه می‌دارد. اطلاعی است: نه به ناخالص اضافه می‌شود نه از آن کم.
    ("COMM_SHORTFALL", "کسری پورسانت", "INFO", "ENGINE_RULE",
     "commission_shortfall", 573, False, False, False, GREY),
]

# اقلامی که از پیش وجود دارند ولی «ورود دستی» بودند و حالا قاعده دارند —
# یعنی سامانه دیگر جوابِ اکسل را عبور نمی‌دهد، خودش حسابش می‌کند.
NOW_COMPUTED = [
    ("DIFF", "seniority_diff", None, "مابه التفاوت"),
    ("LATE", "late_deduction", None, "کسر کار و تاخیر ورود"),
    ("LEAVE_PAY", "leave_pay_monthly", "16", "وجه مرخصی"),
]

# ضریب اقلام گروه راننده استجاری، همان‌طور که در فایل شرکت است
RATES = {"EID": "5", "SEVERANCE": "2.5", "LEAVE_PAY": "16"}


def _scope(component, scope_type, scope_id):
    ComponentScope.objects.get_or_create(
        component=component, scope_type=scope_type, scope_id=str(scope_id)
    )


def _reset_scopes(component, pairs) -> bool:
    """دامنه‌ها را دقیقاً برابر `pairs` می‌کند — نه بیشتر، نه کمتر.

    get_or_create تنها اضافه می‌کند؛ اگر دامنهٔ قبلی اشتباه بود سرِ جایش
    می‌ماند و قلم به گروهی می‌رسد که نباید. این تابع صریحاً پاک هم می‌کند.

    `True` برمی‌گرداند فقط وقتی واقعاً چیزی عوض شده باشد، تا اجرای دوم
    بگوید «چیزی عوض نشد» — وگرنه گزارشِ دستور هر بار پر است و کسی نمی‌فهمد
    این اجرا چه کرد.
    """
    wanted = {(scope_type, str(scope_id)) for scope_type, scope_id in pairs}
    current = {(scope.scope_type, scope.scope_id) for scope in component.scopes.all()}
    if wanted == current:
        return False
    component.scopes.all().delete()
    for scope_type, scope_id in wanted:
        _scope(component, scope_type, scope_id)
    return True


def support_job_titles(company):
    """پست‌های گروه پشتیبانی که زنجیرهٔ مازاد دارند — بدون راننده استجاری.

    چرا با پست و نه با مرکز هزینه: راننده استجاری هم در مرکز هزینهٔ پشتیبانی
    است ولی زنجیره ندارد (در فایل، خانهٔ «قابل پرداخت مازاد» او دستی صفر است).
    دامنه‌های شمول با «یا» ترکیب می‌شوند و راه «این مرکز هزینه به‌جز این پست»
    ندارند، پس پست‌ها یکی‌یکی شمرده می‌شوند.

    فهرست از قراردادهای واقعی ساخته می‌شود، نه از یک لیست ثابت در کد: پستِ
    تازه‌ای که فردا اضافه شود، با اجرای دوبارهٔ همین دستور وارد دامنه می‌شود.
    """
    return list(
        JobTitle.objects.filter(
            company=company,
            contracts__cost_center__name=SUPPORT_UNIT,
            contracts__status=EmploymentContract.Status.ACTIVE,
        )
        .exclude(name=RENTAL_DRIVER)
        .distinct()
    )


def configure(company, stdout=None):
    """پیکربندی را اعمال می‌کند و فهرست کارهای انجام‌شده را برمی‌گرداند."""
    done = []

    def say(text):
        done.append(text)
        if stdout:
            stdout.write("  " + text)

    # ---------------------------------------------------------- پارامترها
    params = LegalParameter.objects.filter(fiscal_year__company=company).first()
    if params and params.overtime_base != "MONTHLY_BASE_30":
        params.overtime_base = "MONTHLY_BASE_30"
        params.save(update_fields=["overtime_base"])
        say("مبنای اضافه‌کاری → (مزد روزانه + پایه سنوات) × ۳۰ ÷ ساعات کار ماهانه")

    # تسهیم مسکن، بن، اولاد و تأهل: کارکرد قابل پرداخت ÷ روزهای ماه کاری.
    #
    # یعنی ماهِ کامل همیشه کامل پرداخت می‌شود — چه اسفندِ ۲۹ روزه، چه تیرِ ۳۱
    # روزه — و این اقلام فقط با غیبت و بیماری و مرخصی بدون حقوق کم می‌شوند.
    #
    # فایل شرکت مخرج را ۳۱ ثابت می‌گیرد و همان‌جا می‌لنگد: در اسفند، کسی که
    # تمام ماه را کار کرده ۲۹ ÷ ۳۱ می‌گیرد. روی تیر و مرداد این دو روش هیچ
    # اختلافی ندارند، پس تغییرش امروز هیچ فیشی را جابه‌جا نمی‌کند.
    if params and params.allowance_proration != "MONTH_DAYS":
        params.allowance_proration = "MONTH_DAYS"
        params.save(update_fields=["allowance_proration"])
        say("تسهیم مزایای ثابت → کارکرد قابل پرداخت ÷ روزهای ماه کاری")

    # ------------------------------------------------------- اقلام تازه
    codes_new = {}
    for (code, name, kind, calc, rule, seq, ins, tax, printed, color) in NEW_COMPONENTS:
        component, created = SalaryComponent.objects.get_or_create(
            company=company, code=code,
            defaults={"name": name, "kind": kind},
        )
        component.name = name
        component.kind = kind
        component.calc_type = calc
        component.engine_rule_key = rule
        component.sequence = seq
        component.is_insurable = ins
        component.is_taxable = tax
        component.print_on_payslip = printed
        component.color = color
        # فعال/غیرفعال بودنِ اقلامِ مخصوص راننده استجاری پایین‌تر تصمیم گرفته
        # می‌شود (بسته به اینکه آن پست در چارت هست یا نه). اگر اینجا بی‌قید
        # فعالشان کنیم، همان تصمیم را هر بار خنثی کرده‌ایم.
        if code not in DRIVER_ONLY_CODES:
            component.is_active = True
        component.save()
        codes_new[code] = component
        if created:
            say(f"قلم ساخته شد: {name} ({code})")

    # «مازاد» ها استخر را پر می‌کنند و مابه‌التفاوت از آن کم می‌شود
    for code in ("SURPLUS_FIXED", "SURPLUS_OT"):
        component = codes_new[code]
        if component.allocation_role != "ADD":
            component.allocation_role = "ADD"
            component.save(update_fields=["allocation_role"])
            say(f"{component.name} → به استخر مازاد اضافه می‌شود")

    existing = {c.code: c for c in SalaryComponent.objects.filter(company=company)}

    # --------------------------------------------- از «ورود دستی» به «قاعده»
    for code, rule_key, rate, label in NOW_COMPUTED:
        component = existing.get(code)
        if component is None:
            continue
        if component.calc_type != "ENGINE_RULE" or component.engine_rule_key != rule_key:
            component.calc_type = "ENGINE_RULE"
            component.engine_rule_key = rule_key
            if rate:
                component.rate = Decimal(rate)
            component.save(update_fields=["calc_type", "engine_rule_key", "rate"])
            say(f"{label}: از «ورود دستی» به قاعدهٔ محاسبه — دیگر دستی وارد نمی‌شود")

    # اضافه‌کاری روی فیش با ساعت و دقیقه نوشته می‌شود، نه ساعتِ اعشاری.
    # مأموریت عمداً «ریال» می‌ماند: روزِ کامل است و اعشار ندارد.
    for code in ("OVERTIME", "OVERTIME_SURPLUS"):
        component = existing.get(code) or codes_new.get(code)
        if component is not None and component.display_unit != "HOUR":
            component.display_unit = "HOUR"
            component.save(update_fields=["display_unit"])
            say(f"{component.name} → نمایش با ساعت و دقیقه")

    for code, value in RATES.items():
        component = existing.get(code) or codes_new.get(code)
        if component is not None and component.rate != Decimal(value):
            component.rate = Decimal(value)
            component.save(update_fields=["rate"])
            say(f"ضریب {component.name} → {value}")

    # ------------------------------------------------------------- رنگ‌ها
    # رنگ روی فیش و در فهرست اقلام یعنی «این از چه جنسی است». سه قلم مأموریت
    # یک جنس‌اند (معاف از بیمه و مالیات) و باید یک رنگ باشند؛ روی سرور یکی‌شان
    # سبز مانده بود و کنار دوتای دیگر مثل قلمی از جنس دیگر دیده می‌شد.
    #
    # این‌جا هم قاعده کد نمی‌شود: فقط هم‌جنس‌ها هم‌رنگ می‌شوند.
    for codes, color, label in (
        (("MISSION", "MISSION2", "MISSION_SURPLUS"), AMBER, "حق مأموریت"),
        (("OVERTIME", "OVERTIME_SURPLUS"), GREEN, "اضافه‌کاری"),
    ):
        changed = []
        for code in codes:
            component = existing.get(code) or codes_new.get(code)
            if component is not None and component.color.upper() != color.upper():
                component.color = color
                component.save(update_fields=["color"])
                changed.append(component.code)
        if changed:
            say(f"هم‌رنگ شدن اقلام {label}: {'، '.join(changed)}")

    diff = existing.get("DIFF")
    if diff and diff.allocation_role != "SUBTRACT":
        diff.allocation_role = "SUBTRACT"
        diff.save(update_fields=["allocation_role"])
        say("مابه التفاوت → از استخر مازاد کم می‌شود (وگرنه دو بار پرداخت می‌شد)")

    # ------------------------------------------------- جذب در پورسانت یک
    reserve = existing.get("COMM_RESERVE")
    if reserve and reserve.kind != SalaryComponent.Kind.INFO:
        # روی سرور «مزایا» بود و چون مبلغ دارد، به ناخالص اضافه می‌شد — در حالی
        # که در فایل فقط داخل فرمول پورسانت است و هیچ‌جا پرداخت نمی‌شود.
        reserve.kind = SalaryComponent.Kind.INFO
        reserve.print_on_payslip = False
        reserve.save(update_fields=["kind", "print_on_payslip"])
        say("ذخیره پورسانت فروش: «مزایا» → «اطلاعی» (به ناخالص اضافه می‌شد)")

    # ------------------------------- تخصیص خودکار پورسانت: برای این شرکت، نه
    #
    # تیک «قلم پورسانت» یعنی مبلغ این قلم وارد استخر تخصیص می‌شود و می‌تواند
    # خودکار به روز مأموریت و ساعت اضافه‌کاری **تبدیل** شود. این شرکت چنین
    # کاری نمی‌کند: پورسانتش مأموریت را **جذب** می‌کند (کم می‌کند)، نه اینکه
    # به آن تبدیل شود.
    #
    # هر دو مکانیزم با هم یعنی یک مبلغ دو بار جابه‌جا شود. در مرداد ۱۴۰۵ که
    # «مبنای روزانهٔ مأموریت» برای آن ماه ثبت شده بود، تبدیل خودکار روشن شد و
    # ۱۴ فیش از ۶۸ فیش را خراب کرد: حق مأموریت بی‌دلیل بالا رفت و پورسانت یک
    # همان‌قدر پایین آمد — تا جایی که برای چند نفر **منفی** شد.
    for code in ("COMM_1", "COMM_2", "COMM_3"):
        component = existing.get(code)
        if component is not None and component.is_commission:
            component.is_commission = False
            component.save(update_fields=["is_commission"])
            say(f"{component.name}: تبدیل خودکار به مأموریت خاموش شد (جذب می‌شود، نه تبدیل)")

    # ------------------------------------- حق تلفن: از «مبالغ دستی» به «پرسنل»
    #
    # در تیر و مرداد هر ۱۱ نفرِ دریافت‌کننده دقیقاً یک میلیون داشتند و فهرست
    # هم عوض نشد. یعنی خاصیتِ پرسنل است نه رویدادِ ماه — از همان جنس مازاد
    # ثابت. تا وقتی «مبلغ دستی» بود، هر ماه باید یازده بار همان عدد تایپ
    # می‌شد و ماهی که تایپ نمی‌شد بی‌صدا صفر می‌شد.
    #
    # حالا مزایای مستمر قرارداد است: در صفحهٔ ویرایش پرسنل وارد می‌شود، تاریخ
    # اعتبار دارد، و از فهرست «مبالغ دستی» خودبه‌خود بیرون می‌رود چون آن صفحه
    # فهرستش را از روی `calc_type` می‌سازد.
    phone = existing.get("PHONE")
    if phone is not None:
        if phone.calc_type != "ENGINE_RULE" or phone.engine_rule_key != "contract_allowance":
            phone.calc_type = "ENGINE_RULE"
            phone.engine_rule_key = "contract_allowance"
            phone.save(update_fields=["calc_type", "engine_rule_key"])
            say("حق تلفن: از «مبالغ دستی» به «مزایای مستمر پرسنل»")
        moved = _phone_inputs_to_allowances(phone, say)
        if moved:
            say(f"حق تلفن: {moved} مبلغ دستی به مزایای مستمر منتقل شد")

    comm1 = existing.get("COMM_1")
    if comm1:
        if comm1.calc_type != "ENGINE_RULE" or comm1.engine_rule_key != "commission_net":
            comm1.calc_type = "ENGINE_RULE"
            comm1.engine_rule_key = "commission_net"
            comm1.save(update_fields=["calc_type", "engine_rule_key"])
            say("پورسانت یک → قاعدهٔ «پورسانت پس از جذب»")
        # فرمول کامل ستون پورسانت در فایل ۱۴۰۵ (در هر سه شیت یکسان):
        #   (پورسانت یک + مازاد ثابت + وجه مرخصی)
        # − (مابه‌التفاوت + ذخیره پورسانت + کسر مازاد پرداختی فروش + مبلغ مأموریت)
        pool = {**existing, **codes_new}
        wanted = [
            pool[c] for c in
            ("MISSION2", "DIFF", "COMM_RESERVE", "SALES_SURPLUS_DEDUCT")
            if c in pool
        ]
        if set(comm1.absorbs.all()) != set(wanted):
            comm1.absorbs.set(wanted)
            say("پورسانت یک جذب می‌کند: " + "، ".join(c.name for c in wanted))
        # «مازاد ثابت» از راه `allocation_role` اضافه می‌شود (زنجیرهٔ مازاد)،
        # پس فقط «وجه مرخصی» اینجا می‌ماند.
        adds = [pool[c] for c in ("LEAVE_PAY",) if c in pool]
        if set(comm1.adds.all()) != set(adds):
            comm1.adds.set(adds)
            say("پورسانت یک به آن اضافه می‌شود: "
                + "، ".join(c.name for c in adds))

    # ------------------------------------------------------------ دامنه‌ها
    sales = CostCenter.objects.filter(company=company, name=SALES_UNIT).first()
    driver = JobTitle.objects.filter(company=company, name=RENTAL_DRIVER).first()
    support = support_job_titles(company)

    if not support:
        say("هشدار: هیچ قرارداد فعالی در مرکز هزینهٔ پشتیبانی نیست — "
            "دامنهٔ زنجیرهٔ مازاد ساخته نشد. اول پرسنل را وارد کنید.")
    else:
        chain_scope = [("JOB_TITLE", job.pk) for job in support]
        # «مازاد ثابت» عمداً دامنه ندارد و به همه می‌رسد: در گروه پشتیبانی
        # استخر مازاد را پر می‌کند و در گروه فروش به پورسانت خام اضافه
        # می‌شود. محدود کردنش به پست‌های پشتیبانی یعنی فروش مازادش را
        # بی‌سروصدا از دست بدهد.
        if _reset_scopes(codes_new["SURPLUS_FIXED"], []):
            say("مازاد ثابت → بدون دامنه (هم فروش، هم پشتیبانی)")
        touched = [
            _reset_scopes(codes_new[code], chain_scope)
            for code in ("OVERTIME_SURPLUS", "MISSION_SURPLUS", "SURPLUS_OT")
        ]
        if any(touched):
            say(f"زنجیرهٔ مازاد برای {len(support)} پست پشتیبانی: "
                + "، ".join(job.name for job in support))

    # اضافه‌کاری عادی و زنجیره‌ای نباید به یک نفر برسند — دو بار پرداخت است.
    overtime = existing.get("OVERTIME")
    if overtime:
        pairs, where = [], []
        if sales:
            pairs.append(("COST_CENTER", sales.pk))
            where.append(SALES_UNIT)
        if driver:
            pairs.append(("JOB_TITLE", driver.pk))
            where.append(RENTAL_DRIVER)
        if pairs and _reset_scopes(overtime, pairs):
            say("اضافه کار عادی → فقط " + " و ".join(where))

    # ------------------------------------- اقلامِ مخصوص گروه راننده استجاری
    #
    # این چهار قلم فقط برای همان یک گروه‌اند. اگر پستِ «راننده استجاری» هنوز
    # در چارت نباشد — مثل سروری که پرسنلش وارد نشده — **نباید دامنه‌شان
    # دست‌نخورده بماند**:
    #
    #   حق ماموریت عادی دامنه‌اش مرکز هزینهٔ پشتیبانی است، یعنی همان گروهی که
    #   مأموریتش از زنجیرهٔ مازاد می‌آید. هر دو قلم روی یک نفر می‌نشینند و
    #   مأموریت **دو بار** پرداخت می‌شود.
    #
    #   عیدی و پایانکار هم دامنه‌ای ندارند، و قلمِ بی‌دامنه یعنی «همه پرسنل».
    #
    # پس تا وقتی آن پست ساخته نشده، غیرفعال می‌شوند؛ و همین دستور بعد از ورود
    # پرسنل، دوباره فعال و درست دامنه‌گذاری‌شان می‌کند.
    driver_only = [
        (existing.get("MISSION"), "حق ماموریت عادی"),
        (codes_new.get("EID"), "عیدی و پاداش"),
        (codes_new.get("SEVERANCE"), "پایانکار"),
    ]
    leave_pay = existing.get("LEAVE_PAY")

    if driver:
        scoped = []
        for component, label in driver_only + [(leave_pay, "وجه مرخصی")]:
            if component is None:
                continue
            if _reset_scopes(component, [("JOB_TITLE", driver.pk)]):
                scoped.append(label)
            if not component.is_active:
                component.is_active = True
                component.save(update_fields=["is_active"])
                scoped.append(f"{label} (دوباره فعال شد)")
        if scoped:
            say("→ فقط راننده استجاری: " + "، ".join(scoped))
    else:
        stopped = []
        for component, label in driver_only:
            if component is not None and component.is_active:
                component.is_active = False
                component.save(update_fields=["is_active"])
                stopped.append(label)
        if stopped:
            say(
                "غیرفعال شد چون پستِ «راننده استجاری» در چارت نیست: "
                + "، ".join(stopped)
                + " — بعد از ورود پرسنل، همین دستور را دوباره اجرا کنید."
            )

    return done


def _phone_inputs_to_allowances(component, say):
    """مبالغ دستیِ حق تلفن را به مزایای مستمر قرارداد منتقل می‌کند.

    بدون این انتقال، عددی که یازده نفر داشتند با تغییرِ `calc_type` بی‌صدا از
    فیش‌ها می‌افتاد: صفحهٔ مبالغ دستی دیگر نشانش نمی‌داد و قاعدهٔ تازه هم
    چیزی برای خواندن نداشت.

    مبلغِ **تازه‌ترین دوره** ملاک است، چون همان چیزی است که الان برقرار است.
    قراردادی که از قبل مزایای مستمر دارد دست نمی‌خورد — ورودی دستی نباید
    عددی را که کسی روی پرسنل ثبت کرده پس بزند.
    """
    from apps.employees.models import ContractAllowance, EmploymentContract
    from apps.payroll.models import PayrollInput

    rows = (
        PayrollInput.objects.filter(component=component)
        .select_related("period", "employee")
        .order_by("employee_id", "-period__year", "-period__month")
    )
    latest = {}
    for row in rows:
        latest.setdefault(row.employee_id, row)

    moved = 0
    for employee_id, row in latest.items():
        contract = (
            EmploymentContract.objects.filter(
                employee_id=employee_id,
                status=EmploymentContract.Status.ACTIVE,
            )
            .order_by("-effective_from")
            .first()
        )
        if contract is None:
            say(f"حق تلفن: {row.employee.full_name} قرارداد فعال ندارد — رد شد")
            continue
        if ContractAllowance.objects.filter(
            contract=contract, component=component
        ).exists():
            continue
        ContractAllowance.objects.create(
            contract=contract, component=component, amount=row.amount,
            effective_from=contract.effective_from, effective_to=None,
        )
        moved += 1
    return moved
