import json
from uuid import uuid4

import pytest
from django.test import Client
from django.urls import reverse

from tasks.models import MouseWallet, MouseWalletEvent


def send(client, url, action, event_id=None, **kwargs):
    return client.post(url, data=json.dumps({"action": action, "event_id": str(event_id or uuid4()), **kwargs}), content_type="application/json")


@pytest.mark.django_db
def test_wallet_is_private_idempotent_and_shared_between_sessions(client, employee, second_employee):
    url = reverse("mouse_wallet")
    assert client.get(url).status_code == 302
    client.force_login(employee)
    assert client.get(url).json()["cheese"] == 0
    event_id = uuid4()
    result = send(client, url, "catch", event_id, reward=5)
    assert result.status_code == 200
    assert (result.json()["cheese"], result.json()["catches"]) == (5, 1)
    assert send(client, url, "catch", event_id, reward=5).json()["cheese"] == 5
    assert MouseWalletEvent.objects.filter(user=employee).count() == 1
    assert send(client, url, "buy", item="hat").json()["wardrobe"]["hat"] is True
    assert send(client, url, "buy", item="hat").status_code == 409
    assert client.get(url).json()["cheese"] == 0
    assert send(client, url, "buy", item="scarf").status_code == 409

    client.force_login(second_employee)
    assert client.get(url).json()["cheese"] == 0
    assert client.get(url).json()["wardrobe"]["hat"] is False
    client.force_login(employee)
    assert client.get(url).json()["wardrobe"]["hat"] is True


@pytest.mark.django_db
def test_legacy_import_is_once_only_and_does_not_reset_new_activity(client, employee):
    client.force_login(employee)
    url = reverse("mouse_wallet")
    assert send(client, url, "catch", reward=1).json()["cheese"] == 1
    legacy = {"cheese": 3, "earned": 11, "catches": 4, "wardrobe": {"hat": True, "scarf": False}}
    event_id = uuid4()
    response = send(client, url, "import", event_id, legacy=legacy)
    assert response.status_code == 200
    assert (response.json()["cheese"], response.json()["earned"], response.json()["catches"]) == (4, 12, 5)
    assert response.json()["wardrobe"] == {"hat": True, "scarf": False}
    assert send(client, url, "import", event_id, legacy=legacy).json()["cheese"] == 4
    assert send(client, url, "import", legacy=legacy).json()["cheese"] == 4
    assert MouseWallet.objects.get(user=employee).legacy_imported


@pytest.mark.django_db
def test_invalid_requests_do_not_change_wallet(client, employee):
    client.force_login(employee)
    url = reverse("mouse_wallet")
    assert send(client, url, "catch", reward=100).status_code == 400
    assert send(client, url, "catch", reward=True).status_code == 400
    assert send(client, url, "import", legacy={"cheese": 9, "earned": 1, "catches": 0, "wardrobe": {"hat": False, "scarf": False}}).status_code == 400
    assert client.get(url).json()["cheese"] == 0


@pytest.mark.django_db
def test_wallet_post_requires_csrf_but_get_provisions_cookie(employee):
    browser = Client(enforce_csrf_checks=True)
    browser.force_login(employee)
    url = reverse("mouse_wallet")
    assert browser.get(url).status_code == 200
    assert "csrftoken" in browser.cookies
    assert send(browser, url, "catch", reward=1).status_code == 403
    response = browser.post(url, data=json.dumps({"action": "catch", "reward": 1, "event_id": str(uuid4())}),
                            content_type="application/json", HTTP_X_CSRFTOKEN=browser.cookies["csrftoken"].value)
    assert response.status_code == 200
