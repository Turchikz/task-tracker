import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from tasks.constants import MANAGERS_GROUP
from tasks.models import SavedTaskFilter, Task, TaskComment
from tasks.permissions import can_manage_task


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
def test_new_task_defaults_responsible_manager_to_creator(manager, employee):
    task = Task.objects.create(
        title="Ответственный по умолчанию",
        created_by=manager,
        assigned_to=employee,
    )
    assert task.responsible_manager_id == manager.id


@pytest.mark.django_db
def test_responsible_manager_controls_permissions(manager, second_manager, employee):
    task = Task.objects.create(
        title="Переданная задача",
        created_by=manager,
        responsible_manager=second_manager,
        assigned_to=employee,
    )
    assert not can_manage_task(manager, task)
    assert can_manage_task(second_manager, task)


@pytest.mark.django_db
def test_bulk_priority_update_only_for_responsible_manager(client, manager, second_manager, employee):
    own = Task.objects.create(
        title="Своя",
        created_by=manager,
        responsible_manager=manager,
        assigned_to=employee,
        priority=Task.Priority.NORMAL,
    )
    foreign = Task.objects.create(
        title="Чужая",
        created_by=manager,
        responsible_manager=second_manager,
        assigned_to=employee,
        priority=Task.Priority.NORMAL,
    )
    client.force_login(manager)

    response = client.post(
        reverse("task_bulk_update"),
        {
            "task_ids": [str(own.pk)],
            "action": "priority",
            "priority": Task.Priority.URGENT,
        },
    )
    assert response.status_code == 302
    own.refresh_from_db()
    assert own.priority == Task.Priority.URGENT

    response = client.post(
        reverse("task_bulk_update"),
        {
            "task_ids": [str(foreign.pk)],
            "action": "priority",
            "priority": Task.Priority.HIGH,
        },
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_saved_filters_are_private_per_user(client, manager, employee):
    client.force_login(manager)
    response = client.post(
        reverse("saved_filter_create"),
        {
            "name": "Срочные",
            "query_string": "priority=urgent&quick=current&unexpected=drop-me",
        },
    )
    assert response.status_code == 302
    saved = SavedTaskFilter.objects.get(user=manager, name="Срочные")
    assert saved.parameters == {"priority": "urgent", "quick": "current"}

    client.force_login(employee)
    response = client.get(reverse("saved_filter_apply", args=[saved.pk]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_global_search_respects_employee_visibility(client, manager, employee, second_employee):
    visible = Task.objects.create(
        title="Поверка манометра",
        description="Уникальный маркер alfa-search",
        created_by=manager,
        assigned_to=employee,
    )
    hidden = Task.objects.create(
        title="Чужая задача",
        description="Уникальный маркер alfa-search",
        created_by=manager,
        assigned_to=second_employee,
    )
    TaskComment.objects.create(task=visible, author=manager, text="комментарий beta-search")

    client.force_login(employee)
    response = client.get(reverse("global_search"), {"q": "alfa-search"})
    content = response.content.decode("utf-8")
    assert response.status_code == 200
    assert visible.title in content
    assert hidden.title not in content

    response = client.get(reverse("global_search"), {"q": "beta-search"})
    assert visible.title in response.content.decode("utf-8")

@pytest.mark.django_db
def test_review_notification_goes_to_responsible_manager_not_creator(
    manager, second_manager, employee
):
    task = Task.objects.create(
        title="Проверка другим руководителем",
        created_by=manager,
        responsible_manager=second_manager,
        assigned_to=employee,
        status=Task.Status.IN_PROGRESS,
    )
    task.status = Task.Status.REVIEW
    task._change_actor = employee
    task.save()

    from tasks.models import Notification

    assert Notification.objects.filter(
        user=second_manager,
        task=task,
        kind=Notification.Kind.SUBMITTED_REVIEW,
    ).exists()
    assert not Notification.objects.filter(
        user=manager,
        task=task,
        kind=Notification.Kind.SUBMITTED_REVIEW,
    ).exists()
