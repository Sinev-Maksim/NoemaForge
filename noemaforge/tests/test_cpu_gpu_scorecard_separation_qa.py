#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_cpu_gpu_scorecard_separation_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test docs and registry coverage for separate CPU/GPU scorecards.
Inputs: Workspace docs and unified registry.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import cpu_gpu_scorecard_separation_runtime as cgs


class CpuGpuScorecardSeparationQATests(unittest.TestCase):
    def test_registry_attaches_cpu_gpu_scorecard_separation_eval_pack(self) -> None:
        policy = cgs.load_policy(ROOT / "configs" / "cpu-gpu-scorecard-separation-policy.json")
        report = cgs.validate_cpu_gpu_scorecard_separation_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        registry = json.loads((ROOT / "configs" / "unified-registry.json").read_text(encoding="utf-8"))
        pack = next(
            entry for entry in registry["entries"]
            if entry.get("kind") == "eval-pack" and entry.get("id") == "cpu-gpu-scorecard-separation-core"
        )
        self.assertIn("configs/cpu-gpu-scorecard-separation-policy.json", pack["refs"])
        self.assertIn("src/model_scorecards.py", pack["refs"])
        self.assertIn("src/role_tournament.py", pack["refs"])
        self.assertIn("cpu_scorecard_namespace", pack["metadata"]["metrics"])

    def test_canonical_docs_record_closed_scorecard_item(self) -> None:
        closed_item = "[x] Record CPU and GPU scorecards separately."
        open_item = "[ ] Record CPU and GPU scorecards separately."
        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("cpu-gpu-scorecard-separation-core", text, str(path))
            self.assertIn("model_scorecards/cpu", text, str(path))
            self.assertIn("model_scorecards/gpu", text, str(path))

        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertIn(closed_item, backlog)
        self.assertNotIn(open_item, backlog)


if __name__ == "__main__":
    unittest.main()
