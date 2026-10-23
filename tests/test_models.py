from datetime import timedelta

import pytest
from django.utils import timezone

from tasks.models import Task


@pytest.mark.django_db
def test_task_completed_at_is_set_and_cleared(manager, employee):
    task = Task.objects.create(title="Тест", created_by=manager, assigned_to=employee, status=Task.Status.DONE)
    assert task.completed_at is not None

    task.status = Task.Status.IN_PROGRESS
    task.save()
    task.refresh_from_db()
    assert task.completed_at is None


@pytest.mark.django_db
def test_deadline_state_overdue(manager, employee):
    task = Task.objects.create(
        title="Просрочено",
        created_by=manager,
        assigned_to=employee,
        due_date=timezone.localdate() - timedelta(days=1),
    )
    assert task.deadline_state == "overdue"
    assert "Просрочено" in task.deadline_label

@pytest.mark.django_db
def test_cancelled_task_is_not_marked_overdue(manager, employee):
    task = Task.objects.create(
        title="Отменена",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.CANCELLED,
        due_date=timezone.localdate() - timedelta(days=3),
    )
    assert task.deadline_state == "done"
    assert task.deadline_label == "Отменена"

@pytest.mark.django_db
def test_task_validation_rejects_non_employee_assignee(manager):
    from django.core.exceptions import ValidationError

    task = Task(title="Нельзя назначить", created_by=manager, assigned_to=manager)
    with pytest.raises(ValidationError):
        task.full_clean()
