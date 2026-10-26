"""Department support views: templates, absences, notifications, and ideas."""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from django.contrib.auth.models import User

from .absence_planning import affected_tasks_for_absences
from .constants import EMPLOYEES_GROUP
from .forms import EmployeeAbsenceForm, TaskTemplateForm
from .models import EmployeeAbsence, FeatureIdea, FeatureVote, Notification, TaskTemplate
from .permissions import is_manager


@login_required
def template_list(request):
    if not is_manager(request.user):
        return HttpResponseForbidden("Шаблоны доступны только руководителю.")
    return render(request, "tasks/template_list.html", {"templates": TaskTemplate.objects.all()})


@login_required
def template_create(request):
    if not is_manager(request.user):
        return HttpResponseForbidden("Шаблоны доступны только руководителю.")
    if request.method == "POST":
        form = TaskTemplateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Шаблон создан.")
            return redirect("template_list")
    else:
        form = TaskTemplateForm()
    return render(request, "tasks/template_form.html", {"form": form, "title": "Новый шаблон"})


@login_required
def template_edit(request, pk):
    if not is_manager(request.user):
        return HttpResponseForbidden("Шаблоны доступны только руководителю.")
    template = get_object_or_404(TaskTemplate, pk=pk)
    if request.method == "POST":
        form = TaskTemplateForm(request.POST, instance=template)
        if form.is_valid():
            form.save()
            messages.success(request, "Шаблон обновлён.")
            return redirect("template_list")
    else:
        form = TaskTemplateForm(instance=template)
    return render(request, "tasks/template_form.html", {"form": form, "title": "Редактирование шаблона"})


@login_required
def notifications_list(request):
    notifications_qs = request.user.task_notifications.select_related("task")
    if not is_manager(request.user):
        notifications_qs = notifications_qs.filter(
            Q(task__assigned_to=request.user) | Q(task__additional_assignees=request.user)
        ).distinct()
    if is_manager(request.user) and not request.user.is_superuser:
        notifications_qs = notifications_qs.exclude(
            Q(kind=Notification.Kind.SUBMITTED_REVIEW)
            & ~Q(task__responsible_manager=request.user)
        )

    notifications = list(notifications_qs[:100])
    for notification in notifications:
        notification.display_day = timezone.localtime(notification.created_at).date()
    today_date = timezone.localdate()
    yesterday_date = today_date - timedelta(days=1)
    action_notifications = [
        notification for notification in notifications if notification.requires_action
    ]
    info_notifications = [
        notification for notification in notifications if not notification.requires_action
    ]
    return render(
        request,
        "tasks/notifications.html",
        {
            "action_notifications": action_notifications,
            "info_notifications": info_notifications,
            "today": today_date,
            "yesterday": yesterday_date,
        },
    )


@login_required
def notification_read(request, pk):
    if request.method != "POST":
        raise Http404
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return redirect("notifications")


@login_required
def notifications_read_all(request):
    if request.method != "POST":
        raise Http404
    request.user.task_notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
    return redirect("notifications")


@login_required
def absences(request):
    if not is_manager(request.user):
        return HttpResponseForbidden("Отсутствия сотрудников доступны только руководителю.")
    today = timezone.localdate()
    if request.method == "POST":
        form = EmployeeAbsenceForm(request.POST)
        if form.is_valid():
            absence = form.save(commit=False)
            absence.created_by = request.user
            absence.save()
            messages.success(request, "Период отсутствия добавлен.")
            return redirect("absences")
    else:
        form = EmployeeAbsenceForm(initial={"start_date": today, "end_date": today})

    active_upcoming = EmployeeAbsence.objects.filter(end_date__gte=today).select_related("user", "created_by")
    recent_past = EmployeeAbsence.objects.filter(end_date__lt=today).select_related("user", "created_by").order_by("-end_date")[:20]
    return render(
        request,
        "tasks/absences.html",
        {"form": form, "active_upcoming": active_upcoming, "recent_past": recent_past,
         "today": today, "affected_tasks": affected_tasks_for_absences(request.user)},
    )


@login_required
def absence_delete(request, pk):
    if request.method != "POST":
        raise Http404
    if not is_manager(request.user):
        return HttpResponseForbidden("Отсутствия сотрудников доступны только руководителю.")
    absence = get_object_or_404(EmployeeAbsence, pk=pk)
    absence.delete()
    messages.success(request, "Период отсутствия удалён.")
    return redirect("absences")


@login_required
def feature_ideas(request):
    from django.contrib.auth.models import User
    from .constants import EMPLOYEES_GROUP
    employee = request.user.is_active and request.user.groups.filter(name=EMPLOYEES_GROUP).exists()
    ideas = list(FeatureIdea.objects.select_related("author").prefetch_related("votes"))
    votes = dict(FeatureVote.objects.filter(user=request.user).values_list("idea_id", "choice"))
    return render(request, "tasks/feature_ideas.html", {
        "ideas": ideas, "my_votes": votes, "can_vote": employee,
        "electorate": User.objects.filter(is_active=True, groups__name=EMPLOYEES_GROUP).distinct().count(),
        "statuses": FeatureIdea.Status.choices,
    })


@login_required
def feature_idea_create(request):
    if request.method != "POST":
        return redirect("feature_ideas")
    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()
    if not (3 <= len(title) <= 160 and 10 <= len(description) <= 4000):
        messages.error(request, "Название должно содержать 3–160 символов, описание — 10–4000.")
    else:
        FeatureIdea.objects.create(title=title, description=description, author=request.user)
        messages.success(request, "Предложение опубликовано.")
    return redirect("feature_ideas")


@login_required
def feature_idea_vote(request, pk):
    from .constants import EMPLOYEES_GROUP
    if request.method != "POST":
        return HttpResponse(status=405)
    if not request.user.is_active or not request.user.groups.filter(name=EMPLOYEES_GROUP).exists():
        return HttpResponseForbidden("Голосовать могут только активные сотрудники группы Employees.")
    idea = get_object_or_404(FeatureIdea, pk=pk)
    if idea.status != FeatureIdea.Status.VOTING:
        messages.error(request, "Голосование по этому предложению завершено.")
        return redirect("feature_ideas")
    choice = request.POST.get("choice")
    if choice not in ("yes", "no", "withdraw"):
        return HttpResponse(status=400)
    with transaction.atomic():
        idea = FeatureIdea.objects.select_for_update().get(pk=pk)
        if idea.status != FeatureIdea.Status.VOTING:
            return redirect("feature_ideas")
        if choice == "withdraw":
            FeatureVote.objects.filter(idea=idea, user=request.user).delete()
        else:
            FeatureVote.objects.update_or_create(idea=idea, user=request.user, defaults={"choice": choice == "yes"})
        idea.refresh_review_status()
    return redirect("feature_ideas")


@login_required
def feature_idea_status(request, pk):
    if request.method != "POST":
        return HttpResponse(status=405)
    if not is_manager(request.user):
        return HttpResponseForbidden("Только руководитель может менять статус.")
    idea = get_object_or_404(FeatureIdea, pk=pk)
    new_status = request.POST.get("status")
    allowed = {FeatureIdea.Status.IN_PROGRESS, FeatureIdea.Status.IMPLEMENTED, FeatureIdea.Status.REJECTED}
    if new_status not in allowed or idea.status == FeatureIdea.Status.VOTING:
        return HttpResponse(status=400)
    idea.status = new_status
    idea.save(update_fields=["status", "updated_at"])
    return redirect("feature_ideas")
