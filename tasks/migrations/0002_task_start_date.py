from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tasks", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="task",
            name="start_date",
            field=models.DateField(blank=True, db_index=True, null=True, verbose_name="Плановое начало"),
        ),
    ]
