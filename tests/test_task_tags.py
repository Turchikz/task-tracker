from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from tasks.models import Task, TaskTag


@pytest.mark.django_db
def test_manager_can_create_and_reuse_project_tags(client, manager, employee):
    client.force_login(manager)
    payload = {
        "title": "Проверить документы проекта",
        "description": "",
        "assigned_to": employee.pk,
        "priority": Task.Priority.NORMAL,
        "effort": Task.Effort.MEDIUM,
        "start_date": "",
        "due_date": "",
        "tags": "1202.55 ООО Ачимгаз",
    }

    response = client.post(reverse("task_create"), payload)
    assert response.status_code == 302
    first = Task.objects.get(title=payload["title"])
    tag = first.tags.get()
    assert tag.name == "1202.55 ООО Ачимгаз"

    payload["title"] = "Согласовать план проекта"
    payload["tags"] = "1202.55 ооо АЧИМГАЗ"
    response = client.post(reverse("task_create"), payload)
    assert response.status_code == 302
    second = Task.objects.get(title=payload["title"])
    assert second.tags.get() == tag
    assert TaskTag.objects.count() == 1


@pytest.mark.django_db
def test_project_tag_can_be_selected_and_used_as_task_list_filter(client, manager, employee):
    tag = TaskTag.objects.create(name="1202.55 ООО Ачимгаз")
    matching = Task.objects.create(title="Ачимгаз — план", created_by=manager, assigned_to=employee)
    matching.tags.add(tag)
    other = Task.objects.create(title="Другая задача", created_by=manager, assigned_to=employee)
    client.force_login(manager)

    response = client.get(reverse("task_list"), {"tag": tag.pk})
    content = response.content.decode()
    assert response.status_code == 200
    assert matching.title in content
    assert other.title not in content
    assert "1202.55 ООО Ачимгаз" in content

    edit = client.get(reverse("task_edit", args=[matching.pk]))
    edit_content = edit.content.decode()
    assert 'name="tags"' in edit_content
    assert 'list="task-tag-options"' in edit_content
    assert 'value="1202.55 ООО Ачимгаз"' in edit_content


@pytest.mark.django_db
def test_soon_quick_filter_includes_next_seven_days_only(client, manager, employee):
    today = timezone.localdate()
    soon = Task.objects.create(
        title="Срок на неделе", created_by=manager, assigned_to=employee,
        due_date=today + timedelta(days=7),
    )
    later = Task.objects.create(
        title="Срок позже", created_by=manager, assigned_to=employee,
        due_date=today + timedelta(days=8),
    )
    done = Task.objects.create(
        title="Уже выполнена", created_by=manager, assigned_to=employee,
        due_date=today + timedelta(days=2), status=Task.Status.DONE,
    )
    client.force_login(employee)

    response = client.get(reverse("task_list"), {"quick": "soon"})
    assert response.status_code == 200
    visible_ids = {task.pk for task in response.context["page_obj"]}
    assert soon.pk in visible_ids
    assert later.pk not in visible_ids
    assert done.pk not in visible_ids
