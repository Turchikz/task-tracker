from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from tasks.models import ChatMessage

class Command(BaseCommand):
    help = "Remove chat messages older than six calendar months (UTC timestamp)."

    def handle(self, *args, **options):
        # Six calendar months rather than a fixed 180-day approximation.
        from django.utils.timezone import localtime
        from datetime import datetime
        from calendar import monthrange
        now = timezone.now()
        month_index = now.year * 12 + now.month - 1 - 6
        year, month_zero = divmod(month_index, 12)
        month = month_zero + 1
        cutoff = now.replace(year=year, month=month, day=min(now.day, monthrange(year, month)[1]))
        total = 0
        while True:
            ids = list(ChatMessage.objects.filter(created_at__lt=cutoff).order_by('pk').values_list('pk', flat=True)[:500])
            if not ids: break
            ChatMessage.objects.filter(pk__in=ids).delete()
            total += len(ids)
        self.stdout.write(self.style.SUCCESS(f"Deleted {total} old chat messages"))
