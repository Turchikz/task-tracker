"""Propose human-confirmed replacement assignments for overlapping absences."""
from django.db.models import Q
from django.utils import timezone

from .models import EmployeeAbsence, Task
from .permissions import can_manage_task
from .services import WORKLOAD_STATUSES, get_workload_ranking


def affected_tasks_for_absences(user, *, limit=80):
    """Only tasks that the requesting manager may change; never auto-assign."""
    today = timezone.localdate()
    upcoming = list(EmployeeAbsence.objects.filter(end_date__gte=today).select_related("user").order_by("start_date", "user_id"))
    if not upcoming:
        return []
    ranking = get_workload_ranking()
    all_absences = list(EmployeeAbsence.objects.filter(end_date__gte=today))
    results, seen = [], set()
    for absence in upcoming:
        tasks = Task.objects.filter(status__in=WORKLOAD_STATUSES).filter(
            Q(assigned_to_id=absence.user_id) | Q(additional_assignees__id=absence.user_id),
        ).distinct().select_related("assigned_to", "responsible_manager", "created_by").prefetch_related("additional_assignees")
        for task in tasks:
            key = (absence.pk, task.pk)
            if key in seen or not can_manage_task(user, task):
                continue
            seen.add(key)
            # Include tasks whose schedules overlap absence; undated work is
            # included if the absence is currently active.
            start = task.start_date or today
            finish = task.due_date or max(today, start)
            if finish < absence.start_date or start > absence.end_date:
                continue
            members = {worker.pk for worker in task.team_members}
            candidates = []
            for row in ranking:
                if row.user.pk in members:
                    continue
                if any(day.user_id == row.user.pk and day.start_date <= finish and day.end_date >= start for day in all_absences):
                    continue
                candidates.append(row)
            name = absence.user.get_full_name() or absence.user.username
            results.append({
                "absence": absence,
                "task": task,
                "is_primary": task.assigned_to_id == absence.user_id,
                "replacement_options": candidates,
                "suggestion": candidates[0] if candidates else None,
                "reason": f"Отсутствие: {name}, {absence.start_date:%d.%m.%Y}–{absence.end_date:%d.%m.%Y}",
            })
            if len(results) >= limit:
                return results
    return results
