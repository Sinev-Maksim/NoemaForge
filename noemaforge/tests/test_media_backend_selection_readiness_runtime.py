#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_media_backend_selection_readiness_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the media backend selection readiness contract.
Inputs: Media backend selection readiness policy and runtime validator.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import media_backend_selection_readiness_runtime as mbsr


class MediaBackendSelectionReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_backends(self) -> None:
        report = mbsr.validate_media_backend_selection_readiness_policy(mbsr.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["media_backend_selection_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertEqual(7, summary["backend_slot_count"])
        self.assertIn("target_smoke_transcript", report["evidence_requirements"])

    def test_privacy_gated_slots_require_privacy_gate(self) -> None:
        broken = copy.deepcopy(mbsr.load_policy())
        for slot in broken["policy"]["required_backend_slots"]:
            if slot["id"] == "stt":
                slot["privacy_gate_required"] = False
        failures = mbsr._policy_failures(broken)
        self.assertIn("slot_privacy_gate_missing:stt", failures)

    def test_target_live_smoke_requires_operator_approval(self) -> None:
        broken = copy.deepcopy(mbsr.load_policy())
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "target-live-media-smoke":
                check["requires_operator_approval"] = False
        failures = mbsr._policy_failures(broken)
        self.assertIn("check_operator_approval_required:target-live-media-smoke", failures)

    def test_backend_slot_must_require_explicit_selection(self) -> None:
        broken = copy.deepcopy(mbsr.load_policy())
        for slot in broken["policy"]["required_backend_slots"]:
            if slot["id"] == "video_generation":
                slot["explicit_selection_required"] = False
        failures = mbsr._policy_failures(broken)
        self.assertIn("slot_explicit_selection_not_true:video_generation", failures)


if __name__ == "__main__":
    unittest.main()
