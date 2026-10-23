from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("tasks", "0010_feature_ideas"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="ChatMessage", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("text", models.TextField(max_length=2000)),
            ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ("author", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="chat_messages", to=settings.AUTH_USER_MODEL)),
            ("reply_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="replies", to="tasks.chatmessage")),
            ("mentions", models.ManyToManyField(blank=True, related_name="chat_mentions", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["id"]}),
        migrations.CreateModel(name="ChatReadState", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("last_read_message_id", models.PositiveBigIntegerField(default=0)),
            ("updated_at", models.DateTimeField(auto_now=True)),
            ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="chat_read_state", to=settings.AUTH_USER_MODEL)),
        ]),
    ]
