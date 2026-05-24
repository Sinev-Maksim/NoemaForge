#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_toolproxy_capability_token_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test ToolProxy capability-token discoverability through registry and docs.
Inputs: Unified Registry, capability-token policy and canonical documentation files.
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

import toolproxy_capability_token_runtime as tctr
import unified_registry_runtime as urr

CLOSURE = "Closed by `toolproxy-capability-token-core`"


class ToolProxyCapabilityTokenQATests(unittest.TestCase):
    def test_toolproxy_capability_pack_is_registered_and_attached_to_tool_policy(self) -> None:
        registry_path = ROOT / "configs" / "unified-registry.json"
        report = urr.validate_unified_registry(
            urr.load_registry(registry_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=registry_path,
        )
        self.assertTrue(report["ok"], report["failures"])

        entries = {
            f"{entry['kind']}:{entry['id']}:{entry['version']}": entry
            for entry in report["normalized_registry"]["entries"]
        }
        pack = entries.get("eval-pack:toolproxy-capability-token-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/toolproxy-capability-token-policy.json", pack["refs"])
        self.assertIn("contracts/toolproxy_capability_token.schema.json", pack["refs"])
        self.assertIn("src/toolproxy_capability_token_runtime.py", pack["refs"])
        self.assertIn("tests/test_toolproxy_capability_token_performance.py", pack["refs"])
        self.assertIn("docs/TODO.md", pack["refs"])
        self.assertIn("docs/reference/PROJECT_CONTEXT.md", pack["refs"])

        tool_policy = entries["tool-policy:tool-policy-main:0.32.1"]
        self.assertIn("eval-pack:toolproxy-capability-token-core:0.32.1", tool_policy["eval_pack_refs"])
        self.assertIn("configs/toolproxy-capability-token-policy.json", tool_policy["refs"])
        self.assertIn("src/noemaforge_toolproxy_diag.py", tool_policy["refs"])

    def test_toolproxy_capability_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = tctr.load_policy(ROOT / "configs" / "toolproxy-capability-token-policy.json")
        self.assertEqual("ToolProxyCapabilityTokenPolicy", policy["kind"])
        self.assertEqual("capability_token_issuance_ux", policy["policy"]["activation_state"])
        self.assertEqual(["issue", "list", "verify", "revoke", "smoke"], policy["policy"]["required_ux_commands"])

        report = tctr.validate_toolproxy_capability_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("toolproxy-capability-token-core", text)
            self.assertIn(CLOSURE, text)

        for path in [
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("toolproxy-capability-token-core", text)
            self.assertIn("issue/list/verify/revoke/smoke", text)
            self.assertIn(CLOSURE, text)

        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertIn("[x] ToolProxy capability token issuance UX.", backlog)
        self.assertIn("[x] ToolProxy capability token UX and issuance path.", backlog)
        self.assertIn("[x] Finish ToolProxy token issue/list/revoke UX.", backlog)

    def test_toolproxy_capability_refs_use_canonical_docs_paths(self) -> None:
        policy = tctr.load_policy(ROOT / "configs" / "toolproxy-capability-token-policy.json")
        refs = set(policy["refs"])

        self.assertIn("docs/TODO.md", refs)
        self.assertIn("docs/reference/PROJECT_CONTEXT.md", refs)
        self.assertIn("noemaforge/docs/TODO.md", refs)
        self.assertFalse({"README.md", "TODO.md", "noemaforge/TODO.md"} & refs)
        docs_refs = {ref for ref in refs if ref.endswith(".md")}
        self.assertTrue(all(ref.startswith(("docs/", "noemaforge/docs/")) for ref in docs_refs))


if __name__ == "__main__":
    unittest.main()

