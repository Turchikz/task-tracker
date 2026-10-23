import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tasks", "0003_task_review_workflow"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TaskComment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.TextField(max_length=5000, verbose_name="Комментарий")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Дата комментария")),
                ("author", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="task_comments", to=settings.AUTH_USER_MODEL, verbose_name="Автор")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comments", to="tasks.task", verbose_name="Задача")),
            ],
            options={
                "verbose_name": "Комментарий к задаче",
                "verbose_name_plural": "Комментарии к задачам",
                "ordering": ["created_at", "pk"],
            },
        ),
    ]
