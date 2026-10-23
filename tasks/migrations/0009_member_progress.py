from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_progress(apps, schema_editor):
    Task = apps.get_model("tasks", "Task")
    Progress = apps.get_model("tasks", "TaskMemberProgress")
    Through = Task.additional_assignees.through
    batch = []
    for task_id, user_id in Task.objects.values_list("pk", "assigned_to_id").iterator():
        if user_id:
            batch.append(Progress(task_id=task_id, user_id=user_id))
    for task_id, user_id in Through.objects.values_list("task_id", "user_id").iterator():
        batch.append(Progress(task_id=task_id, user_id=user_id))
    # Old data can contain primary also in M2M: ignore duplicate key.
    Progress.objects.bulk_create(batch, ignore_conflicts=True, batch_size=300)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tasks", "0008_team_assignments_handovers"),
    ]
    operations = [
        migrations.CreateModel(
            name="TaskMemberProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("state", models.CharField(choices=[("pending", "Не приступил"), ("in_progress", "В работе"), ("ready", "Готово")], default="pending", max_length=20, verbose_name="Готовность")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Изменено")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="member_progress", to="tasks.task", verbose_name="Задача")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="task_progress", to=settings.AUTH_USER_MODEL, verbose_name="Сотрудник")),
            ],
            options={"ordering": ["user__last_name", "user__first_name", "user_id"], "verbose_name": "Готовность участника", "verbose_name_plural": "Готовность участников"},
        ),
        migrations.AddConstraint(model_name="taskmemberprogress", constraint=models.UniqueConstraint(fields=("task", "user"), name="unique_task_member_progress")),
        migrations.RunPython(backfill_progress, migrations.RunPython.noop),
    ]
