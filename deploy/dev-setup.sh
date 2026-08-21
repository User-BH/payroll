#!/usr/bin/env bash
#
# ساخت محیط توسعه‌ای که **دقیقاً مثل سرور** باشد، از روی بکاپ دیتابیس سرور.
#
#   bash deploy/dev-setup.sh /path/to/payroll.sql
#
# چرا ارزش دارد: باگی که کاربر روی سرور می‌بیند اغلب از داده می‌آید نه از کد —
# یک دامنه شمول اشتباه، یک پارامتر صفر، یک قلم وصل‌نشده. با sqlite و دادهٔ
# نمونه، هیچ‌کدام از این‌ها دیده نمی‌شوند. با کپی دیتابیس سرور، همان لحظهٔ اول
# دیده می‌شوند.
#
# این اسکریپت هیچ‌وقت به سرور وصل نمی‌شود و چیزی روی سرور تغییر نمی‌دهد.

set -euo pipefail

DUMP="${1:-}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$APP_DIR/.venv"
DB_NAME="${DB_NAME:-payroll_dev}"
DB_USER="${DB_USER:-payroll}"
DB_PASSWORD="${DB_PASSWORD:-devpass}"

say() { printf '\n\033[1;31m==> %s\033[0m\n' "$1"; }

if [ -z "$DUMP" ] || [ ! -f "$DUMP" ]; then
  echo "استفاده: bash deploy/dev-setup.sh /path/to/payroll.sql[.gz]"
  echo
  echo "بکاپ را از سرور بگیرید:"
  echo "  mysqldump --single-transaction --default-character-set=utf8mb4 \\"
  echo "    -upayroll -p payroll | gzip > payroll.sql.gz"
  exit 1
fi

# ---------------------------------------------------------------- نسخه‌ها
say "بررسی نسخه‌ها"
python3 --version
mysqld --version 2>/dev/null || mysql --version
echo "    سرور: Python 3.12.3 · MySQL 8.0.46 · Ubuntu 24.04"

# ---------------------------------------------------------------- دیتابیس
say "ساخت دیتابیس $DB_NAME"
# کولیشن باید persian_ci باشد وگرنه مرتب‌سازی و جستجوی فارسی با سرور فرق می‌کند
mysql -uroot <<SQL
DROP DATABASE IF EXISTS \`$DB_NAME\`;
CREATE DATABASE \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_persian_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';
FLUSH PRIVILEGES;
SQL

say "بارگذاری بکاپ سرور"
case "$DUMP" in
  *.gz) gunzip < "$DUMP" | mysql -uroot "$DB_NAME" ;;
  *)    mysql -uroot "$DB_NAME" < "$DUMP" ;;
esac
mysql -uroot "$DB_NAME" -N -B -e "SELECT CONCAT('    ', COUNT(*), ' جدول بارگذاری شد') \
  FROM information_schema.tables WHERE table_schema='$DB_NAME';"

# ---------------------------------------------------------------- پایتون
if [ ! -d "$VENV" ]; then
  say "ساخت venv"
  python3 -m venv "$VENV"
fi
say "نصب وابستگی‌ها"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# ---------------------------------------------------------------- تنظیمات
if [ ! -f "$APP_DIR/.env" ]; then
  say "ساخت .env توسعه"
  cat > "$APP_DIR/.env" <<ENV
SECRET_KEY=$("$VENV/bin/python" -c "import secrets; print(secrets.token_urlsafe(50))")
DEBUG=1
ALLOWED_HOSTS=*
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
SECURE_COOKIES=0
DB_ENGINE=mysql
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_HOST=127.0.0.1
DB_PORT=3306
ENV
else
  echo "    .env از قبل هست — دست نخورد. DB_NAME آن باید $DB_NAME باشد."
fi

# ---------------------------------------------------------------- بررسی
say "مهاجرت‌های عقب‌مانده نسبت به کد"
"$VENV/bin/python" "$APP_DIR/manage.py" showmigrations 2>/dev/null | grep -B1 "\[ \]" || echo "    هیچ — دیتابیس با کد هماهنگ است"

say "بررسی سلامت"
"$VENV/bin/python" "$APP_DIR/manage.py" doctor || true

cat <<'DONE'

آماده است. قدم‌های بعدی:

  # اعمال مهاجرت‌های تازه روی کپی محلی (سرور دست نمی‌خورد)
  .venv/bin/python manage.py migrate

  # یک کاربر برای ورود (رمز کاربران سرور را نداریم)
  .venv/bin/python manage.py createsuperuser

  # اجرا
  .venv/bin/python manage.py runserver

هشدار: این کپی دادهٔ واقعی پرسنل است. روی همین ماشین بماند و در گیت نرود.
DONE
