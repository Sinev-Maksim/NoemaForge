#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_backlog_status_legend_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate backlog status legend hygiene policy and scanner behavior.
Inputs: Backlog status legend policy and synthetic Markdown snippets.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import backlog_status_legend_runtime as bslr
import production_ai_contracts as pac


class BacklogStatusLegendRuntimeTests(unittest.TestCase):
    def test_policy_validates_and_maps_to_docs_hygiene_gate(self) -> None:
        policy = bslr.load_policy(ROOT / "configs" / "backlog-status-legend-policy.json")
        report = bslr.validate_backlog_status_legend_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertTrue(report["ok"], report["failures"])
        gate = pac.evaluate_gate(
            {
                "change_id": "backlog-status-legend-core",
                "domain": "pipeline",
                "required_checks": ["docs_hygiene", "rollback_plan"],
            },
            {
                "artifact_uri": "reports/backlog-status-legend.json",
                "run_at": "2026-05-20T00:00:00Z",
                "checks": [
                    {"id": "docs_hygiene", "status": "passed" if report["ok"] else "failed"},
                    {"id": "rollback_plan", "status": "passed"},
                ],
            },
        )
        self.assertTrue(gate["ok"], gate)

    def test_legacy_task_list_legend_is_rejected(self) -> None:
        text = """Status legend:
- [ ] planned
- [~] in progress / partially covered
- [x] done
"""
        policy = bslr.load_policy(ROOT / "configs" / "backlog-status-legend-policy.json")
        violations = bslr.find_status_legend_violations(
            text,
            source="synthetic.md",
            forbidden_markers=policy["policy"]["forbidden_legend_markers"],
        )

        self.assertEqual(3, len(violations))
        self.assertEqual("- [ ] planned", violations[0]["marker"])

    def test_canonical_legend_is_not_a_task_list(self) -> None:
        text = """Status legend:
- `planned`: open/not started.
- `in progress`: partially covered.
- `done`: complete.
- `explicit non-goal`: outside the ASAP window.
"""
        policy = bslr.load_policy(ROOT / "configs" / "backlog-status-legend-policy.json")
        violations = bslr.find_status_legend_violations(
            text,
            source="synthetic.md",
            forbidden_markers=policy["policy"]["forbidden_legend_markers"],
        )

        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
