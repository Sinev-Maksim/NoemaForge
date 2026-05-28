#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_mcp_adapter_registry_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate MCP adapter registry safety policy and reference checks.
Inputs: Workspace MCP adapter registry and temporary broken fixtures.
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

import mcp_adapter_registry_runtime as marr


class MCPAdapterRegistryRuntimeTests(unittest.TestCase):
    def test_workspace_mcp_adapter_registry_validates_zero_trust_defaults(self) -> None:
        registry_path = ROOT / "configs" / "mcp-adapter-registry.json"
        report = marr.validate_mcp_adapter_registry(
            marr.load_registry(registry_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=registry_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(3, report["metrics"]["adapters"])
        self.assertEqual(3, report["metrics"]["disabled_adapters"])
        self.assertEqual(0, report["metrics"]["active_adapters"])
        self.assertEqual(0, report["metrics"]["missing_refs"])
        self.assertEqual(0, report["metrics"]["unsafe_refs"])
        self.assertEqual("deny", report["policy"]["default_network"])

    def test_policy_and_adapter_checks_block_network_and_token_gaps(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mcp-adapter-registry-", dir=os.path.dirname(__file__)) as tmp:
            project = Path(tmp)
            package = project / "noemaforge"
            (package / "configs").mkdir(parents=True)
            (package / "src").mkdir(parents=True)
            (package / "configs" / "tool-policy.yaml").write_text("roles: []\n", encoding="utf-8")
            (package / "src" / "mcp_router.py").write_text("# router\n", encoding="utf-8")

            registry = {
                "apiVersion": "noemaforge.mcp-adapter-registry/v1",
                "kind": "MCPAdapterRegistry",
                "id": "bad-mcp-registry",
                "version": "v1",
                "policy": {
                    "default_state": "enabled",
                    "default_network": "allow",
                    "require_trace_id": True,
                    "require_capability_token": False,
                    "require_registry_entry": True,
                    "require_operator_review_for_enable": True,
                    "allowed_transports": ["stdio", "http"],
                    "blocked_transports": ["websocket"],
                    "max_tool_risk": "medium",
                },
                "adapters": [
                    {
                        "id": "remote.adapter",
                        "version": "v1",
                        "state": "enabled",
                        "transport": "http",
                        "risk": "high",
                        "network": "allow",
                        "capability_scopes": [],
                        "tool_allowlist": ["search"],
                        "trace_required": True,
                        "capability_token_required": False,
                        "registry_entry_required": True,
                        "registry_ref": "tool-policy:tool-policy-main:v1",
                        "audit_logging": False,
                        "sandbox": {"profile": "remote", "write": True, "egress": "allow"},
                        "review": {"required": False, "route": "", "reviewers": []},
                        "rollback_plan": "short",
                        "refs": ["configs/tool-policy.yaml", "src/missing.py"],
                    }
                ],
            }

            report = marr.validate_mcp_adapter_registry(registry, project_root=project, package_root=package)

            self.assertFalse(report["ok"])
            self.assertIn("policy_default_state_not_disabled", report["failures"])
            self.assertIn("policy_default_network_not_deny", report["failures"])
            self.assertIn("policy_require_capability_token_not_true", report["failures"])
            self.assertIn("policy_network_transport_not_blocked:http", report["failures"])
            self.assertIn("adapter_network_not_deny:remote.adapter", report["failures"])
            self.assertIn("adapter_capability_scopes_empty:remote.adapter", report["failures"])
            self.assertIn("adapter_risk_exceeds_policy:remote.adapter:high>medium", report["failures"])
            self.assertEqual(1, report["metrics"]["missing_refs"])

    def test_cli_summary_uses_workspace_registry_contract(self) -> None:
        registry_path = ROOT / "configs" / "mcp-adapter-registry.json"
        report = marr.validate_mcp_adapter_registry(
            json.loads(registry_path.read_text(encoding="utf-8")),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=registry_path,
        )
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual({"disabled": 3}, report["metrics"]["states"])


if __name__ == "__main__":
    unittest.main()
