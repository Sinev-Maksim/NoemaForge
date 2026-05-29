#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_post_reboot_validation_archive_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the post-reboot validation archive readiness contract.
Inputs: Post-reboot validation archive readiness policy and runtime validator.
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

import post_reboot_validation_archive_readiness_runtime as prvar


class PostRebootValidationArchiveReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_target_commands(self) -> None:
        report = prvar.validate_post_reboot_validation_archive_readiness_policy(prvar.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["post_reboot_archive_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertTrue(summary["target_machine_required"])
        self.assertGreaterEqual(summary["target_command_count"], 12)
        self.assertIn("wiki_patch_manifest", report["evidence_requirements"])

    def test_target_smoke_requires_operator_approval(self) -> None:
        broken = copy.deepcopy(prvar.load_policy())
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "target-smoke-transcript":
                check["requires_operator_approval"] = False
        failures = prvar._policy_failures(broken)
        self.assertIn("check_operator_approval_required:target-smoke-transcript", failures)

    def test_wiki_patch_bundle_requires_manifest_and_target_refs(self) -> None:
        broken = copy.deepcopy(prvar.load_policy())
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "wiki-patch-bundle":
                check["completion_gates"] = ["canonical_docs_updated_after_review"]
        failures = prvar._policy_failures(broken)
        self.assertIn("check_wiki_patch_gate_missing:wiki_patch_manifest_exists", failures)
        self.assertIn("check_wiki_patch_gate_missing:target_evidence_refs_recorded", failures)

    def test_forensics_archive_requires_hash_and_redaction(self) -> None:
        broken = copy.deepcopy(prvar.load_policy())
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "forensics-log-archive":
                check["completion_gates"] = ["bundle_exists", "evidence_file_archived"]
        failures = prvar._policy_failures(broken)
        self.assertIn("check_forensics_archive_gate_missing:bundle_sha256_recorded", failures)
        self.assertIn("check_forensics_archive_gate_missing:secrets_redacted", failures)


if __name__ == "__main__":
    unittest.main()
