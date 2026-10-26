"""Django signal registrations for task lifecycle events."""

from django.contrib.auth.models import Group
from django.db.models.signals import m2m_changed, post_delete, post_migrate, post_save, pre_save
from django.dispatch import receiver

from .constants import EMPLOYEES_GROUP, MANAGERS_GROUP
from .models import Task, TaskImage
# Shared with management commands and task action views.
from .task_event_handlers import (
    create_notification,
    delete_task_image_file,
    handle_additional_assignees_changed,
    handle_task_notifications_and_history,
)


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


@receiver(post_save, sender=Task)
def task_notifications_and_history(sender, instance, created, **kwargs):
    handle_task_notifications_and_history(instance, created=created)


@receiver(m2m_changed, sender=Task.additional_assignees.through)
def additional_assignees_changed(sender, instance, action, reverse, pk_set, **kwargs):
    handle_additional_assignees_changed(
        instance,
        action=action,
        reverse=reverse,
        pk_set=pk_set,
    )


@receiver(post_delete, sender=TaskImage)
def task_image_file_deleted(sender, instance, **kwargs):
    delete_task_image_file(instance)
