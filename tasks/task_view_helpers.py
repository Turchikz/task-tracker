"""Shared query, redirect, and presentation helpers for task views."""

from urllib.parse import urlencode

from django.db.models import Case, F, IntegerField, Q, When
from django.http import QueryDict
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .collaboration import all_members_ready, team_progress
from .forms import RevisionReasonForm, TaskCommentForm, TaskHandoverForm, TaskImageForm
from .models import Task, TaskMemberProgress
from .permissions import can_manage_task, is_manager
from .services import WORKLOAD_STATUSES


SAVED_FILTER_KEYS = {
    "quick",
    "status",
    "priority",
    "assigned",
    "responsible",
    "overdue",
    "tag",
    "sort",
}


def _task_queryset_for_user(user):
    qs = Task.objects.select_related("created_by", "assigned_to", "responsible_manager").prefetch_related("additional_assignees", "tags")
    if is_manager(user):
        return qs
    return qs.filter(Q(assigned_to=user) | Q(additional_assignees=user)).distinct()


def _priority_order():
    return Case(
        When(priority=Task.Priority.URGENT, then=4),
        When(priority=Task.Priority.HIGH, then=3),
        When(priority=Task.Priority.NORMAL, then=2),
        When(priority=Task.Priority.LOW, then=1),
        default=0,
        output_field=IntegerField(),
    )


def _smart_order(qs):
    today = timezone.localdate()
    return qs.annotate(
        activity_rank=Case(
            When(status__in=WORKLOAD_STATUSES, then=0),
            When(status=Task.Status.REVIEW, then=1),
            default=2,
            output_field=IntegerField(),
        ),
        deadline_rank=Case(
            When(due_date__lt=today, then=0),
            When(due_date=today, then=1),
            When(due_date__isnull=True, then=3),
            default=2,
            output_field=IntegerField(),
        ),
        priority_rank=_priority_order(),
    ).order_by("activity_rank", "deadline_rank", F("due_date").asc(nulls_last=True), "-priority_rank", "-created_at")


def _redirect_back(request, fallback_name, **kwargs):
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(fallback_name, **kwargs)


def _manager_owned_queryset(queryset, user):
    """Limit write/action queues to the task's responsible manager."""
    if user.is_superuser:
        return queryset
    return queryset.filter(
        Q(responsible_manager=user)
        | Q(responsible_manager__isnull=True, created_by=user)
    )


def _task_detail_context(user, task, *, revision_form=None, comment_form=None, image_form=None):
    """Build task detail context in one place so permissions stay consistent."""
    manager = is_manager(user)
    can_employee_edit = (
        not manager
        and task.has_assignee(user)
        and task.status in {Task.Status.NEW, Task.Status.IN_PROGRESS, Task.Status.REVISION}
    )
    return {
        "task": task,
        "can_manage_task": can_manage_task(user, task) if manager else False,
        "can_employee_edit": can_employee_edit,
        "revision_form": revision_form or RevisionReasonForm(),
        "comment_form": comment_form or TaskCommentForm(),
        "image_form": image_form or TaskImageForm(),
        "handover_form": TaskHandoverForm(task=task) if manager and can_manage_task(user, task) else None,
        "is_task_assignee": task.has_assignee(user) if not manager else False,
        "team_progress": [
            {"user": member, "state": state, "label": TaskMemberProgress.State(state).label}
            for member, state in team_progress(task)
        ],
        "team_all_ready": all_members_ready(task),
    }


def _normalize_saved_filter(query_string):
    parsed = QueryDict(query_string or "", mutable=False)
    normalized = {}
    for key in SAVED_FILTER_KEYS:
        value = parsed.get(key, "").strip()
        if value:
            normalized[key] = value[:120]
    return normalized


def _saved_filter_url(saved_filter):
    return urlencode(saved_filter.parameters or {})


def _search_excerpt(text, terms, *, width=165):
    """Return a short, plain-text excerpt around the first match (escaped by Django)."""
    if not text:
        return ""
    folded = text.casefold()
    positions = [folded.find(term) for term in terms if term and term in folded]
    start = max(0, min(positions) - 45) if positions else 0
    result = text[start:start + width].strip()
    return ("…" if start else "") + result + ("…" if start + width < len(text) else "")
