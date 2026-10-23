from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import tasks.models


class Migration(migrations.Migration):
    dependencies = [("tasks", "0015_roulette_draw_soft_delete"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(name="ImportantFile", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("title", models.CharField(max_length=160, verbose_name="Название")),
            ("description", models.TextField(blank=True, max_length=1000, verbose_name="Описание")),
            ("category", models.CharField(choices=[("regulations", "Регламенты"), ("forms", "Формы и шаблоны"), ("guides", "Инструкции"), ("other", "Прочее")], default="other", max_length=16, verbose_name="Категория")),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
            ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="important_files_created", to=settings.AUTH_USER_MODEL)),
            ("updated_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="important_files_updated", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-updated_at", "-pk"]}),
        migrations.CreateModel(name="ImportantFileRevision", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("file", models.FileField(upload_to=tasks.models.important_file_upload_to)),
            ("original_name", models.CharField(max_length=255)),
            ("size_bytes", models.PositiveBigIntegerField()),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("document", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="versions", to="tasks.importantfile")),
            ("uploaded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="important_file_revisions", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-created_at", "-pk"]}),
    ]
