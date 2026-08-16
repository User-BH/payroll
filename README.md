# سامانه حقوق و دستمزد — تامین کالا باختر

نسخهٔ دمو. Django + HTMX + Alpine.js + MySQL، تمام‌فارسی و RTL.

> **هشدار مهم:** همهٔ اعداد قانونی (حداقل دستمزد، حق مسکن، بن، پلکان مالیات، نرخ بیمه)
> **داده نمونه** هستند و باید پیش از استفادهٔ واقعی با بخشنامه‌های سال تطبیق داده شوند.
> جای همه‌شان در «تنظیمات سال مالی» است و هیچ‌کدام در کد نوشته نشده‌اند.

---

## دیتابیس: فقط MySQL 8

سامانه روی هیچ موتور دیگری اجرا نمی‌شود — نه در توسعه، نه در تولید. دلیلش این است
که رفتار دیتابیس دقیقاً در جاهایی که برای حقوق و دستمزد حیاتی است بین موتورها فرق
دارد: پشتیبانی از قیدهای یکتایی، دقت `DECIMAL`، حالت `STRICT` و کولیشن فارسی. اگر
روی یک موتور توسعه بدهیم و روی موتور دیگری اجرا کنیم، این تفاوت‌ها را دیر و روی
دادهٔ واقعی حقوق کشف می‌کنیم.

> نمونهٔ واقعی همین موضوع: قید «هر پرسنل در هر دوره فقط یک فیش اصلی» ابتدا با
> `UniqueConstraint(condition=...)` نوشته شده بود. MySQL ایندکس شرطی ندارد و جنگو
> چنین قیدی را **بی‌صدا نادیده می‌گیرد**. حالا با ستون `revision` نوشته شده تا قید
> واقعاً در دیتابیس اعمال شود.

## اجرای محلی

```bash
docker run -d --name payroll-mysql \
  -e MYSQL_ROOT_PASSWORD=rootpw -e MYSQL_DATABASE=payroll \
  -e MYSQL_USER=payroll -e MYSQL_PASSWORD=payrollpw \
  -p 3307:3306 mysql:8 \
  --character-set-server=utf8mb4 --collation-server=utf8mb4_persian_ci
```

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # DB_PORT=3307 و DB_PASSWORD=payrollpw
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

سپس <http://127.0.0.1:8000>

### حساب‌های دمو

| نقش | آدرس | نام کاربری | رمز |
|---|---|---|---|
| کارشناس حقوق و دستمزد | `/login/` | `ali` | `demo1234` |
| مدیر سیستم | `/login/` | `admin` | `demo1234` |
| پرسنل (پرتال) | `/portal/login/` | `1001` | `demo1234` |

دادهٔ نمونه: ۱۴۶ پرسنل، دو دورهٔ **اسفند ۱۴۰۴** (قفل‌شده) و **فروردین ۱۴۰۵**
(پیش‌نویس، ۱۴۲ کارکرد تأییدشده از ۱۴۶). برای ساخت دوباره: `seed_demo --reset`.

---

## راه‌اندازی روی سرور لینوکس با MySQL

### ۱. پیش‌نیازها

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential pkg-config \
                    default-libmysqlclient-dev mysql-server nginx
```

### ۲. ساخت دیتابیس

کولیشن `utf8mb4_persian_ci` برای مرتب‌سازی درست فارسی لازم است:

```bash
sudo mysql -e "CREATE DATABASE payroll CHARACTER SET utf8mb4 COLLATE utf8mb4_persian_ci;"
sudo mysql -e "CREATE USER 'payroll'@'localhost' IDENTIFIED BY 'CHANGE_ME';"
sudo mysql -e "GRANT ALL PRIVILEGES ON payroll.* TO 'payroll'@'localhost'; FLUSH PRIVILEGES;"
```

### ۳. گرفتن کد از گیت‌هاب

```bash
sudo mkdir -p /srv/payroll && sudo chown $USER /srv/payroll
git clone https://github.com/User-BH/payroll.git /srv/payroll
cd /srv/payroll
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### به‌روزرسانی‌های بعدی

```bash
sudo bash /srv/payroll/deploy/update.sh
```

این اسکریپت به ترتیب: **بکاپ دیتابیس و فایل‌های آپلودی** → `git pull` →
نصب وابستگی‌ها → `migrate` → `collectstatic` → تنظیم دسترسی پوشه `media` →
ری‌استارت سرویس → `doctor`.

بکاپ اول از همه گرفته می‌شود چون `migrate` برگشت‌پذیر نیست. اگر هر قدم شکست
بخورد، اسکریپت همان‌جا متوقف می‌شود و مسیر فایل بکاپ را برای بازگردانی چاپ
می‌کند. ۱۴ بکاپ آخر نگه داشته می‌شوند.

اگر روی سرور فایلی را دستی تغییر داده باشید، اسکریپت قبل از `git pull` متوقف
می‌شود و تغییرات را نشان می‌دهد تا ناخواسته پاک نشوند.

### ۴. تنظیم `.env`

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(50))"   # SECRET_KEY
```

```ini
SECRET_KEY=<کلید تولیدشده>
DEBUG=0
ALLOWED_HOSTS=tamin.justup.ir
CSRF_TRUSTED_ORIGINS=http://tamin.justup.ir

# تا وقتی SSL نصب نشده باید 0 بماند، وگرنه ورود کار نمی‌کند
SECURE_COOKIES=0

DB_ENGINE=mysql
DB_NAME=payroll
DB_USER=payroll
DB_PASSWORD=CHANGE_ME
DB_HOST=127.0.0.1
DB_PORT=3306
```

### ۵. مهاجرت و فایل‌های استاتیک

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser        # یا seed_demo برای دادهٔ نمونه
```

> `migrate` فقط **جدول‌ها** را می‌سازد و هیچ کاربری ایجاد نمی‌کند. اگر این قدم را
> رد کنید، سایت بالا می‌آید ولی هیچ حسابی برای ورود وجود ندارد.

### بررسی سلامت نصب

هر وقت چیزی کار نکرد، اول این را اجرا کنید:

```bash
python manage.py doctor
```

اتصال دیتابیس، کولیشن، تعداد جدول‌ها، وجود کاربر، `DEBUG`، `ALLOWED_HOSTS`،
`SECURE_COOKIES`، `SECRET_KEY` و `collectstatic` را بررسی می‌کند و برای هر ایراد
دقیقاً می‌گوید چه دستوری را اجرا کنید.

### ۶. سرویس systemd

فایل آماده در `deploy/systemd/payroll.service` است:

```bash
sudo cp deploy/systemd/payroll.service /etc/systemd/system/
sudo chown -R www-data:www-data /srv/payroll
sudo systemctl daemon-reload && sudo systemctl enable --now payroll
sudo systemctl status payroll --no-pager
```

### ۷. nginx

فایل آماده در `deploy/nginx/payroll.conf` است:

```bash
sudo cp deploy/nginx/payroll.conf /etc/nginx/sites-available/payroll
sudo ln -sf /etc/nginx/sites-available/payroll /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

nginx باید بتواند وارد مسیر شود تا فایل‌های استاتیک را بخواند:

```bash
sudo chmod o+x /srv /srv/payroll
```

**سایت `default` را کورکورانه پاک نکنید.** اگر روی این سرور سایت دیگری هم هست،
حذفش آن‌ها را می‌خواباند. کانفیگ ما با `server_name` کار می‌کند و با بقیه‌ی
سایت‌ها تداخلی ندارد. `default` را فقط وقتی غیرفعال کنید که مطمئنید سایت دیگری
به آن وابسته نیست:

```bash
sudo ls -l /etc/nginx/sites-enabled/          # اول ببینید چه چیزی فعال است
sudo rm /etc/nginx/sites-enabled/default      # فقط در صورت اطمینان
```

اگر دامنه به سایت اشتباهی می‌رسد، ببینید nginx کدام بلوک را برای آن انتخاب می‌کند:

```bash
sudo nginx -T | grep -n "server_name"
```

### SSL (توصیه‌شده)

سامانه دادهٔ حقوق دارد؛ روی HTTP رمز عبور به‌صورت متن ساده در شبکه می‌رود.

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d tamin.justup.ir
```

بعد از نصب گواهی، در `.env` مقدار `SECURE_COOKIES=1` و
`CSRF_TRUSTED_ORIGINS=https://tamin.justup.ir` را بگذارید و سرویس را ری‌استارت کنید.

### ۸. بکاپ روزانه

بکاپ بدون تست بازیابی، بکاپ نیست:

```bash
mysqldump --single-transaction --default-character-set=utf8mb4 payroll \
  | gzip > /var/backups/payroll-$(date +%F).sql.gz
```

---

## ساختار پروژه

```
config/                 تنظیمات و مسیرها
apps/
  accounts/             کاربر سفارشی، نقش‌ها، دسترسی
  org/                  شرکت، واحد، مرکز هزینه، پست سازمانی
  employees/            پرسنل، قرارداد تاریخ‌دار، تحت تکفل، حساب بانکی
  payroll_config/       سال مالی، پارامترهای قانونی، پلکان مالیات، اقلام حقوقی
  attendance/           کارکرد ماهانه
  payroll/              دوره، موتور محاسبه، فیش، گزارش‌ها
    engine/
      context.py        بستر محاسبه یک فیش
      rules.py          قواعد محاسبه (منطق واقعی اینجاست)
      runner.py         اجرای دوره — سه پاس، داخل یک transaction
  loans/                وام و اقساط
  portal/               پرتال کارکنان
templates/  static/     رابط کاربری RTL — فونت، HTMX و Alpine همگی لوکال
```

هیچ فایلی از CDN بارگذاری نمی‌شود؛ فونت وزیرمتن، HTMX و Alpine داخل `static/` هستند.

---

## سه اصل معماری

۱. **هیچ داده‌ای «جاری» نیست.** حقوق پایه روی `EmploymentContract` تاریخ‌دار است، نه روی
   `Employee`. هر ترفیع یا تغییر واحد = یک قرارداد جدید با `effective_from` جدید.

۲. **فیش قفل‌شده تغییرناپذیر است.** لحظهٔ محاسبه، کل پارامترهای قانونی داخل
   `Payslip.params_snapshot` کپی می‌شوند. `Payslip.save()` نوشتن روی فیشِ دورهٔ قفل‌شده
   را رد می‌کند.

۳. **هر عدد توضیح خودش را دارد.** `PayslipLine.explanation` مثلاً:
   «اضافه‌کاری: ۳۳ ساعت × ۱٬۱۱۴٬۱۴۳ ریال مزد ساعتی × ۱٫۴».

### موتور محاسبه

منطق در کد است، نه در دیتابیس. هر قلم حقوقی به یک قاعدهٔ ثبت‌شده در
`apps/payroll/engine/rules.py` وصل می‌شود (`engine_rule_key`)؛ دیتابیس فقط ضریب،
ترتیب و شمول بیمه/مالیات را نگه می‌دارد.

اجرا سه پاس دارد: **مزایا → کسور → هزینهٔ کارفرما**. دلیلش این است که
**مبنای بیمه و مبنای مالیات دو عدد جدا هستند**؛ اگر بیمه و مالیات هم‌زمان با مزایا
محاسبه می‌شدند، ترتیب اقلام روی نتیجه اثر می‌گذاشت. در دادهٔ نمونه، پورسانت فروش
مشمول مالیات و معاف از بیمه است و همین تفاوت را نشان می‌دهد.

افزودن یک قلم جدید:

```python
@rule("my_rule", "عنوان")
def my_rule(ctx, component):
    return LineResult(
        amount=...,
        base_amount=..., quantity=..., rate=...,
        explanation="…",
    ).rounded()
```

---

## آنچه در این نسخه هست

داشبورد · پرسنل و تاریخچهٔ قرارداد · دوره و ماشین حالت آن · کارکرد ماهانه با ویرایش
درجا (HTMX) · موتور محاسبه · فیش با ریز محاسبات و نسخهٔ چاپی · اقلام حقوقی ·
تنظیمات سال مالی · گزارش بیمه/مالیات/بانک با خروجی اکسل · پرتال کارکنان.

### افزودن پرسنل

فرم افزودن پرسنل فقط **نوع قرارداد** را می‌پرسد، نه ریز جزئیات قرارداد را. با
ذخیره، یک قرارداد **فعال** از تاریخ استخدام ساخته می‌شود تا پرسنل بلافاصله در
فهرست فعال باشد و بشود رویش کلیک کرد، ویرایشش کرد و خروجش را ثبت کرد.

واحد، مرکز هزینه و پست سازمانی از اولین مقدارِ ساختار سازمانی پر می‌شوند و
**حقوق پایه صفر** می‌ماند — عددِ حدسی برای حقوق، اشتباهی است که تا فیش پنهان
می‌ماند، ولی صفر در همان صفحهٔ پرسنل با هشدار دیده می‌شود. تکمیلش از دکمهٔ
«ویرایش قرارداد» انجام می‌شود.

اگر دورهٔ پیش‌نویسی باز باشد، همان‌جا **کارکرد ماهانه** هم قابل ثبت است. بعد از
ثبت هم، پنل «کارکرد ماهانه» در صفحهٔ خود پرسنل اجازهٔ ورود دستی می‌دهد — بدون
باز کردن جدول کارکرد کل دوره. هر دو مسیر روی همان یک رکورد `Timesheet` می‌نویسند.

## آنچه نیست (فازهای بعد)

فایل DSK تأمین اجتماعی و ثبت کد رهگیری · ورود کارکرد از فایل اکسل و دستگاه حضور و
غیاب · عیدی، سنوات و تسویه‌حساب · فیش اصلاحی · درخواست مرخصی · احراز هویت دومرحله‌ای.

## دو نکته‌ای که باید با حسابدار شرکت تأیید شود

۱. **کسر بیمهٔ سهم کارگر از درآمد مشمول مالیات** — پرچم
   `LegalParameter.deduct_insurance_from_tax_base` (فعلاً فعال). مستقیماً روی مبلغ
   مالیات اثر دارد.

۲. **همپوشانی قراردادها** — MySQL معادل `EXCLUDE` constraint ندارد، پس این قاعده در
   `EmploymentContract.clean()` پیاده شده است. هر مسیر جدیدی که قرارداد می‌سازد باید
   حتماً `full_clean()` را صدا بزند.
