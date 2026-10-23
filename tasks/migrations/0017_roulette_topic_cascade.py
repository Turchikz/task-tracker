from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("tasks", "0016_important_files")]

    operations = [
        migrations.AlterField(model_name="roulettedraw", name="topic", field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="draws", to="tasks.roulettetopic")),
    ]
