"""کارتابل مرخصی — ثبت مستقیم توسط کارگزینی."""

from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import can_edit_required, payroll_staff_required
from apps.attendance.leave import DEFAULT_DAY_MINUTES
from apps.attendance.leave_desk import (
    minutes_from_parts,
    periods_covering,
    sync_period,
    sync_record,
)
from apps.attendance.models import LeaveRecord
from apps.employees.models import Employee
from apps.payroll.form_fields import JalaliDateField
from apps.payroll.models import PayrollPeriod


class LeaveRecordForm(forms.ModelForm):
    """مدت به‌صورت روز/ساعت/دقیقه گرفته می‌شود و به دقیقه ذخیره می‌شود.

    ترتیب سه ورودی از راست: دقیقه، ساعت، روز — همان چیدمانی که در کارکرد
    ماهانه استفاده می‌شود.
    """

    class Meta:
        model = LeaveRecord
        fields = ["employee", "kind", "start_date", "end_date", "reason"]

    start_date = JalaliDateField(label="از تاریخ")
    end_date = JalaliDateField(label="تا تاریخ")

    dur_m = forms.IntegerField(label="دقیقه", required=False, min_value=0, initial=0)
    dur_h = forms.IntegerField(label="ساعت", required=False, min_value=0, initial=0)
    dur_d = forms.IntegerField(label="روز", required=False, min_value=0, initial=0)

    def __init__(self, *args, day_minutes=DEFAULT_DAY_MINUTES, **kwargs):
        super().__init__(*args, **kwargs)
        self.day_minutes = day_minutes
        self.fields["employee"].queryset = Employee.objects.filter(
            status=Employee.Status.ACTIVE
        ).order_by("personnel_code")
        for name, field in self.fields.items():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (css + " input").strip()
        if self.instance.pk:
            parts = self.instance.parts(day_minutes)
            self.fields["dur_d"].initial = parts["d"]
            self.fields["dur_h"].initial = parts["h"]
            self.fields["dur_m"].initial = parts["m"]

    def clean(self):
        cleaned = super().clean()
        minutes = minutes_from_parts(
            cleaned.get("dur_d"), cleaned.get("dur_h"), cleaned.get("dur_m"),
            self.day_minutes,
        )
        self.instance.minutes = minutes
        # صفر بودن مدت و وارونه بودن تاریخ‌ها را `LeaveRecord.clean()` می‌گیرد؛
        # همان‌جا تنها جای این دو قاعده است تا ثبت از شل و ادمین هم پوشش داشته باشد.
        return cleaned


def _day_minutes():
    """طول روز کاری از پارامتر آخرین دوره — مبنای تبدیل روز به دقیقه."""
    period = (
        PayrollPeriod.objects.select_related("legal_parameter")
        .order_by("-year", "-month")
        .first()
    )
    if period and period.legal_parameter:
        return period.legal_parameter.leave_day_minutes
    return DEFAULT_DAY_MINUTES


@payroll_staff_required
def leave_desk(request):
    """فهرست مرخصی‌های ثبت‌شده، با فیلتر دوره و جستجوی پرسنل."""
    day_minutes = _day_minutes()
    periods = PayrollPeriod.objects.order_by("-year", "-month")[:24]

    period_id = request.GET.get("period") or ""
    kind = request.GET.get("kind") or ""
    query = request.GET.get("q", "").strip()

    records = LeaveRecord.objects.select_related("employee", "created_by")
    period = None
    if period_id:
        period = PayrollPeriod.objects.filter(pk=period_id).first()
        if period:
            records = records.filter(
                start_date__lte=period.end_date, end_date__gte=period.start_date
            )
    if kind:
        records = records.filter(kind=kind)
    if query:
        records = records.filter(
            Q(employee__first_name__icontains=query)
            | Q(employee__last_name__icontains=query)
            | Q(employee__personnel_code__icontains=query)
        )

    page = Paginator(records, 40).get_page(request.GET.get("page") or 1)
    rows = [
        {
            "record": record,
            "display": record.display(day_minutes),
            "in_period": (
                record.minutes_in(period.start_date, period.end_date) if period else None
            ),
        }
        for record in page
    ]

    return render(
        request,
        "leave/desk.html",
        {
            "rows": rows,
            "page_obj": page,
            "periods": periods,
            "period": period,
            "period_id": str(period_id),
            "kind": kind,
            "kinds": LeaveRecord.Kind.choices,
            "q": query,
            "total": records.count(),
            "day_minutes": day_minutes,
        },
    )


def _sync_note(record, touched, applied="در کارکرد {} اعمال شد"):
    """توضیح اینکه ثبت این مرخصی در کارکرد کدام دوره‌ها نشست و کجا ننشست.

    سه حالت متفاوت‌اند و پیام مبهم («اعمال نشد») هر سه را قاطی می‌کند: دورهٔ باز،
    دورهٔ قفل‌شده، و اصلاً نبودن دوره برای آن تاریخ.
    """
    if touched:
        return " و " + applied.format("، ".join(p.title for p in touched)) + "."

    covering = list(periods_covering(record.employee, record.start_date, record.end_date))
    if not covering:
        return " ولی هنوز دوره‌ای برای این تاریخ ساخته نشده؛ با ساخت دوره در کارکرد می‌نشیند."
    locked = "، ".join(p.title for p in covering)
    return f" ولی کارکرد {locked} قفل است و دست‌نخورده ماند."


@can_edit_required
def leave_record_form(request, pk=None):
    day_minutes = _day_minutes()
    record = get_object_or_404(LeaveRecord, pk=pk) if pk else None
    form = LeaveRecordForm(
        request.POST or None, instance=record, day_minutes=day_minutes
    )
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        if record.created_by_id is None:
            record.created_by = request.user
        record.save()
        touched = sync_record(record)
        messages.success(
            request,
            f"مرخصی {record.employee.full_name} ثبت شد" + _sync_note(record, touched),
        )
        return redirect("leave_desk")

    return render(
        request,
        "leave/form.html",
        {
            "form": form,
            "record": record,
            "day_minutes": day_minutes,
            "title": "ویرایش مرخصی" if record else "ثبت مرخصی جدید",
        },
    )


@can_edit_required
@require_POST
def leave_record_cancel(request, pk):
    """لغو مرخصی — کارکرد همان لحظه بدون آن بازسازی می‌شود."""
    record = get_object_or_404(LeaveRecord, pk=pk)
    record.status = LeaveRecord.Status.CANCELLED
    record.save(update_fields=["status"])
    touched = sync_record(record)
    messages.success(
        request,
        f"مرخصی {record.employee.full_name} لغو شد"
        + _sync_note(record, touched, "از کارکرد {} برداشته شد"),
    )
    return redirect("leave_desk")


@can_edit_required
@require_POST
def leave_sync_period(request, pk):
    """اعمال دوبارهٔ کل کارتابل روی کارکرد یک دوره."""
    period = get_object_or_404(PayrollPeriod, pk=pk)
    if not period.is_editable:
        messages.error(request, "کارکرد این دوره قابل ویرایش نیست.")
        return redirect("leave_desk")
    count = sync_period(period)
    messages.success(
        request,
        f"کارکرد {count} پرسنل در {period.title} از روی کارتابل مرخصی به‌روز شد.",
    )
    return redirect(f"/leave/desk/?period={period.pk}")
