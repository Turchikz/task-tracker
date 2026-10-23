"""Next-seven-days heatmap for manager resource planning.

Each cell is the sum of existing Task workload points; it is intentionally
NOT estimated hours or a performance rating of the employee.
"""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import EmployeeAbsence, Task
from .services import WORKLOAD_STATUSES, get_workload_ranking, task_load_score


def get_weekly_heatmap(start=None, days=7):
    start = start or timezone.localdate()
    dates = [start + timedelta(days=delta) for delta in range(days)]
    end = dates[-1]
    employees = get_workload_ranking()
    user_ids = {row.user.pk for row in employees}
    scheduled = {key: [] for key in user_ids}
    tasks = Task.objects.filter(status__in=WORKLOAD_STATUSES).select_related("assigned_to").prefetch_related("additional_assignees")
    for task in tasks:
        if task.start_date and task.start_date > end:
            continue
        if task.due_date and task.due_date < start:
            continue  # separate overdue backlog remains visible in the main table.
        for member in task.team_members:
            if member.pk in scheduled:
                scheduled[member.pk].append(task)
    unavailable = {}
    absences = EmployeeAbsence.objects.filter(start_date__lte=end, end_date__gte=start)
    for absence in absences:
        unavailable.setdefault(absence.user_id, []).append(absence)

    rows = []
    for employee in employees:
        cells = []
        for day in dates:
            absence_today = any(a.start_date <= day <= a.end_date for a in unavailable.get(employee.user.pk, []))
            relevant = [task for task in scheduled[employee.user.pk]
                        if (not task.start_date or task.start_date <= day)
                        and (not task.due_date or task.due_date >= day)]
            value = sum(task_load_score(task, day) for task in relevant)
            level = "absent" if absence_today else ("empty" if value == 0 else "high" if value >= 20 else "moderate" if value >= 8 else "low")
            cells.append({"date": day, "level": level, "score": value, "count": len(relevant), "absent": absence_today})
        rows.append({"user": employee.user, "cells": cells})
    return {"days": dates, "rows": rows}
