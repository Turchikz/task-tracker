"""Task-facing HTTP views: list/detail pages and task actions."""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    BulkTaskUpdateForm,
    EmployeeTaskStatusForm,
    SavedTaskFilterForm,
    TaskCreateForm,
    TaskForm,
)
from .models import SavedTaskFilter, Task, TaskTag, TaskTemplate
from .assignments import transfer_primary_assignee
from .permissions import assignable_users, can_manage_task, is_manager, manager_users
from .services import CURRENT_STATUSES, WORKLOAD_STATUSES
from .task_view_helpers import (
    _manager_owned_queryset,
    _normalize_saved_filter,
    _priority_order,
    _redirect_back,
    _saved_filter_url,
    _search_excerpt,
    _smart_order,
    _task_detail_context,
    _task_queryset_for_user,
)


@login_required
def task_list(request):
    qs = _task_queryset_for_user(request.user)

    quick = request.GET.get("quick", "")
    status = request.GET.get("status", "")
    priority = request.GET.get("priority", "")
    assigned = request.GET.get("assigned", "")
    responsible = request.GET.get("responsible", "")
    overdue = request.GET.get("overdue", "")
    tag = request.GET.get("tag", "")
    sort = request.GET.get("sort", "smart")
    today = timezone.localdate()

    if quick == "current":
        qs = qs.filter(status__in=CURRENT_STATUSES)
    elif quick == "overdue":
        qs = qs.filter(due_date__lt=today, status__in=WORKLOAD_STATUSES)
    elif quick == "today":
        qs = qs.filter(due_date=today, status__in=CURRENT_STATUSES)
    elif quick == "soon":
        qs = qs.filter(
            due_date__gte=today,
            due_date__lte=today + timedelta(days=7),
            status__in=CURRENT_STATUSES,
        )
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
    if tag.isdigit():
        qs = qs.filter(tags__pk=int(tag)).distinct()
    else:
        tag = ""
    if is_manager(request.user) and (assigned == "me" or assigned.isdigit()):
        assignee_id = request.user.pk if assigned == "me" else int(assigned)
        qs = qs.filter(Q(assigned_to_id=assignee_id) | Q(additional_assignees__id=assignee_id)).distinct()
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

    active_filter_count = sum(bool(v) for v in (status, priority, assigned, responsible, overdue, tag))
    # Compare the same canonical representation used by saved_filter_create.
    # SavedTaskFilter stores parameters in JSONField, not query_string.
    current_parameters = _normalize_saved_filter(params.urlencode())
    active_saved_filter = next(
        (saved for saved in request.user.saved_task_filters.all()
         if saved.parameters == current_parameters), None
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
            "task_tags": TaskTag.objects.filter(tasks__in=_task_queryset_for_user(request.user)).distinct(),
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
                "tag": tag,
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
            "task_tags": TaskTag.objects.order_by("name"),
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
            "task_tags": TaskTag.objects.order_by("name") if manager else TaskTag.objects.none(),
            "workload_ranking": getattr(form, "workload_ranking", []),
        },
    )
















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
