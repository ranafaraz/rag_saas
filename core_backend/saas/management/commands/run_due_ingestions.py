from django.core.management.base import BaseCommand
from django.utils import timezone

from saas.views import _run_due_schedules


class Command(BaseCommand):
    help = 'Run due ingestion schedules and update next run timestamps.'

    def handle(self, *args, **options):
        now = timezone.now()
        processed = _run_due_schedules(now)

        self.stdout.write(self.style.SUCCESS(f'Processed {processed} due ingestion schedule(s).'))
