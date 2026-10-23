from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from tasks.models import Notification, Task
from tasks.signals import create_notification


class Command(BaseCommand):
    help = "Создаёт внутренние уведомления о задачах на завтра и просроченных задачах."

    def handle(self, *args, **options):
        today = timezone.localdate()
        active = Task.objects.filter(
            status__in=[Task.Status.NEW, Task.Status.IN_PROGRESS, Task.Status.REVISION]
        ).select_related("assigned_to", "created_by", "responsible_manager").prefetch_related("additional_assignees")
        created_before = Notification.objects.count()

        for task in active.filter(due_date=today + timedelta(days=1)):
            for member in task.team_members:
                create_notification(
                    member,
                    task,
                    Notification.Kind.DUE_SOON,
                    f"Срок задачи «{task.title}» — завтра.",
                )

        for task in active.filter(due_date__lt=today):
            for member in task.team_members:
                create_notification(
                    member,
                    task,
                    Notification.Kind.OVERDUE,
                    f"Задача «{task.title}» просрочена.",
                )
            manager = task.responsible_manager or task.created_by
            if manager and manager.pk != task.assigned_to_id:
                create_notification(
                    manager,
                    task,
                    Notification.Kind.OVERDUE,
                    f"Задача «{task.title}» у {task.assigned_to.get_full_name() or task.assigned_to.username} просрочена.",
                )

        created_after = Notification.objects.count()
        self.stdout.write(self.style.SUCCESS(f"Создано уведомлений: {created_after - created_before}"))
