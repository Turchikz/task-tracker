import secrets
from uuid import UUID, uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import RouletteDraw, RouletteTopic
from .permissions import assignable_users, is_manager


def participant(user):
    return {"id": user.pk, "name": user.get_full_name().strip() or user.username}


@login_required
def topics(request):
    return render(request, "tasks/roulette_topics.html", {
        "topics": RouletteTopic.objects.select_related("created_by").annotate(
            visible_draw_count=Count("draws", filter=Q(draws__deleted_at__isnull=True))
        ),
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
    visible = topic.draws.filter(deleted_at__isnull=True).select_related("launched_by")
    latest = visible.first()
    visible_count = visible.count()
    if request.GET.get("status") == "1":
        return JsonResponse({"latest_id": latest.pk if latest else None, "visible_count": visible_count}, headers={"Cache-Control": "no-store"})
    return render(request, "tasks/roulette_detail.html", {
        "topic": topic,
        "employees": list(assignable_users()) if is_manager(request.user) else [],
        "latest": latest,
        "visible_count": visible_count,
        "draws": Paginator(visible, 20).get_page(request.GET.get("page")),
        "deleted_draws": Paginator(topic.draws.filter(deleted_at__isnull=False).select_related("deleted_by"), 20).get_page(request.GET.get("deleted_page")) if request.user.is_superuser else None,
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
            if existing.deleted_at:
                return error("Этот результат удалён администратором. Обновите страницу.", status=409)
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


@login_required
@require_POST
def delete_draw(request, pk, draw_pk):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Удалять результаты может только администратор.")
    with transaction.atomic():
        result = get_object_or_404(RouletteDraw.objects.select_for_update(), pk=draw_pk, topic_id=pk)
        if result.deleted_at is None:
            result.deleted_at = timezone.now()
            result.deleted_by = request.user
            result.save(update_fields=["deleted_at", "deleted_by"])
    messages.success(request, "Результат убран из общей истории. Его можно восстановить.")
    return redirect("roulette_topic", pk=pk)


@login_required
@require_POST
def restore_draw(request, pk, draw_pk):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Восстанавливать результаты может только администратор.")
    with transaction.atomic():
        result = get_object_or_404(RouletteDraw.objects.select_for_update(), pk=draw_pk, topic_id=pk)
        if result.deleted_at is not None:
            result.deleted_at = None
            result.deleted_by = None
            result.save(update_fields=["deleted_at", "deleted_by"])
    messages.success(request, "Результат снова доступен всем сотрудникам.")
    return redirect("roulette_topic", pk=pk)
