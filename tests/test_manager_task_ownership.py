import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from tasks.constants import MANAGERS_GROUP
from tasks.models import Notification, Task


@pytest.fixture
def second_manager(db):
    group, _ = Group.objects.get_or_create(name=MANAGERS_GROUP)
    user = User.objects.create_user(
        username="manager2",
        password="pass12345",
        first_name="Мария",
        last_name="Руководитель",
    )
    user.groups.add(group)
    return user


@pytest.mark.django_db
def test_other_manager_can_view_but_cannot_edit(
    client, manager, second_manager, employee
):
    task = Task.objects.create(
        title="Задача manager 1",
        created_by=manager,
        assigned_to=employee,
    )
    client.force_login(second_manager)

    assert client.get(reverse("task_detail", args=[task.pk])).status_code == 200
    assert client.get(reverse("task_edit", args=[task.pk])).status_code == 403


@pytest.mark.django_db
def test_other_manager_cannot_close_task(
    client, manager, second_manager, employee
):
    task = Task.objects.create(
        title="Чужая задача",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.IN_PROGRESS,
    )
    client.force_login(second_manager)

    response = client.post(
        reverse("task_quick_action", args=[task.pk]),
        {"action": "done"},
    )

    assert response.status_code == 403
    task.refresh_from_db()
    assert task.status == Task.Status.IN_PROGRESS


@pytest.mark.django_db
def test_review_notification_only_for_creator(
    manager, second_manager, employee
):
    task = Task.objects.create(
        title="Проверить",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.IN_PROGRESS,
    )

    task.status = Task.Status.REVIEW
    task._change_actor = employee
    task.save()

    assert Notification.objects.filter(
        user=manager,
        task=task,
        kind=Notification.Kind.SUBMITTED_REVIEW,
    ).exists()

    assert not Notification.objects.filter(
        user=second_manager,
        task=task,
        kind=Notification.Kind.SUBMITTED_REVIEW,
    ).exists()


@pytest.mark.django_db
def test_review_queue_only_own_tasks(
    client, manager, second_manager, employee
):
    own = Task.objects.create(
        title="Моя проверка",
        created_by=manager,
        assigned_to=employee,
        status=Task.Status.REVIEW,
    )
    other = Task.objects.create(
        title="Чужая проверка",
        created_by=second_manager,
        assigned_to=employee,
        status=Task.Status.REVIEW,
    )

    client.force_login(manager)
    response = client.get(reverse("review_queue"))
    content = response.content.decode("utf-8")

    assert own.title in content
    assert other.title not in content


@pytest.mark.django_db
def test_other_manager_detail_is_read_only(client, manager, second_manager, employee):
    task = Task.objects.create(
        title="Только просмотр",
        created_by=manager,
        assigned_to=employee,
    )
    client.force_login(second_manager)

    response = client.get(reverse("task_detail", args=[task.pk]))
    content = response.content.decode("utf-8")

    assert response.status_code == 200
    assert "Для вас она доступна только для просмотра" in content
    assert "Редактировать" not in content


@pytest.mark.django_db
def test_other_manager_cannot_comment(client, manager, second_manager, employee):
    task = Task.objects.create(
        title="Чужая задача",
        created_by=manager,
        assigned_to=employee,
    )
    client.force_login(second_manager)

    response = client.post(
        reverse("task_comment_add", args=[task.pk]),
        {"text": "Не должен сохраниться"},
    )

    assert response.status_code == 403
    assert task.comments.count() == 0
