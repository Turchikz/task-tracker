import pytest
from django.urls import reverse

from tasks.models import Task


@pytest.mark.django_db
def test_manager_can_start_new_task(client, manager, employee):
    task = Task.objects.create(
        title="Принять в работу",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.NEW,
    )

    client.force_login(manager)
    response = client.post(
        reverse("task_quick_action", args=[task.pk]),
        {"action": "start"},
    )

    assert response.status_code == 302

    task.refresh_from_db()
    assert task.status == Task.Status.IN_PROGRESS
    assert task.started_at is not None


@pytest.mark.django_db
def test_manager_can_restart_revision_task(client, manager, employee):
    task = Task.objects.create(
        title="Доработка",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.REVISION,
        revision_reason="Исправить данные",
    )

    client.force_login(manager)
    response = client.post(
        reverse("task_quick_action", args=[task.pk]),
        {"action": "start"},
    )

    assert response.status_code == 302

    task.refresh_from_db()
    assert task.status == Task.Status.IN_PROGRESS


@pytest.mark.django_db
def test_manager_cannot_start_review_task(client, manager, employee):
    task = Task.objects.create(
        title="На проверке",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.REVIEW,
    )

    client.force_login(manager)
    response = client.post(
        reverse("task_quick_action", args=[task.pk]),
        {"action": "start"},
    )

    assert response.status_code == 403
