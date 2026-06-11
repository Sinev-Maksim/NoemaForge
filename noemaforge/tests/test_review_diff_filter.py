#!/usr/bin/env python3
"""Regression tests for the review-diff evidence filter (ci/filter_review_diff.py).

Locks the skip regex so future evidence-file path variants never silently
enter the model review prompt (Codex review optimization, PR #87).
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci"))

from filter_review_diff import filter_diff  # noqa: E402


def block(path: str, body: str = "+x\n") -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n{body}"
    )


class ReviewDiffFilterTests(unittest.TestCase):
    EVIDENCE_PATHS = [
        "MANIFEST.json",
        "MANIFEST.json.sha256",
        "MANIFEST.sha256",
        "SHA256SUMS",
        "SHA256SUMS.sha256",
        "noemaforge/checksums/SHA256SUMS",
        "noemaforge/docs/MANIFEST.json",
        "noemaforge/docs/MANIFEST.json.sha256",
        # future mirrors must also be caught (any path depth)
        "docs/MANIFEST.json",
        "some/deep/dir/SHA256SUMS.sha256",
    ]
    CODE_PATHS = [
        "noemaforge/src/admin_gui_server.py",
        "ci/wiki_check.py",
        # near-misses that must NOT be filtered
        "noemaforge/src/manifest_tools.py",
        "docs/MANIFEST_NOTES.md",
        "SHA256SUMS_README.md",
    ]

    def test_evidence_blocks_are_stripped_and_code_kept(self) -> None:
        raw = "".join(block(p) for p in self.EVIDENCE_PATHS + self.CODE_PATHS)
        filtered, kept, omitted, _ = filter_diff(raw, cap_bytes=10**6)
        self.assertEqual(omitted, len(self.EVIDENCE_PATHS))
        self.assertEqual(kept, len(self.CODE_PATHS))
        for p in self.CODE_PATHS:
            self.assertIn(f"a/{p} ", filtered, p)
        for p in self.EVIDENCE_PATHS:
            self.assertNotIn(f"a/{p} ", filtered, p)
        self.assertIn("generated evidence file diff(s) omitted", filtered)

    def test_evidence_only_diff_reports_zero_kept(self) -> None:
        raw = "".join(block(p) for p in self.EVIDENCE_PATHS)
        _, kept, omitted, _ = filter_diff(raw, cap_bytes=10**6)
        self.assertEqual(kept, 0)
        self.assertEqual(omitted, len(self.EVIDENCE_PATHS))

    def test_cap_appends_truncation_note(self) -> None:
        raw = block("noemaforge/src/big.py", body="+line\n" * 5000)
        filtered, _, _, _ = filter_diff(raw, cap_bytes=2048)
        self.assertLess(len(filtered), 2300)
        self.assertIn("diff truncated", filtered)

    def test_clean_code_diff_passes_through_unchanged(self) -> None:
        raw = block("noemaforge/src/x.py")
        filtered, kept, omitted, _ = filter_diff(raw, cap_bytes=10**6)
        self.assertEqual((kept, omitted), (1, 0))
        self.assertEqual(filtered, raw)


if __name__ == "__main__":
    unittest.main()
