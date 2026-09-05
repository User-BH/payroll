import io
import os
import re

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.core.management import call_command  # noqa: E402
from django.db import transaction  # noqa: E402

from apps.payroll_config.models import SalaryComponent  # noqa: E402

XL = r"C:\Users\A.BH\Desktop\حقوق ومزایا\تبریز\1405.xlsx"


def backtest():
    import subprocess
    out = []
    for m in ("تیر 1405", "مرداد 1405"):
        r = subprocess.run(
            [r".venv\Scripts\python.exe", "tools/compare_excel_platform.py", XL, m],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        for ln in (r.stdout or "").splitlines():
            if ln.startswith("= خالص"):
                nums = re.findall(r"\d+", ln.replace(",", ""))
                out.append(f"{m}: {nums[0]}/{int(nums[0]) + int(nums[1])}")
    return " · ".join(out)


print("وضع فعلی           →", backtest())

for label, mutate in [
    ("is_commission روشن", lambda: SalaryComponent.objects.filter(
        code__in=["COMM_1", "COMM_2", "COMM_3"]).update(is_commission=True)),
    ("COMM_1 نقش ADD",     lambda: SalaryComponent.objects.filter(
        code="COMM_1").update(allocation_role="ADD")),
]:
    try:
        with transaction.atomic():
            mutate()
            print(f"{label:18} →", backtest())
            raise RuntimeError
    except RuntimeError:
        pass

print("\nپس از بازگشت       →", backtest())
