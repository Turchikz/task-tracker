from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from pathlib import Path
from uuid import uuid4

from .constants import EMPLOYEES_GROUP, MANAGERS_GROUP


def task_image_upload_to(instance, filename):
    extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(instance.content_type, Path(filename).suffix.lower() or ".img")
    return f"task_images/{instance.task_id}/{uuid4().hex}{extension}"


class Task(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новая"
        IN_PROGRESS = "in_progress", "В работе"
        REVIEW = "review", "На проверке"
        REVISION = "revision", "На доработке"
        DONE = "done", "Выполнена"
        CANCELLED = "cancelled", "Отменена"

    class Priority(models.TextChoices):
        LOW = "low", "Низкий"
        NORMAL = "normal", "Обычный"
        HIGH = "high", "Высокий"
        URGENT = "urgent", "Срочный"

    class Effort(models.TextChoices):
        SMALL = "small", "Малая"
        MEDIUM = "medium", "Средняя"
        LARGE = "large", "Большая"
        XLARGE = "xlarge", "Очень большая"

    title = models.CharField("Название", max_length=200)
    description = models.TextField("Описание", blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_tasks",
        verbose_name="Автор",
    )
    responsible_manager = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        related_name="responsible_tasks",
        verbose_name="Ответственный руководитель",
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="assigned_tasks",
        verbose_name="Исполнитель",
    )
    additional_assignees = models.ManyToManyField(
        User,
        blank=True,
        related_name="collaborating_tasks",
        verbose_name="Дополнительные исполнители",
    )
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    priority = models.CharField("Приоритет", max_length=20, choices=Priority.choices, default=Priority.NORMAL, db_index=True)
    effort = models.CharField("Трудоёмкость", max_length=20, choices=Effort.choices, default=Effort.MEDIUM)
    start_date = models.DateField("Плановое начало", blank=True, null=True, db_index=True)
    due_date = models.DateField("Срок", blank=True, null=True, db_index=True)
    started_at = models.DateTimeField("Фактически начата", blank=True, null=True, editable=False)
    submitted_at = models.DateTimeField("Последняя отправка на проверку", blank=True, null=True, editable=False)
    completed_at = models.DateTimeField("Дата выполнения", blank=True, null=True, editable=False)
    revision_reason = models.TextField("Последняя причина доработки", blank=True, editable=False)
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Изменена", auto_now=True)

    class Meta:
        ordering = ["due_date", "-priority", "-created_at"]
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"
        indexes = [
            models.Index(fields=["assigned_to", "status", "due_date"], name="task_assignee_status_due_idx"),
            models.Index(fields=["responsible_manager", "status", "due_date"], name="task_manager_status_due_idx"),
            models.Index(fields=["status", "priority"], name="task_status_priority_idx"),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.start_date and self.due_date and self.start_date > self.due_date:
            raise ValidationError({"due_date": "Срок не может быть раньше планового начала."})
        if self.responsible_manager_id:
            if not self.responsible_manager.is_active:
                raise ValidationError({"responsible_manager": "Нельзя назначить неактивного руководителя."})
            if not (
                self.responsible_manager.is_superuser
                or self.responsible_manager.groups.filter(name=MANAGERS_GROUP).exists()
            ):
                raise ValidationError({"responsible_manager": "Ответственный должен состоять в группе Managers."})

        if not self.assigned_to_id:
            return
        if not self.assigned_to.is_active:
            raise ValidationError({"assigned_to": "Нельзя назначить задачу неактивному пользователю."})
        if not self.assigned_to.groups.filter(name=EMPLOYEES_GROUP).exists():
            raise ValidationError({"assigned_to": "Исполнитель должен состоять в группе Employees."})

    def save(self, *args, **kwargs):
        # Backward-compatible default for old code/tests and imported tasks.
        if self.responsible_manager_id is None and self.created_by_id:
            self.responsible_manager_id = self.created_by_id

        previous_status = None
        if self.pk:
            previous_status = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()

        now = timezone.now()
        if self.status == self.Status.IN_PROGRESS and self.started_at is None:
            self.started_at = now
        if self.status == self.Status.REVIEW and previous_status != self.Status.REVIEW:
            self.submitted_at = now
        if self.status == self.Status.DONE and self.completed_at is None:
            self.completed_at = now
        elif self.status != self.Status.DONE:
            self.completed_at = None

        super().save(*args, **kwargs)

    @property
    def team_members(self):
        """Current participants; the primary assignee is never repeated."""
        if not self.assigned_to_id:
            return list(self.additional_assignees.all()) if self.pk else []
        extras = list(self.additional_assignees.all()) if self.pk else []
        return [self.assigned_to] + [user for user in extras if user.pk != self.assigned_to_id]

    @property
    def team_names(self):
        return ", ".join(user.get_full_name() or user.username for user in self.team_members)

    def has_assignee(self, user):
        if not user.is_authenticated:
            return False
        if self.assigned_to_id == user.pk:
            return True
        if not self.pk:
            return False
        cache = getattr(self, "_prefetched_objects_cache", {})
        if "additional_assignees" in cache:
            return any(member.pk == user.pk for member in cache["additional_assignees"])
        return self.additional_assignees.filter(pk=user.pk).exists()

    @property
    def is_active(self):
        return self.status in {
            self.Status.NEW,
            self.Status.IN_PROGRESS,
            self.Status.REVIEW,
            self.Status.REVISION,
        }

    @property
    def contributes_to_workload(self):
        # "На проверке" остаётся текущей задачей, но исполнитель уже не занят её выполнением.
        return self.status in {
            self.Status.NEW,
            self.Status.IN_PROGRESS,
            self.Status.REVISION,
        }

    @property
    def deadline_state(self):
        if self.status in {self.Status.DONE, self.Status.CANCELLED}:
            return "done"
        if self.status == self.Status.REVIEW:
            return "review"
        if self.status == self.Status.REVISION:
            return "revision"
        if self.due_date is None:
            return "no-date"
        today = timezone.localdate()
        days = (self.due_date - today).days
        if days < 0:
            return "overdue"
        if days == 0:
            return "today"
        if days <= 2:
            return "soon"
        if days <= 7:
            return "warning"
        return "normal"

    @property
    def deadline_label(self):
        if self.status == self.Status.DONE:
            return "Выполнена"
        if self.status == self.Status.CANCELLED:
            return "Отменена"
        if self.status == self.Status.REVIEW:
            return "На проверке"
        if self.status == self.Status.REVISION:
            return "На доработке"
        if self.due_date is None:
            return "Без срока"
        today = timezone.localdate()
        days = (self.due_date - today).days
        if days < 0:
            return f"Просрочено на {abs(days)} дн."
        if days == 0:
            return "Сегодня"
        if days == 1:
            return "Завтра"
        return self.due_date.strftime("%d.%m.%Y")


class TaskMemberProgress(models.Model):
    """Independent readiness of each current or former task participant."""

    class State(models.TextChoices):
        PENDING = "pending", "Не приступил"
        IN_PROGRESS = "in_progress", "В работе"
        READY = "ready", "Готово"

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="member_progress", verbose_name="Задача")
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="task_progress", verbose_name="Сотрудник")
    state = models.CharField("Готовность", max_length=20, choices=State.choices, default=State.PENDING)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        ordering = ["user__last_name", "user__first_name", "user_id"]
        constraints = [models.UniqueConstraint(fields=["task", "user"], name="unique_task_member_progress")]
        verbose_name = "Готовность участника"
        verbose_name_plural = "Готовность участников"

    def __str__(self):
        return f"{self.task_id}: {self.user_id} — {self.get_state_display()}"


class TaskHandover(models.Model):
    """Immutable record of who took over a task and why."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="handovers", verbose_name="Задача")
    from_employee = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="task_handovers_from", verbose_name="Прежний исполнитель"
    )
    to_employee = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="task_handovers_to", verbose_name="Новый исполнитель"
    )
    changed_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="task_handovers_made", verbose_name="Кто передал"
    )
    reason = models.CharField("Причина передачи", max_length=500)
    keep_previous = models.BooleanField("Оставить прежнего соисполнителем", default=False)
    created_at = models.DateTimeField("Когда передана", auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Передача задачи"
        verbose_name_plural = "Передачи задач"

    def __str__(self):
        return f"#{self.task_id}: {self.from_employee_id} → {self.to_employee_id}"


class TaskTemplate(models.Model):
    name = models.CharField("Название шаблона", max_length=150, unique=True)
    title = models.CharField("Название задачи", max_length=200)
    description = models.TextField("Описание", blank=True)
    priority = models.CharField("Приоритет", max_length=20, choices=Task.Priority.choices, default=Task.Priority.NORMAL)
    effort = models.CharField("Трудоёмкость", max_length=20, choices=Task.Effort.choices, default=Task.Effort.MEDIUM)
    default_due_days = models.PositiveSmallIntegerField(
        "Срок через N дней",
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(365)],
    )
    is_active = models.BooleanField("Активен", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Шаблон задачи"
        verbose_name_plural = "Шаблоны задач"

    def __str__(self):
        return self.name


class SavedTaskFilter(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="saved_task_filters",
        verbose_name="Пользователь",
    )
    name = models.CharField("Название", max_length=80)
    parameters = models.JSONField("Параметры фильтра", default=dict)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Изменён", auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Сохранённый фильтр задач"
        verbose_name_plural = "Сохранённые фильтры задач"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_user_saved_task_filter_name",
            )
        ]

    def __str__(self):
        return f"{self.user}: {self.name}"


class Notification(models.Model):
    class Kind(models.TextChoices):
        ASSIGNED = "assigned", "Назначена задача"
        DUE_CHANGED = "due_changed", "Изменён срок"
        DUE_SOON = "due_soon", "Срок завтра"
        OVERDUE = "overdue", "Просрочено"
        COMPLETED = "completed", "Задача выполнена (старое)"
        SUBMITTED_REVIEW = "submitted_review", "Отправлена на проверку"
        ACCEPTED = "accepted", "Задача принята"
        REVISION_REQUESTED = "revision_requested", "Возвращена на доработку"
        MANAGER_COMPLETED = "manager_completed", "Выполнена руководителем"
        CANCELLED = "cancelled", "Задача отменена"
        COMMENT = "comment", "Новый комментарий"
        MANAGER_ASSIGNED = "manager_assigned", "Назначен ответственный руководитель"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="task_notifications", verbose_name="Получатель")
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="notifications", verbose_name="Задача")
    kind = models.CharField("Тип", max_length=30, choices=Kind.choices)
    message = models.CharField("Сообщение", max_length=300)
    notification_date = models.DateField("Дата уведомления", default=timezone.localdate, db_index=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    read_at = models.DateTimeField("Прочитано", blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "task", "kind", "notification_date"],
                name="unique_daily_task_notification",
            )
        ]

    def __str__(self):
        return f"{self.user}: {self.message}"

    @property
    def is_read(self):
        return self.read_at is not None

    @property
    def requires_action(self):
        if self.kind == self.Kind.SUBMITTED_REVIEW:
            return self.task.status == Task.Status.REVIEW
        if self.kind == self.Kind.REVISION_REQUESTED:
            return self.task.status == Task.Status.REVISION
        if self.kind == self.Kind.OVERDUE:
            return bool(
                self.task.status in {Task.Status.NEW, Task.Status.IN_PROGRESS, Task.Status.REVISION}
                and self.task.due_date
                and self.task.due_date < timezone.localdate()
            )
        return False

    @property
    def category_label(self):
        return "Требует действия" if self.requires_action else "Информация"


class TaskEvent(models.Model):
    class Kind(models.TextChoices):
        CREATED = "created", "Задача создана"
        STATUS = "status", "Изменён статус"
        DUE_DATE = "due_date", "Изменён срок"
        ASSIGNEE = "assignee", "Изменён исполнитель"
        MANAGER = "manager", "Изменён ответственный руководитель"
        TEAM = "team", "Изменён состав исполнителей"
        HANDOVER = "handover", "Передана задача"
        PRIORITY = "priority", "Изменён приоритет"
        COMMENT = "comment", "Добавлен комментарий"
        IMAGE = "image", "Добавлено изображение"

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="history", verbose_name="Задача")
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_events",
        verbose_name="Кто изменил",
    )
    kind = models.CharField("Тип события", max_length=30, choices=Kind.choices)
    message = models.CharField("Описание", max_length=500)
    from_status = models.CharField("Предыдущий статус", max_length=20, blank=True)
    to_status = models.CharField("Новый статус", max_length=20, blank=True)
    created_at = models.DateTimeField("Дата события", auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "История задачи"
        verbose_name_plural = "История задач"

    def __str__(self):
        return f"{self.task}: {self.message}"


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments", verbose_name="Задача")
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="task_comments",
        verbose_name="Автор",
    )
    text = models.TextField("Комментарий", max_length=5000)
    created_at = models.DateTimeField("Дата комментария", auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "Комментарий к задаче"
        verbose_name_plural = "Комментарии к задачам"

    def __str__(self):
        return f"{self.task}: {self.text[:60]}"


class TaskImage(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="images", verbose_name="Задача")
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="task_images",
        verbose_name="Кто загрузил",
    )
    image = models.ImageField("Изображение", upload_to=task_image_upload_to)
    original_name = models.CharField("Исходное имя", max_length=255)
    content_type = models.CharField("MIME-тип", max_length=50)
    created_at = models.DateTimeField("Дата загрузки", auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "Фото/скриншот задачи"
        verbose_name_plural = "Фото/скриншоты задач"

    def __str__(self):
        return f"{self.task}: {self.original_name}"


class EmployeeAbsence(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="employee_absences",
        verbose_name="Сотрудник",
    )
    start_date = models.DateField("Начало", db_index=True)
    end_date = models.DateField("Окончание", db_index=True)
    reason = models.CharField("Причина", max_length=200, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_employee_absences",
        verbose_name="Добавил",
    )
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        ordering = ["start_date", "user_id"]
        verbose_name = "Отсутствие сотрудника"
        verbose_name_plural = "Отсутствия сотрудников"
        indexes = [
            models.Index(fields=["user", "start_date", "end_date"], name="absence_user_dates_idx"),
        ]

    def __str__(self):
        name = self.user.get_full_name() or self.user.username
        return f"{name}: {self.start_date:%d.%m.%Y}–{self.end_date:%d.%m.%Y}"

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({"end_date": "Дата окончания не может быть раньше даты начала."})
        if self.user_id and not self.user.groups.filter(name=EMPLOYEES_GROUP).exists():
            raise ValidationError({"user": "Отсутствие можно указать только для сотрудника группы Employees."})
        if self.user_id and self.start_date and self.end_date:
            overlapping = type(self).objects.filter(
                user_id=self.user_id,
                start_date__lte=self.end_date,
                end_date__gte=self.start_date,
            ).exclude(pk=self.pk)
            if overlapping.exists():
                raise ValidationError("У сотрудника уже есть пересекающийся период отсутствия.")

    @property
    def is_current(self):
        today = timezone.localdate()
        return self.start_date <= today <= self.end_date


class WorkCalendarDay(models.Model):
    """Explicit override for the Republic of Tatarstan production calendar.

    Ordinary Saturdays/Sundays and fixed holidays are derived automatically.
    This model stores the dates that are published for a concrete year: transferred
    days off, religious holidays, and working weekends.
    """

    date = models.DateField("Дата", unique=True, db_index=True)
    is_working_day = models.BooleanField("Рабочий день", default=False)
    name = models.CharField("Название / причина", max_length=200, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        ordering = ["date"]
        verbose_name = "День производственного календаря РТ"
        verbose_name_plural = "Производственный календарь РТ"

    def __str__(self):
        state = "Рабочий" if self.is_working_day else "Нерабочий"
        suffix = f" — {self.name}" if self.name else ""
        return f"{self.date:%d.%m.%Y}: {state}{suffix}"


import math

class FeatureIdea(models.Model):
    class Status(models.TextChoices):
        VOTING = "voting", "Голосование"
        REVIEW = "review", "Будет рассмотрено"
        IN_PROGRESS = "in_progress", "В работе"
        IMPLEMENTED = "implemented", "Реализовано"
        REJECTED = "rejected", "Отклонено"

    title = models.CharField("Название идеи", max_length=160)
    description = models.TextField("Описание")
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="feature_ideas")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.VOTING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def electorate_size(self):
        return User.objects.filter(is_active=True, groups__name=EMPLOYEES_GROUP).distinct().count()

    @property
    def yes_votes(self):
        return self.votes.filter(user__is_active=True, user__groups__name=EMPLOYEES_GROUP, choice=True).distinct().count()

    @property
    def no_votes(self):
        return self.votes.filter(user__is_active=True, user__groups__name=EMPLOYEES_GROUP, choice=False).distinct().count()

    @property
    def approval_percent(self):
        total = self.electorate_size
        return round(100 * self.yes_votes / total, 1) if total else 0

    @property
    def threshold(self):
        return math.ceil(self.electorate_size * 0.8)

    @property
    def qualifies(self):
        return self.electorate_size > 0 and self.yes_votes >= self.threshold

    def refresh_review_status(self):
        # Review decision is sticky once reached; managers can later advance status.
        if self.status == self.Status.VOTING and self.qualifies:
            self.status = self.Status.REVIEW
            self.save(update_fields=["status", "updated_at"])

    def __str__(self):
        return self.title


class FeatureVote(models.Model):
    idea = models.ForeignKey(FeatureIdea, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="feature_votes")
    choice = models.BooleanField("За")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["idea", "user"], name="unique_feature_idea_vote")]


class ChatMessage(models.Model):
    author = models.ForeignKey(User, on_delete=models.PROTECT, related_name="chat_messages")
    text = models.TextField(max_length=2000)
    reply_to = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    mentions = models.ManyToManyField(User, blank=True, related_name="chat_mentions")

    class Meta:
        ordering = ["id"]


class ChatReadState(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="chat_read_state")
    last_read_message_id = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class ChatNotificationSettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="chat_notification_settings")
    in_app = models.BooleanField(default=True)
    desktop = models.BooleanField(default=False)
    sound = models.BooleanField(default=True)
    mentions = models.BooleanField(default=True)
    volume = models.PositiveSmallIntegerField(default=25, validators=[MinValueValidator(0), MaxValueValidator(100)])
