"""Daily command: re-evaluate and send 90/60/30-day expiry alerts."""
from django.core.management.base import BaseCommand

from compliance.expiry import check_expirations


class Command(BaseCommand):
    help = "Re-evaluate compliance and send 90/60/30-day expiry alerts (each once) plus expired notices."

    def add_arguments(self, parser):
        parser.add_argument("--no-email", action="store_true", help="Create in-app notifications only.")

    def handle(self, *args, **options):
        result = check_expirations(send_email=not options["no_email"])
        self.stdout.write(f"Evaluated {result.evaluated} faculty member(s).")
        for threshold in sorted(result.alerts):
            self.stdout.write(f"  {threshold}-day alerts sent: {result.alerts[threshold]}")
        self.stdout.write(f"  Expired notices sent: {result.expired_notices}")
        self.stdout.write(self.style.SUCCESS(f"Done. {result.total_alerts} new alert(s)."))
