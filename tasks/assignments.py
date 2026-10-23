"""Assign and transfer an existing task without losing its progress or history."""

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Notification, Task, TaskEvent, TaskHandover
from .permissions import assignable_users


def get_assignee_user_ids(task):
    if not task.pk:
        return {task.assigned_to_id} if task.assigned_to_id else set()
    return {task.assigned_to_id, *task.additional_assignees.values_list("pk", flat=True)} - {None}


@transaction.atomic
def transfer_primary_assignee(task, *, new_employee, actor, reason, keep_previous=False):
    """Transfer a task and preserve its identity, dates, progress and all attachments.

    Caller must enforce manager permissions and lock/retrieve the Task before calling.
    """
    if task.status in {Task.Status.DONE, Task.Status.CANCELLED, Task.Status.REVIEW}:
        raise ValidationError("Передать можно только активную задачу, не ожидающую проверки.")
    if task.assigned_to_id == new_employee.pk:
        raise ValidationError("Выбранный сотрудник уже является основным исполнителем.")
    if not assignable_users().filter(pk=new_employee.pk).exists():
        raise ValidationError("Укажите активного сотрудника из группы Employees.")
    reason = (reason or "").strip()
    if not reason or len(reason) > 500:
        raise ValidationError("Укажите причину передачи (до 500 символов).")

    old_employee = task.assigned_to
    task.assigned_to = new_employee
    task._change_actor = actor
    task.save()

    # If the new lead was an additional assignee, avoid listing them twice.
    task.additional_assignees.remove(new_employee)
    if keep_previous:
        task.additional_assignees.add(old_employee)
    else:
        task.additional_assignees.remove(old_employee)

    # Clear any old action notifications for a colleague removed from the team;
    # their record of participation remains in TaskHandover and TaskEvent.
    if not keep_previous:
        task.notifications.filter(user=old_employee).delete()

    record = TaskHandover.objects.create(
        task=task,
        from_employee=old_employee,
        to_employee=new_employee,
        changed_by=actor,
        reason=reason,
        keep_previous=keep_previous,
    )
    old_name = old_employee.get_full_name() or old_employee.username
    new_name = new_employee.get_full_name() or new_employee.username
    TaskEvent.objects.create(
        task=task,
        actor=actor,
        kind=TaskEvent.Kind.HANDOVER,
        message=(
            f"Задача передана: {old_name} → {new_name}. Причина: {reason}."
            + (" Предыдущий исполнитель оставлен в команде." if keep_previous else "")
        )[:500],
    )
    return record


@transaction.atomic
def replace_additional_assignee(task, *, former, replacement, actor, reason):
    """Replace absent co-worker without changing the primary assignee."""
    if task.status not in {Task.Status.NEW, Task.Status.IN_PROGRESS, Task.Status.REVISION}:
        raise ValidationError("Передавать можно только активную работу.")
    if former.pk == task.assigned_to_id or not task.additional_assignees.filter(pk=former.pk).exists():
        raise ValidationError("Этот сотрудник не является дополнительным исполнителем задачи.")
    if replacement.pk in get_assignee_user_ids(task):
        raise ValidationError("Новый сотрудник уже входит в команду задачи.")
    if not assignable_users().filter(pk=replacement.pk).exists():
        raise ValidationError("Новый сотрудник недоступен для назначения.")
    reason = (reason or "").strip()
    if not reason or len(reason) > 500:
        raise ValidationError("Укажите причину передачи (не более 500 символов).")
    task._change_actor = actor
    task.additional_assignees.remove(former)
    task.additional_assignees.add(replacement)
    record = TaskHandover.objects.create(
        task=task, from_employee=former, to_employee=replacement,
        changed_by=actor, reason=reason, keep_previous=False,
    )
    old_name = former.get_full_name() or former.username
    new_name = replacement.get_full_name() or replacement.username
    TaskEvent.objects.create(
        task=task, actor=actor, kind=TaskEvent.Kind.HANDOVER,
        message=f"Заменён соисполнитель: {old_name} → {new_name}. Причина: {reason}."[:500],
    )
    return record
