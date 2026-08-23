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

from apps.employees.models import EmploymentContract
from apps.org.models import CostCenter, JobTitle
from apps.payroll_config.models import ComponentScope, LegalParameter, SalaryComponent

SALES_UNIT = "فروش"
SUPPORT_UNIT = "پشتیبانی"
RENTAL_DRIVER = "راننده استجاری"

GREEN, AMBER, GREY = "#3E8E5B", "#B57B14", "#8A8175"

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
    ("EID", "عیدی و پاداش", "EARNING", "MANUAL", "", 101, True, True, True, GREEN),
    ("SEVERANCE", "پایانکار", "EARNING", "MANUAL", "", 102, True, True, True, GREEN),
]


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

    comm1 = existing.get("COMM_1")
    if comm1:
        if comm1.calc_type != "ENGINE_RULE" or comm1.engine_rule_key != "commission_net":
            comm1.calc_type = "ENGINE_RULE"
            comm1.engine_rule_key = "commission_net"
            comm1.save(update_fields=["calc_type", "engine_rule_key"])
            say("پورسانت یک → قاعدهٔ «پورسانت پس از جذب»")
        wanted = [existing[c] for c in ("MISSION2", "DIFF", "COMM_RESERVE") if c in existing]
        if set(comm1.absorbs.all()) != set(wanted):
            comm1.absorbs.set(wanted)
            say("پورسانت یک جذب می‌کند: " + "، ".join(c.name for c in wanted))

    # ------------------------------------------------------------ دامنه‌ها
    sales = CostCenter.objects.filter(company=company, name=SALES_UNIT).first()
    driver = JobTitle.objects.filter(company=company, name=RENTAL_DRIVER).first()
    support = support_job_titles(company)

    if not support:
        say("هشدار: هیچ قرارداد فعالی در مرکز هزینهٔ پشتیبانی نیست — "
            "دامنهٔ زنجیرهٔ مازاد ساخته نشد. اول پرسنل را وارد کنید.")
    else:
        chain_scope = [("JOB_TITLE", job.pk) for job in support]
        touched = [
            _reset_scopes(codes_new[code], chain_scope)
            for code in ("OVERTIME_SURPLUS", "MISSION_SURPLUS", "SURPLUS_FIXED", "SURPLUS_OT")
        ]
        if any(touched):
            say(f"زنجیرهٔ مازاد برای {len(support)} پست پشتیبانی: "
                + "، ".join(job.name for job in support))

    # اضافه‌کاری عادی و زنجیره‌ای نباید به یک نفر برسند — دو بار پرداخت است.
    overtime = existing.get("OVERTIME")
    if overtime:
        pairs = []
        if sales:
            pairs.append(("COST_CENTER", sales.pk))
        if driver:
            pairs.append(("JOB_TITLE", driver.pk))
        if pairs and _reset_scopes(overtime, pairs):
            say("اضافه کار عادی → فقط فروش و راننده استجاری")

    # مأموریت عادی (ضریب ۱ از جدول کارکرد) فقط برای راننده استجاری می‌ماند؛
    # پشتیبانی مأموریتش را از زنجیره می‌گیرد و فروش قلم ضریب-۲ خودش را دارد.
    mission = existing.get("MISSION")
    if mission and driver and _reset_scopes(mission, [("JOB_TITLE", driver.pk)]):
        say("حق ماموریت عادی → فقط راننده استجاری")

    if driver:
        driver_only = [
            _reset_scopes(codes_new[code], [("JOB_TITLE", driver.pk)])
            for code in ("EID", "SEVERANCE")
        ]
        if any(driver_only):
            say("عیدی و پایانکار → فقط راننده استجاری")

        leave_pay = existing.get("LEAVE_PAY")
        if leave_pay and _reset_scopes(leave_pay, [("JOB_TITLE", driver.pk)]):
            say("وجه مرخصی → فقط راننده استجاری")

    return done
