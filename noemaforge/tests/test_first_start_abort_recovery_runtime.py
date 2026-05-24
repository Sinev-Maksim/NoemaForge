#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_first_start_abort_recovery_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate first-start abort non-blocking GUI recovery regression contract.
Inputs: Workspace first-start-abort-recovery policy, CLI and recovery helper scripts.
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

import first_start_abort_recovery_runtime as fsar


class FirstStartAbortRecoveryRuntimeTests(unittest.TestCase):
    def test_workspace_first_start_abort_recovery_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "first-start-abort-recovery-policy.json"
        report = fsar.validate_first_start_abort_recovery_policy(
            fsar.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(3, report["metrics"]["script_reports"])
        self.assertEqual(3, report["metrics"]["valid_script_reports"])
        self.assertGreaterEqual(report["metrics"]["nonblocking_actions"], 5)

    def test_recovery_plan_prefers_nonblocking_gui_actions(self) -> None:
        plan = fsar.build_recovery_plan(dry_run=True)

        self.assertTrue(plan["dry_run"])
        self.assertIn("noemaforge-gui-recover-minimal.sh --reason first-start-abort --dry-run", plan["mutating_actions"])
        self.assertIn("systemctl start --no-block display-manager.service", plan["gui_recovery_actions"])
        self.assertIn("systemctl isolate --no-block graphical.target", plan["gui_recovery_actions"])
        self.assertGreaterEqual(len(plan["nonblocking_actions"]), 5)

    def test_cli_abort_dry_run_is_parseable_before_root_requirement(self) -> None:
        text = (ROOT / "bin" / "noemaforge").read_text(encoding="utf-8")
        start = text.index("cmd_first_start_abort()")
        end = text.index("cmd_first_start_diagnostics()", start)
        fn = text[start:end]

        self.assertIn("--dry-run", fn)
        self.assertLess(fn.index("dry_run=0"), fn.index("[[ \"$dry_run\" == \"1\" ]] || require_root"))
        self.assertIn("NoemaForge first-start abort dry-run requested.", fn)
        self.assertIn("noemaforge-gui-recover-minimal.sh\" --reason first-start-abort --dry-run", fn)

    def test_minimal_recovery_dry_run_does_not_mutate_host(self) -> None:
        text = (ROOT / "tools" / "prep" / "noemaforge-gui-recover-minimal.sh").read_text(encoding="utf-8")

        self.assertIn('[[ "$DRY_RUN" == "1" ]] || need_root', text)
        self.assertIn('if [[ "$DRY_RUN" != "1" ]]; then\n  mount -o remount,rw /', text)
        self.assertIn('if [[ "$DRY_RUN" != "1" ]]; then\n  install -d -m 0755 /var/lib/noemaforge/bootstrap', text)
        self.assertIn("run systemctl start --no-block display-manager.service", text)
        self.assertIn("run systemctl isolate --no-block graphical.target", text)


if __name__ == "__main__":
    unittest.main()
