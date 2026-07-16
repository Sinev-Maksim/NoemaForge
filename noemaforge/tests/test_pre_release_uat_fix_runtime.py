#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import firstboot_orchestrator
import pre_release_uat_fix_runtime as uatfix


class PreReleaseUATFixRuntimeTests(unittest.TestCase):
    def test_gateway_socket_candidates_prefer_canonical_target_path(self) -> None:
        self.assertEqual(uatfix.gateway_socket_candidates()[0], "/run/noemaforge/llm/gateway.sock")
        self.assertIn("/run/noemaforge/llm-gateway.sock", uatfix.gateway_socket_candidates()[1:])

    def test_contract_epoch_paths_use_epochs_current_and_epoch_dir(self) -> None:
        paths = uatfix.contract_epoch_paths("00006")
        self.assertEqual(paths["current"], "/var/lib/noemaforge/contracts/epochs/current")
        self.assertEqual(paths["epoch_dir"], "/var/lib/noemaforge/contracts/epochs/00006")
        self.assertNotIn("/contracts/current", paths["current"])

    def test_locate_operator_apply_excludes_plan_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_apply_locator_") as td:
            root = Path(td)
            plan = root / "operator_degraded_apply_plan_20260703T174255Z"
            plan.mkdir()
            (plan / "operator-degraded-apply-summary.json").write_text("{}", encoding="utf-8")
            real = root / "operator_degraded_apply_20260703T175500Z"
            real.mkdir()
            (real / "operator-degraded-apply-summary.json").write_text("{}", encoding="utf-8")
            self.assertEqual(uatfix.locate_operator_degraded_apply(root), real)

    def test_model_run_summary_uses_raw_records_not_empty_defaults(self) -> None:
        records = [
            {"model_id": "ok", "started": True, "roles": [{"role_key": "r"}]},
            {"model_id": "partial", "started": True, "partial_valid": True, "reason": "per_model_timeout"},
            {"model_id": "warm", "started": True, "reason": "warmup_failed"},
            {"model_id": "old", "reason": "previously_failed_runtime"},
            {"model_id": "safe", "reason": "default_safety_filter"},
            {"model_id": "svc", "reason": "systemctl_start_failed:1"},
            {"model_id": "slow", "reason": "TimeoutError('timed out')"},
        ]
        summary = uatfix.summarize_model_run_records(records)
        self.assertEqual(summary["model_runs"], 7)
        self.assertEqual(summary["models_started"], 3)
        self.assertEqual(summary["classification_counts"]["completed"], 1)
        self.assertEqual(summary["classification_counts"]["partial_valid"], 1)
        self.assertEqual(summary["classification_counts"]["warmup_failed"], 1)
        self.assertEqual(summary["classification_counts"]["systemctl_start_failed"], 1)
        self.assertEqual(summary["classification_counts"]["timeout"], 1)
        self.assertEqual(summary["classification_counts"]["safety-filtered"], 1)
        self.assertEqual(summary["classification_counts"]["unknown"], 1)

    def test_summarize_artifacts_counts_generator_paths_once(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_artifact_summary_") as td:
            root = Path(td)
            first = root / "one.json"
            second = root / "two.json"
            first.write_text(json.dumps({"records": [{"model_id": "a", "started": True}]}), encoding="utf-8")
            second.write_text(json.dumps({"records": [{"model_id": "b", "reason": "warmup_failed"}]}), encoding="utf-8")

            summary = uatfix.summarize_artifacts(path for path in [first, second])

            self.assertEqual(summary["artifact_count"], 2)
            self.assertEqual(summary["model_runs"], 2)

    def test_full_composite_stale_health_collapse_is_not_max_complexity(self) -> None:
        records = [{"model_id": "ok", "started": True}]
        records.extend({"model_id": f"old-{idx}", "reason": "previously_failed_runtime"} for idx in range(22))
        records.extend({"model_id": f"safe-{idx}", "reason": "default_safety_filter"} for idx in range(3))
        summary = uatfix.summarize_model_run_records(records)

        scope = uatfix.classify_full_composite_dry_run_scope(
            summary,
            mode="full_composite",
            dry_run=True,
            retry_failed_models=False,
            clear_model_health=False,
        )

        self.assertEqual("conservative_health_filtered_dry_run", scope["scope"])
        self.assertFalse(scope["ok_to_label_max_complexity"])
        self.assertIn("persisted_model_health_reused", scope["blocking_reasons"])
        self.assertIn("previously_failed_runtime_dominates", scope["blocking_reasons"])
        self.assertIn("models_started_unexpectedly_low", scope["blocking_reasons"])

    def test_full_composite_retry_run_can_be_labeled_max_complexity(self) -> None:
        records = [
            {"model_id": "a", "started": True},
            {"model_id": "b", "started": True},
            {"model_id": "c", "started": True, "partial_valid": True},
        ]
        summary = uatfix.summarize_model_run_records(records)

        scope = uatfix.classify_full_composite_dry_run_scope(
            summary,
            mode="full_composite",
            dry_run=True,
            retry_failed_models=True,
            clear_model_health=False,
        )

        self.assertEqual("max_complexity_evaluation_dry_run", scope["scope"])
        self.assertTrue(scope["ok_to_label_max_complexity"])
        self.assertEqual([], scope["blocking_reasons"])

    def test_firstboot_selection_artifacts_write_model_run_summary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_firstboot_summary_") as td:
            root = Path(td)
            tournament = {
                "model_run_records": [
                    {"model_id": "m1", "started": True, "roles": [{"role_key": "operator.admin/administrator"}]},
                    {"model_id": "m2", "started": False, "reason": "warmup_failed"},
                ]
            }
            candidate_map = {
                "roles": {
                    "operator.admin/administrator": {
                        "selected": [{"model_id": "m1", "score": 0.9}]
                    }
                }
            }
            staffing = {"staffing_state": "degraded_selected", "selected_roles": 1, "target_met_roles": 1}
            paths = firstboot_orchestrator._write_selection_artifacts(
                state_dir=str(root),
                mode="full_composite",
                composite_top_n=0,
                candidate_map=candidate_map,
                tournament_doc=tournament,
                staffing_summary=staffing,
                dry_run=True,
            )
            summary = json.loads(Path(paths["model_run_summary"]).read_text(encoding="utf-8"))
            self.assertEqual(summary["model_runs"], 2)
            self.assertEqual(summary["models_started"], 1)
            self.assertEqual(summary["classification_counts"]["completed"], 1)
            self.assertEqual(summary["classification_counts"]["warmup_failed"], 1)

    def test_firstboot_selection_artifacts_record_stale_health_scope(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_firstboot_stale_scope_") as td:
            root = Path(td)
            tournament = {
                "model_run_records": [
                    {"model_id": "ok", "started": True, "roles": [{"role_key": "operator.admin/administrator"}]},
                    {"model_id": "old-a", "reason": "previously_failed_runtime"},
                    {"model_id": "old-b", "reason": "previously_failed_runtime"},
                ]
            }
            candidate_map = {
                "roles": {
                    "operator.admin/administrator": {
                        "selected": [{"model_id": "ok", "score": 0.9}]
                    }
                }
            }
            staffing = {"staffing_state": "degraded_selected", "selected_roles": 1, "target_met_roles": 1}
            paths = firstboot_orchestrator._write_selection_artifacts(
                state_dir=str(root),
                mode="full_composite",
                composite_top_n=0,
                candidate_map=candidate_map,
                tournament_doc=tournament,
                staffing_summary=staffing,
                dry_run=True,
                retry_failed_models=False,
                clear_model_health=False,
            )
            summary = json.loads(Path(paths["model_run_summary"]).read_text(encoding="utf-8"))
            decision = json.loads(Path(paths["model_selection_decision"]).read_text(encoding="utf-8"))

            self.assertTrue(decision["ready_to_apply"])
            self.assertEqual("conservative_health_filtered_dry_run", summary["dry_run_evaluation_scope"]["scope"])
            self.assertFalse(decision["dry_run_evaluation_scope"]["ok_to_label_max_complexity"])

    def test_failure_report_is_emitted_for_early_helper_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_failure_report_") as td:
            paths = uatfix.write_failure_report(Path(td), stem="release-decision-known-findings", error="source_gate_failed")
            self.assertTrue(Path(paths["json"]).is_file())
            self.assertTrue(Path(paths["markdown"]).is_file())
            payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
            self.assertIs(payload["ok"], False)
            self.assertEqual(payload["error"], "source_gate_failed")


if __name__ == "__main__":
    unittest.main()
