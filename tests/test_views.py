from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from tasks.models import Task, TaskTemplate


@pytest.mark.django_db
def test_manager_dashboard_contains_workload(client, manager, employee):
    Task.objects.create(title="Работа", created_by=manager, assigned_to=employee)
    client.force_login(manager)
    response = client.get(reverse("manager_dashboard"))
    assert response.status_code == 200
    assert "Загрузка сотрудников" in response.content.decode()
    assert "Иван Иванов" in response.content.decode()


@pytest.mark.django_db
def test_my_today_shows_today_task(client, manager, employee):
    Task.objects.create(title="Сегодняшняя", created_by=manager, assigned_to=employee, due_date=timezone.localdate())
    client.force_login(employee)
    response = client.get(reverse("my_today"))
    assert response.status_code == 200
    assert "Сегодняшняя" in response.content.decode()


@pytest.mark.django_db
def test_calendar_hides_other_employee_tasks(client, manager, employee, second_employee):
    mine = Task.objects.create(title="Мой календарь", created_by=manager, assigned_to=employee, due_date=timezone.localdate())
    other = Task.objects.create(title="Чужой календарь", created_by=manager, assigned_to=second_employee, due_date=timezone.localdate())
    client.force_login(employee)
    response = client.get(reverse("calendar"))
    content = response.content.decode()
    assert mine.title in content
    assert other.title not in content


@pytest.mark.django_db
def test_template_prefills_create_form(client, manager, employee):
    template = TaskTemplate.objects.create(
        name="Отчёт",
        title="Подготовить отчёт",
        description="Типовое описание",
        priority=Task.Priority.HIGH,
        effort=Task.Effort.LARGE,
        default_due_days=2,
    )
    client.force_login(manager)
    response = client.get(reverse("task_create"), {"template": template.pk})
    content = response.content.decode()
    assert response.status_code == 200
    assert "Подготовить отчёт" in content
    assert "Типовое описание" in content

@pytest.mark.django_db
def test_healthcheck_checks_database(client):
    response = client.get(reverse("health"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_manager_can_view_workload_timeline(client, manager, employee):
    client.force_login(manager)
    response = client.get(reverse("workload_timeline"))
    assert response.status_code == 200
    assert "Загрузка сотрудников" in response.content.decode()
    assert "Иван Иванов" in response.content.decode()


@pytest.mark.django_db
def test_employee_cannot_view_workload_timeline(client, employee):
    client.force_login(employee)
    response = client.get(reverse("workload_timeline"))
    assert response.status_code == 403

@pytest.mark.django_db
def test_manager_can_accept_reviewed_task(client, manager, employee):
    task = Task.objects.create(
        title="Принять результат",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.REVIEW,
    )
    client.force_login(manager)
    response = client.post(reverse("task_review_action", args=[task.pk]), {"action": "accept"})
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.status == Task.Status.DONE


@pytest.mark.django_db
def test_manager_can_return_reviewed_task_for_revision(client, manager, employee):
    task = Task.objects.create(
        title="Вернуть результат",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.REVIEW,
    )
    client.force_login(manager)
    response = client.post(reverse("task_review_action", args=[task.pk]), {"action": "revision"})
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.status == Task.Status.REVISION


@pytest.mark.django_db
def test_employee_cannot_review_task(client, manager, employee):
    task = Task.objects.create(
        title="Только руководитель",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.REVIEW,
    )
    client.force_login(employee)
    response = client.post(reverse("task_review_action", args=[task.pk]), {"action": "accept"})
    assert response.status_code == 403
