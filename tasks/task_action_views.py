"""Task workflow actions, comments, handovers, and private attachments."""

from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .assignments import replace_additional_assignee, transfer_primary_assignee
from .collaboration import change_member_progress
from .forms import RevisionReasonForm, TaskCommentForm, TaskHandoverForm, TaskImageForm
from .models import Notification, Task, TaskEvent, TaskImage, TaskMemberProgress
from .permissions import assignable_users, can_manage_task, is_manager
from .signals import create_notification
from .task_view_helpers import _redirect_back, _task_detail_context, _task_queryset_for_user


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
