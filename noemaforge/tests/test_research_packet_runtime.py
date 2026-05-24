#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_research_packet_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Research_Packet contracts for freshness-bounded cited scouting.
Inputs: Workspace Research Packet policy and temporary broken fixtures.
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
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import production_ai_contracts as pac
import research_packet_runtime as rpr


class ResearchPacketRuntimeTests(unittest.TestCase):
    def test_workspace_research_packet_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "research-packet-policy.json"
        report = rpr.validate_research_packet_policy(
            rpr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(2, report["metrics"]["packets"])
        self.assertEqual(2, report["metrics"]["passing_packets"])
        self.assertEqual(2, report["metrics"]["scoring_cases"])
        self.assertEqual(2, report["metrics"]["passing_scoring_cases"])

        gate = pac.evaluate_gate(
            {"change_id": "research-packet-scouting-core", "domain": "pipeline"},
            rpr.research_packet_report_to_gate_evidence(report, artifact_uri="reports/research-packet.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_uncited_claim_and_network_fetch_are_blocked(self) -> None:
        policy_path = ROOT / "configs" / "research-packet-policy.json"
        policy = rpr.load_policy(policy_path)
        example_set = rpr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "research_packet.example.json")
        packet = example_set["packets"][0]
        packet["claims"][0]["citation_ids"] = []
        packet["finalization"]["network_fetch_performed"] = True
        packet["finalization"]["all_claims_cited"] = False

        with patch.object(rpr, "load_example_set", return_value=example_set):
            report = rpr.validate_research_packet_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("claim_citations_missing:research-packet-freshness-official-sources:claim:offline-validation", report["failures"])
        self.assertIn("packet_network_fetch_performed:research-packet-freshness-official-sources", report["failures"])
        self.assertIn("packet_finalization_all_claims_cited_not_true:research-packet-freshness-official-sources", report["failures"])

    def test_source_allowlist_and_freshness_are_blocked(self) -> None:
        policy_path = ROOT / "configs" / "research-packet-policy.json"
        policy = rpr.load_policy(policy_path)
        example_set = rpr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "research_packet.example.json")
        packet = example_set["packets"][0]
        packet["sources"][0]["url"] = "https://untrusted.example/source"
        packet["sources"][0]["domain"] = "untrusted.example"
        packet["sources"][1]["published_at"] = "2025-01-01T00:00:00Z"

        with patch.object(rpr, "load_example_set", return_value=example_set):
            report = rpr.validate_research_packet_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("source_domain_not_allowed:research-packet-freshness-official-sources:source:python-docs-json:untrusted.example", report["failures"])
        self.assertTrue(any(item.startswith("source_stale:research-packet-freshness-official-sources:source:github-artifact-policy") for item in report["failures"]))

    def test_build_research_packet_returns_needs_refresh_for_stale_sources(self) -> None:
        policy = rpr.load_policy(ROOT / "configs" / "research-packet-policy.json")
        packet = rpr.build_research_packet(
            "What is stale?",
            [
                {
                    "id": "source:stale",
                    "kind": "official_docs",
                    "url": "https://docs.python.org/3/library/json.html",
                    "domain": "docs.python.org",
                    "published_at": "2026-01-01T00:00:00Z",
                    "accessed_at": "2026-05-20T00:00:00Z",
                    "primary": True,
                    "excerpt": "Stale source.",
                }
            ],
            [{"id": "claim:one", "text": "Stale claim.", "citation_ids": ["citation:one"]}],
            [{"id": "citation:one", "claim_id": "claim:one", "source_id": "source:stale", "supports": True, "cited_text": "Stale source."}],
            policy,
            collected_at="2026-05-20T00:00:00Z",
        )
        self.assertEqual("needs_refresh", packet["status"])


if __name__ == "__main__":
    unittest.main()
