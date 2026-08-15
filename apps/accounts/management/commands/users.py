"""فهرست و مدیریت کاربران سامانه.

    python manage.py users                          # فهرست همه
    python manage.py users --staff                  # فقط کاربران مالی
    python manage.py users --promote ali --role ADMIN
    python manage.py users --deactivate old_user
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()

ROLE_ORDER = ["ADMIN", "PAYROLL", "MANAGER", "EMPLOYEE"]


class Command(BaseCommand):
    help = "فهرست کاربران سامانه و تغییر نقششان"

    def add_arguments(self, parser):
        parser.add_argument("--staff", action="store_true", help="فقط کاربران دارای دسترسی مالی")
        parser.add_argument("--promote", metavar="USERNAME", help="تغییر نقش یک کاربر")
        parser.add_argument(
            "--role", choices=ROLE_ORDER, help="نقش جدید (همراه با --promote)"
        )
        parser.add_argument("--deactivate", metavar="USERNAME", help="غیرفعال کردن کاربر")
        parser.add_argument("--activate", metavar="USERNAME", help="فعال کردن کاربر")

    def handle(self, *args, **options):
        if options["promote"]:
            return self._promote(options["promote"], options["role"])
        if options["deactivate"]:
            return self._set_active(options["deactivate"], False)
        if options["activate"]:
            return self._set_active(options["activate"], True)
        self._list(options["staff"])

    # ------------------------------------------------------------------

    def _list(self, staff_only):
        users = User.objects.all().order_by("role", "username")
        if staff_only:
            users = [u for u in users if u.is_payroll_staff]

        by_role = {}
        for user in users:
            by_role.setdefault(user.role, []).append(user)

        self.stdout.write("")
        self.stdout.write(f"  {'نام کاربری':<20} {'نام':<26} {'نقش':<22} {'وضعیت':<10} آخرین ورود")
        self.stdout.write("  " + "-" * 96)

        for role in ROLE_ORDER:
            for user in by_role.get(role, []):
                name = user.get_full_name() or "—"
                role_label = user.get_role_display()
                if user.is_superuser:
                    role_label += " ★"
                state = "فعال" if user.is_active else "غیرفعال"
                last = user.last_login.strftime("%Y-%m-%d %H:%M") if user.last_login else "هرگز"
                line = f"  {user.username:<20} {name:<26} {role_label:<22} {state:<10} {last}"
                self.stdout.write(
                    self.style.SUCCESS(line) if user.is_payroll_staff else line
                )

        self.stdout.write("")
        admins = User.objects.filter(role=User.Role.ADMIN).count()
        supers = User.objects.filter(is_superuser=True).count()
        payroll = User.objects.filter(role=User.Role.PAYROLL).count()
        managers = User.objects.filter(role=User.Role.MANAGER).count()
        employees = User.objects.filter(role=User.Role.EMPLOYEE).count()

        self.stdout.write(f"  مدیر سیستم              : {admins}")
        self.stdout.write(f"  کارشناس حقوق و دستمزد   : {payroll}")
        self.stdout.write(f"  مدیر                    : {managers}")
        self.stdout.write(f"  کارمند (پرتال)          : {employees}")
        self.stdout.write(f"  ★ ابرکاربر              : {supers}")
        self.stdout.write("")

        if admins == 0 and supers == 0:
            self.stdout.write(self.style.ERROR(
                "  هیچ مدیر سیستمی وجود ندارد. بسازید:\n"
                "    python manage.py createsuperuser\n"
            ))
        elif admins + payroll == 1:
            self.stdout.write(self.style.WARNING(
                "  فقط یک نفر دسترسی مالی دارد. اگر رمزش را گم کند یا مرخصی برود،\n"
                "  کسی به سامانه دسترسی نخواهد داشت. یک نفر دوم تعریف کنید.\n"
            ))

    def _promote(self, username, role):
        if not role:
            self.stdout.write(self.style.ERROR("همراه --promote باید --role هم بدهید."))
            return
        user = User.objects.filter(username=username).first()
        if user is None:
            self.stdout.write(self.style.ERROR(f"کاربری با نام «{username}» پیدا نشد."))
            return
        old = user.get_role_display()
        user.role = role
        user.save(update_fields=["role"])
        self.stdout.write(self.style.SUCCESS(
            f"نقش {username} از «{old}» به «{user.get_role_display()}» تغییر کرد."
        ))

    def _set_active(self, username, active):
        user = User.objects.filter(username=username).first()
        if user is None:
            self.stdout.write(self.style.ERROR(f"کاربری با نام «{username}» پیدا نشد."))
            return
        if not active and user.is_superuser:
            remaining = User.objects.filter(is_superuser=True, is_active=True).exclude(
                pk=user.pk
            ).count()
            if remaining == 0:
                self.stdout.write(self.style.ERROR(
                    "این تنها ابرکاربر فعال است و غیرفعال کردنش دسترسی به سامانه را می‌بندد."
                ))
                return
        user.is_active = active
        user.save(update_fields=["is_active"])
        self.stdout.write(self.style.SUCCESS(
            f"{username} {'فعال' if active else 'غیرفعال'} شد."
        ))
