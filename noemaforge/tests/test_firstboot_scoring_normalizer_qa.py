#!/usr/bin/env python3
from __future__ import annotations

import os
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent


class FirstbootScoringNormalizerQATests(unittest.TestCase):
    def _read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def test_runtime_paths_integrate_normalizer_before_scoring(self) -> None:
        normalizer = self._read(ROOT / "src" / "model_inventory_normalize.py")
        role_tournament = self._read(ROOT / "src" / "role_tournament.py")
        firstboot_eval = self._read(ROOT / "src" / "firstboot_eval.py")

        self.assertIn("def normalize_inventory_models", normalizer)
        self.assertIn("def normalize_inventory_for_scoring", role_tournament)
        self.assertIn("normalize_inventory_for_scoring(inventory)", role_tournament)
        self.assertIn("_normalize_registry_models_for_scoring", firstboot_eval)
        self.assertIn("normalizer_rejected", firstboot_eval)

    def test_docs_and_release_notes_track_closed_todo(self) -> None:
        expected = "Integrate normalizer directly into every firstboot scoring path."
        for rel in (
            "docs/backlog/ROADMAP_AND_TODO.md",
            "noemaforge/docs/backlog/ROADMAP_AND_TODO.md",
        ):
            text = self._read(PROJECT_ROOT / rel)
            self.assertIn(f"- [x] {expected}", text)

        for rel in ("TODO.md", "noemaforge/TODO.md", "CHANGELOG.md", "RELEASE_NOTES.md", "docs/history/CHANGELOG.md", "noemaforge/docs/history/CHANGELOG.md"):
            text = self._read(PROJECT_ROOT / rel).lower()
            self.assertIn("firstboot scoring normalizer", text, rel)
            self.assertIn("non-head", text, rel)


if __name__ == "__main__":
    unittest.main()
