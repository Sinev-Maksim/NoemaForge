#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_a2a_interop_registry_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate optional A2A interoperability safety policy and reference checks.
Inputs: Workspace A2A interop registry and temporary broken fixtures.
Outputs: unittest assertions only.
Side effects: Creates and removes temporary fixture directories.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import a2a_interop_registry_runtime as airr


class A2AInteropRegistryRuntimeTests(unittest.TestCase):
    def test_workspace_a2a_interop_registry_validates_optional_defaults(self) -> None:
        registry_path = ROOT / "configs" / "a2a-interop-registry.json"
        report = airr.validate_a2a_interop_registry(
            airr.load_registry(registry_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=registry_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(2, report["metrics"]["peers"])
        self.assertEqual(2, report["metrics"]["disabled_peers"])
        self.assertEqual(0, report["metrics"]["active_peers"])
        self.assertEqual(0, report["metrics"]["missing_refs"])
        self.assertEqual(0, report["metrics"]["unsafe_refs"])
        self.assertEqual("deny", report["policy"]["default_network"])
        self.assertEqual("none", report["policy"]["default_direction"])

    def test_policy_and_peer_checks_block_unreviewed_active_network_peer(self) -> None:
        with tempfile.TemporaryDirectory(prefix="a2a-interop-", dir=os.path.dirname(__file__)) as tmp:
            project = Path(tmp)
            package = project / "noemaforge"
            (package / "configs").mkdir(parents=True)
            (package / "src").mkdir(parents=True)
            (package / "configs" / "tool-policy.yaml").write_text("roles: []\n", encoding="utf-8")
            (package / "src" / "a2a_interop_registry_runtime.py").write_text("# runtime\n", encoding="utf-8")

            registry = {
                "apiVersion": "noemaforge.a2a-interop/v1",
                "kind": "A2AInteropRegistry",
                "id": "bad-a2a-registry",
                "version": "v1",
                "policy": {
                    "default_state": "enabled",
                    "default_direction": "bidirectional",
                    "default_network": "allow",
                    "require_trace_id": True,
                    "require_capability_token": False,
                    "require_registry_entry": True,
                    "require_operator_review": True,
                    "require_release_evidence_before_enable": True,
                    "allowed_transports": ["offline_manifest", "http"],
                    "blocked_transports": ["websocket"],
                    "allowed_payload_classes": ["task_summary"],
                    "max_peer_risk": "medium",
                },
                "peers": [
                    {
                        "id": "remote.agent",
                        "version": "v1",
                        "protocol": "a2a",
                        "state": "enabled",
                        "transport": "http",
                        "direction": "bidirectional",
                        "network": "allow",
                        "risk": "high",
                        "autonomy_increase": True,
                        "capability_scopes": [],
                        "allowed_payload_classes": ["tool_execution"],
                        "allowed_actions": ["delegate"],
                        "trace_required": True,
                        "capability_token_required": False,
                        "registry_entry_required": True,
                        "registry_ref": "tool-policy:tool-policy-main:v1",
                        "audit_logging": False,
                        "human_review_required": False,
                        "sandbox": {"profile": "remote", "write": True, "egress": "allow", "external_identity": "remote"},
                        "review": {"required": False, "route": "", "reviewers": []},
                        "release_evidence": {"required_before_enable": True, "evidence_ref": ""},
                        "rollback_plan": "short",
                        "refs": ["configs/tool-policy.yaml", "src/missing.py"],
                    }
                ],
            }

            report = airr.validate_a2a_interop_registry(registry, project_root=project, package_root=package)

            self.assertFalse(report["ok"])
            self.assertIn("policy_default_state_not_disabled", report["failures"])
            self.assertIn("policy_default_direction_not_none", report["failures"])
            self.assertIn("policy_default_network_not_deny", report["failures"])
            self.assertIn("policy_require_capability_token_not_true", report["failures"])
            self.assertIn("policy_network_transport_not_blocked:http", report["failures"])
            self.assertIn("peer_network_not_deny:remote.agent", report["failures"])
            self.assertIn("peer_autonomy_increase_not_false:remote.agent", report["failures"])
            self.assertIn("peer_capability_scopes_empty:remote.agent", report["failures"])
            self.assertIn("peer_invalid_payload_class:remote.agent:tool_execution", report["failures"])
            self.assertIn("peer_active_without_release_evidence:remote.agent", report["failures"])
            self.assertEqual(1, report["metrics"]["missing_refs"])

    def test_cli_summary_uses_workspace_registry_contract(self) -> None:
        registry_path = ROOT / "configs" / "a2a-interop-registry.json"
        report = airr.validate_a2a_interop_registry(
            json.loads(registry_path.read_text(encoding="utf-8")),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=registry_path,
        )
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual({"disabled": 2}, report["metrics"]["states"])
        self.assertEqual({"inbound": 1, "outbound": 1}, report["metrics"]["directions"])


if __name__ == "__main__":
    unittest.main()
