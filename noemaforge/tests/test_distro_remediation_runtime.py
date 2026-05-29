#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_distro_remediation_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate distro detection and dependency remediation contract.
Inputs: Workspace distro-remediation policy and prep scripts.
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

import distro_remediation_runtime as drr


class DistroRemediationRuntimeTests(unittest.TestCase):
    def test_workspace_distro_remediation_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "distro-remediation-policy.json"
        report = drr.validate_distro_remediation_policy(
            drr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(4, report["metrics"]["supported_families"])
        self.assertEqual(4, report["metrics"]["valid_package_reports"])
        self.assertEqual(3, report["metrics"]["valid_script_reports"])

    def test_os_release_classification_covers_target_families(self) -> None:
        fixtures = {
            "debian": 'ID=debian\nVERSION_ID="13"\nVERSION_CODENAME=trixie\n',
            "ubuntu": 'ID=ubuntu\nID_LIKE=debian\nVERSION_ID="24.04"\n',
            "fedora": 'ID=fedora\nVERSION_ID="40"\n',
            "rhel_like": 'ID=rocky\nID_LIKE="rhel fedora"\n',
            "arch": 'ID=arch\n',
            "suse": 'ID=opensuse-leap\nID_LIKE="suse"\n',
        }

        self.assertEqual("debian", drr.classify_os_release(fixtures["debian"])["family"])
        self.assertEqual("debian", drr.classify_os_release(fixtures["ubuntu"])["family"])
        self.assertEqual("fedora", drr.classify_os_release(fixtures["fedora"])["family"])
        self.assertEqual("fedora", drr.classify_os_release(fixtures["rhel_like"])["family"])
        self.assertEqual("arch", drr.classify_os_release(fixtures["arch"])["family"])
        self.assertEqual("suse", drr.classify_os_release(fixtures["suse"])["family"])

    def test_remediation_plan_is_not_detection_only(self) -> None:
        plan = drr.build_remediation_plan(
            'ID=debian\nVERSION_ID="13"\nVERSION_CODENAME=trixie\n',
            available_commands={"curl", "git", "python3", "findmnt", "systemctl"},
        )

        self.assertTrue(plan["supported"])
        self.assertEqual("apt-get", plan["package_manager"])
        self.assertIn("python3-yaml", plan["packages"])
        self.assertIn("jq", plan["missing_commands"])
        self.assertIn("apt-get install -y", plan["install_command"])
        self.assertIn("NOEMAFORGE_ALLOW_PACKAGE_REMEDIATION=1", plan["apply_gates"])

    def test_preflight_and_first_launch_remediation_surfaces_exist(self) -> None:
        preflight = (ROOT / "tools" / "prep" / "noemaforge-trixie-preflight.sh").read_text(encoding="utf-8")
        first_launch = (ROOT / "tools" / "prep" / "noemaforge-first-launch.sh").read_text(encoding="utf-8")

        self.assertIn("--remediation-plan", preflight)
        self.assertIn("--apply-remediation", preflight)
        self.assertIn("'remediation': {", preflight)
        self.assertIn("NOEMAFORGE_ALLOW_PACKAGE_REMEDIATION", preflight)
        for token in ["apt-get", "dnf", "pacman", "zypper"]:
            self.assertIn(token, first_launch)


if __name__ == "__main__":
    unittest.main()
