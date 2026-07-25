#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
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

    def test_gateway_probe_classifies_legacy_path_mismatch(self) -> None:
        finding = uatfix.classify_gateway_probe(
            observed_sockets=["/run/noemaforge/llm/gateway.sock"],
            probed_sockets=["/run/noemaforge/llm-gateway.sock", "/run/noemaforge/gateway.sock"],
        )

        self.assertTrue(finding["gateway_ok_now"])
        self.assertTrue(finding["canonical_socket_present"])
        self.assertTrue(finding["probe_path_mismatch"])
        self.assertFalse(finding["real_gateway_failure"])
        self.assertEqual("legacy_probe_path_mismatch", finding["reason"])

    def test_gateway_probe_classifies_real_missing_gateway(self) -> None:
        finding = uatfix.classify_gateway_probe(
            observed_sockets=[],
            probed_sockets=uatfix.gateway_socket_candidates(),
        )

        self.assertFalse(finding["gateway_ok_now"])
        self.assertFalse(finding["probe_path_mismatch"])
        self.assertTrue(finding["real_gateway_failure"])
        self.assertEqual("gateway_socket_missing", finding["reason"])

    def test_contract_epoch_paths_use_epochs_current_and_epoch_dir(self) -> None:
        paths = uatfix.contract_epoch_paths("00006")
        self.assertEqual(paths["current"], "/var/lib/noemaforge/contracts/epochs/current")
        self.assertEqual(paths["epoch_dir"], "/var/lib/noemaforge/contracts/epochs/00006")
        self.assertNotIn("/contracts/current", paths["current"])

    def test_contract_epoch_resolution_uses_current_symlink_target(self) -> None:
        finding = uatfix.classify_contract_epoch_resolution(
            "00006",
            current_resolved="/var/lib/noemaforge/contracts/epochs/00006",
            epoch_dir_exists=False,
        )

        self.assertTrue(finding["applied_epoch_dir_exists"])
        self.assertTrue(finding["current_points_to_epoch"])
        self.assertTrue(finding["path_mismatch_suspected"])
        self.assertEqual("current_symlink_confirms_epoch_path_mismatch", finding["reason"])

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

    def test_locate_operator_apply_prefers_complete_run_over_later_partial_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_apply_locator_") as td:
            root = Path(td)
            complete = root / "operator_degraded_apply_20260703T174255Z"
            complete.mkdir()
            (complete / "operator-degraded-apply-summary.json").write_text("{}", encoding="utf-8")
            (complete / "post_apply_artifacts").mkdir()

            partial = root / "operator_degraded_apply_20260703T175500Z"
            partial.mkdir()
            (partial / "operator-degraded-apply-summary.json").write_text("{}", encoding="utf-8")

            self.assertEqual(uatfix.locate_operator_degraded_apply(root), complete)

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

    def test_summarize_artifacts_normalizes_dict_list_and_string_shapes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_artifact_shapes_") as td:
            root = Path(td)
            json_artifact = root / "artifact.json"
            json_artifact.write_text(
                json.dumps({"records": [{"model_id": "path", "started": True}]}),
                encoding="utf-8",
            )

            summary = uatfix.summarize_artifacts([
                json_artifact,
                {"model_run_records": [{"model_id": "dict", "reason": "warmup_failed"}]},
                [{"model_id": "list", "started": True, "partial_valid": True}],
                "raw-string-artifact",
            ])

            self.assertEqual(summary["artifact_count"], 4)
            self.assertEqual(summary["model_runs"], 4)
            self.assertEqual(summary["models_started"], 2)
            self.assertIn("unknown", summary["classification_counts"])

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

    def test_full_composite_without_model_run_evidence_is_not_max_complexity(self) -> None:
        summary = uatfix.summarize_model_run_records([])

        scope = uatfix.classify_full_composite_dry_run_scope(
            summary,
            mode="full_composite",
            dry_run=True,
            retry_failed_models=True,
            clear_model_health=False,
        )

        self.assertEqual("conservative_health_filtered_dry_run", scope["scope"])
        self.assertFalse(scope["ok_to_label_max_complexity"])
        self.assertIn("model_run_evidence_missing", scope["blocking_reasons"])

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

    def test_target_layout_discovery_prefers_service_unit_source_root(self) -> None:
        unit = '''
        [Service]
        Environment="PYTHONPATH=/opt/noemaforge/noemaforge/src:/opt/noemaforge/noemaforge"
        ExecStart=/usr/bin/python3 /opt/noemaforge/noemaforge/src/admin_gui_server.py
        '''

        layout = uatfix.discover_target_layout(
            service_unit_texts=[unit],
            existing_paths=["/opt/noemaforge/noemaforge/src", "/opt/noemaforge/src"],
        )

        self.assertTrue(layout["ok"])
        self.assertEqual("/opt/noemaforge/noemaforge/src", layout["source_root"])
        self.assertEqual("/opt/noemaforge/noemaforge", layout["package_root"])
        self.assertTrue(layout["matched_existing"])
        self.assertFalse(layout["live_evidence_claimed"])

    def test_runtime_deploy_plan_maps_package_paths_into_active_layout(self) -> None:
        plan = uatfix.build_runtime_deploy_plan(
            [
                "noemaforge/src/admin_gui_server.py",
                "noemaforge/tests/test_admin_gui_server.py",
                "noemaforge/configs/runtime-invariants.yaml",
            ],
            source_root="/opt/noemaforge/noemaforge/src",
        )

        self.assertTrue(plan["ok"])
        by_repo = {item["repo_path"]: item for item in plan["mappings"]}
        self.assertEqual(
            "/opt/noemaforge/noemaforge/src/admin_gui_server.py",
            by_repo["noemaforge/src/admin_gui_server.py"]["target_path"],
        )
        self.assertEqual(
            "/opt/noemaforge/noemaforge/tests/test_admin_gui_server.py",
            by_repo["noemaforge/tests/test_admin_gui_server.py"]["target_path"],
        )
        self.assertEqual(
            "/opt/noemaforge/noemaforge/configs/runtime-invariants.yaml",
            by_repo["noemaforge/configs/runtime-invariants.yaml"]["target_path"],
        )

    def test_runtime_deploy_plan_requires_discovered_source_root_for_src_files(self) -> None:
        plan = uatfix.build_runtime_deploy_plan(
            ["noemaforge/src/admin_gui_server.py"],
            source_root="",
        )

        self.assertFalse(plan["ok"])
        self.assertEqual(["noemaforge/src/admin_gui_server.py"], plan["unmapped"])
        self.assertEqual("", plan["mappings"][0]["target_path"])

    def test_deployed_pythonpath_includes_active_src_and_package_root(self) -> None:
        entries = uatfix.deployed_pythonpath(
            "/opt/noemaforge/noemaforge/src",
            service_unit_texts=['Environment="PYTHONPATH=/opt/noemaforge/noemaforge/src:/custom"'],
        )

        self.assertEqual("/opt/noemaforge/noemaforge/src", entries[0])
        self.assertEqual("/opt/noemaforge/noemaforge", entries[1])
        self.assertIn("/custom", entries)
        self.assertEqual(len(entries), len(set(entries)))

    def test_verify_deployed_file_hashes_detects_mismatch_after_copy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_deploy_hash_") as td:
            root = Path(td)
            repo = root / "repo"
            target = root / "target" / "src"
            (repo / "noemaforge" / "src").mkdir(parents=True)
            target.mkdir(parents=True)
            source = repo / "noemaforge" / "src" / "module.py"
            deployed = target / "module.py"
            source.write_text("VALUE = 1\n", encoding="utf-8")
            deployed.write_text("VALUE = 2\n", encoding="utf-8")
            mappings = [
                {
                    "repo_path": "noemaforge/src/module.py",
                    "target_path": str(deployed),
                    "mapped": True,
                }
            ]

            report = uatfix.verify_deployed_file_hashes(repo, mappings)

            self.assertFalse(report["ok"])
            self.assertEqual(1, len(report["failures"]))
            self.assertNotEqual(
                report["checked"][0]["source_sha256"],
                report["checked"][0]["target_sha256"],
            )

    def test_runtime_deploy_summary_writer_handles_quotes_and_newlines(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_deploy_summary_") as td:
            payload = {
                "ok": False,
                "evidence": "repo-evidenced",
                "live_evidence_claimed": False,
                "message": "quote ' and newline\nkept in JSON",
                "failures": [{"id": "hash_mismatch"}],
            }

            paths = uatfix.write_runtime_deploy_summary(Path(td), payload)

            parsed = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["message"], parsed["message"])
            markdown = Path(paths["markdown"]).read_text(encoding="utf-8")
            self.assertIn("live_evidence_claimed: false", markdown)
            self.assertIn("failures: 1", markdown)

    def test_failure_report_is_emitted_for_early_helper_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_failure_report_") as td:
            paths = uatfix.write_failure_report(Path(td), stem="release-decision-known-findings", error="source_gate_failed")
            self.assertTrue(Path(paths["json"]).is_file())
            self.assertTrue(Path(paths["markdown"]).is_file())
            payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
            self.assertIs(payload["ok"], False)
            self.assertEqual(payload["error"], "source_gate_failed")

    def test_reconcile_full_composite_artifacts_flags_missing_model_run_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_forensics_mismatch_") as td:
            root = Path(td)
            (root / "model-selection-decision.json").write_text(json.dumps({
                "mode": "full_composite",
                "dry_run": True,
                "ready_to_apply": True,
                "chosen_by_role": {
                    "operator.admin/administrator": {"model_id": "m-admin"},
                    "dev.work/solution_architect": {"model_id": "m-dev"},
                },
            }), encoding="utf-8")
            (root / "firstboot-staffing-summary.json").write_text(json.dumps({
                "staffing_state": "degraded_selected",
                "selected_roles": 2,
                "target_met_roles": 2,
                "selected_model_count": 2,
                "selected_model_ids": ["m-admin", "m-dev"],
            }), encoding="utf-8")
            (root / "role-candidate-map.json").write_text(json.dumps({
                "roles": {
                    "operator.admin/administrator": {
                        "chosen": {"model_id": "m-admin", "score": 0.91},
                        "selected": [{"model_id": "m-admin", "score": 0.91}],
                    },
                    "dev.work/solution_architect": {
                        "chosen": {"model_id": "m-dev", "score": 0.88},
                        "selected": [{"model_id": "m-dev", "score": 0.88}],
                    },
                }
            }), encoding="utf-8")
            (root / "role-tournament-results.json").write_text(json.dumps({
                "selection_mode": "full_composite",
                "roles": {
                    "operator.admin/administrator": {},
                    "dev.work/solution_architect": {},
                },
                "model_run_records": [],
            }), encoding="utf-8")
            (root / "model-run-records.json").write_text(json.dumps([]), encoding="utf-8")
            (root / "composite-selection-plan.json").write_text(json.dumps({
                "top_n": 0,
                "roles": {
                    "operator.admin/administrator": {"candidate_count": 1, "candidates": ["m-admin"]},
                    "dev.work/solution_architect": {"candidate_count": 1, "candidates": ["m-dev"]},
                },
                "estimated_compositions": 1,
                "materialized": True,
                "valid_compositions": 1,
            }), encoding="utf-8")

            report = uatfix.reconcile_full_composite_artifacts(root, retry_failed_models=True)

            self.assertEqual(report["mode"], "full_composite")
            self.assertFalse(report["max_complexity_gate"]["accepted"])
            self.assertIn("model_run_evidence_missing", report["max_complexity_gate"]["blocking_reasons"])
            self.assertIn("measured_candidates_without_model_run_evidence", report["mismatches"])
            self.assertIn("selected_roles_without_started_models", report["mismatches"])

    def test_reconcile_full_composite_artifacts_accepts_consistent_retry_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_forensics_consistent_") as td:
            root = Path(td)
            (root / "model-selection-decision.json").write_text(json.dumps({
                "mode": "full_composite",
                "dry_run": True,
                "ready_to_apply": True,
                "chosen_by_role": {
                    "operator.admin/administrator": {"model_id": "m-admin"},
                    "dev.work/solution_architect": {"model_id": "m-dev"},
                },
            }), encoding="utf-8")
            (root / "firstboot-staffing-summary.json").write_text(json.dumps({
                "staffing_state": "selected",
                "selected_roles": 2,
                "target_met_roles": 2,
                "selected_model_count": 2,
                "selected_model_ids": ["m-admin", "m-dev"],
            }), encoding="utf-8")
            (root / "role-candidate-map.json").write_text(json.dumps({
                "roles": {
                    "operator.admin/administrator": {
                        "chosen": {"model_id": "m-admin", "score": 0.91},
                        "selected": [{"model_id": "m-admin", "score": 0.91}],
                    },
                    "dev.work/solution_architect": {
                        "chosen": {"model_id": "m-dev", "score": 0.88},
                        "selected": [{"model_id": "m-dev", "score": 0.88}],
                    },
                }
            }), encoding="utf-8")
            records = [
                {"model_id": "m-admin", "started": True},
                {"model_id": "m-dev", "started": True},
                {"model_id": "m-qa", "started": True, "partial_valid": True},
            ]
            (root / "role-tournament-results.json").write_text(json.dumps({
                "selection_mode": "full_composite",
                "roles": {
                    "operator.admin/administrator": {},
                    "dev.work/solution_architect": {},
                },
                "model_run_records": records,
                "composite_selection_plan": str(root / "composite-selection-plan.json"),
            }), encoding="utf-8")
            (root / "model-run-records.json").write_text(json.dumps({"records": records}), encoding="utf-8")
            (root / "composite-selection-plan.json").write_text(json.dumps({
                "top_n": 0,
                "roles": {
                    "operator.admin/administrator": {"candidate_count": 1, "candidates": ["m-admin"]},
                    "dev.work/solution_architect": {"candidate_count": 1, "candidates": ["m-dev"]},
                },
                "estimated_compositions": 1,
                "materialized": True,
                "valid_compositions": 1,
            }), encoding="utf-8")

            report = uatfix.reconcile_full_composite_artifacts(root, retry_failed_models=True)

            self.assertEqual([], report["mismatches"])
            self.assertTrue(report["dry_run_evaluation_scope"]["ok_to_label_max_complexity"])
            self.assertTrue(report["max_complexity_gate"]["accepted"])

    def test_reconcile_full_composite_artifacts_blocks_malformed_json_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_forensics_malformed_") as td:
            root = Path(td)
            (root / "model-selection-decision.json").write_text(json.dumps({
                "mode": "full_composite",
                "dry_run": True,
                "ready_to_apply": True,
                "chosen_by_role": {"operator.admin/administrator": {"model_id": "m-admin"}},
            }), encoding="utf-8")
            (root / "firstboot-staffing-summary.json").write_text(json.dumps({
                "staffing_state": "selected",
                "selected_roles": 1,
                "target_met_roles": 1,
                "selected_model_count": 1,
                "selected_model_ids": ["m-admin"],
            }), encoding="utf-8")
            (root / "role-candidate-map.json").write_text(json.dumps({
                "roles": {
                    "operator.admin/administrator": {
                        "chosen": {"model_id": "m-admin", "score": 0.91},
                        "selected": [{"model_id": "m-admin", "score": 0.91}],
                    },
                }
            }), encoding="utf-8")
            (root / "role-tournament-results.json").write_text(json.dumps({
                "selection_mode": "full_composite",
                "roles": {"operator.admin/administrator": {}},
                "model_run_records": [{"model_id": "m-admin", "started": True}],
                "composite_selection_plan": str(root / "composite-selection-plan.json"),
            }), encoding="utf-8")
            (root / "model-run-records.json").write_text('{"records": [', encoding="utf-8")
            (root / "composite-selection-plan.json").write_text(json.dumps({
                "top_n": 0,
                "roles": {"operator.admin/administrator": {"candidate_count": 1, "candidates": ["m-admin"]}},
                "estimated_compositions": 1,
                "materialized": True,
                "valid_compositions": 1,
            }), encoding="utf-8")

            report = uatfix.reconcile_full_composite_artifacts(root, retry_failed_models=True)

            self.assertFalse(report["ok"])
            self.assertFalse(report["max_complexity_gate"]["accepted"])
            self.assertEqual("parse_error", report["artifacts"]["model_run_records"]["error"].split(":", 1)[0])
            self.assertIn("model_run_records_artifact_parse_error", report["artifact_integrity_blockers"])
            self.assertIn("model_run_records_artifact_parse_error", report["max_complexity_gate"]["blocking_reasons"])

    def test_reconcile_full_composite_artifacts_blocks_invalid_numeric_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_forensics_invalid_fields_") as td:
            root = Path(td)
            (root / "model-selection-decision.json").write_text(json.dumps({
                "mode": "full_composite",
                "dry_run": True,
                "ready_to_apply": True,
                "chosen_by_role": {"operator.admin/administrator": {"model_id": "m-admin"}},
            }), encoding="utf-8")
            (root / "firstboot-staffing-summary.json").write_text(json.dumps({
                "staffing_state": "selected",
                "selected_roles": "not-a-number",
                "target_met_roles": 1,
                "selected_model_count": 1,
                "selected_model_ids": ["m-admin"],
            }), encoding="utf-8")
            (root / "role-candidate-map.json").write_text(json.dumps({
                "roles": {
                    "operator.admin/administrator": {
                        "chosen": {"model_id": "m-admin", "score": 0.91},
                        "selected": [{"model_id": "m-admin", "score": 0.91}],
                    },
                }
            }), encoding="utf-8")
            records = [{"model_id": "m-admin", "started": True}, {"model_id": "m-extra", "started": True}]
            (root / "role-tournament-results.json").write_text(json.dumps({
                "selection_mode": "full_composite",
                "roles": {"operator.admin/administrator": {}},
                "model_run_records": records,
                "composite_selection_plan": str(root / "composite-selection-plan.json"),
            }), encoding="utf-8")
            (root / "model-run-records.json").write_text(json.dumps({"records": records}), encoding="utf-8")
            (root / "composite-selection-plan.json").write_text(json.dumps({
                "top_n": "bad",
                "roles": {"operator.admin/administrator": {"candidate_count": "bad", "candidates": ["m-admin"]}},
                "estimated_compositions": 1,
                "materialized": True,
                "valid_compositions": 1,
            }), encoding="utf-8")

            report = uatfix.reconcile_full_composite_artifacts(root, retry_failed_models=True)

            self.assertTrue(report["ok"])
            self.assertFalse(report["max_complexity_gate"]["accepted"])
            self.assertIn("staffing_summary_invalid_fields", report["mismatches"])
            self.assertIn("composite_selection_plan_invalid_fields", report["mismatches"])
            self.assertEqual(["selected_roles"], report["sources"]["firstboot_staffing_summary"]["invalid_fields"])
            self.assertEqual(
                ["roles.candidate_count", "top_n"],
                report["sources"]["composite_selection_plan"]["invalid_fields"],
            )

    def test_summarize_model_selection_decision_rejects_stringy_boolean_dry_run(self) -> None:
        # bool("false") is True in Python -- a malformed string-typed artifact field
        # must never be silently coerced to True and treated as a real dry run.
        summary = uatfix.summarize_model_selection_decision({
            "mode": "full_composite",
            "dry_run": "false",
            "ready_to_apply": 1,
        })

        self.assertIs(summary["dry_run"], False)
        self.assertIs(summary["ready_to_apply"], False)
        self.assertIn("dry_run", summary["invalid_fields"])
        self.assertIn("ready_to_apply", summary["invalid_fields"])

    def test_reconcile_full_composite_artifacts_blocks_stringy_dry_run_field(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_forensics_stringy_bool_") as td:
            root = Path(td)
            (root / "model-selection-decision.json").write_text(json.dumps({
                "mode": "full_composite",
                "dry_run": "false",
                "ready_to_apply": True,
                "chosen_by_role": {"operator.admin/administrator": {"model_id": "m-admin"}},
            }), encoding="utf-8")
            (root / "firstboot-staffing-summary.json").write_text(json.dumps({
                "staffing_state": "selected",
                "selected_roles": 1,
                "target_met_roles": 1,
                "selected_model_count": 1,
                "selected_model_ids": ["m-admin"],
            }), encoding="utf-8")
            (root / "role-candidate-map.json").write_text(json.dumps({
                "roles": {
                    "operator.admin/administrator": {
                        "chosen": {"model_id": "m-admin", "score": 0.91},
                        "selected": [{"model_id": "m-admin", "score": 0.91}],
                    },
                }
            }), encoding="utf-8")
            records = [{"model_id": "m-admin", "started": True}]
            (root / "role-tournament-results.json").write_text(json.dumps({
                "selection_mode": "full_composite",
                "roles": {"operator.admin/administrator": {}},
                "model_run_records": records,
            }), encoding="utf-8")
            (root / "model-run-records.json").write_text(json.dumps({"records": records}), encoding="utf-8")
            (root / "composite-selection-plan.json").write_text(json.dumps({
                "top_n": 0,
                "roles": {"operator.admin/administrator": {"candidate_count": 1, "candidates": ["m-admin"]}},
                "estimated_compositions": 1,
                "materialized": True,
                "valid_compositions": 1,
            }), encoding="utf-8")

            report = uatfix.reconcile_full_composite_artifacts(root)

            self.assertIs(report["sources"]["model_selection_decision"]["dry_run"], False)
            self.assertIn("model_selection_decision_invalid_fields", report["mismatches"])
            self.assertIn("not_dry_run", report["dry_run_evaluation_scope"]["blocking_reasons"])
            self.assertFalse(report["max_complexity_gate"]["accepted"])

    def test_summarize_staffing_summary_rejects_non_list_collection_fields(self) -> None:
        # A string field would previously be iterated character-by-character
        # (for x in "m-admin" yields 'm','-','a',...); an int field would raise
        # TypeError outright since `2 or []` is truthy and `list(2)` is not iterable.
        summary = uatfix.summarize_staffing_summary({
            "staffing_state": "degraded_selected",
            "selected_roles": 1,
            "target_met_roles": 1,
            "selected_model_count": 1,
            "selected_model_ids": "m-admin",
            "missing_mandatory_core_roles": 2,
            "unstaffed_roles": {"not": "a-list"},
        })

        self.assertEqual([], summary["selected_model_ids"])
        self.assertEqual([], summary["missing_mandatory_core_roles"])
        self.assertEqual([], summary["unstaffed_roles"])
        self.assertIn("selected_model_ids", summary["invalid_fields"])
        self.assertIn("missing_mandatory_core_roles", summary["invalid_fields"])
        self.assertIn("unstaffed_roles", summary["invalid_fields"])

    def test_summarize_composite_selection_plan_rejects_non_list_candidates(self) -> None:
        # `len(role_spec.get("candidates") or [])` would raise TypeError when
        # "candidates" is a truthy non-list (e.g. an int).
        summary = uatfix.summarize_composite_selection_plan({
            "top_n": 0,
            "roles": {
                "operator.admin/administrator": {"candidates": 5},
            },
            "missing_candidate_roles": "role-a",
        })

        self.assertIn("roles.candidates", summary["invalid_fields"])
        self.assertIn("missing_candidate_roles", summary["invalid_fields"])
        self.assertEqual([], summary["missing_candidate_roles"])

    def test_summarize_preferred_model_run_records_flags_empty_dedicated_vs_nonempty_embedded(self) -> None:
        embedded_tournament = {"model_run_records": [{"model_id": "m1", "started": True}]}

        summary = uatfix.summarize_preferred_model_run_records([], embedded_tournament, dedicated_loaded=True)

        self.assertEqual(0, summary["model_runs"])
        self.assertEqual("model-run-records.json", summary["source"])
        self.assertTrue(summary["dedicated_present_and_empty"])
        self.assertEqual(1, summary["embedded_model_runs"])

    def test_summarize_preferred_model_run_records_falls_back_only_when_dedicated_absent(self) -> None:
        embedded_tournament = {"model_run_records": [{"model_id": "m1", "started": True}]}

        summary = uatfix.summarize_preferred_model_run_records(None, embedded_tournament, dedicated_loaded=False)

        self.assertEqual(1, summary["model_runs"])
        self.assertEqual("role-tournament-results.json:model_run_records", summary["source"])

    def test_reconcile_full_composite_artifacts_flags_empty_dedicated_records_against_nonempty_embedded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_forensics_empty_dedicated_") as td:
            root = Path(td)
            (root / "model-selection-decision.json").write_text(json.dumps({
                "mode": "full_composite",
                "dry_run": True,
                "ready_to_apply": True,
                "chosen_by_role": {"operator.admin/administrator": {"model_id": "m-admin"}},
            }), encoding="utf-8")
            (root / "firstboot-staffing-summary.json").write_text(json.dumps({
                "staffing_state": "selected",
                "selected_roles": 1,
                "target_met_roles": 1,
                "selected_model_count": 1,
                "selected_model_ids": ["m-admin"],
            }), encoding="utf-8")
            (root / "role-candidate-map.json").write_text(json.dumps({
                "roles": {
                    "operator.admin/administrator": {
                        "chosen": {"model_id": "m-admin", "score": 0.91},
                        "selected": [{"model_id": "m-admin", "score": 0.91}],
                    },
                }
            }), encoding="utf-8")
            embedded_records = [{"model_id": "m-admin", "started": True}, {"model_id": "m-dev", "started": True}]
            (root / "role-tournament-results.json").write_text(json.dumps({
                "selection_mode": "full_composite",
                "roles": {"operator.admin/administrator": {}},
                "model_run_records": embedded_records,
            }), encoding="utf-8")
            # Dedicated artifact is present and genuinely, validly empty -- this must
            # NOT be silently treated the same as "absent" / fallback to embedded.
            (root / "model-run-records.json").write_text(json.dumps([]), encoding="utf-8")
            (root / "composite-selection-plan.json").write_text(json.dumps({
                "top_n": 0,
                "roles": {"operator.admin/administrator": {"candidate_count": 1, "candidates": ["m-admin"]}},
                "estimated_compositions": 1,
                "materialized": True,
                "valid_compositions": 1,
            }), encoding="utf-8")

            report = uatfix.reconcile_full_composite_artifacts(root)

            self.assertEqual("model-run-records.json", report["sources"]["model_run_records"]["source"])
            self.assertEqual(0, report["sources"]["model_run_records"]["model_runs"])
            self.assertIn("dedicated_model_run_records_empty_but_embedded_present", report["mismatches"])
            self.assertFalse(report["max_complexity_gate"]["accepted"])

    def test_reconcile_full_composite_artifacts_ignores_cli_retry_flag_contradicted_by_recorded_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_forensics_cli_flag_provenance_") as td:
            root = Path(td)
            records = [{"model_id": "ok", "started": True}]
            records.extend({"model_id": f"old-{idx}", "reason": "previously_failed_runtime"} for idx in range(9))
            (root / "model-selection-decision.json").write_text(json.dumps({
                "mode": "full_composite",
                "dry_run": True,
                "ready_to_apply": True,
                "chosen_by_role": {"operator.admin/administrator": {"model_id": "ok"}},
                # Recorded evidence: the ORIGINAL run did NOT retry failed models.
                "dry_run_evaluation_scope": {
                    "retry_failed_models": False,
                    "clear_model_health": False,
                },
            }), encoding="utf-8")
            (root / "firstboot-staffing-summary.json").write_text(json.dumps({
                "staffing_state": "degraded_selected",
                "selected_roles": 1,
                "target_met_roles": 1,
                "selected_model_count": 1,
                "selected_model_ids": ["ok"],
            }), encoding="utf-8")
            (root / "role-candidate-map.json").write_text(json.dumps({
                "roles": {
                    "operator.admin/administrator": {
                        "chosen": {"model_id": "ok", "score": 0.9},
                        "selected": [{"model_id": "ok", "score": 0.9}],
                    }
                }
            }), encoding="utf-8")
            (root / "role-tournament-results.json").write_text(json.dumps({
                "selection_mode": "full_composite",
                "roles": {"operator.admin/administrator": {}},
                "model_run_records": records,
            }), encoding="utf-8")
            (root / "model-run-records.json").write_text(json.dumps({"records": records}), encoding="utf-8")
            (root / "composite-selection-plan.json").write_text(json.dumps({
                "top_n": 0,
                "roles": {"operator.admin/administrator": {"candidate_count": 1, "candidates": ["ok"]}},
                "estimated_compositions": 1,
                "materialized": True,
                "valid_compositions": 1,
            }), encoding="utf-8")

            # An analyst re-runs the CLI with --retry-failed-models even though the
            # ORIGINAL run (recorded in dry_run_evaluation_scope) did not retry. This
            # unverified CLI claim must not flip the gate result on unchanged artifacts.
            report = uatfix.reconcile_full_composite_artifacts(root, retry_failed_models=True)

            self.assertFalse(report["dry_run_evaluation_scope"]["retry_failed_models"])
            self.assertIn("persisted_model_health_reused", report["dry_run_evaluation_scope"]["blocking_reasons"])
            self.assertFalse(report["max_complexity_gate"]["accepted"])
            self.assertTrue(report["cli_flag_provenance"]["retry_failed_models_cli_argument"])
            self.assertFalse(report["cli_flag_provenance"]["retry_failed_models_effective"])
            self.assertTrue(report["cli_flag_provenance"]["cli_retry_failed_models_contradicted_by_evidence"])

    def test_reconcile_full_composite_artifacts_detects_zero_versus_nonzero_role_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_forensics_zero_mismatch_") as td:
            root = Path(td)
            (root / "model-selection-decision.json").write_text(json.dumps({
                "mode": "full_composite",
                "dry_run": True,
                "ready_to_apply": False,
                "chosen_by_role": {},
            }), encoding="utf-8")
            # staffing_summary reports zero selected roles...
            (root / "firstboot-staffing-summary.json").write_text(json.dumps({
                "staffing_state": "failed_selection",
                "selected_roles": 0,
                "target_met_roles": 0,
                "selected_model_count": 0,
                "selected_model_ids": [],
            }), encoding="utf-8")
            # ...but role_candidate_map disagrees: it actually selected one role.
            # A truthiness-guarded comparison (`if a and b and a != b`) would silently
            # skip this because 0 is falsy; the real values 0 != 1 must be compared.
            (root / "role-candidate-map.json").write_text(json.dumps({
                "roles": {
                    "operator.admin/administrator": {
                        "selected": [{"model_id": "m-admin", "score": 0.9}],
                    }
                }
            }), encoding="utf-8")
            (root / "role-tournament-results.json").write_text(json.dumps({
                "selection_mode": "full_composite",
                "roles": {"operator.admin/administrator": {}},
                "model_run_records": [{"model_id": "m-admin", "started": True}],
            }), encoding="utf-8")
            (root / "model-run-records.json").write_text(json.dumps([{"model_id": "m-admin", "started": True}]), encoding="utf-8")
            (root / "composite-selection-plan.json").write_text(json.dumps({
                "top_n": 0,
                "roles": {"operator.admin/administrator": {"candidate_count": 1, "candidates": ["m-admin"]}},
                "estimated_compositions": 1,
                "materialized": True,
                "valid_compositions": 1,
            }), encoding="utf-8")

            report = uatfix.reconcile_full_composite_artifacts(root)

            self.assertIn("selected_roles_mismatch", report["mismatches"])
            self.assertFalse(report["max_complexity_gate"]["accepted"])

    def test_forensics_cli_returns_nonzero_when_gate_is_not_accepted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_forensics_cli_fail_") as td:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = uatfix.main(["--root", td])

            payload = json.loads(stdout.getvalue())
            self.assertEqual(1, rc)
            self.assertFalse(payload["ok"])
            self.assertFalse(payload["max_complexity_gate"]["accepted"])


if __name__ == "__main__":
    unittest.main()
