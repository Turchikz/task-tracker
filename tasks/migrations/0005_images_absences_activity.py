import django.db.models.deletion
import tasks.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tasks", "0004_taskcomment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
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
                    ("comment", "Добавлен комментарий"),
                    ("image", "Добавлено изображение"),
                ],
                max_length=30,
                verbose_name="Тип события",
            ),
        ),
        migrations.CreateModel(
            name="EmployeeAbsence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_date", models.DateField(db_index=True, verbose_name="Начало")),
                ("end_date", models.DateField(db_index=True, verbose_name="Окончание")),
                ("reason", models.CharField(blank=True, max_length=200, verbose_name="Причина")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_employee_absences", to=settings.AUTH_USER_MODEL, verbose_name="Добавил")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="employee_absences", to=settings.AUTH_USER_MODEL, verbose_name="Сотрудник")),
            ],
            options={
                "verbose_name": "Отсутствие сотрудника",
                "verbose_name_plural": "Отсутствия сотрудников",
                "ordering": ["start_date", "user_id"],
            },
        ),
        migrations.CreateModel(
            name="TaskImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to=tasks.models.task_image_upload_to, verbose_name="Изображение")),
                ("original_name", models.CharField(max_length=255, verbose_name="Исходное имя")),
                ("content_type", models.CharField(max_length=50, verbose_name="MIME-тип")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Дата загрузки")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="images", to="tasks.task", verbose_name="Задача")),
                ("uploaded_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="task_images", to=settings.AUTH_USER_MODEL, verbose_name="Кто загрузил")),
            ],
            options={
                "verbose_name": "Фото/скриншот задачи",
                "verbose_name_plural": "Фото/скриншоты задач",
                "ordering": ["created_at", "pk"],
            },
        ),
        migrations.AddIndex(
            model_name="employeeabsence",
            index=models.Index(fields=["user", "start_date", "end_date"], name="absence_user_dates_idx"),
        ),
    ]
