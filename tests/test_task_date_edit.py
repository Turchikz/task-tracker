from datetime import date

import pytest
from django.contrib.auth.models import Group, User

from tasks.constants import EMPLOYEES_GROUP
from tasks.forms import TaskForm
from tasks.models import Task


@pytest.mark.django_db
def test_task_edit_form_renders_existing_dates_as_html5_iso_values():
    employees, _ = Group.objects.get_or_create(name=EMPLOYEES_GROUP)
    manager = User.objects.create_user(username="manager")
    employee = User.objects.create_user(username="employee")
    employee.groups.add(employees)

    task = Task.objects.create(
        title="Проверка дат",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.NEW,
        priority=Task.Priority.NORMAL,
        effort=Task.Effort.MEDIUM,
        start_date=date(2026, 10, 21),
        due_date=date(2026, 10, 30),
    )

    form = TaskForm(instance=task)
    html = form.as_p()

    assert 'name="start_date"' in html
    assert 'value="2026-10-21"' in html
    assert 'name="due_date"' in html
    assert 'value="2026-10-30"' in html


@pytest.mark.django_db
def test_task_form_preserves_dates_when_manager_saves_edit():
    employees, _ = Group.objects.get_or_create(name=EMPLOYEES_GROUP)
    manager = User.objects.create_user(username="manager")
    employee = User.objects.create_user(username="employee")
    employee.groups.add(employees)

    task = Task.objects.create(
        title="Исходная задача",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.NEW,
        priority=Task.Priority.NORMAL,
        effort=Task.Effort.MEDIUM,
        start_date=date(2026, 10, 21),
        due_date=date(2026, 10, 30),
    )

    form = TaskForm(
        data={
            "title": "Изменённая задача",
            "description": "",
            "assigned_to": employee.pk,
            "status": Task.Status.NEW,
            "priority": Task.Priority.NORMAL,
            "effort": Task.Effort.MEDIUM,
            "start_date": "2026-10-21",
            "due_date": "2026-10-30",
        },
        instance=task,
    )

    assert form.is_valid(), form.errors
    saved = form.save()

    assert saved.start_date == date(2026, 10, 21)
    assert saved.due_date == date(2026, 10, 30)
