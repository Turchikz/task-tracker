from django.contrib.auth.models import User
from django.db.models import Q

from .constants import EMPLOYEES_GROUP, MANAGERS_GROUP


def is_manager(user):
    return bool(
        user.is_authenticated
        and (user.is_superuser or user.groups.filter(name=MANAGERS_GROUP).exists())
    )


def manager_users():
    return (
        User.objects.filter(is_active=True)
        .filter(Q(is_superuser=True) | Q(groups__name=MANAGERS_GROUP))
        .distinct()
        .order_by("last_name", "first_name", "username")
    )


def task_manager_id(task):
    """Responsible manager with backward-compatible fallback to the author."""
    return task.responsible_manager_id or task.created_by_id


def can_manage_task(user, task):
    """Only the responsible manager may change a task; superuser is an override."""
    return bool(
        is_manager(user)
        and (user.is_superuser or task_manager_id(task) == user.id)
    )


def assignable_users():
    return User.objects.filter(
        is_active=True,
        groups__name=EMPLOYEES_GROUP,
    ).distinct().order_by("last_name", "first_name", "username")
