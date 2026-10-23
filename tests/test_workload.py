from datetime import timedelta

import pytest
from django.utils import timezone

from tasks.models import Task
from tasks.services import get_workload_ranking, task_load_score


@pytest.mark.django_db
def test_workload_ranking_less_loaded_first(manager, employee, second_employee):
    Task.objects.create(
        title="Лёгкая",
        created_by=manager,
        assigned_to=employee,
        priority=Task.Priority.LOW,
        effort=Task.Effort.SMALL,
        due_date=timezone.localdate() + timedelta(days=10),
    )
    Task.objects.create(
        title="Срочная большая",
        created_by=manager,
        assigned_to=second_employee,
        priority=Task.Priority.URGENT,
        effort=Task.Effort.XLARGE,
        due_date=timezone.localdate(),
        status=Task.Status.IN_PROGRESS,
    )

    ranking = get_workload_ranking()
    assert ranking[0].user == employee
    assert ranking[1].user == second_employee
    assert ranking[0].score < ranking[1].score


@pytest.mark.django_db
def test_completed_task_does_not_add_load(manager, employee):
    task = Task.objects.create(
        title="Готово",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.DONE,
        priority=Task.Priority.URGENT,
        effort=Task.Effort.XLARGE,
    )
    assert task_load_score(task) == 0

@pytest.mark.django_db
def test_create_form_orders_assignees_by_workload(manager, employee, second_employee):
    from tasks.forms import TaskCreateForm

    Task.objects.create(
        title="Нагрузка второго",
        created_by=manager,
        assigned_to=second_employee,
        priority=Task.Priority.URGENT,
        effort=Task.Effort.XLARGE,
        due_date=timezone.localdate(),
    )
    form = TaskCreateForm()
    ids = list(form.fields["assigned_to"].queryset.values_list("id", flat=True))
    assert ids == [employee.id, second_employee.id]


@pytest.mark.django_db
def test_overlapping_tasks_use_separate_timeline_lanes(manager, employee):
    from tasks.services import build_timeline_lanes

    today = timezone.localdate()
    first = Task.objects.create(
        title="Первая",
        created_by=manager,
        assigned_to=employee,
        start_date=today,
        due_date=today + timedelta(days=3),
    )
    second = Task.objects.create(
        title="Вторая",
        created_by=manager,
        assigned_to=employee,
        start_date=today + timedelta(days=2),
        due_date=today + timedelta(days=5),
    )

    lanes = build_timeline_lanes([first, second], today, today + timedelta(days=10))
    assert len(lanes) == 2


@pytest.mark.django_db
def test_non_overlapping_tasks_share_timeline_lane(manager, employee):
    from tasks.services import build_timeline_lanes

    today = timezone.localdate()
    first = Task.objects.create(
        title="Первая",
        created_by=manager,
        assigned_to=employee,
        start_date=today,
        due_date=today + timedelta(days=1),
    )
    second = Task.objects.create(
        title="Вторая",
        created_by=manager,
        assigned_to=employee,
        start_date=today + timedelta(days=2),
        due_date=today + timedelta(days=4),
    )

    lanes = build_timeline_lanes([first, second], today, today + timedelta(days=10))
    assert len(lanes) == 1
    task_cells = [cell for cell in lanes[0] if cell.kind == "task"]
    assert [cell.task for cell in task_cells] == [first, second]

@pytest.mark.django_db
def test_reviewed_task_does_not_add_employee_load(manager, employee):
    task = Task.objects.create(
        title="На проверке",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.REVIEW,
        priority=Task.Priority.URGENT,
        effort=Task.Effort.XLARGE,
        due_date=timezone.localdate(),
    )
    assert task_load_score(task) == 0


@pytest.mark.django_db
def test_all_timeline_can_include_completed_tasks(manager, employee):
    from tasks.services import get_workload_timeline

    today = timezone.localdate()
    completed = Task.objects.create(
        title="Архивная задача",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.DONE,
        start_date=today,
        due_date=today + timedelta(days=2),
    )

    current_rows = get_workload_timeline(today, today + timedelta(days=5), include_all=False)
    all_rows = get_workload_timeline(today, today + timedelta(days=5), include_all=True)

    current_tasks = [cell.task for row in current_rows for lane in row.lanes for cell in lane if cell.kind == "task"]
    all_tasks = [cell.task for row in all_rows for lane in row.lanes for cell in lane if cell.kind == "task"]
    assert completed not in current_tasks
    assert completed in all_tasks
