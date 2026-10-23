import json
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from .models import ChatMessage, ChatNotificationSettings


class ChatNotificationTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(username='alice', password='x')
        self.b = User.objects.create_user(username='bob', password='x')
        self.client.force_login(self.a)

    def test_defaults_and_per_user_persistence(self):
        url = reverse('chat_notification_settings')
        self.assertTrue(self.client.get(url).json()['settings']['in_app'])
        response = self.client.post(url, json.dumps({'sound': False, 'volume': 40, 'desktop': True}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ChatNotificationSettings.objects.get(user=self.a).sound)
        self.client.force_login(self.b)
        self.assertTrue(self.client.get(url).json()['settings']['sound'])

    def test_validation(self):
        url = reverse('chat_notification_settings')
        for payload in ({'volume': 101}, {'sound': 'false'}, {'unknown': True}, {'volume': True}):
            self.assertEqual(self.client.post(url, json.dumps(payload), content_type='application/json').status_code, 400)

    def test_events_exclude_self_and_identify_mentions(self):
        mine = ChatMessage.objects.create(author=self.a, text='My message')
        other = ChatMessage.objects.create(author=self.b, text='@alice hello')
        other.mentions.add(self.a)
        events = self.client.get(reverse('chat_notification_events'), {'after': 0}).json()
        self.assertEqual([e['id'] for e in events['events']], [other.id])
        self.assertTrue(events['events'][0]['mention'])
        self.assertEqual(events['latest'], other.id)
        self.assertEqual(self.client.get(reverse('chat_notification_events'), {'after': other.id}).json()['events'], [])

    def test_auth_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('chat_notification_settings')).status_code, 302)
        self.assertEqual(self.client.get(reverse('chat_notification_events')).status_code, 302)
