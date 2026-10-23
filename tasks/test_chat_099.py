import json
from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import ChatMessage, ChatReadState


class ChatTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(username='alice', password='secret')
        self.b = User.objects.create_user(username='bob', password='secret', first_name='Борис')
        self.client.force_login(self.a)

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('department_chat')).status_code, 302)

    def test_send_and_fetch(self):
        response = self.client.post(reverse('chat_send'), json.dumps({'text': 'Привет 😀'}), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ChatMessage.objects.count(), 1)
        messages = self.client.get(reverse('chat_messages')).json()['messages']
        self.assertEqual(messages[0]['text'], 'Привет 😀')

    def test_empty_message_rejected(self):
        response = self.client.post(reverse('chat_send'), json.dumps({'text': '   '}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_reply_and_mention(self):
        original = ChatMessage.objects.create(author=self.b, text='Вопрос')
        response = self.client.post(reverse('chat_send'), json.dumps({'text': '@Борис ответ', 'reply_to': original.pk, 'mentions': [self.b.pk]}), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        message = ChatMessage.objects.latest('pk')
        self.assertEqual(message.reply_to, original)
        self.assertEqual(list(message.mentions.all()), [self.b])

    def test_read_counter(self):
        message = ChatMessage.objects.create(author=self.b, text='Непрочитанное')
        self.assertEqual(self.client.get(reverse('chat_status')).json()['unread'], 1)
        response = self.client.post(reverse('chat_mark_read'), json.dumps({'message_id': message.pk}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse('chat_status')).json()['unread'], 0)

    def test_old_messages_purged(self):
        from django.core.management import call_command
        old = ChatMessage.objects.create(author=self.a, text='Старое')
        ChatMessage.objects.filter(pk=old.pk).update(created_at=timezone.now()-timedelta(days=220))
        fresh = ChatMessage.objects.create(author=self.a, text='Новое')
        call_command('purge_old_chat')
        self.assertFalse(ChatMessage.objects.filter(pk=old.pk).exists())
        self.assertTrue(ChatMessage.objects.filter(pk=fresh.pk).exists())
