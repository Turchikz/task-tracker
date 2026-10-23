from django.contrib.auth.models import Group
from django.db.models.signals import m2m_changed, post_delete, post_migrate, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .constants import EMPLOYEES_GROUP, MANAGERS_GROUP
from .models import Notification, Task, TaskEvent, TaskImage, TaskMemberProgress


@receiver(post_migrate)
def ensure_default_groups(sender, **kwargs):
    if sender.name != "tasks":
        return
    Group.objects.get_or_create(name=EMPLOYEES_GROUP)
    Group.objects.get_or_create(name=MANAGERS_GROUP)


@receiver(pre_save, sender=Task)
def remember_previous_task_state(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_task_state = None
        return
    try:
        previous = sender.objects.only(
            "assigned_to_id",
            "responsible_manager_id",
            "due_date",
            "status",
            "priority",
        ).get(pk=instance.pk)
    except sender.DoesNotExist:
        instance._previous_task_state = None
        return
    instance._previous_task_state = {
        "assigned_to_id": previous.assigned_to_id,
        "responsible_manager_id": previous.responsible_manager_id,
        "due_date": previous.due_date,
        "status": previous.status,
        "priority": previous.priority,
    }


def create_notification(user, task, kind, message, *, refresh_existing=False):
    if user is None:
        return
    lookup = {
        "user": user,
        "task": task,
        "kind": kind,
        "notification_date": timezone.localdate(),
    }
    if refresh_existing:
        Notification.objects.update_or_create(
            **lookup,
            defaults={"message": message, "read_at": None},
        )
    else:
        Notification.objects.get_or_create(
            **lookup,
            defaults={"message": message},
        )


def _display_name(user):
    if user is None:
        return "Не назначен"
    return user.get_full_name() or user.username


@receiver(post_save, sender=Task)
def task_notifications_and_history(sender, instance, created, **kwargs):
    previous = getattr(instance, "_previous_task_state", None)
    actor = getattr(instance, "_change_actor", None)
    change_comment = (getattr(instance, "_change_comment", "") or "").strip()
    manager = instance.responsible_manager or instance.created_by

    if created:
        TaskMemberProgress.objects.get_or_create(task=instance, user_id=instance.assigned_to_id)
        TaskEvent.objects.create(
            task=instance,
            actor=actor,
            kind=TaskEvent.Kind.CREATED,
            message=(
                "Задача создана. Исполнитель: "
                f"{_display_name(instance.assigned_to)}. "
                f"Ответственный руководитель: {_display_name(manager)}."
            ),
        )
        create_notification(
            instance.assigned_to,
            instance,
            Notification.Kind.ASSIGNED,
            f"Вам назначена задача «{instance.title}».",
            refresh_existing=True,
        )
        if manager and actor and manager.pk != actor.pk:
            create_notification(
                manager,
                instance,
                Notification.Kind.MANAGER_ASSIGNED,
                f"Вы назначены ответственным за задачу «{instance.title}».",
                refresh_existing=True,
            )
        return

    if previous is None:
        return

    if previous["assigned_to_id"] != instance.assigned_to_id:
        TaskMemberProgress.objects.get_or_create(task=instance, user_id=instance.assigned_to_id)
        TaskEvent.objects.create(
            task=instance,
            actor=actor,
            kind=TaskEvent.Kind.ASSIGNEE,
            message=f"Исполнитель изменён на {_display_name(instance.assigned_to)}.",
        )
        create_notification(
            instance.assigned_to,
            instance,
            Notification.Kind.ASSIGNED,
            f"Вам назначена задача «{instance.title}».",
            refresh_existing=True,
        )

    if previous["responsible_manager_id"] != instance.responsible_manager_id:
        TaskEvent.objects.create(
            task=instance,
            actor=actor,
            kind=TaskEvent.Kind.MANAGER,
            message=f"Ответственный руководитель изменён на {_display_name(manager)}.",
        )
        create_notification(
            manager,
            instance,
            Notification.Kind.MANAGER_ASSIGNED,
            f"Вы назначены ответственным за задачу «{instance.title}».",
            refresh_existing=True,
        )
        # If the task is already waiting for review, move the review action to
        # the new responsible manager immediately.
        instance.notifications.filter(
            kind=Notification.Kind.SUBMITTED_REVIEW,
        ).exclude(user_id=manager.pk if manager else None).delete()
        if instance.status == Task.Status.REVIEW and manager:
            create_notification(
                manager,
                instance,
                Notification.Kind.SUBMITTED_REVIEW,
                (
                    f"{_display_name(instance.assigned_to)} завершил задачу "
                    f"«{instance.title}». Требуется проверка."
                ),
                refresh_existing=True,
            )

    if previous["priority"] != instance.priority:
        old_label = Task.Priority(previous["priority"]).label
        new_label = Task.Priority(instance.priority).label
        TaskEvent.objects.create(
            task=instance,
            actor=actor,
            kind=TaskEvent.Kind.PRIORITY,
            message=f"Приоритет изменён: {old_label} → {new_label}.",
        )

    if previous["due_date"] != instance.due_date:
        old_text = (
            previous["due_date"].strftime("%d.%m.%Y")
            if previous["due_date"]
            else "без срока"
        )
        new_text = (
            instance.due_date.strftime("%d.%m.%Y")
            if instance.due_date
            else "без срока"
        )
        TaskEvent.objects.create(
            task=instance,
            actor=actor,
            kind=TaskEvent.Kind.DUE_DATE,
            message=f"Срок изменён: {old_text} → {new_text}.",
        )
        for member in instance.team_members:
            create_notification(
                member,
                instance,
                Notification.Kind.DUE_CHANGED,
                f"Срок задачи «{instance.title}» изменён: {new_text}.",
                refresh_existing=True,
            )

    old_status = previous["status"]
    if old_status == instance.status:
        return

    old_label = Task.Status(old_status).label
    new_label = Task.Status(instance.status).label
    message = f"Статус изменён: {old_label} → {new_label}."
    if instance.status == Task.Status.REVISION and change_comment:
        message += f" Причина: {change_comment}"

    TaskEvent.objects.create(
        task=instance,
        actor=actor,
        kind=TaskEvent.Kind.STATUS,
        message=message,
        from_status=old_status,
        to_status=instance.status,
    )

    if instance.status == Task.Status.REVIEW:
        performer = _display_name(actor) if actor and instance.has_assignee(actor) else _display_name(instance.assigned_to)
        instance.notifications.filter(
            kind=Notification.Kind.SUBMITTED_REVIEW,
        ).exclude(user_id=manager.pk if manager else None).delete()
        if manager and manager.pk != instance.assigned_to_id:
            create_notification(
                manager,
                instance,
                Notification.Kind.SUBMITTED_REVIEW,
                f"{performer} завершил задачу «{instance.title}». Требуется проверка.",
                refresh_existing=True,
            )

    if (
        old_status == Task.Status.REVIEW
        and instance.status in {Task.Status.REVISION, Task.Status.DONE}
    ):
        instance.notifications.filter(
            kind=Notification.Kind.SUBMITTED_REVIEW,
            read_at__isnull=True,
        ).update(read_at=timezone.now())

    if instance.status == Task.Status.REVISION:
        TaskMemberProgress.objects.filter(task=instance, user_id__in=[member.pk for member in instance.team_members]).update(
            state=TaskMemberProgress.State.IN_PROGRESS,
        )
        reason = change_comment or instance.revision_reason or "Причина не указана."
        for member in instance.team_members:
            create_notification(
                member,
                instance,
                Notification.Kind.REVISION_REQUESTED,
                f"Задача «{instance.title}» возвращена на доработку. Причина: {reason}",
                refresh_existing=True,
            )

    if instance.status == Task.Status.DONE:
        if old_status == Task.Status.REVIEW:
            kind = Notification.Kind.ACCEPTED
            notification_message = f"Задача «{instance.title}» принята руководителем."
        else:
            kind = Notification.Kind.MANAGER_COMPLETED
            notification_message = f"Руководитель отметил задачу «{instance.title}» выполненной."
        for member in instance.team_members:
            create_notification(
                member,
                instance,
                kind,
                notification_message,
                refresh_existing=True,
            )

    if instance.status == Task.Status.CANCELLED:
        for member in instance.team_members:
            create_notification(
                member,
                instance,
                Notification.Kind.CANCELLED,
                f"Задача «{instance.title}» отменена.",
                refresh_existing=True,
            )


@receiver(m2m_changed, sender=Task.additional_assignees.through)
def additional_assignees_changed(sender, instance, action, reverse, pk_set, **kwargs):
    """Notify newly added coworkers and keep an audit trail.

    A manager-created task saves its lead first; co-workers are added later.
    """
    if reverse or action not in {"post_add", "post_remove"} or not pk_set:
        return
    from django.contrib.auth import get_user_model

    users = list(get_user_model().objects.filter(pk__in=pk_set).exclude(pk=instance.assigned_to_id))
    if not users:
        return
    actor = getattr(instance, "_change_actor", None)
    names = ", ".join(_display_name(user) for user in users)
    if action == "post_add":
        for user in users:
            TaskMemberProgress.objects.get_or_create(task=instance, user=user)
        for user in users:
            if user.pk == instance.assigned_to_id:
                continue
            create_notification(
                user,
                instance,
                Notification.Kind.ASSIGNED,
                f"Вас добавили к задаче «{instance.title}» как соисполнителя.",
                refresh_existing=True,
            )
        prefix = "Добавлены соисполнители"
    else:
        prefix = "Удалены соисполнители"
        for user in users:
            if user.pk != instance.assigned_to_id:
                instance.notifications.filter(user=user).delete()
    TaskEvent.objects.create(
        task=instance,
        actor=actor,
        kind=TaskEvent.Kind.TEAM,
        message=f"{prefix}: {names}."[:500],
    )


@receiver(post_delete, sender=TaskImage)
def delete_task_image_file(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)
