from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("tasks", "0009_member_progress"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="FeatureIdea", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("title", models.CharField(max_length=160, verbose_name="Название идеи")),
            ("description", models.TextField(verbose_name="Описание")),
            ("status", models.CharField(choices=[("voting", "Голосование"), ("review", "Будет рассмотрено"), ("in_progress", "В работе"), ("implemented", "Реализовано"), ("rejected", "Отклонено")], default="voting", max_length=20)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("author", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="feature_ideas", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-created_at"]}),
        migrations.CreateModel(name="FeatureVote", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("choice", models.BooleanField(verbose_name="За")),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("idea", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="votes", to="tasks.featureidea")),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="feature_votes", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.AddConstraint(model_name="featurevote", constraint=models.UniqueConstraint(fields=("idea", "user"), name="unique_feature_idea_vote")),
    ]
