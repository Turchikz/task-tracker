"""Task collaboration and handover regression tests for v0.8.3."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse
from django.utils import timezone

from tasks.constants import EMPLOYEES_GROUP, MANAGERS_GROUP
from tasks.models import Notification, Task, TaskEvent, TaskHandover
from tasks.services import get_workload_ranking, get_workload_timeline


@pytest.mark.django_db
def test_existing_single_assignee_remains_compatible(manager, employee):
    task = Task.objects.create(title="Старая задача", created_by=manager, assigned_to=employee)
    assert task.team_members == [employee]
    assert task.additional_assignees.count() == 0
    assert task.has_assignee(employee)


@pytest.mark.django_db
def test_create_with_multiple_assignees(client, manager, employee, second_employee):
    client.force_login(manager)
    resp = client.post(reverse("task_create"), {
        "title": "Общая проверка", "description": "",
        "assigned_to": employee.pk, "additional_assignees": [second_employee.pk],
        "priority": Task.Priority.NORMAL, "effort": Task.Effort.MEDIUM,
        "start_date": "", "due_date": "",
    })
    assert resp.status_code == 302
    task = Task.objects.get(title="Общая проверка")
    assert task.assigned_to_id == employee.pk
    assert list(task.additional_assignees.all()) == [second_employee]
    assert Notification.objects.filter(
        user=second_employee, task=task, kind=Notification.Kind.ASSIGNED,
    ).exists()


@pytest.mark.django_db
def test_coworker_sees_only_own_tasks(client, manager, employee, second_employee):
    common = Task.objects.create(title="Командная", created_by=manager, assigned_to=employee)
    common.additional_assignees.add(second_employee)
    other = Task.objects.create(title="Только Иванов", created_by=manager, assigned_to=employee)
    client.force_login(second_employee)
    result = client.get(reverse("task_list"))
    assert common.title in result.content.decode()
    assert other.title not in result.content.decode()
    assert client.get(reverse("task_detail", args=[common.pk])).status_code == 200
    assert client.get(reverse("task_detail", args=[other.pk])).status_code == 404


@pytest.mark.django_db
def test_coworker_can_start_and_submit_for_review(client, manager, employee, second_employee):
    task = Task.objects.create(title="Работают вместе", created_by=manager, assigned_to=employee)
    task.additional_assignees.add(second_employee)
    client.force_login(second_employee)
    assert client.post(reverse("task_quick_action", args=[task.pk]), {"action": "start"}).status_code == 302
    task.refresh_from_db()
    assert task.status == Task.Status.IN_PROGRESS
    assert client.post(reverse("task_quick_action", args=[task.pk]), {"action": "submit"}).status_code == 302
    task.refresh_from_db()
    assert task.status == Task.Status.REVIEW
    assert Notification.objects.filter(
        user=manager, task=task, kind=Notification.Kind.SUBMITTED_REVIEW,
    ).exists()


@pytest.mark.django_db
def test_coworker_is_in_workload_and_today(client, manager, employee, second_employee):
    today = timezone.localdate()
    task = Task.objects.create(
        title="На двоих", created_by=manager, assigned_to=employee,
        start_date=today, due_date=today + timedelta(days=2),
    )
    task.additional_assignees.add(second_employee)
    scores = {row.user.pk: row for row in get_workload_ranking()}
    assert scores[employee.pk].active_count == 1
    assert scores[second_employee.pk].active_count == 1
    timeline = get_workload_timeline(today, today + timedelta(days=3))
    user_rows = {row.workload.user.pk: row for row in timeline}
    assert any(cell.task and cell.task.pk == task.pk for lane in user_rows[employee.pk].lanes for cell in lane)
    assert any(cell.task and cell.task.pk == task.pk for lane in user_rows[second_employee.pk].lanes for cell in lane)
    client.force_login(second_employee)
    assert task.title in client.get(reverse("my_today")).content.decode()


@pytest.mark.django_db
def test_handover_sick_leave_preserves_task(client, manager, employee, second_employee):
    today = timezone.localdate()
    task = Task.objects.create(
        title="На 10 дней", created_by=manager, assigned_to=employee,
        start_date=today - timedelta(days=4), due_date=today + timedelta(days=5),
        status=Task.Status.IN_PROGRESS,
    )
    task_started = task.started_at
    client.force_login(manager)
    response = client.post(reverse("task_handover", args=[task.pk]), {
        "to_employee": second_employee.pk, "reason": "Больничный",
    })
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.pk == Task.objects.get(title="На 10 дней").pk
    assert task.assigned_to_id == second_employee.pk
    assert task.status == Task.Status.IN_PROGRESS
    assert task.started_at == task_started
    assert task.due_date == today + timedelta(days=5)
    assert not task.has_assignee(employee)
    handover = TaskHandover.objects.get(task=task)
    assert handover.from_employee == employee
    assert handover.to_employee == second_employee
    assert handover.reason == "Больничный"
    assert TaskEvent.objects.filter(task=task, kind=TaskEvent.Kind.HANDOVER).exists()
    assert Notification.objects.filter(user=second_employee, task=task, kind=Notification.Kind.ASSIGNED).exists()
    client.force_login(employee)
    assert client.get(reverse("task_detail", args=[task.pk])).status_code == 404
    client.force_login(second_employee)
    assert client.get(reverse("task_detail", args=[task.pk])).status_code == 200


@pytest.mark.django_db
def test_handover_can_keep_previous_coworker(client, manager, employee, second_employee):
    task = Task.objects.create(title="Совместная передача", created_by=manager, assigned_to=employee)
    client.force_login(manager)
    response = client.post(reverse("task_handover", args=[task.pk]), {
        "to_employee": second_employee.pk, "reason": "Перераспределение",
        "keep_previous": "on",
    })
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.assigned_to == second_employee
    assert task.has_assignee(employee)
    assert TaskHandover.objects.get(task=task).keep_previous is True


@pytest.mark.django_db
def test_handover_requires_manager_and_reason(client, manager, employee, second_employee):
    task = Task.objects.create(title="Запрет", created_by=manager, assigned_to=employee)
    client.force_login(employee)
    response = client.post(reverse("task_handover", args=[task.pk]), {
        "to_employee": second_employee.pk, "reason": "Больничный",
    })
    assert response.status_code == 403
    client.force_login(manager)
    response = client.post(reverse("task_handover", args=[task.pk]), {
        "to_employee": second_employee.pk, "reason": "",
    })
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.assigned_to == employee
    assert not TaskHandover.objects.filter(task=task).exists()


@pytest.mark.django_db
def test_other_manager_cannot_handover(client, manager, employee, second_employee):
    group, _ = Group.objects.get_or_create(name=MANAGERS_GROUP)
    foreign = User.objects.create_user("foreign_mgr", password="secret")
    foreign.groups.add(group)
    task = Task.objects.create(title="Не его", created_by=manager, assigned_to=employee)
    client.force_login(foreign)
    response = client.post(reverse("task_handover", args=[task.pk]), {
        "to_employee": second_employee.pk, "reason": "Больничный",
    })
    assert response.status_code == 403
    task.refresh_from_db()
    assert task.assigned_to == employee


@pytest.mark.django_db
def test_completed_task_is_not_transferable(client, manager, employee, second_employee):
    task = Task.objects.create(
        title="Уже завершено", created_by=manager, assigned_to=employee, status=Task.Status.DONE,
    )
    client.force_login(manager)
    response = client.post(reverse("task_handover", args=[task.pk]), {
        "to_employee": second_employee.pk, "reason": "Больничный",
    })
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.assigned_to_id == employee.pk
    assert not TaskHandover.objects.filter(task=task).exists()


@pytest.mark.django_db
def test_handover_promotes_existing_coworker_without_duplication(client, manager, employee, second_employee):
    task = Task.objects.create(title="Уже в команде", created_by=manager, assigned_to=employee)
    task.additional_assignees.add(second_employee)
    client.force_login(manager)
    response = client.post(reverse("task_handover", args=[task.pk]), {
        "to_employee": second_employee.pk, "reason": "Больничный",
    })
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.team_members == [second_employee]
    assert task.additional_assignees.count() == 0


@pytest.mark.django_db
def test_team_comments_notify_manager_and_all_workers(client, manager, employee, second_employee):
    task = Task.objects.create(title="Командные комментарии", created_by=manager, assigned_to=employee)
    task.additional_assignees.add(second_employee)
    client.force_login(manager)
    response = client.post(reverse("task_comment_add", args=[task.pk]), {"text": "Ответ руководителя"})
    assert response.status_code == 302
    assert Notification.objects.filter(user=employee, task=task, kind=Notification.Kind.COMMENT).exists()
    assert Notification.objects.filter(user=second_employee, task=task, kind=Notification.Kind.COMMENT).exists()


@pytest.mark.django_db
def test_form_manager_can_add_coworker_to_existing_task(client, manager, employee, second_employee):
    task = Task.objects.create(title="Редактируем состав", created_by=manager, assigned_to=employee)
    client.force_login(manager)
    response = client.post(reverse("task_edit", args=[task.pk]), {
        "title": task.title, "description": "", "responsible_manager": manager.pk,
        "assigned_to": employee.pk, "additional_assignees": [second_employee.pk],
        "status": Task.Status.NEW, "priority": Task.Priority.NORMAL,
        "effort": Task.Effort.MEDIUM, "start_date": "", "due_date": "",
    })
    assert response.status_code == 302
    assert task.additional_assignees.filter(pk=second_employee.pk).exists()


@pytest.mark.django_db
def test_primary_cannot_be_silently_changed_in_edit_form(client, manager, employee, second_employee):
    task = Task.objects.create(title="Без скрытой передачи", created_by=manager, assigned_to=employee)
    client.force_login(manager)
    response = client.post(reverse("task_edit", args=[task.pk]), {
        "title": task.title, "description": "", "responsible_manager": manager.pk,
        "assigned_to": second_employee.pk,
        "status": Task.Status.NEW, "priority": Task.Priority.NORMAL,
        "effort": Task.Effort.MEDIUM, "start_date": "", "due_date": "",
    })
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.assigned_to == employee
