"""RaTracker v0.9.0 regression tests for staffing, teamwork, export and monitoring."""
from datetime import timedelta
from io import BytesIO
import json
from zipfile import ZipFile

import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse
from django.utils import timezone

from tasks.constants import EMPLOYEES_GROUP
from tasks.forms import TaskCreateForm, TaskForm
from tasks.models import EmployeeAbsence, Notification, Task, TaskMemberProgress, TaskHandover
from tasks.absence_planning import affected_tasks_for_absences
from tasks.backup_monitor import get_backup_status
from tasks.services import get_workload_ranking


@pytest.mark.django_db
def test_primary_is_not_in_additional_assignees_form(manager, employee, second_employee):
    form = TaskCreateForm(initial={"assigned_to": employee.pk})
    assert employee.pk not in set(form.fields["additional_assignees"].queryset.values_list("pk", flat=True))
    assert second_employee.pk in set(form.fields["additional_assignees"].queryset.values_list("pk", flat=True))
    existing = Task.objects.create(title="Редактирование", created_by=manager, assigned_to=employee)
    form_edit = TaskForm(instance=existing)
    assert employee.pk not in set(form_edit.fields["additional_assignees"].queryset.values_list("pk", flat=True))


@pytest.mark.django_db
def test_new_task_progress_records_and_individual_status(client, manager, employee, second_employee):
    task = Task.objects.create(title="Общая работа", created_by=manager, assigned_to=employee)
    task.additional_assignees.add(second_employee)
    assert TaskMemberProgress.objects.filter(task=task).count() == 2
    client.force_login(second_employee)
    result = client.post(reverse("task_member_progress_update", args=[task.pk]), {"state": "ready"})
    assert result.status_code == 302
    assert TaskMemberProgress.objects.get(task=task, user=second_employee).state == "ready"
    assert TaskMemberProgress.objects.get(task=task, user=employee).state == "pending"
    # Main workflow is intentionally unchanged: status belongs to whole task.
    assert Task.objects.get(pk=task.pk).status == Task.Status.NEW
    assert "Готовность участников" in client.get(reverse("task_detail", args=[task.pk])).content.decode()


@pytest.mark.django_db
def test_stranger_cannot_set_progress(client, manager, employee, second_employee):
    task = Task.objects.create(title="Только одному", created_by=manager, assigned_to=employee)
    client.force_login(second_employee)
    response = client.post(reverse("task_member_progress_update", args=[task.pk]), {"state": "ready"})
    assert response.status_code in (403, 404)


@pytest.mark.django_db
def test_absence_recommendation_and_primary_transfer(client, manager, employee, second_employee):
    today = timezone.localdate()
    task = Task.objects.create(
        title="Срок во время больничного", created_by=manager, assigned_to=employee,
        status=Task.Status.IN_PROGRESS,
        start_date=today - timedelta(days=2), due_date=today + timedelta(days=8),
    )
    EmployeeAbsence.objects.create(
        user=employee, start_date=today, end_date=today + timedelta(days=6), created_by=manager,
        reason="Больничный",
    )
    proposals = affected_tasks_for_absences(manager)
    match = next(item for item in proposals if item["task"].pk == task.pk)
    assert match["is_primary"]
    assert match["suggestion"].user == second_employee
    client.force_login(manager)
    response = client.get(reverse("absences"))
    assert "Задачи, затронутые отсутствиями" in response.content.decode()
    response = client.post(reverse("task_handover", args=[task.pk]), {
        "to_employee": second_employee.pk, "reason": match["reason"],
    })
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.assigned_to == second_employee
    assert TaskHandover.objects.filter(task=task, from_employee=employee).exists()


@pytest.mark.django_db
def test_absence_recommendation_additional_replacement(client, manager, employee, second_employee):
    group, _ = Group.objects.get_or_create(name=EMPLOYEES_GROUP)
    substitute = User.objects.create_user(username="replacement", password="pass12345")
    substitute.groups.add(group)
    today = timezone.localdate()
    task = Task.objects.create(title="Соисполнитель отсутствует", created_by=manager,
                               assigned_to=employee, due_date=today + timedelta(days=3))
    task.additional_assignees.add(second_employee)
    EmployeeAbsence.objects.create(user=second_employee, start_date=today,
                                   end_date=today + timedelta(days=2), created_by=manager)
    items = affected_tasks_for_absences(manager)
    match = next(i for i in items if i["task"].pk == task.pk)
    assert not match["is_primary"]
    assert substitute.pk in [row.user.pk for row in match["replacement_options"]]
    client.force_login(manager)
    response = client.post(reverse("task_substitute", args=[task.pk]), {
        "from_employee": second_employee.pk, "to_employee": substitute.pk,
        "reason": "Больничный",
    })
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.assigned_to == employee
    assert task.additional_assignees.filter(pk=substitute.pk).exists()
    assert not task.additional_assignees.filter(pk=second_employee.pk).exists()
    assert TaskMemberProgress.objects.filter(task=task, user=substitute).exists()


@pytest.mark.django_db
def test_excel_export_is_xlsx_and_manager_only(client, manager, employee):
    Task.objects.create(title="Тест Excel", created_by=manager, assigned_to=employee)
    client.force_login(employee)
    assert client.get(reverse("analytics_export")).status_code == 403
    client.force_login(manager)
    response = client.get(reverse("analytics_export"))
    assert response.status_code == 200
    assert response.content.startswith(b"PK")
    with ZipFile(BytesIO(response.content)) as z:
        assert "xl/workbook.xml" in z.namelist()
        workbook_xml = z.read("xl/workbook.xml").decode()
        assert "Обзор" in workbook_xml
        assert "Сотрудники" in workbook_xml
        assert "Текущая загрузка" in workbook_xml


def test_backup_metadata_is_safe_and_marks_stale(tmp_path):
    status_file = tmp_path / "backup_status.json"
    assert get_backup_status(status_file)["state"] == "unknown"
    status_file.write_text(json.dumps({
        "completed_at": (timezone.now() - timedelta(days=3)).isoformat(),
        "archive_name": "testbackup.tar.gz", "size_bytes": 4096,
        "media_included": True, "sha256": "a" * 64, "host_os": "Windows",
    }), encoding="utf-8")
    status = get_backup_status(status_file)
    assert status["state"] == "stale"
    assert status["archive_name"] == "testbackup.tar.gz"


@pytest.mark.django_db
def test_backup_screen_superuser_only(client, manager, employee):
    client.force_login(manager)
    assert client.get(reverse("backup_monitor")).status_code == 403
    admin = User.objects.create_superuser(username="root_v090", password="pass12345", email="a@example.com")
    client.force_login(admin)
    assert client.get(reverse("backup_monitor")).status_code == 200


@pytest.mark.django_db
def test_notification_drawer_only_current_user(client, manager, employee, second_employee):
    own_task = Task.objects.create(title="Свой сигнал", created_by=manager, assigned_to=employee)
    other_task = Task.objects.create(title="Чужой сигнал", created_by=manager, assigned_to=second_employee)
    client.force_login(employee)
    html = client.get(reverse("my_today")).content.decode()
    assert "notification-drawer" in html
    assert "Свой сигнал" in html
    assert "Чужой сигнал" not in html


@pytest.mark.django_db
def test_load_heat_level_consistent(manager, employee):
    ranking = get_workload_ranking()
    entry = next(item for item in ranking if item.user.pk == employee.pk)
    assert entry.load_level in {"low", "moderate", "high", "absent"}
    assert 0 <= entry.load_percent <= 100
