from uuid import uuid4

import pytest
from django.contrib.auth.models import Group, User
from django.urls import reverse

from tasks.constants import EMPLOYEES_GROUP
from tasks.models import RouletteDraw, RouletteTopic


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
