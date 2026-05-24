#!/usr/bin/env python3
from __future__ import annotations

import os
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent


class DatasetAssuranceQATests(unittest.TestCase):
    def _read(self, rel: str) -> str:
        return (PROJECT_ROOT / rel).read_text(encoding="utf-8")

    def test_launcher_happy_path_records_dataset_assurance(self) -> None:
        orchestrator = self._read("noemaforge/src/firstboot_orchestrator.py")
        datasets = self._read("noemaforge/src/dataset_inventory.py")
        progress = self._read("noemaforge/src/firstboot_progress_runtime.py")

        self.assertIn("assure_role_eval_dataset()", orchestrator)
        self.assertIn("dataset-assurance.json", orchestrator)
        self.assertIn("blocked_dataset_assurance", orchestrator)
        self.assertIn("def assure_role_eval_dataset", datasets)
        self.assertIn("dataset_assurance", progress)

    def test_docs_track_closed_dataset_assurance_todo(self) -> None:
        item = "Add dataset assurance to launcher happy path."
        for rel in ("docs/backlog/ROADMAP_AND_TODO.md", "noemaforge/docs/backlog/ROADMAP_AND_TODO.md"):
            self.assertIn(f"- [x] {item}", self._read(rel))

        for rel in ("TODO.md", "noemaforge/TODO.md", "CHANGELOG.md", "RELEASE_NOTES.md", "docs/history/CHANGELOG.md", "noemaforge/docs/history/CHANGELOG.md"):
            text = self._read(rel).lower()
            self.assertIn("dataset assurance", text, rel)
            self.assertIn("role_eval_cases", text, rel)


if __name__ == "__main__":
    unittest.main()
