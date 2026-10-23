from uuid import uuid4

import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from tasks.constants import EMPLOYEES_GROUP
from tasks.models import RouletteDraw, RouletteTopic
from tasks.project_version import __version__


@pytest.mark.django_db
def test_guide_is_hidden_and_forbidden_for_employee(client, employee, manager):
    client.force_login(employee)
    assert "Как считается нагрузка" not in client.get(reverse("my_today")).content.decode()
    assert client.get(reverse("workload_guide")).status_code == 403
    client.force_login(manager)
    assert "Как считается нагрузка" in client.get(reverse("manager_dashboard")).content.decode()
    assert client.get(reverse("workload_guide")).status_code == 200


@pytest.mark.django_db
def test_manager_draw_exclusions_results_idempotency_and_independent_topics(client, manager, employee, second_employee):
    group = Group.objects.get(name=EMPLOYEES_GROUP)
    others = [User.objects.create_user(username=f"roulette{i}", first_name=f"Кандидат {i}") for i in range(3)]
    for person in others:
        person.groups.add(group)
    client.force_login(manager)
    create = client.post(reverse("roulette_create"), {"title": "Командировка", "winner_count": "3"})
    assert create.status_code == 302
    topic = RouletteTopic.objects.get(title="Командировка")
    second = RouletteTopic.objects.create(title="Конференция", winner_count=1, created_by=manager)
    token = uuid4()
    url = reverse("roulette_draw", args=[topic.pk])
    request = {"request_id": str(token), "exclude": [str(employee.pk), str(second_employee.pk)]}
    result = client.post(url, request, HTTP_ACCEPT="application/json")
    assert result.status_code == 200
    data = result.json()
    assert len(data["participants"]) == len(data["winners"]) == 3
    assert {person["id"] for person in data["winners"]} == {person.pk for person in others}
    assert {person["id"] for person in RouletteDraw.objects.get(topic=topic).excluded} == {employee.pk, second_employee.pk}
    assert client.post(url, request, HTTP_ACCEPT="application/json").json()["draw_id"] == data["draw_id"]
    assert RouletteDraw.objects.filter(topic=topic).count() == 1
    assert not RouletteDraw.objects.filter(topic=second).exists()

    # The historical names stay visible even if the employee later leaves.
    others[0].is_active = False
    others[0].save(update_fields=["is_active"])

    client.force_login(employee)
    page = client.get(reverse("roulette_topic", args=[topic.pk]))
    assert page.status_code == 200
    assert 'href="/roulette/"' in page.content.decode()
    for person in others:
        assert person.first_name in page.content.decode()
    assert client.get(reverse("roulette_topic", args=[topic.pk]), {"status": "1"}).json()["latest_id"] == data["draw_id"]
    assert client.post(url, request, HTTP_ACCEPT="application/json").status_code == 403
    assert client.post(reverse("roulette_create"), {"title": "Скрытая", "winner_count": 1}).status_code == 403


@pytest.mark.django_db
def test_draw_rejects_insufficient_pool_and_stale_exclusions(client, manager, employee, second_employee):
    topic = RouletteTopic.objects.create(title="Поездка", winner_count=2, created_by=manager)
    client.force_login(manager)
    url = reverse("roulette_draw", args=[topic.pk])
    response = client.post(url, {"request_id": str(uuid4()), "exclude": [employee.pk]}, HTTP_ACCEPT="application/json")
    assert response.status_code == 400
    response = client.post(url, {"request_id": str(uuid4()), "exclude": [999999]}, HTTP_ACCEPT="application/json")
    assert response.status_code == 400
    assert not RouletteDraw.objects.exists()


@pytest.mark.django_db
def test_admin_can_hide_and_restore_draw_without_manager_access(client, manager, employee):
    admin = User.objects.create_superuser(username="roulette-admin", password="pass12345")
    topic = RouletteTopic.objects.create(title="Поездка команды", winner_count=1, created_by=manager)
    client.force_login(manager)
    token = uuid4()
    draw_url = reverse("roulette_draw", args=[topic.pk])
    result = client.post(draw_url, {"request_id": str(token)}, HTTP_ACCEPT="application/json")
    assert result.status_code == 200
    draw = RouletteDraw.objects.get(pk=result.json()["draw_id"])
    delete_url = reverse("roulette_draw_delete", args=[topic.pk, draw.pk])
    restore_url = reverse("roulette_draw_restore", args=[topic.pk, draw.pk])
    page = client.get(reverse("roulette_topic", args=[topic.pk])).content.decode()
    assert "Удалить результат" not in page
    assert client.post(delete_url).status_code == 403
    assert client.post(restore_url).status_code == 403

    client.force_login(employee)
    assert client.post(delete_url).status_code == 403
    assert client.get(reverse("roulette_topic", args=[topic.pk])).status_code == 200

    client.force_login(admin)
    page = client.get(reverse("roulette_topic", args=[topic.pk])).content.decode()
    assert "Удалить результат" in page
    assert client.get(delete_url).status_code == 405
    assert client.post(delete_url).status_code == 302
    draw.refresh_from_db()
    assert draw.deleted_at is not None and draw.deleted_by_id == admin.pk
    assert client.get(reverse("roulette_topic", args=[topic.pk]), {"status": "1"}).json()["latest_id"] is None
    assert "Восстановить результат" in client.get(reverse("roulette_topic", args=[topic.pk])).content.decode()
    assert client.post(draw_url, {"request_id": str(token)}, HTTP_ACCEPT="application/json").status_code == 409

    client.force_login(employee)
    page = client.get(reverse("roulette_topic", args=[topic.pk])).content.decode()
    assert "Удалённые результаты" not in page
    assert "Розыгрышей пока не было" in page
    assert client.get(reverse("roulette_topics")).context["topics"][0].visible_draw_count == 0

    client.force_login(admin)
    assert client.post(restore_url).status_code == 302
    draw.refresh_from_db()
    assert draw.deleted_at is None and draw.deleted_by_id is None
    client.force_login(employee)
    assert client.get(reverse("roulette_topic", args=[topic.pk]), {"status": "1"}).json()["latest_id"] == draw.pk
    assert f"<li>{employee.get_full_name()}</li>" in client.get(reverse("roulette_topic", args=[topic.pk])).content.decode()


@pytest.mark.django_db
def test_profile_shows_installed_version_after_sound_settings(client, employee):
    client.force_login(employee)
    page = client.get(reverse("my_today")).content.decode()
    assert page.index("Звуки и пасхалки") < page.index(f"RaTracker v{__version__}") < page.index("Выйти из RaTracker")


@pytest.mark.django_db
def test_removing_older_draw_updates_open_pages_while_newer_result_remains(client, manager, employee):
    admin = User.objects.create_superuser(username="archive-admin", password="pass12345")
    topic = RouletteTopic.objects.create(title="Две поездки", winner_count=1, created_by=manager)
    client.force_login(manager)
    first = client.post(reverse("roulette_draw", args=[topic.pk]), {"request_id": str(uuid4())}, HTTP_ACCEPT="application/json").json()["draw_id"]
    second = client.post(reverse("roulette_draw", args=[topic.pk]), {"request_id": str(uuid4())}, HTTP_ACCEPT="application/json").json()["draw_id"]
    client.force_login(admin)
    client.post(reverse("roulette_draw_delete", args=[topic.pk, first]))
    state = client.get(reverse("roulette_topic", args=[topic.pk]), {"status": "1"}).json()
    assert state == {"latest_id": second, "visible_count": 1}
    assert 'data-visible-count="1"' in client.get(reverse("roulette_topic", args=[topic.pk])).content.decode()


@pytest.mark.django_db
def test_admin_deletes_whole_topic_and_draws_with_explicit_confirmation(client, manager, employee):
    admin = User.objects.create_superuser(username="topic-admin", password="pass12345")
    topic = RouletteTopic.objects.create(title="Устаревшая тема", winner_count=1, created_by=manager)
    client.force_login(manager)
    client.post(reverse("roulette_draw", args=[topic.pk]), {"request_id": str(uuid4())})
    client.post(reverse("roulette_draw", args=[topic.pk]), {"request_id": str(uuid4())})
    assert topic.draws.count() == 2
    delete_url = reverse("admin:tasks_roulettetopic_delete", args=[topic.pk])
    client.force_login(admin)
    confirmation = client.get(delete_url)
    assert confirmation.status_code == 200
    assert "вместе с ней" in confirmation.content.decode().lower()
    assert "2 розыгрышей" in confirmation.content.decode()
    assert client.post(delete_url, {"post": "yes"}).status_code == 302
    assert not RouletteTopic.objects.filter(pk=topic.pk).exists()
    assert not RouletteDraw.objects.filter(topic_id=topic.pk).exists()
    client.force_login(employee)
    assert client.get(reverse("roulette_topic", args=[topic.pk])).status_code == 404
