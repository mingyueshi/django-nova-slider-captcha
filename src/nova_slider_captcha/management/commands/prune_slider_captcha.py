from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import connections, router
from django.utils import timezone
from nova_slider_captcha.models import Challenge, RateBucket, RateLimitState
from nova_slider_captcha.services import timestamp_us


class Command(BaseCommand):
    help = "Remove expired CAPTCHA records, legacy buckets and fully refilled rate states. Run regularly."

    def handle(self, *args, **options):
        now = timezone.now()
        # Proof can outlive the challenge; retain well beyond both TTLs.
        challenges, _ = Challenge.objects.filter(expires_at__lt=now - timedelta(minutes=5)).delete()
        buckets, _ = RateBucket.objects.filter(expires_at__lt=now).delete()
        # A row is disposable only after ALL quota debt and upgrade blocking
        # have expired. Conditional DELETE cannot remove a concurrent new claim.
        now_us = timestamp_us(now)
        database = connections[router.db_for_write(RateLimitState)]
        quote = database.ops.quote_name
        # QuerySet.delete() may select IDs first when deletion signals exist.
        # Internal quota state must retain its predicate at the write boundary.
        with database.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {quote(RateLimitState._meta.db_table)} "
                f"WHERE {quote('tat_us')} <= %s AND {quote('blocked_until_us')} <= %s",
                [now_us, now_us],
            )
            states = cursor.rowcount
        self.stdout.write(f"Removed {challenges} CAPTCHA records and {buckets} legacy rate buckets and {states} rate states.")
