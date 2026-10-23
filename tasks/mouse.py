import json
from uuid import UUID

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .models import MouseWallet, MouseWalletEvent


def state(wallet):
    return {
        "cheese": wallet.cheese, "earned": wallet.earned, "catches": wallet.catches,
        "wardrobe": {"hat": wallet.hat, "scarf": wallet.scarf},
        "legacy_imported": wallet.legacy_imported,
    }


def number(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 100000:
        raise ValueError("Неверное значение счётчика")
    return value


@login_required
@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def wallet_api(request):
    if request.method == "GET":
        wallet, _ = MouseWallet.objects.get_or_create(user=request.user)
        response = JsonResponse(state(wallet))
        response["Cache-Control"] = "no-store"
        return response
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError("Неверный формат")
        action = data.get("action")
        if action not in ("import", "catch", "buy"):
            raise ValueError("Неизвестное действие")
        event_id = UUID(str(data.get("event_id")))
        if action == "catch":
            reward = data.get("reward")
            if type(reward) is not int or reward not in (1, 5):
                raise ValueError("Неверная награда")
        if action == "buy" and data.get("item") not in ("hat", "scarf"):
            raise ValueError("Неизвестная вещь")
        if action == "import":
            legacy = data.get("legacy")
            if not isinstance(legacy, dict):
                raise ValueError("Неверный формат")
            balance, earned, catches = (number(legacy.get(k)) for k in ("cheese", "earned", "catches"))
            wardrobe = legacy.get("wardrobe")
            if earned < balance or not isinstance(wardrobe, dict) or any(type(wardrobe.get(k)) is not bool for k in ("hat", "scarf")):
                raise ValueError("Неверный прогресс")
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({"error": "Неверные данные"}, status=400)

    with transaction.atomic():
        wallet, _ = MouseWallet.objects.get_or_create(user=request.user)
        wallet = MouseWallet.objects.select_for_update().get(pk=wallet.pk)
        if MouseWalletEvent.objects.filter(user=request.user, event_id=event_id).exists():
            response = JsonResponse(state(wallet))
            response["Cache-Control"] = "no-store"
            return response
        if action == "import" and not wallet.legacy_imported:
            wallet.cheese += balance
            wallet.earned += earned
            wallet.catches += catches
            wallet.hat |= wardrobe["hat"]
            wallet.scarf |= wardrobe["scarf"]
            wallet.legacy_imported = True
        elif action == "catch":
            wallet.cheese += reward
            wallet.earned += reward
            wallet.catches += 1
        elif action == "buy":
            item = data["item"]
            cost = 5 if item == "hat" else 8
            if not getattr(wallet, item) and wallet.cheese >= cost:
                wallet.cheese -= cost
                setattr(wallet, item, True)
            else:
                return JsonResponse({"error": "Недостаточно сыра или вещь уже куплена", **state(wallet)}, status=409)
        wallet.save()
        MouseWalletEvent.objects.create(user=request.user, event_id=event_id, action=action)
    response = JsonResponse(state(wallet))
    response["Cache-Control"] = "no-store"
    return response
