"""v0.8.0 UI tests: check rendered navigation and server-backed interactions.

Client tests run inside the project's Docker image with pytest and Django.
"""

import pytest
from django.urls import reverse
from django.utils import timezone

from tasks.models import Task, TaskComment


@pytest.mark.django_db
def test_manager_navigation_and_clickable_dashboard(client, manager, employee):
    Task.objects.create(title="Новая задача", created_by=manager, assigned_to=employee)
    client.force_login(manager)
    response = client.get(reverse("manager_dashboard"))
    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert 'class="primary-nav"' in html
    assert 'aria-current="page"' in html
    assert 'class="stats stats-clickable"' in html
    assert 'href="' + reverse("review_queue") + '"' in html


@pytest.mark.django_db
def test_bulk_toolbar_initially_hidden_but_selectable(client, manager, employee):
    task = Task.objects.create(title="Выделяемая задача", created_by=manager, assigned_to=employee)
    client.force_login(manager)
    response = client.get(reverse("task_list"))
    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert 'data-bulk-form hidden' in html
    assert f'value="{task.pk}"' in html
    assert 'data-columns-menu' in html
    assert 'data-filter-panel' in html


@pytest.mark.django_db
def test_employee_today_inline_action(client, manager, employee):
    today = timezone.localdate()
    task = Task.objects.create(
        title="Приступить сегодня",
        created_by=manager,
        assigned_to=employee,
        start_date=today,
        due_date=today,
        status=Task.Status.NEW,
    )
    client.force_login(employee)
    response = client.get(reverse("my_today"))
    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert f'action="{reverse("task_quick_action", args=[task.pk])}"' in html
    assert "Начать работу" in html


@pytest.mark.django_db
def test_calendar_agenda_and_month_are_available(client, employee):
    client.force_login(employee)
    response = client.get(reverse("calendar"), {"year": 2026, "month": 10})
    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert 'data-calendar-mode="month"' in html
    assert 'data-calendar-mode="agenda"' in html
    assert 'data-calendar-agenda' in html


@pytest.mark.django_db
def test_workload_week_and_two_week_ranges(client, manager, employee):
    client.force_login(manager)
    for period, expected in (("week", 7), ("two_weeks", 14), ("month", 31)):
        response = client.get(
            reverse("workload_timeline"),
            {"year": 2026, "month": 10, "period": period},
        )
        assert response.status_code == 200
        assert len(response.context["days"]) == expected


@pytest.mark.django_db
def test_search_explains_comment_match(client, manager, employee):
    task = Task.objects.create(title="Контрольная задача", created_by=manager, assigned_to=employee)
    TaskComment.objects.create(
        task=task,
        author=manager,
        text="Было обсуждение, затем найдено слово редкий_маркер для дальнейшей проверки",
    )
    client.force_login(employee)
    response = client.get(reverse("global_search"), {"q": "редкий_маркер"})
    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert "Совпадение в комментарии:" in html
    assert "редкий_маркер" in html


@pytest.mark.django_db
def test_notifications_unread_filter_and_groups(client, employee):
    client.force_login(employee)
    response = client.get(reverse("notifications"))
    assert response.status_code == 200
    assert 'data-notify-filter="unread"' in response.content.decode("utf-8")
