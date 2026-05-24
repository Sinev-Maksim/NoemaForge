#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_cgroup_aware_stop_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate cgroup-aware stop/reboot-safe helper contract.
Inputs: Workspace cgroup-aware-stop policy and helper scripts.
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

import cgroup_aware_stop_runtime as casr


class CgroupAwareStopRuntimeTests(unittest.TestCase):
    def test_workspace_cgroup_aware_stop_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "cgroup-aware-stop-policy.json"
        report = casr.validate_cgroup_aware_stop_policy(
            casr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(3, report["metrics"]["stop_helpers"])
        self.assertEqual(3, report["metrics"]["valid_stop_helpers"])
        self.assertEqual(1, report["metrics"]["reboot_helpers"])
        self.assertEqual(2, report["metrics"]["ops_helpers"])

    def test_common_helpers_discover_unit_cgroups_and_read_cgroup_procs(self) -> None:
        common = (PROJECT_ROOT / "lib" / "noemaforge-common.sh").read_text(encoding="utf-8")
        self.assertIn("noemaforge_unit_control_group()", common)
        self.assertIn("systemctl show -p ControlGroup --value", common)
        self.assertIn("/sys/fs/cgroup${cg}", common)
        self.assertIn("cgroup.procs", common)
        self.assertIn("cgroup.threads", common)
        self.assertIn("kill \"-$signal\"", common)

    def test_stop_helpers_drain_cgroups_before_pkill_fallback(self) -> None:
        for helper in ["noemaforge-stop", "noemaforge-service-stop", "noemaforge-llm-stop"]:
            text = (PROJECT_ROOT / "helpers" / helper).read_text(encoding="utf-8")
            self.assertIn("=== drain NoemaForge systemd cgroups ===", text, helper)
            self.assertIn("noemaforge_drain_unit_cgroups TERM", text, helper)
            self.assertIn("noemaforge_drain_unit_cgroups KILL", text, helper)
            self.assertLess(text.index("noemaforge_drain_unit_cgroups TERM"), text.index("pkill -u"), helper)

    def test_reboot_safe_audits_cgroups_after_stop(self) -> None:
        text = (PROJECT_ROOT / "helpers" / "noemaforge-reboot-safe").read_text(encoding="utf-8")
        self.assertIn("=== NoemaForge unit cgroups after stop ===", text)
        self.assertIn("noemaforge_print_unit_cgroups", text)


if __name__ == "__main__":
    unittest.main()
