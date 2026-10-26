"""Department-wide chat: authenticated JSON endpoints, no websocket dependency."""
import json
from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from .models import ChatMessage, ChatReadState, ChatNotificationSettings


def _name(user):
    return user.get_full_name().strip() or user.username


def _serialize(message, viewer):
    reply = message.reply_to
    return {
        "id": message.pk, "text": message.text, "author": _name(message.author),
        "author_id": message.author_id, "mine": message.author_id == viewer.pk,
        "created_at": timezone.localtime(message.created_at).strftime("%d.%m %H:%M"),
        "reply": {"id": reply.pk, "author": _name(reply.author), "text": reply.text[:110]} if reply else None,
        "mentions": list(message.mentions.values_list("pk", flat=True)),
    }


@login_required
@require_GET
def room(request):
    users = User.objects.filter(is_active=True).order_by("first_name", "last_name", "username")
    return render(request, "tasks/chat.html", {"chat_users": users})


@login_required
@require_GET
def messages(request):
    try:
        after = max(0, int(request.GET.get("after", 0)))
        before = max(0, int(request.GET.get("before", 0)))
    except (ValueError, TypeError):
        return JsonResponse({"error": "Неверный курсор"}, status=400)
    if before:
        qs = ChatMessage.objects.filter(pk__lt=before).order_by("-pk")[:50]
        batch = list(qs)[::-1]
    elif after:
        batch = list(ChatMessage.objects.filter(pk__gt=after).order_by("pk")[:100])
    else:
        batch = list(ChatMessage.objects.order_by("-pk")[:50])[::-1]
    # Fetch author and reply in bounded queries for larger chat rooms.
    ids = [m.pk for m in batch]
    batch = list(ChatMessage.objects.filter(pk__in=ids).select_related("author", "reply_to__author").prefetch_related("mentions").order_by("pk"))
    return JsonResponse({"messages": [_serialize(m, request.user) for m in batch]})


@login_required
@require_POST
def send(request):
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Некорректный JSON"}, status=400)
    text = data.get("text", "")
    if not isinstance(text, str) or not text.strip() or len(text.strip()) > 2000:
        return JsonResponse({"error": "Введите сообщение (не более 2000 символов)"}, status=400)
    # Simple database-backed throttle, independent of Gunicorn worker count.
    if ChatMessage.objects.filter(author=request.user, created_at__gte=timezone.now()-timedelta(seconds=2)).exists():
        return JsonResponse({"error": "Подождите две секунды перед отправкой"}, status=429)
    reply_id = data.get("reply_to")
    reply = ChatMessage.objects.filter(pk=reply_id).first() if isinstance(reply_id, int) and not isinstance(reply_id, bool) else None
    if reply_id is not None and reply is None:
        return JsonResponse({"error": "Исходное сообщение не найдено"}, status=400)
    raw_ids = data.get("mentions", [])
    if not isinstance(raw_ids, list) or len(raw_ids) > 30 or any(type(i) is not int for i in raw_ids):
        return JsonResponse({"error": "Некорректные упоминания"}, status=400)
    users = list(User.objects.filter(is_active=True, pk__in=set(raw_ids)))
    # Only selected @mentions actually present in text are eligible.
    users = [u for u in users if "@" + _name(u) in text]
    with transaction.atomic():
        message = ChatMessage.objects.create(author=request.user, text=text.strip(), reply_to=reply)
        message.mentions.set(users)
    return JsonResponse({"message": _serialize(message, request.user)}, status=201)


@login_required
@require_GET
def status(request):
    state, _ = ChatReadState.objects.get_or_create(user=request.user)
    latest = ChatMessage.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
    unread = ChatMessage.objects.filter(pk__gt=state.last_read_message_id).exclude(author=request.user).count()
    mentioned = ChatMessage.objects.filter(pk__gt=state.last_read_message_id, mentions=request.user).exclude(author=request.user).count()
    return JsonResponse({"unread": unread, "mentions": mentioned, "latest": latest})


@login_required
@require_POST
def mark_read(request):
    try:
        data = json.loads(request.body)
        message_id = int(data.get("message_id", 0))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"error": "Неверный идентификатор"}, status=400)
    latest = ChatMessage.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
    message_id = max(0, min(message_id, latest))
    state, _ = ChatReadState.objects.get_or_create(user=request.user)
    if message_id > state.last_read_message_id:
        state.last_read_message_id = message_id
        state.save(update_fields=["last_read_message_id", "updated_at"])
    return JsonResponse({"ok": True})


def _prefs(instance):
    return {key: getattr(instance, key) for key in ("in_app", "desktop", "sound", "mentions", "volume")}


@login_required
def notification_settings(request):
    if request.method not in ("GET", "POST"):
        return JsonResponse({"error": "Метод не поддерживается"}, status=405)
    prefs, _ = ChatNotificationSettings.objects.get_or_create(user=request.user)
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "Некорректный JSON"}, status=400)
        if not isinstance(data, dict) or not data or any(k not in ("in_app", "desktop", "sound", "mentions", "volume") for k in data):
            return JsonResponse({"error": "Некорректные настройки"}, status=400)
        for key, value in data.items():
            if key == "volume":
                if type(value) is not int or not 0 <= value <= 100:
                    return JsonResponse({"error": "Громкость должна быть от 0 до 100"}, status=400)
            elif type(value) is not bool:
                return JsonResponse({"error": "Ожидается true/false"}, status=400)
        for key, value in data.items():
            setattr(prefs, key, value)
        prefs.save(update_fields=list(data))
    return JsonResponse({"settings": _prefs(prefs)})


@login_required
@ensure_csrf_cookie
@require_GET
def notification_events(request):
    try:
        after = max(0, int(request.GET.get("after", 0)))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Неверный курсор"}, status=400)
    # Return at most 30 newest items. No read-state changes: alerts and unread are independent.
    latest = ChatMessage.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
    batch = list(ChatMessage.objects.filter(pk__gt=after).exclude(author=request.user)
        .select_related("author").prefetch_related("mentions").order_by("-pk")[:30])
    batch.reverse()
    return JsonResponse({"latest": latest, "events": [{
        "id": m.pk, "author": _name(m.author), "text": m.text[:160],
        "mention": any(u.pk == request.user.pk for u in m.mentions.all()),
    } for m in batch]})
