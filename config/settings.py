"""
تنظیمات سامانه حقوق و دستمزد — تامین کالا باختر

همه‌ی مقادیر محیطی از فایل .env خوانده می‌شوند (نمونه: .env.example).
دیتابیس پیش‌فرض SQLite است تا دمو بدون هیچ پیش‌نیازی بالا بیاید؛
با DB_ENGINE=mysql به MySQL سوییچ می‌کند.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_list(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# ---------------------------------------------------------------- core

SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-key-please-change-on-server")
DEBUG = os.getenv("DEBUG", "1") == "1"
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "127.0.0.1,localhost") or ["*"]
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000"
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # اپ‌های سامانه
    "apps.accounts",
    "apps.org",
    "apps.employees",
    "apps.payroll_config",
    "apps.attendance",
    "apps.payroll",
    "apps.loans",
    "apps.portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.payroll.context_processors.current_period",
            ],
        },
    },
]


# ---------------------------------------------------------------- database

if os.getenv("DB_ENGINE", "sqlite") == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DB_NAME", "payroll"),
            "USER": os.getenv("DB_USER", "payroll"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
                # بدون STRICT_TRANS_TABLES مای‌اس‌کیوال داده نامعتبر را بی‌صدا برش می‌دهد
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------- auth

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# کوکی امن فقط روی HTTPS کار می‌کند. اگر سایت هنوز روی HTTP بالا می‌آید و این
# گزینه روشن باشد، مرورگر کوکی نشست را نمی‌فرستد و ورود بی‌هیچ پیام خطایی شکست
# می‌خورد. پس صریح و محیطی کنترل می‌شود، نه ضمنی از روی DEBUG.
SECURE_COOKIES = os.getenv("SECURE_COOKIES", "0" if DEBUG else "1") == "1"

if SECURE_COOKIES:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
    # پشت nginx، تشخیص درست پروتکل برای ساخت لینک‌های مطلق
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# ---------------------------------------------------------------- locale

LANGUAGE_CODE = "fa"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True
# ارقام را خودمان با فیلترهای قالب فارسی می‌کنیم؛ فرمت‌بندی خودکار جنگو خاموش
USE_THOUSAND_SEPARATOR = False


# ---------------------------------------------------------------- static

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"


# ---------------------------------------------------------------- payroll

# واحد گرد کردن نهایی مبالغ (ریال). در LegalParameter هر سال قابل تغییر است.
PAYROLL_ENGINE_VERSION = "1.0.0"
