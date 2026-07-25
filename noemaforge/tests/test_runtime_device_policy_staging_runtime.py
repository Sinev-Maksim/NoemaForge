#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_runtime_device_policy_staging_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate CPU/GPU device-policy staging without live backend migration.
Inputs: Workspace runtime-device-policy-staging policy and Admin GUI server runtime.
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

import runtime_device_policy_staging_runtime as rdps


class RuntimeDevicePolicyStagingRuntimeTests(unittest.TestCase):
    def test_workspace_runtime_device_policy_staging_validates(self) -> None:
        policy_path = ROOT / "configs" / "runtime-device-policy-staging-policy.json"
        report = rdps.validate_runtime_device_policy_staging_policy(
            rdps.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(3, report["metrics"]["source_reports"])
        self.assertEqual(3, report["metrics"]["valid_source_reports"])
        self.assertGreater(report["metrics"]["device_policy_set_chars"], 100)

    def test_device_policy_set_stages_cpu_gpu_and_cuda_alias_without_jobs(self) -> None:
        sequence = rdps.build_device_policy_sequence(package_root=ROOT)

        for key in ["cpu", "gpu", "cuda"]:
            response = sequence[key]
            self.assertTrue(response["ok"], response)
            self.assertTrue(response["policy"]["pending_apply"], response)
            self.assertEqual(response["policy"]["policy"], response["policy"]["session_override"]["policy"])
            self.assertEqual("session_override", response["policy"]["effective_policy"]["source"])
            self.assertEqual("next_persona_or_model_switch_or_backend_restart", response["policy"]["applies_on"])
            self.assertIn("backend restart", response["reply"])
        self.assertEqual("gpu", sequence["cuda"]["policy"]["policy"])
        self.assertFalse(sequence["invalid"]["ok"])
        self.assertFalse(any(key.endswith("runtime/device-policy.json") for key in sequence["store_keys"]))
        self.assertFalse(any("jobs" in key for key in sequence["store_keys"]))

    def test_staging_notes_make_no_active_model_migration_claim(self) -> None:
        sequence = rdps.build_device_policy_sequence(package_root=ROOT)
        note = sequence["gpu"]["policy"]["note"]

        self.assertIn("does not migrate the currently running model", note)
        self.assertIn("only on the next persona/model switch or backend restart", note)
        self.assertIn("session-only override", note)

    def test_session_override_does_not_survive_new_gui_session(self) -> None:
        first = rdps.build_offline_admin_gui_server(package_root=ROOT)
        first_set = first.device_policy_set("gpu")
        self.assertEqual("gpu", first_set["policy"]["effective_policy"]["policy"])
        self.assertEqual("session_override", first_set["policy"]["effective_policy"]["source"])

        second = rdps.build_offline_admin_gui_server(package_root=ROOT)
        second_policy = second.device_policy()["policy"]
        self.assertEqual("cpu", second_policy["effective_policy"]["policy"])
        self.assertEqual("safe_default", second_policy["effective_policy"]["source"])
        self.assertIsNone(second_policy["session_override"])


if __name__ == "__main__":
    unittest.main()
