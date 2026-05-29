#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_production_ai_contracts.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-18
Modified: 2026-05-18
Purpose: Validate production-AI lifecycle contracts introduced by the TODO backlog.
Inputs: In-memory registry, gate and rollout fixtures.
Outputs: unittest assertions only.
Side effects: None.
Tests: unittest discovery.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

import production_ai_contracts as pac


class ProductionAIContractTests(unittest.TestCase):
    def test_unified_registry_requires_all_todo_kinds(self) -> None:
        registry = {"entries": []}
        for kind in sorted(pac.REGISTRY_KINDS):
            registry = pac.upsert_registry_entry(
                registry,
                {
                    "kind": kind,
                    "id": f"{kind}-main",
                    "version": "v1",
                    "status": "shadow",
                    "channels": ["stable"],
                },
            )

        status = pac.summarize_contract_status(registry)
        self.assertTrue(status["ok"], status)
        self.assertEqual([], status["missing_kinds"])
        self.assertEqual(len(pac.REGISTRY_KINDS), len(pac.active_registry_refs(registry)))

    def test_registry_rejects_duplicate_identity(self) -> None:
        doc = {
            "entries": [
                {"kind": "model", "id": "main", "version": "v1"},
                {"kind": "model", "id": "main", "version": "v1"},
            ]
        }
        with self.assertRaises(ValueError):
            pac.normalize_registry(doc)

    def test_evaluation_gate_blocks_missing_required_checks(self) -> None:
        result = pac.evaluate_gate(
            {"change_id": "router-change-1", "domain": "router"},
            {"checks": [{"id": "intent_router_eval", "status": "passed"}]},
        )
        self.assertFalse(result["ok"])
        self.assertEqual("block", result["decision"])
        self.assertIn("check_missing:per_route_metrics", result["failures"])

    def test_rollout_promote_requires_gate_and_approval(self) -> None:
        gate = pac.evaluate_gate(
            {
                "change_id": "pipeline-change-1",
                "domain": "pipeline",
                "required_checks": ["pipeline_eval", "rollback_plan"],
            },
            {
                "artifact_uri": "reports/pipeline-change-1.json",
                "run_at": "2026-05-18T00:00:00Z",
                "checks": [
                    {"id": "pipeline_eval", "status": "passed"},
                    {"id": "rollback_plan", "status": "passed"},
                ],
            },
        )
        blocked = pac.rollout_transition("canary", "promoted", gate, approved=False)
        self.assertFalse(blocked["ok"])
        self.assertIn("operator_approval_missing", blocked["failures"])

        allowed = pac.rollout_transition("canary", "promoted", gate, approved=True)
        self.assertTrue(allowed["ok"])

    def test_registry_prompt_routing_promotion_requires_release_evidence(self) -> None:
        registry = pac.upsert_registry_entry(
            {"entries": []},
            {
                "kind": "prompt",
                "id": "admin-routing-system",
                "version": "v2",
                "status": "canary",
                "channels": ["stable"],
                "refs": ["configs/head-gateway.json"],
                "metadata": {
                    "domains": ["router"],
                    "summary": "Promote Admin routing prompt.",
                },
            },
        )
        evidence = {
            "artifact_uri": "reports/intent-router-eval.json",
            "run_at": "2026-05-19T00:00:00Z",
            "checks": [
                {"id": "intent_router_eval", "status": "passed"},
                {"id": "per_route_metrics", "score": 1.0, "threshold": 1.0},
            ],
        }

        result = pac.promote_registry_entry(
            registry,
            "prompt:admin-routing-system:v2",
            evidence,
            requested_status="promoted",
            approved=True,
            trace_id="trace-routing-promote",
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual("RegistryPromotionResult", result["kind"])
        self.assertEqual("promoted", result["entry"]["status"])
        self.assertEqual("router", result["release_evidence"]["change"]["domain"])
        self.assertEqual("trace-routing-promote", result["release_evidence"]["trace_id"])
        promoted = pac.registry_index(result["registry"])["prompt:admin-routing-system:v2"]
        self.assertEqual("promoted", promoted["status"])
        self.assertEqual("trace-routing-promote", promoted["metadata"]["last_release_evidence_trace_id"])

    def test_registry_promotion_blocks_missing_checks_and_preserves_status(self) -> None:
        registry = pac.upsert_registry_entry(
            {"entries": []},
            {
                "kind": "prompt",
                "id": "admin-routing-system",
                "version": "v2",
                "status": "canary",
                "channels": ["stable"],
                "metadata": {"domains": ["router"]},
            },
        )
        result = pac.promote_registry_entry(
            registry,
            "prompt:admin-routing-system:v2",
            {"checks": [{"id": "intent_router_eval", "status": "passed"}]},
            requested_status="promoted",
            approved=True,
        )
        self.assertFalse(result["ok"])
        self.assertIn("check_missing:per_route_metrics", result["failures"])
        preserved = pac.registry_index(result["registry"])["prompt:admin-routing-system:v2"]
        self.assertEqual("canary", preserved["status"])

    def test_release_evidence_carries_trace_gate_rollout_and_refs(self) -> None:
        gate = {
            "ok": True,
            "decision": "allow",
            "failures": [],
            "evidence": {"artifact_uri": "reports/eval.json"},
        }
        rollout = {"from": "shadow", "to": "canary", "decision": "allow", "ok": True}
        evidence = pac.build_release_evidence(
            {"change_id": "rag-change-1", "domain": "rag", "summary": "Tune retrieval."},
            gate,
            rollout,
            registry_refs=["retriever:knowledge-keyword-retrieval:0.32.1"],
            trace_id="trace-123",
        )
        self.assertEqual("ReleaseEvidence", evidence["kind"])
        self.assertEqual("trace-123", evidence["trace_id"])
        self.assertTrue(evidence["gate"]["ok"])
        self.assertEqual(["retriever:knowledge-keyword-retrieval:0.32.1"], evidence["registry_refs"])

    def test_artifact_cards_cover_model_prompt_pipeline_epoch_and_tool_policy(self) -> None:
        registry = {"entries": []}
        for kind in ["model", "prompt", "pipeline", "epoch", "tool-policy", "eval-pack"]:
            registry = pac.upsert_registry_entry(
                registry,
                {
                    "kind": kind,
                    "id": f"{kind}-main",
                    "version": "v1",
                    "status": "shadow",
                    "channels": ["stable"],
                    "refs": [f"configs/{kind}.json"],
                    "eval_pack_refs": ["eval-pack:smoke:v1"],
                    "metadata": {
                        "summary": f"{kind} review target",
                        "risk_level": "low",
                        "rollback_plan": "restore previous registry ref",
                    },
                },
            )

        gate = {
            "ok": True,
            "decision": "allow",
            "failures": [],
            "evidence": {"artifact_uri": "reports/pipeline-eval.json"},
        }
        rollout = {"from": "shadow", "to": "canary", "decision": "allow", "ok": True}
        evidence = pac.build_release_evidence(
            {"change_id": "pipeline-change-1", "domain": "pipeline", "summary": "Promote pipeline."},
            gate,
            rollout,
            trace_id="trace-card",
        )
        cards = pac.build_registry_cards(
            registry,
            release_evidence_by_ref={"pipeline:pipeline-main:v1": evidence},
            trace_id="trace-cards",
        )
        self.assertEqual("ProductionAICardSet", cards["kind"])
        self.assertEqual([], cards["coverage"]["missing_card_kinds"])
        self.assertEqual(
            ["EpochCard", "ModelCard", "PipelineCard", "PromptCard", "ToolPolicyCard"],
            cards["coverage"]["present_card_kinds"],
        )
        pipeline_card = next(card for card in cards["cards"] if card["kind"] == "PipelineCard")
        self.assertEqual("trace-cards", pipeline_card["trace_id"])
        self.assertEqual("reports/pipeline-eval.json", pipeline_card["release_evidence_refs"][0])
        self.assertTrue(pipeline_card["rollback"]["available"])

    def test_artifact_card_rejects_unsupported_registry_kind(self) -> None:
        with self.assertRaises(ValueError):
            pac.build_artifact_card({"kind": "eval-pack", "id": "smoke", "version": "v1"})

    def test_data_error_loop_builds_taxonomy_regression_eval_and_task(self) -> None:
        artifact = pac.build_data_error_loop_artifact(
            {
                "error_id": "err-router-1",
                "component": "admin_router",
                "input": {"text": "Запусти evolution по стандартному сценарию"},
                "expected": {
                    "route_id": "model_evolution",
                    "intent": "model_evolution",
                    "abstention_action": "route",
                    "min_confidence": 0.8,
                },
                "actual": {"route_id": "greeting", "intent": "greeting", "abstention_action": "route"},
                "severity": "high",
            },
            trace_id="trace-error-loop",
        )

        self.assertEqual("DataCentricErrorLoopArtifact", artifact["kind"])
        self.assertEqual("router", artifact["taxonomy"]["domain"])
        self.assertEqual("intent_routing_mismatch", artifact["taxonomy"]["error_type"])
        self.assertEqual(["SR"], artifact["review"]["reviewers_required"])
        self.assertEqual("P0", artifact["task_item"]["priority"])
        self.assertEqual("IntentRouterEvalPack", artifact["eval_case"]["target_pack_kind"])
        self.assertEqual("model_evolution", artifact["eval_case"]["case"]["expected_route_id"])

    def test_data_error_loop_appends_eval_case_idempotently(self) -> None:
        artifact = pac.build_data_error_loop_artifact(
            {
                "error_id": "err-router-2",
                "component": "admin_router",
                "input": {"text": "Подготовь релиз"},
                "expected": {"route_id": "release", "intent": "release_prep", "abstention_action": "ask_clarification"},
                "actual": {"route_id": "general", "intent": "general_admin", "abstention_action": "ask_clarification"},
            }
        )
        pack = {"apiVersion": "noemaforge.intent-router-eval/v1", "kind": "IntentRouterEvalPack", "cases": []}
        updated = pac.append_error_loop_eval_case(pack, artifact)
        updated_again = pac.append_error_loop_eval_case(updated, artifact)

        self.assertEqual(1, len(updated_again["cases"]))
        self.assertEqual(["err-router-2"], updated_again["error_loop_sources"])
        self.assertEqual("release", updated_again["cases"][0]["expected_route_id"])

    def test_rag_eval_report_emits_gate_compatible_checks(self) -> None:
        cases = [
            {
                "id": "docs_model_selection_dev_team",
                "query": "What does optimize model for Dev Team mean?",
                "expected_source_refs": ["docs/wiki/first-start/model-selection-modes-0.32.1.md"],
                "expected_answer_terms": ["model", "dev team", "trace"],
            }
        ]
        results = [
            {
                "case_id": "docs_model_selection_dev_team",
                "retrieved_refs": ["docs/wiki/first-start/model-selection-modes-0.32.1.md"],
                "citations": [{"source_ref": "docs/wiki/first-start/model-selection-modes-0.32.1.md"}],
                "grounded": True,
                "answer": "Model selection for Dev Team should carry trace evidence.",
            }
        ]
        report = pac.evaluate_rag_eval_cases(cases, results, trace_id="trace-rag")
        self.assertTrue(report["ok"], report)
        self.assertEqual("RAGEvalReport", report["kind"])
        self.assertEqual(1.0, report["metrics"]["retrieval_hit_rate"])
        self.assertEqual(1.0, report["metrics"]["citation_coverage"])
        gate = pac.evaluate_gate(
            {"change_id": "rag-doc-index-v1", "domain": "rag"},
            pac.rag_eval_report_to_gate_evidence(report, artifact_uri="reports/rag-eval.json"),
        )
        self.assertTrue(gate["ok"], gate)
        self.assertIn("answer_helpfulness", gate["passed_checks"])

    def test_rag_eval_report_blocks_missing_citations(self) -> None:
        cases = [
            {
                "id": "docs_admin_routing_eval_pack",
                "query": "How is Admin intent routing evaluated?",
                "expected_source_refs": ["docs/wiki/architecture/production-ai-lifecycle-registry-trace-evaluation-0.32.1.md"],
                "expected_answer_terms": ["intent", "route", "abstention"],
            }
        ]
        results = [
            {
                "case_id": "docs_admin_routing_eval_pack",
                "retrieved_refs": ["docs/wiki/architecture/production-ai-lifecycle-registry-trace-evaluation-0.32.1.md"],
                "citations": [],
                "grounded": True,
                "answer": "Intent route abstention is evaluated.",
            }
        ]
        report = pac.evaluate_rag_eval_cases(cases, results)
        self.assertFalse(report["ok"])
        self.assertIn("citation_coverage", report["threshold_failures"])
        self.assertIn("groundedness", report["threshold_failures"])

    def test_trajectory_eval_report_emits_gate_compatible_checks(self) -> None:
        trajectory = {
            "id": "dev-loop-1",
            "loop_type": "dev_team",
            "budget": {"max_steps": 4, "max_tool_calls": 2, "human_interrupt": True},
            "interruptible": True,
            "steps": [
                {"id": "intent", "type": "intent", "ok": True},
                {"id": "plan", "type": "plan", "ok": True},
                {"id": "patch", "type": "artifact", "ok": True, "tool_calls": [{"name": "apply_patch"}], "artifact_refs": ["patch.diff"]},
                {"id": "qa", "type": "eval", "ok": True, "tool_calls": [{"name": "unittest"}], "artifact_refs": ["reports/tests.json"]},
            ],
            "final_state": "waiting_for_operator_approval",
        }
        report = pac.evaluate_trajectory(trajectory, trace_id="trace-trajectory")
        self.assertTrue(report["ok"], report)
        self.assertEqual("TrajectoryEvalReport", report["kind"])
        self.assertEqual(1.0, report["metrics"]["step_success_rate"])
        self.assertEqual(1.0, report["metrics"]["artifact_coverage"])
        gate = pac.evaluate_gate(
            {
                "change_id": "trajectory-dev-loop-1",
                "domain": "pipeline",
                "required_checks": [
                    "trajectory_step_success_rate",
                    "trajectory_artifact_coverage",
                    "trajectory_budget_compliance",
                    "trajectory_safety_flags",
                    "trajectory_safe_final_state",
                ],
            },
            pac.trajectory_eval_report_to_gate_evidence(report, artifact_uri="reports/trajectory.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_trajectory_eval_blocks_budget_safety_and_bad_final_state(self) -> None:
        report = pac.evaluate_trajectory(
            {
                "id": "unsafe-loop",
                "loop_type": "self_optimization",
                "budget": {"max_steps": 1, "max_tool_calls": 0},
                "steps": [
                    {"id": "plan", "type": "plan", "ok": True},
                    {"id": "mutate", "type": "artifact", "ok": False, "tool": "shell", "safety_flags": ["unsafe_tool_request"]},
                ],
                "final_state": "mutated_without_review",
            }
        )
        self.assertFalse(report["ok"])
        self.assertIn("step_success_rate", report["threshold_failures"])
        self.assertIn("budget_compliance", report["threshold_failures"])
        self.assertIn("safety_flags", report["threshold_failures"])
        self.assertIn("safe_final_state", report["threshold_failures"])

    def test_epoch_apply_release_evidence_wraps_prestart_and_canary_reports(self) -> None:
        evidence = pac.build_epoch_release_evidence(
            "epoch_20260518T000000Z",
            {"overall_decision": "pass", "created_at": "2026-05-18T00:00:00Z"},
            {"decision": "pass", "overall_ok": True, "created_at": "2026-05-18T00:00:01Z"},
            build_report_path="prestart_build_report.json",
            scary_report_path="scary_report.json",
            registry_refs=["epoch:noemaforge-runtime:0.32.1"],
            trace_id="trace-epoch",
        )
        self.assertEqual("ReleaseEvidence", evidence["kind"])
        self.assertEqual("trace-epoch", evidence["trace_id"])
        self.assertTrue(evidence["gate"]["ok"])
        self.assertTrue(evidence["rollout"]["ok"])
        self.assertEqual("promoted", evidence["rollout"]["to"])

    def test_abstention_decision_routes_or_defers_deterministically(self) -> None:
        routed = pac.decide_abstention({"confidence": 0.91, "risk_level": "low"})
        self.assertEqual("route", routed["action"])
        self.assertTrue(routed["ok_to_route"])

        clarify = pac.decide_abstention({"confidence": 0.72, "missing_context": ["project path"]})
        self.assertEqual("ask_clarification", clarify["action"])
        self.assertFalse(clarify["ok_to_route"])
        self.assertIn("Provide project path.", clarify["questions"])

        high = pac.decide_abstention({"confidence": 0.95, "risk_level": "high"})
        self.assertEqual("defer_ssr", high["action"])
        self.assertEqual(["SR", "SSR"], high["reviewers_required"])

        unsafe = pac.decide_abstention({"confidence": 0.99, "safety_flags": ["unsafe_tool_request"]})
        self.assertEqual("block", unsafe["action"])


if __name__ == "__main__":
    unittest.main()
