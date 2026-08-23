#!/usr/bin/env bash
#
# به‌روزرسانی سامانه روی سرور.
#
#   sudo bash /srv/payroll/deploy/update.sh
#
# پیش از هر migrate بکاپ می‌گیرد، چون migrate برگشت‌پذیر نیست و روی داده واقعی
# حقوق اجرا می‌شود. اگر هر قدم شکست بخورد، اسکریپت همان‌جا متوقف می‌شود.

set -euo pipefail

APP_DIR="/srv/payroll"
VENV="$APP_DIR/.venv"
BACKUP_DIR="/var/backups/payroll"
SERVICE="payroll"
RUN_USER="www-data"

say() { printf '\n\033[1;31m==> %s\033[0m\n' "$1"; }

cd "$APP_DIR"

# ---------------------------------------------------------------- ۱) بکاپ
say "بکاپ دیتابیس"
mkdir -p "$BACKUP_DIR"
DB_NAME=$(grep -E '^DB_NAME=' .env | cut -d= -f2-)
DB_USER=$(grep -E '^DB_USER=' .env | cut -d= -f2-)
DB_PASSWORD=$(grep -E '^DB_PASSWORD=' .env | cut -d= -f2-)
STAMP=$(date +%F-%H%M%S)
BACKUP_FILE="$BACKUP_DIR/payroll-$STAMP.sql.gz"

mysqldump --single-transaction --default-character-set=utf8mb4 \
  -u"$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" | gzip > "$BACKUP_FILE"
echo "    $BACKUP_FILE  ($(du -h "$BACKUP_FILE" | cut -f1))"

# بکاپ فایل‌های آپلودی (امضاها و خروجی‌های قانونی)
if [ -d "$APP_DIR/media" ]; then
  tar -czf "$BACKUP_DIR/media-$STAMP.tar.gz" -C "$APP_DIR" media
  echo "    $BACKUP_DIR/media-$STAMP.tar.gz"
fi

# ---------------------------------------------------------------- ۲) کد
say "گرفتن آخرین نسخه کد"
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "    هشدار: روی سرور تغییر محلی وجود دارد. ابتدا آن را بررسی کنید:"
  git status --short
  exit 1
fi
git pull --ff-only

# ---------------------------------------------------------------- ۳) وابستگی‌ها
say "نصب وابستگی‌ها"
"$VENV/bin/pip" install --quiet -r requirements.txt

# بررسی پیکربندی پیش از دست زدن به دیتابیس. اگر وابستگی‌ای جا افتاده باشد یا
# تنظیمات ایراد داشته باشد، همین‌جا معلوم می‌شود — نه وسط migrate.
say "بررسی پیکربندی"
"$VENV/bin/python" manage.py check

# اگر مدلی تغییر کرده ولی مهاجرتش ساخته نشده، migrate آن را بی‌صدا نادیده
# می‌گیرد و دیتابیس با کد ناهماهنگ می‌ماند. اینجا صریح متوقف می‌شویم.
if ! "$VENV/bin/python" manage.py makemigrations --check --dry-run >/dev/null 2>&1; then
  echo
  echo "    خطا: مدل‌هایی تغییر کرده‌اند که مهاجرتشان ساخته نشده."
  echo "    این یعنی نسخه‌ای که pull شد ناقص است. جزئیات:"
  "$VENV/bin/python" manage.py makemigrations --check --dry-run 2>&1 | sed 's/^/      /'
  echo
  echo "    دیتابیس دست نخورد. به توسعه‌دهنده اطلاع دهید."
  exit 1
fi

# ---------------------------------------------------------------- ۴) دیتابیس
say "اعمال مهاجرت‌های دیتابیس"
"$VENV/bin/python" manage.py migrate --noinput

# ------------------------------------------------- ۴٫۵) پیکربندی شرکت
# پیکربندیِ محاسبه (زنجیرهٔ مازاد، جذب پورسانت، گروه راننده استجاری، رنگ اقلام)
# داده است نه ساختار، پس migrate آن را نمی‌آورد. تا پیش از این باید دستی از
# پنل ساخته می‌شد و روی سرور ساخته نشده بود — یعنی همان اعدادی که بک‌تست وعده
# داده بود از دستورهای خودش درنمی‌آمد.
#
# دستور idempotent است: اگر همه‌چیز سر جایش باشد چیزی عوض نمی‌کند و همان را
# می‌گوید.
say "پیکربندی اقلام حقوقی شرکت"
"$VENV/bin/python" manage.py configure_1405

# ---------------------------------------------------------------- ۵) فایل‌ها
say "جمع‌آوری فایل‌های استاتیک"
"$VENV/bin/python" manage.py collectstatic --noinput

# پوشه media باید وجود داشته باشد و سرویس بتواند در آن بنویسد
# (امضای پرسنل و فایل‌های خروجی قانونی اینجا ذخیره می‌شوند)
mkdir -p "$APP_DIR/media/signatures" "$APP_DIR/media/exports"
chown -R "$RUN_USER:$RUN_USER" "$APP_DIR/media" "$APP_DIR/staticfiles"
chmod o+x /srv "$APP_DIR"

# ---------------------------------------------------------------- ۶) سرویس
say "راه‌اندازی مجدد سرویس"
systemctl restart "$SERVICE"
sleep 2
systemctl is-active --quiet "$SERVICE" && echo "    سرویس فعال است" || {
  echo "    سرویس بالا نیامد. لاگ:"
  journalctl -u "$SERVICE" -n 30 --no-pager
  exit 1
}

# اگر کانفیگ nginx در مخزن تغییر کرده بود، اعلام کن (خودکار کپی نمی‌کنیم)
if ! diff -q "$APP_DIR/deploy/nginx/payroll.conf" /etc/nginx/sites-available/payroll >/dev/null 2>&1; then
  echo "    توجه: کانفیگ nginx در مخزن با نسخه نصب‌شده فرق دارد."
  echo "          برای اعمال:  sudo cp deploy/nginx/payroll.conf /etc/nginx/sites-available/payroll"
  echo "                       sudo nginx -t && sudo systemctl reload nginx"
fi

# ---------------------------------------------------------------- ۷) بررسی
say "بررسی سلامت"
"$VENV/bin/python" manage.py doctor

# نگه داشتن ۱۴ بکاپ آخر
find "$BACKUP_DIR" -name 'payroll-*.sql.gz' -type f -printf '%T@ %p\n' \
  | sort -rn | tail -n +15 | cut -d' ' -f2- | xargs -r rm --

say "به‌روزرسانی تمام شد"
echo "    برخی تغییرها به ورود دستی داده از پنل نیاز دارند و با این اسکریپت"
echo "    کامل نمی‌شوند. فهرستشان:  docs/DEPLOY-STEPS.md"
echo
echo "    اگر چیزی خراب شد، بازگردانی دیتابیس:"
echo "    gunzip < $BACKUP_FILE | mysql -u$DB_USER -p $DB_NAME"
