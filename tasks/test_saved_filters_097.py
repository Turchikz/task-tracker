from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import SavedTaskFilter


class SavedFilterRegressionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="saved_filter_097", password="test-password")
        self.client.force_login(self.user)

    def test_task_list_with_saved_filter_does_not_crash(self):
        SavedTaskFilter.objects.create(user=self.user, name="Мои", parameters={"assigned": "me", "sort": "smart"})
        response = self.client.get(reverse("task_list"))
        self.assertEqual(response.status_code, 200)

    def test_saved_filter_is_personal(self):
        saved = SavedTaskFilter.objects.create(user=self.user, name="Мои", parameters={"assigned": "me"})
        other = get_user_model().objects.create_user(username="other_filter_097", password="test-password")
        self.client.force_login(other)
        response = self.client.get(reverse("saved_filter_apply", args=[saved.pk]))
        self.assertEqual(response.status_code, 404)
