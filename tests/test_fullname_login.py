import pytest
from django.contrib.auth.models import User
from django.urls import reverse


@pytest.mark.django_db
def test_login_page_uses_full_name_select(client):
    user = User.objects.create_user(
        username="ivanov",
        password="pass12345",
        first_name="Иван",
        last_name="Иванов",
    )

    response = client.get(reverse("login"))
    content = response.content.decode("utf-8")

    assert response.status_code == 200
    assert '<select' in content
    assert 'Иванов Иван' in content
    assert 'name="employee"' in content


@pytest.mark.django_db
def test_login_excludes_users_without_full_name(client):
    User.objects.create_user(
        username="service",
        password="pass12345",
        first_name="",
        last_name="",
    )

    response = client.get(reverse("login"))
    content = response.content.decode("utf-8")

    assert "service" not in content


@pytest.mark.django_db
def test_login_authenticates_selected_employee(client):
    user = User.objects.create_user(
        username="ivanov",
        password="pass12345",
        first_name="Иван",
        last_name="Иванов",
    )

    response = client.post(
        reverse("login"),
        {
            "employee": user.pk,
            "password": "pass12345",
        },
    )

    assert response.status_code == 302
    assert client.session.get("_auth_user_id") == str(user.pk)
