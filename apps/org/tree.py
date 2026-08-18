"""چارت سازمانی و تجمیع روی هر سطح آن.

بند ۸ سند دو چیز می‌خواهد: سطوح **سازمان → مرکز هزینه → واحد → پرسنل** با کد
مستقل برای هر گره، و گزارش‌هایی که بتوانند روی هر سطح تجمیع کنند.

«تجمیع روی یک گره» یعنی جمع همهٔ فیش‌های زیرِ آن گره، نه فقط فیش‌هایی که مستقیم
به خودش وصل‌اند: مرکز هزینهٔ «اداری» باید جمع واحدهای اداری، مالی و فنی را نشان
دهد. برای همین همه‌جا از `subtree_department_ids()` رد می‌شویم و هیچ گزارشی
`department_id=X` مستقیم فیلتر نمی‌کند.

**فیش قفل‌شده جابه‌جا نمی‌شود.** `Payslip.department` و `Payslip.cost_center`
عکس‌های لحظهٔ محاسبه‌اند؛ تجمیع از روی همان‌ها انجام می‌شود، پس اگر فردا واحدی
زیر مرکز هزینهٔ دیگری برود، فیش‌های قدیمی همان‌جا که بودند می‌مانند و فقط درخت
امروز عوض می‌شود.
"""

from decimal import Decimal

from django.db.models import Count, Sum

from apps.org.models import CostCenter, Department

ZERO = Decimal("0")

# کلیدِ گره در URL و فرم‌ها: «نوع:شناسه». یک رشته به‌جای دو پارامتر، تا فیلترِ
# گزارش و چاپ با یک <select> ساده کار کند.
NODE_KINDS = {"cc": CostCenter, "dep": Department}


def node_key(node) -> str:
    return f"{'cc' if isinstance(node, CostCenter) else 'dep'}:{node.pk}"


def parse_node_key(key):
    """«dep:12» → گره، یا None اگر کلید نامعتبر یا گره حذف شده باشد."""
    if not key or ":" not in str(key):
        return None
    kind, _, raw = str(key).partition(":")
    model = NODE_KINDS.get(kind)
    if model is None or not raw.isdigit():
        return None
    return model.objects.filter(pk=int(raw)).first()


def _children_map(company):
    """یک بار خواندن کل چارت، تا پیمایش درخت به دیتابیس برنگردد."""
    cost_centers = list(CostCenter.objects.filter(company=company))
    departments = list(
        Department.objects.filter(company=company).select_related("cost_center", "parent")
    )
    children = {}
    for node in cost_centers:
        children.setdefault(("cc", node.parent_id), []).append(node)
    for node in departments:
        if node.parent_id:
            children.setdefault(("dep", node.parent_id), []).append(node)
        else:
            children.setdefault(("cc", node.cost_center_id), []).append(node)
    for bucket in children.values():
        # مرتب‌سازی عددیِ کد: «۱۰۰» بعد از «۵۰» بیاید نه قبلش. کد غیرعددی
        # (مثل «FIN») آخر فهرست و بین خودشان الفبایی می‌نشیند.
        bucket.sort(
            key=lambda item: (
                int(item.code) if (item.code or "").isdigit() else 10**9,
                item.code or "",
                item.name,
            )
        )
    return children, cost_centers, departments


def walk(company, children=None):
    """درخت چارت را از ریشه به پایین برمی‌گرداند: (گره، عمق).

    واحدی که مرکز هزینه ندارد گم نمی‌شود؛ زیر ریشه می‌آید تا در صفحهٔ تنظیمات
    دیده و اصلاح شود. گزارشی که واحدهای بی‌مرکز را نشان ندهد، همان‌قدر خطرناک
    است که عدد اشتباه نشان دهد.
    """
    if children is None:
        children, _, _ = _children_map(company)
    rows = []

    def descend(key, depth):
        for node in children.get(key, []):
            if depth > 12:  # همان سد MAX_DEPTH مدل، برای دادهٔ حلقه‌دار
                return
            rows.append((node, depth))
            kind = "cc" if isinstance(node, CostCenter) else "dep"
            descend((kind, node.pk), depth + 1)

    descend(("cc", None), 0)
    return rows


def subtree_department_ids(node, children=None) -> list:
    """شناسهٔ همهٔ واحدهای زیر یک گره — مبنای هر فیلتر و تجمیع.

    فیش به واحد وصل است، پس تجمیع روی مرکز هزینه هم در نهایت یعنی «فیش‌های این
    فهرست از واحدها».
    """
    if children is None:
        children, _, _ = _children_map(node.company)
    if isinstance(node, Department):
        found, stack = [], [node]
        while stack:
            current = stack.pop()
            if current.pk in found:
                continue
            found.append(current.pk)
            stack.extend(children.get(("dep", current.pk), []))
        return found

    found, stack = [], [("cc", node.pk)]
    seen = set()
    while stack:
        key = stack.pop()
        if key in seen:
            continue
        seen.add(key)
        for child in children.get(key, []):
            if isinstance(child, CostCenter):
                stack.append(("cc", child.pk))
            else:
                found.append(child.pk)
                stack.append(("dep", child.pk))
    return found


def aggregate_period(period):
    """جمع فیش‌های یک دوره روی هر گره چارت، با سرشکن شدن به بالا.

    هر گره دو عدد دارد: «مستقیم» (فیش‌هایی که خودش دارد) و «تجمیعی» (خودش +
    همهٔ زیرمجموعه‌ها). عدد تجمیعی همان چیزی است که مدیر می‌خواهد و عدد مستقیم
    همان چیزی که وقتی جمع نمی‌خواند، جواب می‌دهد کجا افتاده است.
    """
    from apps.payroll.models import Payslip

    direct = {
        row["department_id"]: row
        for row in Payslip.objects.filter(period=period)
        .values("department_id")
        .annotate(
            count=Count("id"),
            gross=Sum("gross_total"),
            deductions=Sum("total_deductions"),
            net=Sum("net_payable"),
            insurance=Sum("ins_employer"),
            cost=Sum("employer_total_cost"),
        )
    }

    children, _, _ = _children_map(period.company)
    tree = walk(period.company, children)

    rows = []
    for node, depth in tree:
        ids = subtree_department_ids(node, children)
        own = direct.get(node.pk) if isinstance(node, Department) else None
        rows.append(
            {
                "node": node,
                "key": node_key(node),
                "kind": "مرکز هزینه" if isinstance(node, CostCenter) else "واحد",
                "depth": depth,
                "indent_px": depth * 26,
                "is_cost_center": isinstance(node, CostCenter),
                "own_count": (own or {}).get("count", 0),
                **_sum_of(direct, ids),
            }
        )

    # واحدی که در درخت نیامده (مثلاً بعداً حذف یا جابه‌جا شده) نباید از جمع
    # بیفتد؛ جداگانه گزارش می‌شود تا جمع ستون‌ها همیشه با جمع کل بخواند.
    orphans = set(direct) - {
        node.pk for node, _ in tree if isinstance(node, Department)
    }
    return rows, _sum_of(direct, list(orphans)), _sum_of(direct, list(direct))


def _sum_of(direct, department_ids):
    """جمع چند واحد — با کلیدهای یکسان، حتی وقتی هیچ فیشی نیست."""
    keys = ("count", "gross", "deductions", "net", "insurance", "cost")
    total = {key: (0 if key == "count" else ZERO) for key in keys}
    for department_id in department_ids:
        row = direct.get(department_id)
        if not row:
            continue
        for key in keys:
            total[key] = total[key] + (row.get(key) or (0 if key == "count" else ZERO))
    return total
