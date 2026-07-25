#!/usr/bin/env python3
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DISPOSITION = REPO / "noemaforge" / "docs" / "security" / "code-scanning-0.33.0-disposition.md"
COLLECTED_ALERTS = {
    289, 288, 286, 285, 271, 223, 217, 180, 179, 178,
    177, 167, 149, 143, 140, 139, 137, 130, 104, 103,
    102, 101, 100, 99, 96, 69, 66, 65, 64, 63, 62,
    61, 60, 59, 58, 57, 56, 55, 53, 52, 51, 50, 49,
    48, 47, 46, 45, 20, 19, 4,
}


class CodeScanningDispositionTests(unittest.TestCase):
    def test_every_collected_alert_has_disposition(self) -> None:
        text = DISPOSITION.read_text(encoding="utf-8")
        documented = {int(match) for match in re.findall(r"ALERT-(\d+)", text)}
        self.assertEqual(COLLECTED_ALERTS, documented)

    def test_disposition_does_not_claim_all_alerts_closed(self) -> None:
        text = DISPOSITION.read_text(encoding="utf-8")
        self.assertIn("It does not claim that all collected", text)
        self.assertIn("production tag still needs", text)


if __name__ == "__main__":
    unittest.main()
