import hashlib
import hmac
import json
from threading import BoundedSemaphore
from unittest.mock import patch

from django.conf import settings
from django.db import transaction
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from nova_slider_captcha import services, webhooks
from nova_slider_captcha.checks import captcha_settings_check
from nova_slider_captcha.models import Challenge
from tests.test_boundaries import CaptchaReplicaRouter
from tests.test_captcha import CaptchaHelpers

CONFIG = {"url": "https://receiver.invalid:8443/captcha", "secret": "ab" * 32}


class WebhookTransportTests(SimpleTestCase):
    def test_disabled_and_invalid_configurations(self):
        self.assertIsNone(webhooks.webhook_configuration())
        for value in (
            False, {}, {**CONFIG, "secret": "private"}, {**CONFIG, "url": "http://receiver.invalid"},
            {**CONFIG, "url": "https://private@receiver.invalid/"},
            {**CONFIG, "url": "https://receiver.invalid/?private"},
            {**CONFIG, "url": "https://receiver.invalid:99999"},
            {**CONFIG, "url": "https://receiver.invalid/\nprivate"},
            {**CONFIG, "url": "https://receiver%2einvalid"},
        ):
            with self.subTest(value=value), self.settings(NOVA_SLIDER_WEBHOOK=value):
                with self.assertRaises(ValueError) as error:
                    webhooks.webhook_configuration()
                self.assertNotIn("private", str(error.exception))
                self.assertIn("nova_slider_captcha.E011", [item.id for item in captcha_settings_check(None)])

    @override_settings(NOVA_SLIDER_WEBHOOK=CONFIG)
    def test_signed_request_and_error_response_are_single_attempts(self):
        config = webhooks.webhook_configuration()
        notification_ids = set()
        for status in (200, 302, 503):
            slot = BoundedSemaphore(1)
            self.assertTrue(slot.acquire(blocking=False))
            with (
                patch.object(webhooks, "time", return_value=1700000000),
                patch.object(webhooks.http.client, "HTTPSConnection") as connect,
            ):
                connection = connect.return_value
                connection.getresponse.return_value.status = status
                webhooks._deliver(config, "verification_succeeded", slot)
                connect.assert_called_once_with("receiver.invalid", 8443, timeout=2)
                body = connection.request.call_args.args[2]
                payload = json.loads(body)
                self.assertEqual(set(payload), {"event", "notification_id"})
                self.assertEqual(payload["event"], "verification_succeeded")
                self.assertRegex(payload["notification_id"], r"^[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}$")
                notification_ids.add(payload["notification_id"])
                signature = hmac.new(bytes.fromhex(CONFIG["secret"]), b"1700000000." + body, hashlib.sha256).hexdigest()
                connection.request.assert_called_once_with("POST", "/captcha", body, headers={
                    "Content-Type": "application/json",
                    "X-Nova-Webhook-Timestamp": "1700000000",
                    "X-Nova-Webhook-Signature": "sha256=" + signature,
                })
                connection.getresponse.assert_called_once()
                connection.getresponse.return_value.read.assert_not_called()
                connection.close.assert_called_once()
            self.assertTrue(slot.acquire(blocking=False))
        self.assertEqual(len(notification_ids), 3)

    @override_settings(NOVA_SLIDER_WEBHOOK=CONFIG)
    def test_timeout_and_thread_start_failure_release_capacity(self):
        config = webhooks.webhook_configuration()
        slot = BoundedSemaphore(1)
        with patch.object(webhooks, "_slots", slot), patch.object(webhooks, "Thread") as thread:
            thread.return_value.start.side_effect = RuntimeError("thread unavailable")
            webhooks._submit(config, "proof_consumed")
            self.assertTrue(slot.acquire(blocking=False))
            webhooks._submit(config, "proof_consumed")
            thread.assert_called_once()
        with patch.object(webhooks.http.client, "HTTPSConnection") as connect:
            connect.return_value.getresponse.side_effect = TimeoutError("private")
            webhooks._deliver(config, "proof_consumed", slot)
            connect.return_value.close.assert_called_once()
        self.assertTrue(slot.acquire(blocking=False))


@override_settings(NOVA_SLIDER_WEBHOOK=CONFIG, DATABASE_ROUTERS=[CaptchaReplicaRouter()])
class WebhookCommitTests(CaptchaHelpers, TransactionTestCase):
    databases = {"default", "captcha", "replica"}

    def setUp(self):
        self.request_obj = self.request(self.client_with_init())

    def issue(self):
        data = services.issue(self.request_obj, "demo")
        return Challenge.objects.using("captcha").get(pk=data["challengeId"])

    def verify_row(self, row):
        return services.verify(self.request_obj, row.pk, row.target_x)["token"]

    def test_correct_writer_commit_and_no_events_for_failure_or_replay(self):
        with patch.object(webhooks, "Thread") as thread, transaction.atomic():
            with transaction.atomic(using="captcha"):
                row = self.issue()
                services.verify(self.request_obj, row.pk, row.target_x - 20)
                token = self.verify_row(row)
                self.assertTrue(services.consume(token, self.request_obj, "demo"))
                self.assertFalse(services.consume(token, self.request_obj, "demo"))
                thread.assert_not_called()
            self.assertEqual(
                [call.kwargs["args"][1] for call in thread.call_args_list],
                ["verification_succeeded", "proof_consumed"],
            )
            for call in thread.call_args_list:
                call.kwargs["args"][2].release()

    def test_nested_and_outer_rollbacks_drop_notifications(self):
        with patch.object(webhooks, "_submit") as submit:
            row = self.issue()
            with transaction.atomic(using="captcha"):
                with transaction.atomic(using="captcha"):
                    token = self.verify_row(row)
                    self.assertTrue(services.consume(token, self.request_obj, "demo"))
                    transaction.set_rollback(True, using="captcha")
            with transaction.atomic(using="captcha"):
                self.verify_row(row)
                transaction.set_rollback(True, using="captcha")
            submit.assert_not_called()
            self.verify_row(row)
            self.assertEqual(submit.call_args.args[1], "verification_succeeded")

    def test_manual_commit_and_rollback_and_unsupported_manual_hook(self):
        using = "captcha"
        write = transaction.get_connection(using)
        with patch.object(webhooks, "_submit") as submit:
            for committed in (False, True):
                row = self.issue()
                write.set_autocommit(False)
                try:
                    # Ensure SQLite starts a transaction before its first savepoint.
                    Challenge.objects.using(using).filter(pk=row.pk).update(attempts=0)
                    with transaction.atomic(using=using):
                        self.verify_row(row)
                    if committed:
                        write.commit()
                    else:
                        write.rollback()
                    submit.assert_not_called()
                finally:
                    write.set_autocommit(True)
            submit.assert_called_once()
            submit.reset_mock()
            row = self.issue()
            write.set_autocommit(False)
            try:
                self.verify_row(row)
                write.rollback()
            finally:
                write.set_autocommit(True)
            submit.assert_not_called()

    def test_configuration_and_delivery_failures_do_not_interrupt_commit_callbacks(self):
        with patch.object(webhooks, "Thread") as thread:
            thread.return_value.start.side_effect = RuntimeError("private")
            other = []
            with transaction.atomic(using="captcha"):
                row = self.issue()
                self.verify_row(row)
                transaction.on_commit(lambda: other.append("committed"), using="captcha")
            self.assertEqual(other, ["committed"])
            self.assertEqual(thread.call_count, 1)
            with self.settings(NOVA_SLIDER_WEBHOOK={"url": "invalid"}):
                self.verify_row(self.issue())
            with self.settings(NOVA_SLIDER_WEBHOOK=CONFIG):
                with transaction.atomic(using="captcha"):
                    self.verify_row(self.issue())
                    # Live configuration also gates delayed dispatch.
                    settings.NOVA_SLIDER_WEBHOOK = None
            self.assertEqual(thread.call_count, 1)
