"""Deliberate test failure to verify report generation; no services or writes."""
import os
import unittest
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
import django
django.setup()
from nova_slider_captcha.services import session_binding


class ReportingProbe(unittest.TestCase):
    def test_deliberate_failure(self):
        self.assertIsNone(session_binding(None))
        self.fail("Deliberate local coverage reporting probe")


if __name__ == "__main__":
    unittest.main()
