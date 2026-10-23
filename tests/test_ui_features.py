import pytest
from django.urls import reverse

from tasks.models import Task, TaskComment


@pytest.mark.django_db
def test_employee_can_add_comment_to_own_task(client, manager, employee):
    task = Task.objects.create(title="Комментарий", created_by=manager, assigned_to=employee)
    client.force_login(employee)

    response = client.post(reverse("task_comment_add", args=[task.pk]), {"text": "Проверил исходные данные."})

    assert response.status_code == 302
    comment = TaskComment.objects.get(task=task)
    assert comment.author == employee
    assert comment.text == "Проверил исходные данные."


@pytest.mark.django_db
def test_employee_cannot_comment_other_employee_task(client, manager, employee, second_employee):
    task = Task.objects.create(title="Чужая", created_by=manager, assigned_to=second_employee)
    client.force_login(employee)

    response = client.post(reverse("task_comment_add", args=[task.pk]), {"text": "Не должен добавиться"})

    assert response.status_code == 404
    assert not TaskComment.objects.filter(task=task).exists()


@pytest.mark.django_db
def test_employee_quick_actions_start_and_submit(client, manager, employee):
    task = Task.objects.create(title="Быстрые действия", created_by=manager, assigned_to=employee)
    client.force_login(employee)

    response = client.post(reverse("task_quick_action", args=[task.pk]), {"action": "start"})
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.status == Task.Status.IN_PROGRESS
    assert task.started_at is not None

    response = client.post(reverse("task_quick_action", args=[task.pk]), {"action": "submit"})
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.status == Task.Status.REVIEW
    assert task.submitted_at is not None


@pytest.mark.django_db
def test_manager_quick_accepts_review_task(client, manager, employee):
    task = Task.objects.create(
        title="На проверке",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.REVIEW,
    )
    client.force_login(manager)

    response = client.post(reverse("task_quick_action", args=[task.pk]), {"action": "accept"})

    assert response.status_code == 302
    task.refresh_from_db()
    assert task.status == Task.Status.DONE
    assert task.completed_at is not None


@pytest.mark.django_db
def test_employee_kanban_shows_only_own_tasks(client, manager, employee, second_employee):
    mine = Task.objects.create(title="Моя канбан", created_by=manager, assigned_to=employee)
    other = Task.objects.create(title="Чужая канбан", created_by=manager, assigned_to=second_employee)
    client.force_login(employee)

    response = client.get(reverse("kanban"))
    content = response.content.decode()

    assert response.status_code == 200
    assert mine.title in content
    assert other.title not in content


@pytest.mark.django_db
def test_task_list_current_chip_hides_done_tasks(client, manager, employee):
    active = Task.objects.create(title="Текущая", created_by=manager, assigned_to=employee)
    done = Task.objects.create(title="Архивная", created_by=manager, assigned_to=employee, status=Task.Status.DONE)
    client.force_login(employee)

    response = client.get(reverse("task_list"), {"quick": "current"})
    content = response.content.decode()

    assert active.title in content
    assert done.title not in content
