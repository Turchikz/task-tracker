from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("tasks", "0013_mouse_wallet"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(name="RouletteTopic", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("title", models.CharField(max_length=120, unique=True, verbose_name="Тема")),
            ("winner_count", models.PositiveSmallIntegerField(default=3, verbose_name="Сколько выбрать")),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="roulette_topics", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-created_at", "-pk"]}),
        migrations.CreateModel(name="RouletteDraw", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("request_id", models.UUIDField(unique=True)),
            ("participants", models.JSONField(default=list)),
            ("excluded", models.JSONField(default=list)),
            ("winners", models.JSONField(default=list)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("launched_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="roulette_draws", to=settings.AUTH_USER_MODEL)),
            ("topic", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="draws", to="tasks.roulettetopic")),
        ], options={"ordering": ["-created_at", "-pk"]}),
    ]
