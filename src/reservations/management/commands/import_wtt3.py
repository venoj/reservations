"""Management command to import reservations from WTT3 API."""

from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from reservations.models import Reservation


class Command(BaseCommand):
    """Import reservations from Wyse Timetables (WTT3) API."""

    help = "Import reservations from Wyse Timetables (WTT3) API"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--api-url",
            type=str,
            help="Base URL for WTT3 API (overrides WTT3_API_URL setting)",
        )
        parser.add_argument(
            "--api-key",
            type=str,
            help="API key for authentication (overrides WTT3_API_KEY setting)",
        )
        parser.add_argument(
            "--start-date",
            type=str,
            help="Start date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
        )
        parser.add_argument(
            "--end-date",
            type=str,
            help="End date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Test the API connection without importing data",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        api_url = options.get("api_url")
        api_key = options.get("api_key")
        start_date_str = options.get("start_date")
        end_date_str = options.get("end_date")
        dry_run = options.get("dry_run", False)

        # Parse date strings if provided
        start_date = None
        end_date = None

        if start_date_str:
            try:
                start_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
                if timezone.is_naive(start_date):
                    start_date = timezone.make_aware(start_date)
            except ValueError:
                raise CommandError(
                    f"Invalid start-date format: {start_date_str}. "
                    "Use ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS"
                )

        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                if timezone.is_naive(end_date):
                    end_date = timezone.make_aware(end_date)
            except ValueError:
                raise CommandError(
                    f"Invalid end-date format: {end_date_str}. "
                    "Use ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS"
                )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No data will be imported")
            )
            self.stdout.write(f"API URL: {api_url or 'Using WTT3_API_URL from settings'}")
            self.stdout.write(f"API Key: {'***' if api_key else 'Using WTT3_API_KEY from settings'}")
            if start_date:
                self.stdout.write(f"Start Date: {start_date}")
            if end_date:
                self.stdout.write(f"End Date: {end_date}")
            return

        try:
            self.stdout.write("Importing reservations from WTT3 API...")
            created, updated = Reservation.objects.import_from_wtt3(
                api_url=api_url,
                api_key=api_key,
                start_date=start_date,
                end_date=end_date,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully imported {created} new reservations "
                    f"and updated {updated} existing reservations."
                )
            )
        except Exception as e:
            raise CommandError(f"Error importing reservations: {e}")