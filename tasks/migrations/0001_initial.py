import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="TaskTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150, unique=True, verbose_name="Название шаблона")),
                ("title", models.CharField(max_length=200, verbose_name="Название задачи")),
                ("description", models.TextField(blank=True, verbose_name="Описание")),
                ("priority", models.CharField(choices=[("low", "Низкий"), ("normal", "Обычный"), ("high", "Высокий"), ("urgent", "Срочный")], default="normal", max_length=20, verbose_name="Приоритет")),
                ("effort", models.CharField(choices=[("small", "Малая"), ("medium", "Средняя"), ("large", "Большая"), ("xlarge", "Очень большая")], default="medium", max_length=20, verbose_name="Трудоёмкость")),
                ("default_due_days", models.PositiveSmallIntegerField(default=1, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(365)], verbose_name="Срок через N дней")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активен")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Шаблон задачи", "verbose_name_plural": "Шаблоны задач", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Task",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200, verbose_name="Название")),
                ("description", models.TextField(blank=True, verbose_name="Описание")),
                ("status", models.CharField(choices=[("new", "Новая"), ("in_progress", "В работе"), ("done", "Выполнена"), ("cancelled", "Отменена")], db_index=True, default="new", max_length=20, verbose_name="Статус")),
                ("priority", models.CharField(choices=[("low", "Низкий"), ("normal", "Обычный"), ("high", "Высокий"), ("urgent", "Срочный")], db_index=True, default="normal", max_length=20, verbose_name="Приоритет")),
                ("effort", models.CharField(choices=[("small", "Малая"), ("medium", "Средняя"), ("large", "Большая"), ("xlarge", "Очень большая")], default="medium", max_length=20, verbose_name="Трудоёмкость")),
                ("due_date", models.DateField(blank=True, db_index=True, null=True, verbose_name="Срок")),
                ("completed_at", models.DateTimeField(blank=True, editable=False, null=True, verbose_name="Дата выполнения")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создана")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Изменена")),
                ("assigned_to", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="assigned_tasks", to=settings.AUTH_USER_MODEL, verbose_name="Исполнитель")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_tasks", to=settings.AUTH_USER_MODEL, verbose_name="Автор")),
            ],
            options={"verbose_name": "Задача", "verbose_name_plural": "Задачи", "ordering": ["due_date", "-priority", "-created_at"]},
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("assigned", "Назначена задача"), ("due_changed", "Изменён срок"), ("due_soon", "Срок завтра"), ("overdue", "Просрочено"), ("completed", "Задача выполнена")], max_length=30, verbose_name="Тип")),
                ("message", models.CharField(max_length=300, verbose_name="Сообщение")),
                ("notification_date", models.DateField(db_index=True, default=django.utils.timezone.localdate, verbose_name="Дата уведомления")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("read_at", models.DateTimeField(blank=True, null=True, verbose_name="Прочитано")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="tasks.task", verbose_name="Задача")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="task_notifications", to=settings.AUTH_USER_MODEL, verbose_name="Получатель")),
            ],
            options={"verbose_name": "Уведомление", "verbose_name_plural": "Уведомления", "ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="task", index=models.Index(fields=["assigned_to", "status", "due_date"], name="task_assignee_status_due_idx")),
        migrations.AddIndex(model_name="task", index=models.Index(fields=["status", "priority"], name="task_status_priority_idx")),
        migrations.AddConstraint(model_name="notification", constraint=models.UniqueConstraint(fields=("user", "task", "kind", "notification_date"), name="unique_daily_task_notification")),
    ]
