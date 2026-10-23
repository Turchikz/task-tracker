from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators

class Migration(migrations.Migration):
    dependencies = [("tasks", "0011_department_chat"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="ChatNotificationSettings", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("in_app", models.BooleanField(default=True)),
        ("desktop", models.BooleanField(default=False)),
        ("sound", models.BooleanField(default=True)),
        ("mentions", models.BooleanField(default=True)),
        ("volume", models.PositiveSmallIntegerField(default=25, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
        ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="chat_notification_settings", to=settings.AUTH_USER_MODEL)),
    ])]
