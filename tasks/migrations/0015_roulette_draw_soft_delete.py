from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("tasks", "0014_roulette"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.AddField(model_name="roulettedraw", name="deleted_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="roulettedraw", name="deleted_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="removed_roulette_draws", to=settings.AUTH_USER_MODEL)),
    ]
