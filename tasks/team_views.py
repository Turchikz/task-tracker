"""Team-level dashboards, calendar, workload, and activity views."""

import calendar
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from .backup_monitor import get_backup_status
from .heatmap import get_weekly_heatmap
from .holidays import get_rt_calendar_map
from .models import EmployeeAbsence, Notification, Task, TaskEvent
from .permissions import assignable_users, is_manager
from .services import CURRENT_STATUSES, WORKLOAD_STATUSES, get_workload_ranking, get_workload_timeline
from .task_view_helpers import _manager_owned_queryset, _smart_order, _task_queryset_for_user


@login_required
def manager_dashboard(request):
    if not is_manager(request.user):
        return redirect("my_today")

    today = timezone.localdate()
    workload_tasks = Task.objects.filter(status__in=WORKLOAD_STATUSES)
    current = Task.objects.filter(status__in=CURRENT_STATUSES)
    reviews = _manager_owned_queryset(
        Task.objects.filter(status=Task.Status.REVIEW),
        request.user,
    ).select_related("assigned_to").order_by(
        F("submitted_at").asc(nulls_last=True), "due_date"
    )
    week_ago = timezone.now() - timedelta(days=7)
    ranking = get_workload_ranking()
    attention = _smart_order(
        workload_tasks.select_related("assigned_to", "created_by", "responsible_manager").filter(
            Q(due_date__lte=today + timedelta(days=2)) | Q(priority=Task.Priority.URGENT)
        )
    )[:12]

    stats = {
        "active": current.count(),
        "review": reviews.count(),
        "overdue": workload_tasks.filter(due_date__lt=today).count(),
        "today": workload_tasks.filter(due_date=today).count(),
        "urgent": workload_tasks.filter(priority=Task.Priority.URGENT).count(),
        "completed_week": Task.objects.filter(
            status=Task.Status.DONE, completed_at__gte=week_ago
        ).count(),
    }
    activity = TaskEvent.objects.select_related("task", "actor").order_by("-created_at", "-pk")[:12]
    active_absences = EmployeeAbsence.objects.filter(
        start_date__lte=today, end_date__gte=today
    ).select_related("user").order_by("end_date")
    return render(
        request,
        "tasks/manager_dashboard.html",
        {
            "stats": stats,
            "today": today,
            "ranking": ranking,
            "weekly_heatmap": get_weekly_heatmap(today),
            "attention": attention,
            "reviews": reviews[:8],
            "activity": activity,
            "active_absences": active_absences,
            "backup": get_backup_status() if request.user.is_superuser else None,
        },
    )


@login_required
def workload_timeline(request):
    if not is_manager(request.user):
        return HttpResponseForbidden("План загрузки доступен только руководителю.")

    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        if not (1 <= month <= 12 and 2000 <= year <= 2100):
            raise ValueError
    except (TypeError, ValueError):
        year, month = today.year, today.month

    scope = request.GET.get("scope", "current")
    if scope not in {"current", "all"}:
        scope = "current"

    period = request.GET.get("period", "month")
    if period not in {"month", "two_weeks", "week"}:
        period = "month"
    requested_day = request.GET.get("day", "1")
    try:
        day = max(1, min(int(requested_day), calendar.monthrange(year, month)[1]))
    except (ValueError, TypeError):
        day = 1
    month_start = date(year, month, day if period != "month" else 1)
    last_day = calendar.monthrange(year, month)[1]
    if period == "month":
        month_end = date(year, month, last_day)
    else:
        month_end = month_start + timedelta(days=13 if period == "two_weeks" else 6)
    prev_month_date = date(year - 1, 12, 1) if month == 1 else date(year, month - 1, 1)
    next_month_date = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    calendar_map = get_rt_calendar_map(month_start, month_end)
    days = []
    for day_number in range((month_end - month_start).days + 1):
        day_date = month_start + timedelta(days=day_number)
        calendar_day = calendar_map[day_date]
        days.append(
            {
                "date": day_date,
                "day": day_date.day,
                "weekday": weekdays[day_date.weekday()],
                "is_weekend": calendar_day.is_weekend,
                "is_holiday": calendar_day.is_holiday,
                "is_non_working": calendar_day.is_non_working,
                "is_working_override": calendar_day.is_working_override,
                "holiday_name": calendar_day.name,
                "calendar_source": calendar_day.source,
                "is_today": day_date == today,
            }
        )

    month_names = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    common = {"scope": scope, "period": period}
    if period != "month":
        offset = 14 if period == "two_weeks" else 7
        prev_month_date = month_start - timedelta(days=offset)
        next_month_date = month_start + timedelta(days=offset)
        common_prev = {**common, "year": prev_month_date.year, "month": prev_month_date.month, "day": prev_month_date.day}
        common_next = {**common, "year": next_month_date.year, "month": next_month_date.month, "day": next_month_date.day}
    else:
        common_prev = {**common, "year": prev_month_date.year, "month": prev_month_date.month}
        common_next = {**common, "year": next_month_date.year, "month": next_month_date.month}
    return render(
        request,
        "tasks/workload_timeline.html",
        {
            "rows": get_workload_timeline(month_start, month_end, include_all=scope == "all"),
            "days": days,
            "month_name": month_names[month],
            "year": year,
            "month": month,
            "today": today,
            "scope": scope,
            "period": period,
            "start_day": month_start.day,
            "export_start": month_start.isoformat(),
            "export_end": month_end.isoformat(),
            "prev_query": urlencode(common_prev),
            "next_query": urlencode(common_next),
        },
    )


@login_required
def calendar_view(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        if not (1 <= month <= 12 and 2000 <= year <= 2100):
            raise ValueError
    except (TypeError, ValueError):
        year, month = today.year, today.month

    next_month_date = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    prev_month_date = date(year - 1, 12, 1) if month == 1 else date(year, month - 1, 1)

    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdatescalendar(year, month)
    range_start = month_days[0][0]
    range_end = month_days[-1][-1]

    qs = _task_queryset_for_user(request.user).filter(due_date__range=(range_start, range_end))
    status = request.GET.get("status", "")
    priority = request.GET.get("priority", "")
    assigned = request.GET.get("assigned", "")
    if status in {value for value, _ in Task.Status.choices}:
        qs = qs.filter(status=status)
    if priority in {value for value, _ in Task.Priority.choices}:
        qs = qs.filter(priority=priority)
    if is_manager(request.user) and assigned.isdigit():
        qs = qs.filter(Q(assigned_to_id=int(assigned)) | Q(additional_assignees__id=int(assigned))).distinct()

    task_map = {}
    for task in qs.order_by("due_date", "priority", "title"):
        task_map.setdefault(task.due_date, []).append(task)

    absence_map = {}
    for absence in EmployeeAbsence.objects.filter(
        start_date__lte=range_end, end_date__gte=range_start,
    ).select_related("user").order_by("user__last_name", "user__first_name", "user__username", "start_date"):
        for offset in range((min(absence.end_date, range_end) - max(absence.start_date, range_start)).days + 1):
            absence_day = max(absence.start_date, range_start) + timedelta(days=offset)
            absence_map.setdefault(absence_day, []).append(absence)

    calendar_map = get_rt_calendar_map(range_start, range_end)
    weeks = []
    for week in month_days:
        rendered_week = []
        for day in week:
            calendar_day = calendar_map[day]
            rendered_week.append(
                {
                    "date": day,
                    "in_month": day.month == month,
                    "tasks": task_map.get(day, []),
                    "absences": absence_map.get(day, []),
                    "is_weekend": calendar_day.is_weekend,
                    "is_holiday": calendar_day.is_holiday,
                    "is_non_working": calendar_day.is_non_working,
                    "is_working_override": calendar_day.is_working_override,
                    "holiday_name": calendar_day.name,
                    "calendar_source": calendar_day.source,
                }
            )
        weeks.append(rendered_week)

    preserved = {}
    for key in ("status", "priority", "assigned"):
        value = request.GET.get(key)
        if value:
            preserved[key] = value
    prev_query = urlencode({**preserved, "year": prev_month_date.year, "month": prev_month_date.month})
    next_query = urlencode({**preserved, "year": next_month_date.year, "month": next_month_date.month})

    month_names = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    return render(
        request,
        "tasks/calendar.html",
        {
            "weeks": weeks,
            "month_name": month_names[month],
            "year": year,
            "month": month,
            "today": today,
            "prev_query": prev_query,
            "next_query": next_query,
            "statuses": Task.Status.choices,
            "priorities": Task.Priority.choices,
            "employees": assignable_users() if is_manager(request.user) else [],
            "filters": {"status": status, "priority": priority, "assigned": assigned},
        },
    )


@login_required
def activity_feed(request):
    if not is_manager(request.user):
        return HttpResponseForbidden("Лента активности доступна только руководителю.")
    qs = TaskEvent.objects.select_related("task", "actor").order_by("-created_at", "-pk")
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "tasks/activity.html", {"page_obj": page_obj})


@login_required
def sound_notifications_feed(request):
    """Newest permitted notification; no message text is exposed."""
    notices = request.user.task_notifications.order_by("-id")
    if is_manager(request.user) and not request.user.is_superuser:
        notices = notices.exclude(Q(kind=Notification.Kind.SUBMITTED_REVIEW) & ~Q(task__responsible_manager=request.user))
    item = notices.values("id", "kind").first()
    response = JsonResponse({"latest": item["id"] if item else 0, "kind": item["kind"] if item else None})
    response["Cache-Control"] = "no-store"
    return response


@login_required
def workload_guide(request):
    """Document the exact workload scoring rules implemented in services.py."""
    if not is_manager(request.user):
        return HttpResponseForbidden("Описание расчёта нагрузки доступно только руководителю.")
    return render(request, "tasks/workload_guide.html")
