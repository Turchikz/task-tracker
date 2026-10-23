from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tasks", "0007_responsible_manager_saved_filters"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="additional_assignees",
            field=models.ManyToManyField(
                blank=True,
                related_name="collaborating_tasks",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Дополнительные исполнители",
            ),
        ),
        migrations.CreateModel(
            name="TaskHandover",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.CharField(max_length=500, verbose_name="Причина передачи")),
                ("keep_previous", models.BooleanField(default=False, verbose_name="Оставить прежнего соисполнителем")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Когда передана")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="handovers", to="tasks.task", verbose_name="Задача")),
                ("from_employee", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="task_handovers_from", to=settings.AUTH_USER_MODEL, verbose_name="Прежний исполнитель")),
                ("to_employee", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="task_handovers_to", to=settings.AUTH_USER_MODEL, verbose_name="Новый исполнитель")),
                ("changed_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="task_handovers_made", to=settings.AUTH_USER_MODEL, verbose_name="Кто передал")),
            ],
            options={"ordering": ["-created_at", "-pk"], "verbose_name": "Передача задачи", "verbose_name_plural": "Передачи задач"},
        ),
        migrations.AlterField(
            model_name="taskevent", name="kind",
            field=models.CharField(
                max_length=30, verbose_name="Тип события",
                choices=[
                    ("created", "Задача создана"), ("status", "Изменён статус"),
                    ("due_date", "Изменён срок"), ("assignee", "Изменён исполнитель"),
                    ("manager", "Изменён ответственный руководитель"),
                    ("team", "Изменён состав исполнителей"), ("handover", "Передана задача"),
                    ("priority", "Изменён приоритет"), ("comment", "Добавлен комментарий"),
                    ("image", "Добавлено изображение"),
                ],
            ),
        ),
    ]
