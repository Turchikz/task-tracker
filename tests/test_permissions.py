from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from tasks.models import Task


@pytest.mark.django_db
def test_anonymous_user_is_redirected(client):
    response = client.get(reverse("task_list"))
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_employee_sees_only_assigned_tasks(client, manager, employee, second_employee):
    mine = Task.objects.create(title="Моя", created_by=manager, assigned_to=employee)
    other = Task.objects.create(title="Чужая", created_by=manager, assigned_to=second_employee)
    client.force_login(employee)

    response = client.get(reverse("task_list"))
    content = response.content.decode()
    assert mine.title in content
    assert other.title not in content

    response = client.get(reverse("task_detail", args=[other.pk]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_employee_cannot_create_task(client, employee):
    client.force_login(employee)
    response = client.get(reverse("task_create"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_manager_can_create_task(client, manager, employee):
    client.force_login(manager)
    response = client.post(
        reverse("task_create"),
        {
            "title": "Новая задача",
            "description": "Описание",
            "assigned_to": employee.pk,
            "status": Task.Status.NEW,
            "priority": Task.Priority.HIGH,
            "effort": Task.Effort.MEDIUM,
            "due_date": (timezone.localdate() + timedelta(days=2)).isoformat(),
        },
    )
    assert response.status_code == 302
    task = Task.objects.get(title="Новая задача")
    assert task.created_by == manager
    assert task.assigned_to == employee


@pytest.mark.django_db
def test_employee_edit_changes_only_status(client, manager, employee):
    task = Task.objects.create(title="Исходное название", created_by=manager, assigned_to=employee)
    client.force_login(employee)
    response = client.post(
        reverse("task_edit", args=[task.pk]),
        {"status": Task.Status.IN_PROGRESS, "title": "Попытка подмены"},
    )
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.status == Task.Status.IN_PROGRESS
    assert task.title == "Исходное название"

@pytest.mark.django_db
def test_employee_cannot_reopen_cancelled_task(client, manager, employee):
    task = Task.objects.create(
        title="Отменённая",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.CANCELLED,
    )
    client.force_login(employee)
    response = client.post(reverse("task_edit", args=[task.pk]), {"status": Task.Status.NEW})
    assert response.status_code == 403
    task.refresh_from_db()
    assert task.status == Task.Status.CANCELLED


@pytest.mark.django_db
def test_new_task_is_always_created_with_new_status(client, manager, employee):
    client.force_login(manager)
    response = client.post(
        reverse("task_create"),
        {
            "title": "Всегда новая",
            "description": "",
            "assigned_to": employee.pk,
            "status": Task.Status.DONE,
            "priority": Task.Priority.NORMAL,
            "effort": Task.Effort.SMALL,
            "due_date": "",
        },
    )
    assert response.status_code == 302
    assert Task.objects.get(title="Всегда новая").status == Task.Status.NEW

@pytest.mark.django_db
def test_employee_must_start_before_submitting_for_review(client, manager, employee):
    task = Task.objects.create(title="По шагам", created_by=manager, assigned_to=employee)
    client.force_login(employee)

    response = client.post(reverse("task_edit", args=[task.pk]), {"status": Task.Status.REVIEW})
    assert response.status_code == 200
    task.refresh_from_db()
    assert task.status == Task.Status.NEW

    response = client.post(reverse("task_edit", args=[task.pk]), {"status": Task.Status.IN_PROGRESS})
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.status == Task.Status.IN_PROGRESS

    response = client.post(reverse("task_edit", args=[task.pk]), {"status": Task.Status.REVIEW})
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.status == Task.Status.REVIEW


@pytest.mark.django_db
def test_employee_cannot_edit_task_while_under_review(client, manager, employee):
    task = Task.objects.create(
        title="На проверке",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.REVIEW,
    )
    client.force_login(employee)
    response = client.get(reverse("task_edit", args=[task.pk]))
    assert response.status_code == 403
