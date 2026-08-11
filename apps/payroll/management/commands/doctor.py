"""بررسی سلامت نصب — چرا سامانه بالا نمی‌آید یا ورود کار نمی‌کند.

    python manage.py doctor

هر چیزی که معمولاً بعد از نصب روی سرور اشتباه می‌شود را یک‌جا گزارش می‌دهد.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection

OK = "✓"
BAD = "✗"
WARN = "!"


class Command(BaseCommand):
    help = "بررسی سلامت نصب: دیتابیس، کاربران، پیکربندی و فایل‌های استاتیک"

    def handle(self, *args, **options):
        self.problems = []
        self._database()
        self._users()
        self._config()
        self._static()
        self._verdict()

    # ------------------------------------------------------------------

    def line(self, mark, label, value=""):
        style = self.style.SUCCESS if mark == OK else (
            self.style.ERROR if mark == BAD else self.style.WARNING
        )
        self.stdout.write(f"  {style(mark)} {label}" + (f": {value}" if value else ""))

    def head(self, title):
        self.stdout.write(f"\n{title}")

    # ------------------------------------------------------------------

    def _database(self):
        self.head("دیتابیس")
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT VERSION()")
                version = cur.fetchone()[0]
                cur.execute(
                    "SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME "
                    "FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = DATABASE()"
                )
                charset, collation = cur.fetchone()
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE()"
                )
                tables = cur.fetchone()[0]
        except Exception as exc:
            self.line(BAD, "اتصال برقرار نشد", str(exc)[:120])
            self.problems.append(
                "به دیتابیس وصل نمی‌شود. مقادیر DB_* در فایل .env را چک کنید "
                "و مطمئن شوید سرویس mysql بالاست."
            )
            return

        self.line(OK, "اتصال", f"MySQL {version} — دیتابیس {connection.settings_dict['NAME']}")

        if charset == "utf8mb4":
            self.line(OK, "کاراکترست", f"{charset} / {collation}")
        else:
            self.line(BAD, "کاراکترست", f"{charset} / {collation}")
            self.problems.append(
                "دیتابیس utf8mb4 نیست؛ متن فارسی خراب ذخیره می‌شود. دیتابیس را با "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_persian_ci بسازید."
            )

        if tables >= 20:
            self.line(OK, "جدول‌ها", f"{tables} جدول")
        else:
            self.line(BAD, "جدول‌ها", f"فقط {tables} جدول")
            self.problems.append("مهاجرت‌ها اجرا نشده‌اند: python manage.py migrate")

    def _users(self):
        self.head("کاربران")
        User = get_user_model()
        try:
            total = User.objects.count()
        except Exception as exc:
            self.line(BAD, "خواندن جدول کاربران", str(exc)[:120])
            return

        if total == 0:
            self.line(BAD, "هیچ کاربری در دیتابیس نیست")
            self.problems.append(
                "دیتابیس خالی است، برای همین ورود ممکن نیست. یکی را اجرا کنید:\n"
                "      python manage.py seed_demo        (داده نمونه + کاربر ali)\n"
                "      python manage.py createsuperuser  (شروع خالی)"
            )
            return

        self.line(OK, "تعداد کل", str(total))
        staff = User.objects.exclude(role=User.Role.EMPLOYEE)
        if staff.exists():
            for user in staff[:10]:
                self.line(OK, "دسترسی مالی", f"{user.username} ({user.get_role_display()})")
        else:
            self.line(BAD, "هیچ کاربری دسترسی بخش مالی ندارد")
            self.problems.append(
                "کاربران فقط نقش «کارمند» دارند و به بخش مالی راه ندارند. "
                "یک کاربر با createsuperuser بسازید."
            )

    def _config(self):
        self.head("پیکربندی")
        debug = settings.DEBUG
        self.line(WARN if debug else OK, "DEBUG", str(debug))
        if debug:
            self.problems.append("روی سرور DEBUG باید 0 باشد.")

        hosts = settings.ALLOWED_HOSTS
        self.line(OK if hosts else BAD, "ALLOWED_HOSTS", ", ".join(hosts) or "خالی")

        origins = getattr(settings, "CSRF_TRUSTED_ORIGINS", [])
        self.line(OK if origins else WARN, "CSRF_TRUSTED_ORIGINS", ", ".join(origins) or "خالی")

        secure = getattr(settings, "SECURE_COOKIES", False)
        https_origins = [o for o in origins if o.startswith("https://")]
        if secure and not https_origins:
            self.line(BAD, "SECURE_COOKIES", "روشن، ولی دامنه روی HTTPS نیست")
            self.problems.append(
                "SECURE_COOKIES روشن است ولی سایت روی HTTP بالا می‌آید. مرورگر کوکی "
                "نشست را نمی‌فرستد و ورود بدون هیچ پیام خطایی شکست می‌خورد.\n"
                "      در .env بگذارید: SECURE_COOKIES=0\n"
                "      (بعد از نصب SSL دوباره 1 کنید)"
            )
        else:
            self.line(OK, "SECURE_COOKIES", str(secure))

        if "insecure" in settings.SECRET_KEY or settings.SECRET_KEY == "local-test-key":
            self.line(BAD, "SECRET_KEY", "هنوز مقدار پیش‌فرض است")
            self.problems.append(
                "SECRET_KEY را عوض کنید:\n"
                '      python -c "import secrets; print(secrets.token_urlsafe(50))"'
            )
        else:
            self.line(OK, "SECRET_KEY", "تنظیم شده")

    def _static(self):
        self.head("فایل‌های استاتیک")
        root = settings.STATIC_ROOT
        css = root / "css" / "app.css" if root else None
        if settings.DEBUG:
            self.line(OK, "در حالت DEBUG از پوشه static سرو می‌شود")
        elif css and css.exists():
            self.line(OK, "collectstatic", f"انجام شده — {root}")
        else:
            self.line(BAD, "collectstatic", "اجرا نشده")
            self.problems.append(
                "صفحه بدون CSS بالا می‌آید. اجرا کنید:\n"
                "      python manage.py collectstatic --noinput"
            )

    def _verdict(self):
        self.stdout.write("")
        if not self.problems:
            self.stdout.write(self.style.SUCCESS("همه‌چیز سالم است."))
            return
        self.stdout.write(self.style.ERROR(f"{len(self.problems)} مورد نیاز به رسیدگی دارد:\n"))
        for index, problem in enumerate(self.problems, start=1):
            self.stdout.write(f"  {index}) {problem}\n")
