from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_responsible_manager(apps, schema_editor):
    Task = apps.get_model("tasks", "Task")
    Task.objects.filter(responsible_manager__isnull=True).update(
        responsible_manager_id=models.F("created_by_id")
    )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tasks", "0006_workcalendarday"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="responsible_manager",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="responsible_tasks",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Ответственный руководитель",
            ),
        ),
        migrations.RunPython(
            backfill_responsible_manager,
            migrations.RunPython.noop,
        ),
        migrations.AddIndex(
            model_name="task",
            index=models.Index(
                fields=["responsible_manager", "status", "due_date"],
                name="task_manager_status_due_idx",
            ),
        ),
        migrations.CreateModel(
            name="SavedTaskFilter",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=80, verbose_name="Название")),
                (
                    "parameters",
                    models.JSONField(default=dict, verbose_name="Параметры фильтра"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создан")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Изменён")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="saved_task_filters",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Сохранённый фильтр задач",
                "verbose_name_plural": "Сохранённые фильтры задач",
                "ordering": ["name"],
            },
        ),
        migrations.AddConstraint(
            model_name="savedtaskfilter",
            constraint=models.UniqueConstraint(
                fields=("user", "name"),
                name="unique_user_saved_task_filter_name",
            ),
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
                    ("comment", "Новый комментарий"),
                    ("manager_assigned", "Назначен ответственный руководитель"),
                ],
                max_length=30,
                verbose_name="Тип",
            ),
        ),
        migrations.AlterField(
            model_name="taskevent",
            name="kind",
            field=models.CharField(
                choices=[
                    ("created", "Задача создана"),
                    ("status", "Изменён статус"),
                    ("due_date", "Изменён срок"),
                    ("assignee", "Изменён исполнитель"),
                    ("manager", "Изменён ответственный руководитель"),
                    ("priority", "Изменён приоритет"),
                    ("comment", "Добавлен комментарий"),
                    ("image", "Добавлено изображение"),
                ],
                max_length=30,
                verbose_name="Тип события",
            ),
        ),
    ]
