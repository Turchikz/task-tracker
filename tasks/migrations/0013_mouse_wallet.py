from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("tasks", "0012_chat_notification_settings"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(name="MouseWallet", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("cheese", models.PositiveIntegerField(default=0)),
            ("earned", models.PositiveIntegerField(default=0)),
            ("catches", models.PositiveIntegerField(default=0)),
            ("hat", models.BooleanField(default=False)),
            ("scarf", models.BooleanField(default=False)),
            ("legacy_imported", models.BooleanField(default=False)),
            ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="mouse_wallet", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="MouseWalletEvent", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("event_id", models.UUIDField()),
            ("action", models.CharField(max_length=12)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mouse_wallet_events", to=settings.AUTH_USER_MODEL)),
        ], options={"constraints": [models.UniqueConstraint(fields=("user", "event_id"), name="unique_mouse_wallet_event")]}),
    ]
