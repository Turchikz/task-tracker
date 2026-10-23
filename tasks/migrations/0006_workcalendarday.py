from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tasks", "0005_images_absences_activity")]

    operations = [
        migrations.CreateModel(
            name="WorkCalendarDay",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(db_index=True, unique=True, verbose_name="Дата")),
                ("is_working_day", models.BooleanField(default=False, verbose_name="Рабочий день")),
                ("name", models.CharField(blank=True, max_length=200, verbose_name="Название / причина")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Изменено")),
            ],
            options={
                "verbose_name": "День производственного календаря РТ",
                "verbose_name_plural": "Производственный календарь РТ",
                "ordering": ["date"],
            },
        ),
    ]
