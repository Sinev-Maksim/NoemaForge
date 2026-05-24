#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_media_capture_privacy_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate media capture privacy gate runtime behaviour.
Inputs: Workspace media capture privacy policy and examples.
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

import media_capture_privacy_runtime as mcpr


class MediaCapturePrivacyRuntimeTests(unittest.TestCase):
    def test_workspace_media_capture_privacy_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "media-capture-privacy-policy.json"
        report = mcpr.validate_media_capture_privacy_policy(
            mcpr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(3, report["metrics"]["guarded_actions"])
        self.assertEqual(2, report["metrics"]["scenarios"])
        self.assertEqual(2, report["metrics"]["passing_scenarios"])

    def test_hidden_microphone_capture_is_blocked(self) -> None:
        policy = mcpr.load_policy(ROOT / "configs" / "media-capture-privacy-policy.json")
        result = mcpr.validate_capture_request(
            {
                "action": "voice.capture_live",
                "source": "microphone",
                "operator_consent": False,
                "visible_privacy_state": False,
                "manual_operator_command": False,
                "autostart": True,
                "max_seconds": 60,
            },
            policy,
        )

        self.assertEqual("block", result["decision"])
        self.assertIn("operator_consent_required", result["failures"])
        self.assertIn("visible_privacy_state_required", result["failures"])
        self.assertIn("autostart_forbidden", result["failures"])
        self.assertIn("max_seconds_exceeds_policy", result["failures"])

    def test_manual_virtual_camera_mask_plan_is_allowed(self) -> None:
        policy = mcpr.load_policy(ROOT / "configs" / "media-capture-privacy-policy.json")
        result = mcpr.validate_capture_request(
            {
                "action": "camera.mask_virtual_camera",
                "source": "camera",
                "target": "virtual_camera",
                "operator_consent": True,
                "visible_privacy_state": True,
                "manual_operator_command": True,
                "user_selected_target": True,
                "autostart": False,
                "max_seconds": 0,
            },
            policy,
        )

        self.assertEqual("allow", result["decision"])
        self.assertEqual([], result["failures"])


if __name__ == "__main__":
    unittest.main()
