import secrets
from uuid import UUID, uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import RouletteDraw, RouletteTopic
from .permissions import assignable_users, is_manager


def participant(user):
    return {"id": user.pk, "name": user.get_full_name().strip() or user.username}


@login_required
def topics(request):
    return render(request, "tasks/roulette_topics.html", {
        "topics": RouletteTopic.objects.select_related("created_by").all(),
    })


@login_required
@require_POST
def create_topic(request):
    if not is_manager(request.user):
        return HttpResponseForbidden("Создавать темы может только руководитель.")
    title = request.POST.get("title", "").strip()
    raw_count = request.POST.get("winner_count", "3")
    if not 3 <= len(title) <= 120 or not raw_count.isdecimal() or not 1 <= int(raw_count) <= 20:
        messages.error(request, "Укажите тему от 3 до 120 символов и число участников от 1 до 20.")
        return redirect("roulette_topics")
    if RouletteTopic.objects.filter(title__iexact=title).exists():
        messages.error(request, "Такая тема уже есть.")
        return redirect("roulette_topics")
    try:
        topic = RouletteTopic.objects.create(title=title, winner_count=int(raw_count), created_by=request.user)
    except IntegrityError:
        messages.error(request, "Такая тема уже есть.")
        return redirect("roulette_topics")
    return redirect("roulette_topic", pk=topic.pk)


@login_required
def detail(request, pk):
    topic = get_object_or_404(RouletteTopic, pk=pk)
    latest = topic.draws.select_related("launched_by").first()
    if request.GET.get("status") == "1":
        return JsonResponse({"latest_id": latest.pk if latest else None}, headers={"Cache-Control": "no-store"})
    return render(request, "tasks/roulette_detail.html", {
        "topic": topic,
        "employees": list(assignable_users()) if is_manager(request.user) else [],
        "latest": latest,
        "draws": Paginator(topic.draws.select_related("launched_by"), 20).get_page(request.GET.get("page")),
        "request_id": uuid4(),
    })


@login_required
@require_POST
def draw(request, pk):
    if not is_manager(request.user):
        return HttpResponseForbidden("Запускать рулетку может только руководитель.")
    topic = get_object_or_404(RouletteTopic, pk=pk)
    wants_json = "application/json" in request.headers.get("Accept", "")

    def error(message, status=400):
        if wants_json:
            return JsonResponse({"error": message}, status=status)
        messages.error(request, message)
        return redirect("roulette_topic", pk=pk)

    try:
        request_id = UUID(request.POST["request_id"])
        raw_ids = request.POST.getlist("exclude")
        if any(not item.isdecimal() for item in raw_ids):
            raise ValueError
        excluded_ids = {int(item) for item in raw_ids}
    except (KeyError, ValueError):
        return error("Некорректные данные розыгрыша. Обновите страницу.")

    with transaction.atomic():
        topic = RouletteTopic.objects.select_for_update().get(pk=topic.pk)
        existing = RouletteDraw.objects.filter(request_id=request_id).first()
        if existing:
            if existing.topic_id != topic.pk:
                return error("Некорректный идентификатор розыгрыша.")
            result = existing
        else:
            employees = list(assignable_users())
            all_ids = {user.pk for user in employees}
            if not excluded_ids <= all_ids:
                return error("Состав сотрудников изменился. Обновите страницу и выберите заново.")
            pool = [participant(user) for user in employees if user.pk not in excluded_ids]
            if len(pool) < topic.winner_count:
                return error(f"Нужно минимум {topic.winner_count} участников после исключений.")
            chosen = secrets.SystemRandom().sample(pool, topic.winner_count)
            result = RouletteDraw.objects.create(
                topic=topic, launched_by=request.user, request_id=request_id,
                participants=pool,
                excluded=[participant(user) for user in employees if user.pk in excluded_ids],
                winners=chosen,
            )
    if wants_json:
        return JsonResponse({
            "draw_id": result.pk, "participants": result.participants,
            "winners": result.winners, "detail_url": request.path.rsplit("/draw/", 1)[0] + "/",
        })
    messages.success(request, "Розыгрыш завершён. Результат виден всем сотрудникам.")
    return redirect("roulette_topic", pk=pk)
