# -*- coding: utf-8 -*-
"""The data-report envelope's own guarantees: no credential reaches a
warning (2026-09-25)."""
from __future__ import annotations

import unittest

from src.tiered_analysis.providers.base import DataReport, SourceKind, redact_secrets


class TestRedactSecrets(unittest.TestCase):
    def test_every_credential_parameter_is_blanked_and_the_rest_kept(self):
        text = ("for url: https://x.io/a?symbol=AAPL&token=abc123&from=2026-09-18 "
                "and https://api.stlouisfed.org/fred/series?series_id=GDP&api_key=K9&file_type=json "
                "Key=UPPER apikey=z access_token=t")
        out = redact_secrets(text)
        for secret in ("abc123", "K9", "UPPER", "apikey=z", "access_token=t"):
            self.assertNotIn(secret, out)
        self.assertIn("symbol=AAPL", out)
        self.assertIn("series_id=GDP", out)
        self.assertIn("token=<redacted>", out)
        self.assertIn("api_key=<redacted>", out)
        self.assertIn("from=2026-09-18", out)

    def test_a_plain_message_is_unchanged(self):
        self.assertEqual(redact_secrets("Yahoo down"), "Yahoo down")
        # A field named *_key is not a credential parameter.
        self.assertEqual(redact_secrets("ticker_key=AAPL"), "ticker_key=AAPL")


class TestDataReportRedaction(unittest.TestCase):
    def test_warnings_and_field_notes_are_redacted_on_construction(self):
        report = DataReport(
            name="company_news", kind=SourceKind.TEXTUAL,
            warnings=["failed: https://x.io/?token=S1"],
            field_warnings={"news.items": ["failed: https://x.io/?api_key=S2"]},
        )
        self.assertEqual(report.warnings, ["failed: https://x.io/?token=<redacted>"])
        self.assertEqual(report.field_warnings, {"news.items": ["failed: https://x.io/?api_key=<redacted>"]})


if __name__ == "__main__":
    unittest.main()
