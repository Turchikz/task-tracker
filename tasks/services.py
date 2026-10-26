from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from .models import EmployeeAbsence, Task, TaskEvent
from .permissions import EMPLOYEES_GROUP

PRIORITY_WEIGHT = {
    Task.Priority.LOW: 1,
    Task.Priority.NORMAL: 2,
    Task.Priority.HIGH: 3,
    Task.Priority.URGENT: 5,
}

EFFORT_WEIGHT = {
    Task.Effort.SMALL: 1,
    Task.Effort.MEDIUM: 2,
    Task.Effort.LARGE: 3,
    Task.Effort.XLARGE: 5,
}

CURRENT_STATUSES = [
    Task.Status.NEW,
    Task.Status.IN_PROGRESS,
    Task.Status.REVIEW,
    Task.Status.REVISION,
]

WORKLOAD_STATUSES = [
    Task.Status.NEW,
    Task.Status.IN_PROGRESS,
    Task.Status.REVISION,
]


@dataclass(frozen=True)
class WorkloadRow:
    user: User
    score: int
    active_count: int
    urgent_count: int
    due_soon_count: int
    overdue_count: int
    absence: EmployeeAbsence | None = None

    @property
    def load_level(self):
        if self.absence is not None:
            return "absent"
        if self.score >= 20:
            return "high"
        if self.score >= 8:
            return "moderate"
        return "low"

    @property
    def load_percent(self):
        return min(100, round(self.score * 100 / 30))

    @property
    def load_label(self):
        return {"absent": "Отсутствует", "high": "Высокая", "moderate": "Умеренная", "low": "Низкая"}[self.load_level]


def deadline_weight(task, today=None):
    if task.due_date is None:
        return 0
    today = today or timezone.localdate()
    days = (task.due_date - today).days
    if days < 0:
        return 4
    if days == 0:
        return 3
    if days <= 2:
        return 2
    if days <= 7:
        return 1
    return 0


def task_load_score(task, today=None):
    if not task.contributes_to_workload:
        return 0
    status_weight = 1 if task.status == Task.Status.IN_PROGRESS else 0
    return (
        EFFORT_WEIGHT.get(task.effort, 0)
        + PRIORITY_WEIGHT.get(task.priority, 0)
        + deadline_weight(task, today)
        + status_weight
    )


def get_workload_ranking():
    today = timezone.localdate()
    # Each current team member receives the task in their personal load.
    workload_tasks = list(
        Task.objects.filter(status__in=WORKLOAD_STATUSES)
        .select_related("assigned_to")
        .prefetch_related("additional_assignees")
        .order_by("due_date")
    )
    employees = list(
        User.objects.filter(is_active=True, groups__name=EMPLOYEES_GROUP).distinct()
    )
    tasks_by_user = {user.pk: [] for user in employees}
    for task in workload_tasks:
        for member in task.team_members:
            if member.pk in tasks_by_user:
                tasks_by_user[member.pk].append(task)

    active_absences = {
        absence.user_id: absence
        for absence in EmployeeAbsence.objects.filter(start_date__lte=today, end_date__gte=today).select_related("user")
    }

    rows = []
    for user in employees:
        tasks = tasks_by_user[user.pk]
        rows.append(
            WorkloadRow(
                user=user,
                score=sum(task_load_score(task, today) for task in tasks),
                active_count=len(tasks),
                urgent_count=sum(task.priority == Task.Priority.URGENT for task in tasks),
                due_soon_count=sum(
                    bool(task.due_date and 0 <= (task.due_date - today).days <= 3)
                    for task in tasks
                ),
                overdue_count=sum(bool(task.due_date and task.due_date < today) for task in tasks),
                absence=active_absences.get(user.pk),
            )
        )
    return sorted(
        rows,
        key=lambda row: (
            row.absence is not None,
            row.score,
            row.overdue_count,
            row.active_count,
            row.user.get_full_name() or row.user.username,
        ),
    )


@dataclass(frozen=True)
class TimelineSegment:
    task: Task
    start_date: object
    end_date: object
    span: int


@dataclass(frozen=True)
class TimelineCell:
    kind: str
    colspan: int
    task: Task | None = None
    absence: EmployeeAbsence | None = None


@dataclass(frozen=True)
class WorkloadTimelineRow:
    workload: WorkloadRow
    lanes: list
    no_due_count: int
    absence_cells: list
    has_absences: bool
    row_span: int


def task_planned_span(task):
    if task.due_date is None:
        return None
    start = task.start_date or task.due_date
    end = task.due_date
    if start > end:
        start = end
    return start, end


def _blank_day_cells(start_date, end_date):
    """Return one blank cell per day.

    Blank cells must not use colspan: browsers may paint the background of the
    first <col> across the whole spanning cell, making an entire month look like
    a weekend or holiday when day 1 is non-working.
    """
    if start_date > end_date:
        return []
    return [
        TimelineCell("blank", 1)
        for _ in range((end_date - start_date).days + 1)
    ]


def _timeline_cells(segments, range_start, range_end):
    cells = []
    cursor = range_start
    for segment in segments:
        if cursor < segment.start_date:
            cells.extend(_blank_day_cells(cursor, segment.start_date - timedelta(days=1)))
        cells.append(TimelineCell("task", segment.span, segment.task))
        cursor = segment.end_date + timedelta(days=1)
    if cursor <= range_end:
        cells.extend(_blank_day_cells(cursor, range_end))
    return cells


def build_timeline_lanes(tasks, range_start, range_end):
    segments = []
    for task in tasks:
        span = task_planned_span(task)
        if span is None:
            continue
        start, end = span
        if end < range_start or start > range_end:
            continue
        clipped_start = max(start, range_start)
        clipped_end = min(end, range_end)
        segments.append(
            TimelineSegment(
                task=task,
                start_date=clipped_start,
                end_date=clipped_end,
                span=(clipped_end - clipped_start).days + 1,
            )
        )

    segments.sort(key=lambda item: (item.start_date, item.end_date, item.task.pk or 0))
    lanes = []
    lane_ends = []
    for segment in segments:
        for index, lane_end in enumerate(lane_ends):
            if lane_end < segment.start_date:
                lanes[index].append(segment)
                lane_ends[index] = segment.end_date
                break
        else:
            lanes.append([segment])
            lane_ends.append(segment.end_date)

    if not lanes:
        return [_blank_day_cells(range_start, range_end)]
    return [_timeline_cells(lane, range_start, range_end) for lane in lanes]


def build_absence_cells(absences, range_start, range_end):
    """Build one visual availability row for non-overlapping employee absences.

    Blank periods are emitted day-by-day so weekend/holiday column backgrounds
    remain aligned with the exact calendar date.
    """
    cells = []
    cursor = range_start
    for absence in sorted(absences, key=lambda item: (item.start_date, item.end_date, item.pk or 0)):
        if absence.end_date < range_start or absence.start_date > range_end:
            continue
        start = max(absence.start_date, range_start)
        end = min(absence.end_date, range_end)
        if cursor < start:
            cells.extend(_blank_day_cells(cursor, start - timedelta(days=1)))
        cells.append(
            TimelineCell(
                "absence",
                (end - start).days + 1,
                absence=absence,
            )
        )
        cursor = end + timedelta(days=1)

    if cursor <= range_end:
        cells.extend(_blank_day_cells(cursor, range_end))
    return cells


def get_workload_timeline(range_start, range_end, *, include_all=False):
    """Рейтинг считает текущую работу; шкала показывает задачи и периоды отсутствия."""
    ranking = get_workload_ranking()
    result = []
    for workload in ranking:
        qs = Task.objects.filter(
            Q(assigned_to=workload.user) | Q(additional_assignees=workload.user)
        ).distinct()
        if not include_all:
            qs = qs.filter(status__in=CURRENT_STATUSES)
        tasks = list(qs.select_related("assigned_to").prefetch_related("additional_assignees")
                     .order_by("start_date", "due_date", "created_at"))
        lanes = build_timeline_lanes(tasks, range_start, range_end)

        absences = list(
            workload.user.employee_absences.filter(
                start_date__lte=range_end,
                end_date__gte=range_start,
            ).order_by("start_date", "end_date")
        )
        has_absences = bool(absences)
        result.append(
            WorkloadTimelineRow(
                workload=workload,
                lanes=lanes,
                no_due_count=sum(task.due_date is None for task in tasks),
                absence_cells=build_absence_cells(absences, range_start, range_end),
                has_absences=has_absences,
                row_span=len(lanes) + (1 if has_absences else 0),
            )
        )
    return result



def _average_cycle_hours(tasks):
    values = []
    for task in tasks:
        if task.started_at and task.completed_at and task.completed_at >= task.started_at:
            values.append((task.completed_at - task.started_at).total_seconds() / 3600)
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def get_manager_analytics(date_from, date_to):
    """Return lightweight process analytics for a small internal team."""
    created_qs = Task.objects.filter(created_at__date__range=(date_from, date_to))
    completed = list(
        Task.objects.filter(
            status=Task.Status.DONE,
            completed_at__date__range=(date_from, date_to),
        ).select_related("assigned_to").prefetch_related("additional_assignees")
    )
    revision_events = TaskEvent.objects.filter(
        to_status=Task.Status.REVISION,
        created_at__date__range=(date_from, date_to),
    )

    completed_with_due = [task for task in completed if task.due_date]
    on_time = [
        task
        for task in completed_with_due
        if timezone.localtime(task.completed_at).date() <= task.due_date
    ]
    late = [task for task in completed_with_due if task not in on_time]

    today = timezone.localdate()
    current_overdue = Task.objects.filter(
        status__in=WORKLOAD_STATUSES,
        due_date__lt=today,
    ).count()

    revisions_by_user = {}
    for event in revision_events.select_related("task").prefetch_related("task__additional_assignees"):
        for member in event.task.team_members:
            revisions_by_user[member.pk] = revisions_by_user.get(member.pk, 0) + 1
    completed_by_user = {}
    for task in completed:
        for member in task.team_members:
            completed_by_user.setdefault(member.pk, []).append(task)

    employee_rows = []
    employees = User.objects.filter(is_active=True, groups__name=EMPLOYEES_GROUP).distinct()
    for user in employees:
        user_tasks = completed_by_user.get(user.pk, [])
        with_due = [task for task in user_tasks if task.due_date]
        user_on_time = [
            task
            for task in with_due
            if timezone.localtime(task.completed_at).date() <= task.due_date
        ]
        employee_rows.append(
            {
                "user": user,
                "completed": len(user_tasks),
                "on_time": len(user_on_time),
                "on_time_rate": round(len(user_on_time) * 100 / len(with_due)) if with_due else None,
                "revisions": revisions_by_user.get(user.pk, 0),
                "avg_cycle_hours": _average_cycle_hours(user_tasks),
            }
        )

    employee_rows.sort(key=lambda row: (-row["completed"], row["user"].get_full_name() or row["user"].username))
    return {
        "created": created_qs.count(),
        "completed": len(completed),
        "on_time": len(on_time),
        "on_time_rate": round(len(on_time) * 100 / len(completed_with_due)) if completed_with_due else None,
        "late": len(late),
        "revisions": revision_events.count(),
        "avg_cycle_hours": _average_cycle_hours(completed),
        "current_overdue": current_overdue,
        "employees": employee_rows,
    }
