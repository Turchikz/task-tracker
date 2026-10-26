"""Manager reporting and operational monitoring HTTP views."""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone

from .backup_monitor import get_backup_status
from .excel_reports import build_manager_excel
from .permissions import is_manager
from .services import get_manager_analytics
from .workload_export import build_workload_excel


def _date_from_query(value, default):
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        return default


@login_required
def workload_export(request):
    if not is_manager(request.user):
        return HttpResponseForbidden("Экспорт загрузки доступен только руководителю.")
    try:
        start = date.fromisoformat(request.GET.get("from", ""))
        end = date.fromisoformat(request.GET.get("to", ""))
        if start > end or not (2000 <= start.year <= end.year <= 2100):
            raise ValueError
    except (TypeError, ValueError):
        messages.error(request, "Укажите корректный период: начало не позже окончания, годы 2000–2100.")
        return redirect("workload_timeline")
    content = build_workload_excel(start, end, request.build_absolute_uri("/").rstrip("/"))
    response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="RaTracker_workload_{start:%Y%m%d}_{end:%Y%m%d}.xlsx"'
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
def analytics(request):
    if not is_manager(request.user):
        return HttpResponseForbidden("Аналитика доступна только руководителю.")
    today = timezone.localdate()
    default_from = today.replace(day=1)
    date_from = _date_from_query(request.GET.get("from"), default_from)
    date_to = _date_from_query(request.GET.get("to"), today)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    data = get_manager_analytics(date_from, date_to)
    return render(
        request,
        "tasks/analytics.html",
        {"analytics": data, "date_from": date_from, "date_to": date_to},
    )


@login_required
def backup_monitor(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Просмотр состояния резервных копий доступен только администратору.")
    return render(request, "tasks/backup_monitor.html", {"backup": get_backup_status()})


@login_required
def analytics_export(request):
    if not is_manager(request.user):
        return HttpResponseForbidden("Экспорт отчёта доступен руководителям.")
    today = timezone.localdate()
    start = _date_from_query(request.GET.get("from"), today.replace(day=1))
    end = _date_from_query(request.GET.get("to"), today)
    if start > end:
        start, end = end, start
    content = build_manager_excel(start, end)
    response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="RaTracker_report_{start:%Y%m%d}_{end:%Y%m%d}.xlsx"'
    response["Cache-Control"] = "private, no-store"
    return response
