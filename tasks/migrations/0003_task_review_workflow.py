import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tasks", "0002_task_start_date"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="task",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "Новая"),
                    ("in_progress", "В работе"),
                    ("review", "На проверке"),
                    ("revision", "На доработке"),
                    ("done", "Выполнена"),
                    ("cancelled", "Отменена"),
                ],
                db_index=True,
                default="new",
                max_length=20,
                verbose_name="Статус",
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="started_at",
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name="Фактически начата"),
        ),
        migrations.AddField(
            model_name="task",
            name="submitted_at",
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name="Последняя отправка на проверку"),
        ),
        migrations.AddField(
            model_name="task",
            name="revision_reason",
            field=models.TextField(blank=True, editable=False, verbose_name="Последняя причина доработки"),
        ),
        migrations.AlterField(
            model_name="notification",
            name="kind",
            field=models.CharField(
                choices=[
                    ("assigned", "Назначена задача"),
                    ("due_changed", "Изменён срок"),
                    ("due_soon", "Срок завтра"),
                    ("overdue", "Просрочено"),
                    ("completed", "Задача выполнена (старое)"),
                    ("submitted_review", "Отправлена на проверку"),
                    ("accepted", "Задача принята"),
                    ("revision_requested", "Возвращена на доработку"),
                    ("manager_completed", "Выполнена руководителем"),
                    ("cancelled", "Задача отменена"),
                ],
                max_length=30,
                verbose_name="Тип",
            ),
        ),
        migrations.CreateModel(
            name="TaskEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("created", "Задача создана"), ("status", "Изменён статус"), ("due_date", "Изменён срок"), ("assignee", "Изменён исполнитель")], max_length=30, verbose_name="Тип события")),
                ("message", models.CharField(max_length=500, verbose_name="Описание")),
                ("from_status", models.CharField(blank=True, max_length=20, verbose_name="Предыдущий статус")),
                ("to_status", models.CharField(blank=True, max_length=20, verbose_name="Новый статус")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Дата события")),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="task_events", to=settings.AUTH_USER_MODEL, verbose_name="Кто изменил")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="history", to="tasks.task", verbose_name="Задача")),
            ],
            options={
                "verbose_name": "История задачи",
                "verbose_name_plural": "История задач",
                "ordering": ["-created_at", "-pk"],
            },
        ),
    ]
