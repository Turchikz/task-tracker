from datetime import timedelta

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.utils import timezone

from tasks.constants import MANAGERS_GROUP
from tasks.models import Notification, Task


@pytest.mark.django_db
def test_assignment_creates_notification(manager, employee):
    task = Task.objects.create(title="Назначение", created_by=manager, assigned_to=employee)
    assert Notification.objects.filter(user=employee, task=task, kind=Notification.Kind.ASSIGNED).exists()


@pytest.mark.django_db
def test_due_date_change_creates_notification(manager, employee):
    task = Task.objects.create(title="Срок", created_by=manager, assigned_to=employee)
    Notification.objects.all().delete()
    task.due_date = timezone.localdate() + timedelta(days=4)
    task.save()
    assert Notification.objects.filter(user=employee, task=task, kind=Notification.Kind.DUE_CHANGED).exists()


@pytest.mark.django_db
def test_submit_for_review_notifies_all_managers(manager, employee):
    group = Group.objects.get(name=MANAGERS_GROUP)
    second_manager = User.objects.create_user(username="manager2", password="pass12345")
    second_manager.groups.add(group)
    task = Task.objects.create(title="Проверка", created_by=manager, assigned_to=employee, status=Task.Status.IN_PROGRESS)
    Notification.objects.all().delete()

    task.status = Task.Status.REVIEW
    task.save()

    assert Notification.objects.filter(task=task, kind=Notification.Kind.SUBMITTED_REVIEW, user=manager).exists()
    assert Notification.objects.filter(task=task, kind=Notification.Kind.SUBMITTED_REVIEW, user=second_manager).exists()


@pytest.mark.django_db
def test_revision_notification_contains_reason(manager, employee):
    task = Task.objects.create(title="Доработка", created_by=manager, assigned_to=employee, status=Task.Status.REVIEW)
    Notification.objects.all().delete()
    task.status = Task.Status.REVISION
    task.revision_reason = "Добавить подпись"
    task._change_comment = "Добавить подпись"
    task.save()
    notification = Notification.objects.get(user=employee, task=task, kind=Notification.Kind.REVISION_REQUESTED)
    assert "Добавить подпись" in notification.message


@pytest.mark.django_db
def test_acceptance_notifies_employee(manager, employee):
    task = Task.objects.create(title="Принять", created_by=manager, assigned_to=employee, status=Task.Status.REVIEW)
    Notification.objects.all().delete()
    task.status = Task.Status.DONE
    task.save()
    assert Notification.objects.filter(user=employee, task=task, kind=Notification.Kind.ACCEPTED).exists()


@pytest.mark.django_db
def test_due_command_is_idempotent_per_day(manager, employee):
    task = Task.objects.create(
        title="Завтра",
        created_by=manager,
        assigned_to=employee,
        due_date=timezone.localdate() + timedelta(days=1),
    )
    Notification.objects.filter(task=task, kind=Notification.Kind.DUE_SOON).delete()
    call_command("generate_due_notifications")
    call_command("generate_due_notifications")
    assert Notification.objects.filter(task=task, user=employee, kind=Notification.Kind.DUE_SOON).count() == 1


@pytest.mark.django_db
def test_second_due_change_same_day_becomes_unread_with_latest_message(manager, employee):
    task = Task.objects.create(title="Меняем срок", created_by=manager, assigned_to=employee)
    Notification.objects.all().delete()

    task.due_date = timezone.localdate() + timedelta(days=3)
    task.save()
    notification = Notification.objects.get(task=task, user=employee, kind=Notification.Kind.DUE_CHANGED)
    notification.read_at = timezone.now()
    notification.save(update_fields=["read_at"])

    task.due_date = timezone.localdate() + timedelta(days=5)
    task.save()
    notification.refresh_from_db()
    assert notification.read_at is None
    assert task.due_date.strftime("%d.%m.%Y") in notification.message
