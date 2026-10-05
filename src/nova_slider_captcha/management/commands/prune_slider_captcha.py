from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from nova_slider_captcha.models import Challenge, RateBucket


class Command(BaseCommand):
    help = "Remove expired CAPTCHA records and fixed-window rate buckets. Run regularly."

    def handle(self, *args, **options):
        now = timezone.now()
        # Proof can outlive the challenge; retain well beyond both TTLs.
        challenges, _ = Challenge.objects.filter(expires_at__lt=now - timedelta(minutes=5)).delete()
        buckets, _ = RateBucket.objects.filter(expires_at__lt=now).delete()
        self.stdout.write(f"Removed {challenges} CAPTCHA records and {buckets} rate buckets.")
