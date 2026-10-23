import calendar
from pathlib import Path
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import Case, F, IntegerField, Q, When
from django.http import FileResponse, Http404, HttpResponseForbidden, JsonResponse, QueryDict, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .holidays import get_rt_calendar_map
from .forms import (
    BulkTaskUpdateForm,
    EmployeeAbsenceForm,
    EmployeeTaskStatusForm,
    RevisionReasonForm,
    TaskCommentForm,
    TaskCreateForm,
    TaskForm,
    TaskImageForm,
    TaskHandoverForm,
    TaskTemplateForm,
    SavedTaskFilterForm,
)
from .models import EmployeeAbsence, Notification, SavedTaskFilter, Task, TaskEvent, TaskImage, TaskTemplate, TaskMemberProgress
from .assignments import transfer_primary_assignee, replace_additional_assignee
from .permissions import assignable_users, can_manage_task, is_manager, manager_users
from .signals import create_notification
from .collaboration import team_progress, all_members_ready, change_member_progress
from .absence_planning import affected_tasks_for_absences
from .excel_reports import build_manager_excel
from .backup_monitor import get_backup_status
from .heatmap import get_weekly_heatmap
from .services import (
    CURRENT_STATUSES,
    WORKLOAD_STATUSES,
    get_manager_analytics,
    get_workload_ranking,
    get_workload_timeline,
)


def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok"})


def _task_queryset_for_user(user):
    qs = Task.objects.select_related("created_by", "assigned_to", "responsible_manager").prefetch_related("additional_assignees")
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


@login_required
def home(request):
    return redirect("manager_dashboard" if is_manager(request.user) else "my_today")


@login_required
def task_list(request):
    qs = _task_queryset_for_user(request.user)

    quick = request.GET.get("quick", "")
    status = request.GET.get("status", "")
    priority = request.GET.get("priority", "")
    assigned = request.GET.get("assigned", "")
    responsible = request.GET.get("responsible", "")
    overdue = request.GET.get("overdue", "")
    sort = request.GET.get("sort", "smart")
    today = timezone.localdate()

    if quick == "current":
        qs = qs.filter(status__in=CURRENT_STATUSES)
    elif quick == "overdue":
        qs = qs.filter(due_date__lt=today, status__in=WORKLOAD_STATUSES)
    elif quick == "today":
        qs = qs.filter(due_date=today, status__in=CURRENT_STATUSES)
    elif quick == "review":
        qs = qs.filter(status=Task.Status.REVIEW)
    elif quick == "revision":
        qs = qs.filter(status=Task.Status.REVISION)
    elif quick == "done":
        qs = qs.filter(status=Task.Status.DONE)
    elif quick:
        quick = ""

    valid_statuses = {value for value, _ in Task.Status.choices}
    valid_priorities = {value for value, _ in Task.Priority.choices}
    if status in valid_statuses:
        qs = qs.filter(status=status)
    if priority in valid_priorities:
        qs = qs.filter(priority=priority)
    if is_manager(request.user) and assigned.isdigit():
        qs = qs.filter(Q(assigned_to_id=int(assigned)) | Q(additional_assignees__id=int(assigned))).distinct()
    if is_manager(request.user) and responsible.isdigit():
        qs = qs.filter(responsible_manager_id=int(responsible))
    if overdue == "1":
        qs = qs.filter(due_date__lt=today, status__in=WORKLOAD_STATUSES)

    if sort == "due":
        qs = qs.order_by(F("due_date").asc(nulls_last=True), "-created_at")
    elif sort == "priority":
        qs = qs.annotate(priority_rank=_priority_order()).order_by("-priority_rank", F("due_date").asc(nulls_last=True))
    elif sort == "created":
        qs = qs.order_by("-created_at")
    else:
        sort = "smart"
        qs = _smart_order(qs)

    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    active_filter_count = sum(bool(v) for v in (status, priority, assigned, responsible, overdue))
    active_saved_filter = next(
        (saved for saved in request.user.saved_task_filters.all()
         if saved.query_string == params.urlencode()), None
    )
    return render(
        request,
        "tasks/task_list.html",
        {
            "page_obj": page_obj,
            "statuses": Task.Status.choices,
            "priorities": Task.Priority.choices,
            "employees": assignable_users() if is_manager(request.user) else [],
            "managers": manager_users() if is_manager(request.user) else [],
            "saved_filters": request.user.saved_task_filters.all(),
            "saved_filter_form": SavedTaskFilterForm(),
            "bulk_form": BulkTaskUpdateForm() if is_manager(request.user) else None,
            "current_filter_query": params.urlencode(),
            "active_saved_filter": active_saved_filter,
            "active_filter_count": active_filter_count,
            "filters": {
                "quick": quick,
                "status": status,
                "priority": priority,
                "assigned": assigned,
                "responsible": responsible,
                "overdue": overdue,
                "sort": sort,
            },
            "query_without_page": params.urlencode(),
        },
    )


@login_required
def kanban(request):
    qs = _task_queryset_for_user(request.user)
    priority = request.GET.get("priority", "")
    assigned = request.GET.get("assigned", "")
    scope = request.GET.get("scope", "current")

    if scope not in {"current", "all"}:
        scope = "current"
    if scope == "current":
        qs = qs.filter(status__in=CURRENT_STATUSES)

    if priority in {value for value, _ in Task.Priority.choices}:
        qs = qs.filter(priority=priority)
    if is_manager(request.user) and assigned.isdigit():
        qs = qs.filter(Q(assigned_to_id=int(assigned)) | Q(additional_assignees__id=int(assigned))).distinct()

    column_statuses = [
        Task.Status.NEW,
        Task.Status.IN_PROGRESS,
        Task.Status.REVIEW,
        Task.Status.REVISION,
    ]
    if scope == "all":
        column_statuses += [Task.Status.DONE, Task.Status.CANCELLED]

    ordered = _smart_order(qs.select_related("assigned_to", "created_by").prefetch_related("additional_assignees"))
    columns = []
    for status_value in column_statuses:
        tasks = [task for task in ordered if task.status == status_value]
        columns.append(
            {
                "value": status_value,
                "label": Task.Status(status_value).label,
                "tasks": tasks,
            }
        )

    return render(
        request,
        "tasks/kanban.html",
        {
            "columns": columns,
            "scope": scope,
            "priorities": Task.Priority.choices,
            "employees": assignable_users() if is_manager(request.user) else [],
            "filters": {"priority": priority, "assigned": assigned},
        },
    )


@login_required
def task_detail(request, pk):
    task = get_object_or_404(
        _task_queryset_for_user(request.user).prefetch_related(
            "history__actor", "comments__author", "images__uploaded_by",
            "handovers__from_employee", "handovers__to_employee", "handovers__changed_by"
        ),
        pk=pk,
    )
    return render(
        request,
        "tasks/task_detail.html",
        _task_detail_context(request.user, task),
    )



@login_required
def task_create(request):
    if not is_manager(request.user):
        return HttpResponseForbidden("Создавать задачи может только руководитель.")

    initial = {"responsible_manager": request.user}
    selected_template = None
    template_id = request.GET.get("template")
    if template_id and template_id.isdigit():
        selected_template = get_object_or_404(TaskTemplate, pk=int(template_id), is_active=True)
        initial.update(
            {
                "title": selected_template.title,
                "description": selected_template.description,
                "priority": selected_template.priority,
                "effort": selected_template.effort,
                "start_date": timezone.localdate(),
                "due_date": timezone.localdate() + timedelta(days=selected_template.default_due_days),
            }
        )

    if request.method == "POST":
        form = TaskCreateForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.created_by = request.user
            if not task.responsible_manager_id:
                task.responsible_manager = request.user
            task._change_actor = request.user
            task.save()
            form.save_m2m()
            messages.success(request, "Задача создана.")
            return redirect("task_detail", pk=task.pk)
    else:
        initial.setdefault("start_date", timezone.localdate())
        form = TaskCreateForm(initial=initial)

    return render(
        request,
        "tasks/task_form.html",
        {
            "form": form,
            "title": "Новая задача",
            "templates": TaskTemplate.objects.filter(is_active=True),
            "selected_template": selected_template,
            "workload_ranking": getattr(form, "workload_ranking", []),
        },
    )


@login_required
def task_edit(request, pk):
    task = get_object_or_404(_task_queryset_for_user(request.user), pk=pk)
    manager = is_manager(request.user)
    original_responsible_manager_id = task.responsible_manager_id or task.created_by_id

    if manager:
        if not can_manage_task(request.user, task):
            return HttpResponseForbidden(
                "Изменять эту задачу может только руководитель, который её назначил."
            )
        form_class = TaskForm
    else:
        if not task.has_assignee(request.user):
            return HttpResponseForbidden("Нет доступа к задаче.")
        if task.status not in {Task.Status.NEW, Task.Status.IN_PROGRESS, Task.Status.REVISION}:
            return HttpResponseForbidden("Эту задачу сейчас может изменить только руководитель.")
        form_class = EmployeeTaskStatusForm

    if request.method == "POST":
        form = form_class(request.POST, instance=task)
        if form.is_valid():
            task = form.save(commit=False)
            if manager and not task.responsible_manager_id:
                task.responsible_manager_id = original_responsible_manager_id
            task._change_actor = request.user
            task.save()
            if manager:
                form.save_m2m()
            messages.success(request, "Задача обновлена.")
            return redirect("task_detail", pk=task.pk)
    else:
        form = form_class(instance=task)

    return render(
        request,
        "tasks/task_form.html",
        {
            "form": form,
            "title": "Редактирование задачи",
            "task": task,
            "workload_ranking": getattr(form, "workload_ranking", []),
        },
    )



@login_required
def task_handover(request, pk):
    """Manager-only reassignment of a single existing task with a reason."""
    if request.method != "POST":
        raise Http404
    if not is_manager(request.user):
        return HttpResponseForbidden("Передавать задачи может только руководитель.")

    with transaction.atomic():
        task = get_object_or_404(
            Task.objects.select_for_update().select_related("assigned_to", "responsible_manager", "created_by"),
            pk=pk,
        )
        if not can_manage_task(request.user, task):
            return HttpResponseForbidden("Передать эту задачу может только ответственный руководитель.")
        form = TaskHandoverForm(request.POST, task=task)
        if not form.is_valid():
            messages.error(request, "Проверьте нового исполнителя и причину передачи.")
            return redirect("task_detail", pk=pk)
        try:
            transfer_primary_assignee(
                task,
                new_employee=form.cleaned_data["to_employee"],
                actor=request.user,
                reason=form.cleaned_data["reason"],
                keep_previous=form.cleaned_data["keep_previous"],
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("task_detail", pk=pk)

    messages.success(request, "Задача передана новому исполнителю. История и срок сохранены.")
    return redirect("task_detail", pk=pk)


@login_required
def task_member_progress_update(request, pk):
    if request.method != "POST":
        raise Http404
    task = get_object_or_404(_task_queryset_for_user(request.user), pk=pk)
    if is_manager(request.user) or not task.has_assignee(request.user):
        return HttpResponseForbidden("Готовность может менять только исполнитель задачи.")
    if task.status not in {Task.Status.NEW, Task.Status.IN_PROGRESS, Task.Status.REVISION}:
        return HttpResponseForbidden("У завершённой или отправленной на проверку задачи готовность не изменяется.")
    state = request.POST.get("state", "")
    if state not in TaskMemberProgress.State.values:
        return HttpResponseForbidden("Неизвестный статус готовности.")
    member_state = change_member_progress(task, request.user, state)
    TaskEvent.objects.create(
        task=task, actor=request.user, kind=TaskEvent.Kind.TEAM,
        message=f"{request.user.get_full_name() or request.user.username}: личная готовность — {member_state.get_state_display()}.",
    )
    messages.success(request, "Ваша готовность обновлена.")
    return redirect("task_detail", pk=pk)


@login_required
def task_substitute(request, pk):
    if request.method != "POST" or not is_manager(request.user):
        return HttpResponseForbidden("Заменить соисполнителя может только руководитель.")
    try:
        former_id = int(request.POST.get("from_employee", ""))
        replacement_id = int(request.POST.get("to_employee", ""))
    except (TypeError, ValueError):
        return HttpResponseForbidden("Укажите сотрудников.")
    with transaction.atomic():
        task = get_object_or_404(Task.objects.select_for_update(), pk=pk)
        if not can_manage_task(request.user, task):
            return HttpResponseForbidden("Только ответственный руководитель может заменить соисполнителя.")
        former = get_object_or_404(assignable_users(), pk=former_id)
        replacement = get_object_or_404(assignable_users(), pk=replacement_id)
        try:
            replace_additional_assignee(
                task, former=former, replacement=replacement, actor=request.user,
                reason=request.POST.get("reason", ""),
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("absences")
    messages.success(request, "Соисполнитель заменён. Задача, сроки и история сохранены.")
    return redirect("absences")


@login_required
def task_quick_action(request, pk):
    if request.method != "POST":
        raise Http404

    task = get_object_or_404(_task_queryset_for_user(request.user), pk=pk)
    action = request.POST.get("action", "")
    manager = is_manager(request.user)

    if manager:
        if not can_manage_task(request.user, task):
            return HttpResponseForbidden(
                "Изменять статус этой задачи может только руководитель, который её назначил."
            )
        if action == "start" and task.status in {Task.Status.NEW, Task.Status.REVISION}:
            task.status = Task.Status.IN_PROGRESS
            success_message = "Задача принята в работу."
        elif action == "accept" and task.status == Task.Status.REVIEW:
            task.status = Task.Status.DONE
            success_message = "Задача принята."
        elif action == "done" and task.status in {Task.Status.NEW, Task.Status.IN_PROGRESS, Task.Status.REVISION}:
            task.status = Task.Status.DONE
            success_message = "Задача отмечена выполненной."
        else:
            return HttpResponseForbidden("Недопустимое действие с задачей.")
    else:
        if not task.has_assignee(request.user):
            return HttpResponseForbidden("Нет доступа к задаче.")
        if action == "start" and task.status in {Task.Status.NEW, Task.Status.REVISION}:
            task.status = Task.Status.IN_PROGRESS
            success_message = "Работа над задачей начата."
        elif action == "submit" and task.status == Task.Status.IN_PROGRESS:
            task.status = Task.Status.REVIEW
            success_message = "Задача отправлена руководителю на проверку."
        else:
            return HttpResponseForbidden("Недопустимое действие с задачей.")

    task._change_actor = request.user
    task.save()
    messages.success(request, success_message)
    return _redirect_back(request, "task_detail", pk=task.pk)



@login_required
def task_comment_add(request, pk):
    if request.method != "POST":
        raise Http404

    task = get_object_or_404(_task_queryset_for_user(request.user), pk=pk)
    if is_manager(request.user) and not can_manage_task(request.user, task):
        return HttpResponseForbidden("Для задач другого руководителя доступен только просмотр.")

    form = TaskCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.task = task
        comment.author = request.user
        comment.save()
        TaskEvent.objects.create(
            task=task,
            actor=request.user,
            kind=TaskEvent.Kind.COMMENT,
            message="Добавлен комментарий.",
        )
        manager = task.responsible_manager or task.created_by
        participants = task.team_members
        recipients = [manager] if not is_manager(request.user) else participants
        for recipient in recipients:
            if recipient and recipient.id != request.user.id:
                author_name = request.user.get_full_name() or request.user.username
                create_notification(
                    recipient,
                    task,
                    Notification.Kind.COMMENT,
                    f"{author_name} добавил комментарий к задаче «{task.title}».",
                    refresh_existing=True,
                )
        messages.success(request, "Комментарий добавлен.")
        return _redirect_back(request, "task_detail", pk=task.pk)

    task = get_object_or_404(
        _task_queryset_for_user(request.user).prefetch_related(
            "history__actor", "comments__author", "images__uploaded_by",
            "handovers__from_employee", "handovers__to_employee", "handovers__changed_by"
        ),
        pk=pk,
    )
    return render(
        request,
        "tasks/task_detail.html",
        _task_detail_context(request.user, task, comment_form=form),
        status=400,
    )



@login_required
def task_accept(request, pk):
    if request.method != "POST":
        raise Http404
    if not is_manager(request.user):
        return HttpResponseForbidden("Принять задачу может только руководитель.")

    task = get_object_or_404(Task, pk=pk, status=Task.Status.REVIEW)
    if not can_manage_task(request.user, task):
        return HttpResponseForbidden(
            "Принять задачу может только руководитель, который её назначил."
        )

    task.status = Task.Status.DONE
    task._change_actor = request.user
    task.save()
    messages.success(request, "Задача принята и отмечена выполненной.")
    return redirect("task_detail", pk=task.pk)



@login_required
def task_request_revision(request, pk):
    if request.method != "POST":
        raise Http404
    if not is_manager(request.user):
        return HttpResponseForbidden("Вернуть задачу на доработку может только руководитель.")

    task = get_object_or_404(Task, pk=pk, status=Task.Status.REVIEW)
    if not can_manage_task(request.user, task):
        return HttpResponseForbidden(
            "Вернуть задачу может только руководитель, который её назначил."
        )

    form = RevisionReasonForm(request.POST)
    if not form.is_valid():
        task = get_object_or_404(
            _task_queryset_for_user(request.user).prefetch_related(
                "history__actor", "comments__author", "images__uploaded_by",
            "handovers__from_employee", "handovers__to_employee", "handovers__changed_by"
            ),
            pk=pk,
        )
        return render(
            request,
            "tasks/task_detail.html",
            _task_detail_context(request.user, task, revision_form=form),
            status=400,
        )

    reason = form.cleaned_data["revision_reason"].strip()
    task.status = Task.Status.REVISION
    task.revision_reason = reason
    task._change_actor = request.user
    task._change_comment = reason
    task.save()
    messages.success(request, "Задача возвращена исполнителю на доработку.")
    return redirect("task_detail", pk=task.pk)



@login_required
def review_queue(request):
    if not is_manager(request.user):
        return HttpResponseForbidden("Очередь проверки доступна только руководителю.")

    qs = _manager_owned_queryset(
        Task.objects.filter(status=Task.Status.REVIEW),
        request.user,
    ).select_related("assigned_to", "created_by").prefetch_related("additional_assignees").order_by(
        F("submitted_at").asc(nulls_last=True), "due_date", "created_at"
    )
    return render(request, "tasks/review_queue.html", {"tasks": qs})



@login_required
def my_today(request):
    today = timezone.localdate()
    qs = Task.objects.filter(
        Q(assigned_to=request.user) | Q(additional_assignees=request.user),
        status__in=[Task.Status.NEW, Task.Status.IN_PROGRESS, Task.Status.REVISION],
    ).distinct().select_related("created_by").prefetch_related("additional_assignees")
    overdue = _smart_order(qs.filter(due_date__lt=today))
    today_tasks = _smart_order(qs.filter(due_date=today))
    upcoming = _smart_order(qs.filter(due_date__gt=today, due_date__lte=today + timedelta(days=7)))
    no_date = qs.filter(due_date__isnull=True).order_by("-created_at")
    review_tasks = Task.objects.filter(
        Q(assigned_to=request.user) | Q(additional_assignees=request.user),
        status=Task.Status.REVIEW,
    ).distinct().order_by("-submitted_at")
    return render(
        request,
        "tasks/my_today.html",
        {
            "overdue": overdue,
            "today_tasks": today_tasks,
            "upcoming": upcoming,
            "no_date": no_date,
            "review_tasks": review_tasks,
            "today": today,
        },
    )


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
def template_list(request):
    if not is_manager(request.user):
        return HttpResponseForbidden("Шаблоны доступны только руководителю.")
    return render(request, "tasks/template_list.html", {"templates": TaskTemplate.objects.all()})


@login_required
def template_create(request):
    if not is_manager(request.user):
        return HttpResponseForbidden("Шаблоны доступны только руководителю.")
    if request.method == "POST":
        form = TaskTemplateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Шаблон создан.")
            return redirect("template_list")
    else:
        form = TaskTemplateForm()
    return render(request, "tasks/template_form.html", {"form": form, "title": "Новый шаблон"})


@login_required
def template_edit(request, pk):
    if not is_manager(request.user):
        return HttpResponseForbidden("Шаблоны доступны только руководителю.")
    template = get_object_or_404(TaskTemplate, pk=pk)
    if request.method == "POST":
        form = TaskTemplateForm(request.POST, instance=template)
        if form.is_valid():
            form.save()
            messages.success(request, "Шаблон обновлён.")
            return redirect("template_list")
    else:
        form = TaskTemplateForm(instance=template)
    return render(request, "tasks/template_form.html", {"form": form, "title": "Редактирование шаблона"})


@login_required
def notifications_list(request):
    notifications_qs = request.user.task_notifications.select_related("task")
    if not is_manager(request.user):
        notifications_qs = notifications_qs.filter(
            Q(task__assigned_to=request.user) | Q(task__additional_assignees=request.user)
        ).distinct()
    if is_manager(request.user) and not request.user.is_superuser:
        notifications_qs = notifications_qs.exclude(
            Q(kind=Notification.Kind.SUBMITTED_REVIEW)
            & ~Q(task__responsible_manager=request.user)
        )

    notifications = list(notifications_qs[:100])
    for notification in notifications:
        notification.display_day = timezone.localtime(notification.created_at).date()
    today_date = timezone.localdate()
    yesterday_date = today_date - timedelta(days=1)
    action_notifications = [
        notification for notification in notifications if notification.requires_action
    ]
    info_notifications = [
        notification for notification in notifications if not notification.requires_action
    ]
    return render(
        request,
        "tasks/notifications.html",
        {
            "action_notifications": action_notifications,
            "info_notifications": info_notifications,
            "today": today_date,
            "yesterday": yesterday_date,
        },
    )



@login_required
def notification_read(request, pk):
    if request.method != "POST":
        raise Http404
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return redirect("notifications")


@login_required
def notifications_read_all(request):
    if request.method != "POST":
        raise Http404
    request.user.task_notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
    return redirect("notifications")


@login_required
def task_image_upload(request, pk):
    if request.method != "POST":
        raise Http404
    task = get_object_or_404(_task_queryset_for_user(request.user), pk=pk)
    if is_manager(request.user) and not can_manage_task(request.user, task):
        return HttpResponseForbidden("Для задач другого руководителя доступен только просмотр.")

    form = TaskImageForm(request.POST, request.FILES)
    if form.is_valid():
        uploaded = form.cleaned_data["image"]
        image = form.save(commit=False)
        image.task = task
        image.uploaded_by = request.user
        image.original_name = Path(uploaded.name).name[:255]
        image.content_type = uploaded.content_type
        image.save()
        TaskEvent.objects.create(
            task=task,
            actor=request.user,
            kind=TaskEvent.Kind.IMAGE,
            message=f"Добавлено изображение «{image.original_name}».",
        )
        messages.success(request, "Изображение добавлено.")
        return redirect("task_detail", pk=task.pk)

    task = get_object_or_404(
        _task_queryset_for_user(request.user).prefetch_related(
            "history__actor", "comments__author", "images__uploaded_by",
            "handovers__from_employee", "handovers__to_employee", "handovers__changed_by"
        ),
        pk=pk,
    )
    return render(
        request,
        "tasks/task_detail.html",
        _task_detail_context(request.user, task, image_form=form),
        status=400,
    )



@login_required
def task_image_file(request, pk, image_pk):
    get_object_or_404(_task_queryset_for_user(request.user), pk=pk)
    image = get_object_or_404(TaskImage, pk=image_pk, task_id=pk)
    if not image.image:
        raise Http404
    try:
        file_handle = image.image.open("rb")
    except FileNotFoundError:
        raise Http404
    response = FileResponse(
        file_handle,
        content_type=image.content_type,
        as_attachment=False,
        filename=image.original_name,
    )
    response["Cache-Control"] = "private, max-age=3600"
    return response


@login_required
def task_image_delete(request, pk, image_pk):
    if request.method != "POST":
        raise Http404
    task = get_object_or_404(_task_queryset_for_user(request.user), pk=pk)
    image = get_object_or_404(TaskImage, pk=image_pk, task=task)

    if is_manager(request.user):
        if not can_manage_task(request.user, task):
            return HttpResponseForbidden("Для задач другого руководителя доступен только просмотр.")
    elif image.uploaded_by_id != request.user.id:
        return HttpResponseForbidden(
            "Удалить изображение может руководитель или пользователь, который его загрузил."
        )

    original_name = image.original_name
    image.delete()
    TaskEvent.objects.create(
        task=task,
        actor=request.user,
        kind=TaskEvent.Kind.IMAGE,
        message=f"Удалено изображение «{original_name}».",
    )
    messages.success(request, "Изображение удалено.")
    return redirect("task_detail", pk=task.pk)



@login_required
def absences(request):
    if not is_manager(request.user):
        return HttpResponseForbidden("Отсутствия сотрудников доступны только руководителю.")
    today = timezone.localdate()
    if request.method == "POST":
        form = EmployeeAbsenceForm(request.POST)
        if form.is_valid():
            absence = form.save(commit=False)
            absence.created_by = request.user
            absence.save()
            messages.success(request, "Период отсутствия добавлен.")
            return redirect("absences")
    else:
        form = EmployeeAbsenceForm(initial={"start_date": today, "end_date": today})

    active_upcoming = EmployeeAbsence.objects.filter(end_date__gte=today).select_related("user", "created_by")
    recent_past = EmployeeAbsence.objects.filter(end_date__lt=today).select_related("user", "created_by").order_by("-end_date")[:20]
    return render(
        request,
        "tasks/absences.html",
        {"form": form, "active_upcoming": active_upcoming, "recent_past": recent_past,
         "today": today, "affected_tasks": affected_tasks_for_absences(request.user)},
    )


@login_required
def absence_delete(request, pk):
    if request.method != "POST":
        raise Http404
    if not is_manager(request.user):
        return HttpResponseForbidden("Отсутствия сотрудников доступны только руководителю.")
    absence = get_object_or_404(EmployeeAbsence, pk=pk)
    absence.delete()
    messages.success(request, "Период отсутствия удалён.")
    return redirect("absences")


SAVED_FILTER_KEYS = {
    "quick",
    "status",
    "priority",
    "assigned",
    "responsible",
    "overdue",
    "sort",
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


@login_required
def saved_filter_create(request):
    if request.method != "POST":
        raise Http404
    form = SavedTaskFilterForm(request.POST)
    if form.is_valid():
        parameters = _normalize_saved_filter(request.POST.get("query_string", ""))
        SavedTaskFilter.objects.update_or_create(
            user=request.user,
            name=form.cleaned_data["name"].strip(),
            defaults={"parameters": parameters},
        )
        messages.success(request, "Фильтр сохранён для вашей учётной записи.")
    else:
        messages.error(request, "Не удалось сохранить фильтр. Проверьте название.")
    return _redirect_back(request, "task_list")


@login_required
def saved_filter_apply(request, pk):
    saved = get_object_or_404(SavedTaskFilter, pk=pk, user=request.user)
    query = _saved_filter_url(saved)
    base_url = reverse("task_list")
    return redirect(f"{base_url}?{query}" if query else base_url)


@login_required
def saved_filter_delete(request, pk):
    if request.method != "POST":
        raise Http404
    saved = get_object_or_404(SavedTaskFilter, pk=pk, user=request.user)
    saved.delete()
    messages.success(request, "Сохранённый фильтр удалён.")
    return _redirect_back(request, "task_list")


@login_required
def task_bulk_update(request):
    if request.method != "POST":
        raise Http404
    if not is_manager(request.user):
        return HttpResponseForbidden("Массовое изменение доступно только руководителю.")

    raw_ids = request.POST.getlist("task_ids")
    task_ids = sorted({int(value) for value in raw_ids if value.isdigit()})
    if not task_ids:
        messages.warning(request, "Выберите хотя бы одну задачу.")
        return _redirect_back(request, "task_list")

    selected = Task.objects.filter(pk__in=task_ids).select_related(
        "assigned_to", "created_by", "responsible_manager"
    )
    manageable = _manager_owned_queryset(selected, request.user)
    if manageable.count() != len(task_ids):
        return HttpResponseForbidden(
            "В выбранном списке есть задачи другого ответственного руководителя."
        )

    form = BulkTaskUpdateForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Не удалось выполнить массовое изменение: проверьте выбранное значение.")
        return _redirect_back(request, "task_list")

    action = form.cleaned_data["action"]
    if action == BulkTaskUpdateForm.Action.ASSIGNEE:
        disallowed = selected.exclude(
            status__in=[Task.Status.NEW, Task.Status.IN_PROGRESS, Task.Status.REVISION]
        )
        if disallowed.exists():
            messages.error(request, "Среди выбранных есть завершённые задачи или задачи на проверке — их нельзя передать.")
            return _redirect_back(request, "task_list")
    changed = 0
    with transaction.atomic():
        locked = _manager_owned_queryset(
            Task.objects.select_for_update().filter(pk__in=task_ids),
            request.user,
        )
        for task in locked:
            if action == BulkTaskUpdateForm.Action.ASSIGNEE:
                new_assignee = form.cleaned_data["assigned_to"]
                if task.assigned_to_id != new_assignee.pk:
                    transfer_primary_assignee(
                        task, new_employee=new_assignee, actor=request.user,
                        reason="Массовое переназначение руководителем",
                    )
                    changed += 1
                continue
            elif action == BulkTaskUpdateForm.Action.MANAGER:
                task.responsible_manager = form.cleaned_data["responsible_manager"]
            elif action == BulkTaskUpdateForm.Action.PRIORITY:
                task.priority = form.cleaned_data["priority"]
            elif action == BulkTaskUpdateForm.Action.DUE_DATE:
                task.due_date = form.cleaned_data["due_date"]
            task._change_actor = request.user
            task.save()
            changed += 1

    messages.success(request, f"Обновлено задач: {changed}.")
    return _redirect_back(request, "task_list")



def _search_excerpt(text, terms, *, width=165):
    """Return a short, plain-text excerpt around the first match (escaped by Django)."""
    if not text:
        return ""
    folded = text.casefold()
    positions = [folded.find(term) for term in terms if term and term in folded]
    start = max(0, min(positions) - 45) if positions else 0
    result = text[start:start + width].strip()
    return ("…" if start else "") + result + ("…" if start + width < len(text) else "")

@login_required
def global_search(request):
    query = request.GET.get("q", "").strip()[:200]
    qs = _task_queryset_for_user(request.user).prefetch_related("comments")

    if query:
        terms = [term for term in query.split() if term][:8]
        for term in terms:
            clean_id = term[1:] if term.startswith("#") else term
            condition = (
                Q(title__icontains=term)
                | Q(description__icontains=term)
                | Q(comments__text__icontains=term)
                | Q(assigned_to__first_name__icontains=term)
                | Q(assigned_to__last_name__icontains=term)
                | Q(assigned_to__username__icontains=term)
                | Q(additional_assignees__first_name__icontains=term)
                | Q(additional_assignees__last_name__icontains=term)
                | Q(additional_assignees__username__icontains=term)
                | Q(created_by__first_name__icontains=term)
                | Q(created_by__last_name__icontains=term)
                | Q(responsible_manager__first_name__icontains=term)
                | Q(responsible_manager__last_name__icontains=term)
            )
            if clean_id.isdigit():
                condition |= Q(pk=int(clean_id))
            qs = qs.filter(condition)
        qs = qs.distinct().order_by("-updated_at")
    else:
        qs = qs.none()

    paginator = Paginator(qs, 40)
    page_obj = paginator.get_page(request.GET.get("page"))
    if query:
        search_terms = [term.casefold() for term in query.split() if term]
        for task in page_obj.object_list:
            comment_text = next(
                (comment.text for comment in task.comments.all()
                 if any(term in comment.text.casefold() for term in search_terms)),
                None,
            )
            task.match_comment = _search_excerpt(comment_text, search_terms) if comment_text else None
            task.match_in_description = bool(
                task.description and any(term in task.description.casefold() for term in search_terms)
            )
            task.match_description = (
                _search_excerpt(task.description, search_terms)
                if task.match_in_description else None
            )
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "tasks/search_results.html",
        {
            "query": query,
            "page_obj": page_obj,
            "query_without_page": params.urlencode(),
        },
    )


def _date_from_query(value, default):
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        return default


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
    return render(request, "tasks/workload_guide.html")
