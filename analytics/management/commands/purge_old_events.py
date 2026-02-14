"""
Management command to purge old analytics events and deletion logs.

Usage:
    python manage.py purge_old_events                # Purge events older than 730 days (default)
    python manage.py purge_old_events --days 365     # Purge events older than 365 days
    python manage.py purge_old_events --dry-run      # Show what would be deleted without deleting

Recommended: Run via cron job (weekly)
    0 3 * * 0 cd /app && python manage.py purge_old_events >> /var/log/respectlytics/purge.log 2>&1
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from analytics.models import Event, DeletionLog


class Command(BaseCommand):
    help = 'Purge analytics events and deletion logs older than N days (default: 730)'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=730, help='Delete events older than this many days')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without deleting')

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        cutoff = timezone.now() - timedelta(days=days)

        old_events = Event.objects.filter(timestamp__lt=cutoff)
        event_count = old_events.count()

        old_logs = DeletionLog.objects.filter(deleted_at__lt=cutoff)
        log_count = old_logs.count()

        if dry_run:
            self.stdout.write(f'[DRY RUN] Would delete {event_count} events older than {days} days')
            self.stdout.write(f'[DRY RUN] Would delete {log_count} deletion logs older than {days} days')
            return

        events_deleted, _ = old_events.delete()
        logs_deleted, _ = old_logs.delete()

        self.stdout.write(self.style.SUCCESS(
            f'Purged {events_deleted} events and {logs_deleted} deletion logs older than {days} days'
        ))
