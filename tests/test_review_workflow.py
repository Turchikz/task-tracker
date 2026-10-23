import pytest
from django.urls import reverse

from tasks.models import Notification, Task, TaskEvent
from tasks.services import get_workload_timeline


@pytest.mark.django_db
def test_employee_workflow_records_actual_times(client, manager, employee):
    task = Task.objects.create(title="Workflow", created_by=manager, assigned_to=employee)
    client.force_login(employee)

    response = client.post(reverse("task_edit", args=[task.pk]), {"status": Task.Status.IN_PROGRESS})
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.status == Task.Status.IN_PROGRESS
    assert task.started_at is not None

    response = client.post(reverse("task_edit", args=[task.pk]), {"status": Task.Status.REVIEW})
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.status == Task.Status.REVIEW
    assert task.submitted_at is not None


@pytest.mark.django_db
def test_employee_cannot_set_done_directly(client, manager, employee):
    task = Task.objects.create(title="Нельзя закрыть", created_by=manager, assigned_to=employee, status=Task.Status.IN_PROGRESS)
    client.force_login(employee)
    response = client.post(reverse("task_edit", args=[task.pk]), {"status": Task.Status.DONE})
    assert response.status_code == 200
    task.refresh_from_db()
    assert task.status == Task.Status.IN_PROGRESS


@pytest.mark.django_db
def test_manager_accepts_review(client, manager, employee):
    task = Task.objects.create(title="Принять", created_by=manager, assigned_to=employee, status=Task.Status.REVIEW)
    client.force_login(manager)
    response = client.post(reverse("task_accept", args=[task.pk]))
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.status == Task.Status.DONE
    assert task.completed_at is not None
    assert Notification.objects.filter(task=task, user=employee, kind=Notification.Kind.ACCEPTED).exists()


@pytest.mark.django_db
def test_revision_reason_is_required(client, manager, employee):
    task = Task.objects.create(title="Проверка", created_by=manager, assigned_to=employee, status=Task.Status.REVIEW)
    client.force_login(manager)
    response = client.post(reverse("task_request_revision", args=[task.pk]), {"revision_reason": ""})
    assert response.status_code == 400
    task.refresh_from_db()
    assert task.status == Task.Status.REVIEW


@pytest.mark.django_db
def test_manager_returns_task_with_reason_and_history(client, manager, employee):
    task = Task.objects.create(title="Исправить", created_by=manager, assigned_to=employee, status=Task.Status.REVIEW)
    client.force_login(manager)
    response = client.post(
        reverse("task_request_revision", args=[task.pk]),
        {"revision_reason": "Добавить результаты измерений"},
    )
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.status == Task.Status.REVISION
    assert task.revision_reason == "Добавить результаты измерений"
    event = TaskEvent.objects.filter(task=task, kind=TaskEvent.Kind.STATUS).first()
    assert event.actor == manager
    assert "Добавить результаты измерений" in event.message


@pytest.mark.django_db
def test_due_date_change_is_written_to_history(client, manager, employee):
    task = Task.objects.create(title="Срок", created_by=manager, assigned_to=employee)
    client.force_login(manager)
    response = client.post(
        reverse("task_edit", args=[task.pk]),
        {
            "title": task.title,
            "description": "",
            "assigned_to": employee.pk,
            "status": Task.Status.NEW,
            "priority": Task.Priority.NORMAL,
            "effort": Task.Effort.MEDIUM,
            "start_date": "",
            "due_date": "2030-01-10",
        },
    )
    assert response.status_code == 302
    event = TaskEvent.objects.filter(task=task, kind=TaskEvent.Kind.DUE_DATE).first()
    assert event is not None
    assert event.actor == manager


@pytest.mark.django_db
def test_review_queue_is_manager_only(client, manager, employee):
    Task.objects.create(title="Очередь", created_by=manager, assigned_to=employee, status=Task.Status.REVIEW)
    client.force_login(manager)
    response = client.get(reverse("review_queue"))
    assert response.status_code == 200
    assert "Очередь" in response.content.decode()

    client.force_login(employee)
    response = client.get(reverse("review_queue"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_workload_all_scope_can_show_completed_task(manager, employee):
    from django.utils import timezone

    today = timezone.localdate()
    task = Task.objects.create(
        title="Историческая",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.DONE,
        start_date=today,
        due_date=today,
    )
    current_rows = get_workload_timeline(today, today, include_all=False)
    all_rows = get_workload_timeline(today, today, include_all=True)

    current_tasks = [cell.task for row in current_rows for lane in row.lanes for cell in lane if cell.kind == "task"]
    all_tasks = [cell.task for row in all_rows for lane in row.lanes for cell in lane if cell.kind == "task"]
    assert task not in current_tasks
    assert task in all_tasks


@pytest.mark.django_db
def test_task_filters_have_no_apply_button(client, manager):
    client.force_login(manager)
    response = client.get(reverse("task_list"))
    assert "Применить" not in response.content.decode()
