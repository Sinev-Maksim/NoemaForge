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

    def test_gateway_probe_spec_uses_openai_models_over_canonical_unix_socket(self) -> None:
        spec = uatfix.gateway_probe_spec()

        self.assertEqual("/run/noemaforge/llm/gateway.sock", spec["socket"])
        self.assertEqual("http://localhost/v1/models", spec["url"])
        self.assertEqual("http_over_unix_socket", spec["protocol"])
        self.assertIn("--unix-socket", spec["command"])
        self.assertIn("/run/noemaforge/llm/gateway.sock", spec["command"])

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

    def test_resolve_current_epoch_state_reports_symlink_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_epoch_state_") as td:
            root = Path(td) / "contracts"
            epochs = root / "epochs"
            epoch = epochs / "00006"
            epoch.mkdir(parents=True)
            (epochs / "current_epoch.txt").write_text("00006\n", encoding="utf-8")
            try:
                (epochs / "current").symlink_to(epoch)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink unavailable on this host: {exc}")

            state = uatfix.resolve_current_epoch_state(root)

            self.assertTrue(state["ok"], state)
            self.assertEqual("00006", state["current_epoch_id"])
            self.assertEqual(str(epoch), state["current_target"])
            self.assertTrue(state["current_target_exists"])
            self.assertTrue(state["current_target_matches_canonical_dir"])

    def test_resolve_current_epoch_state_rejects_link_outside_canonical_dir(self) -> None:
        # Regression for CodeRabbit finding: an existing external symlink target that
        # happens to share the expected epoch id's *basename* (but lives entirely
        # outside contracts/epochs/) must not be accepted as pointing at the
        # canonical applied epoch just because a directory of that name exists
        # somewhere under epochs_dir too.
        with tempfile.TemporaryDirectory(prefix="nf_epoch_state_outside_") as td:
            root = Path(td) / "contracts"
            epochs = root / "epochs"
            canonical_epoch = epochs / "00006"
            canonical_epoch.mkdir(parents=True)
            external = Path(td) / "external" / "00006"
            external.mkdir(parents=True)
            try:
                (epochs / "current").symlink_to(external)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink unavailable on this host: {exc}")
            # No current_epoch.txt written: the epoch id must be inferred from the
            # symlink target's basename, which collides with the unrelated
            # already-existing canonical directory name.

            state = uatfix.resolve_current_epoch_state(root)

            # The basename-derived canonical dir really does exist, so a check that
            # only compared names/ids (the pre-fix behavior) would have reported ok.
            self.assertTrue(state["epoch_dir_exists"], state)
            self.assertFalse(state["current_target_matches_canonical_dir"], state)
            self.assertIn("current_epoch_link_outside_canonical_dir", state["problems"])
            self.assertFalse(state["ok"], state)

    def test_reconcile_post_apply_classifies_gateway_outage_with_backend_ok(self) -> None:
        report = uatfix.reconcile_post_apply_forensics(
            apply_summary={
                "applied_epoch_id": "00006",
                "post_backend_ok": True,
                "post_gateway_ok": False,
            },
            firstboot_status={"state": "applied_no_reboot", "applied_epoch_id": "00006"},
            current_epoch={
                "current_epoch_id": "00006",
                "current_target": "/var/lib/noemaforge/contracts/epochs/00006",
            },
            gateway_health={
                "ok": False,
                "socket": "/run/noemaforge/llm/gateway.sock",
                "protocol": "http_over_unix_socket",
                "socket_present": False,
            },
            backend_health={"ok": True, "socket": "/run/noemaforge/llm/backends/main.sock"},
            toolproxy_diag={"ok": True},
            prestart_requests={"requests": [{"id": "firstboot-roleaware"}]},
        )

        self.assertFalse(report["ok"])
        self.assertEqual("gateway_outage", report["determination"])
        self.assertEqual("/var/lib/noemaforge/contracts/epochs/00006", report["current_epoch_target"])
        self.assertTrue(report["canonical_gateway_probe_used"])
        self.assertIn("post_gateway_not_ok", report["blockers"])

    def test_reconcile_post_apply_flags_wrong_gateway_smoke_path(self) -> None:
        report = uatfix.reconcile_post_apply_forensics(
            apply_summary={"applied_epoch_id": "00006", "post_backend_ok": True, "post_gateway_ok": False},
            current_epoch={
                "current_epoch_id": "00006",
                "current_target": "/var/lib/noemaforge/contracts/epochs/00006",
            },
            gateway_health={
                "ok": False,
                "socket": "/run/noemaforge/llm-gateway.sock",
                "protocol": "raw_unix",
                "socket_present": True,
            },
            backend_health={"ok": True},
        )

        self.assertEqual("wrong_smoke_path_or_protocol", report["determination"])
        self.assertFalse(report["canonical_gateway_probe_used"])

    def test_reconcile_post_apply_detects_summary_helper_missing_epoch_target(self) -> None:
        report = uatfix.reconcile_post_apply_forensics(
            apply_summary={"applied_epoch_id": "00006", "post_backend_ok": True, "post_gateway_ok": True},
            firstboot_status={"state": "applied_no_reboot", "applied_epoch_id": "00006"},
            current_epoch={"current_epoch_id": "00006", "current_target": ""},
            gateway_health={"ok": True, "socket": "/run/noemaforge/llm/gateway.sock"},
            backend_health={"ok": True},
        )

        self.assertFalse(report["ok"])
        self.assertEqual("summary_helper_issue", report["determination"])
        self.assertIn("current_epoch_target_missing", report["blockers"])

    def test_reconcile_post_apply_does_not_infer_applied_epoch_from_current_epoch(self) -> None:
        # Regression for CodeRabbit finding: when neither the apply summary nor the
        # firstboot status recorded an explicit applied_epoch_id, the current epoch
        # id must NOT be silently substituted as if it were apply evidence.
        report = uatfix.reconcile_post_apply_forensics(
            apply_summary={"post_backend_ok": True, "post_gateway_ok": True},
            firstboot_status={"state": "applied_no_reboot"},
            current_epoch={
                "current_epoch_id": "00006",
                "current_target": "/var/lib/noemaforge/contracts/epochs/00006",
            },
            gateway_health={
                "ok": True,
                "socket": "/run/noemaforge/llm/gateway.sock",
                "protocol": "http_over_unix_socket",
            },
            backend_health={"ok": True},
        )

        self.assertEqual("", report["applied_epoch_id"])
        self.assertNotEqual("00006", report["applied_epoch_id"])
        self.assertIn("applied_epoch_id_missing", report["blockers"])
        self.assertFalse(report["ok"])

    def test_reconcile_post_apply_prefers_direct_gateway_probe_over_stale_summary_ok(self) -> None:
        # Regression for CodeRabbit finding: a stale/indirect apply_summary field
        # claiming the gateway is healthy must not override a direct, current
        # post-apply health probe that says otherwise via `or` logic.
        report = uatfix.reconcile_post_apply_forensics(
            apply_summary={
                "applied_epoch_id": "00006",
                "post_backend_ok": True,
                "post_gateway_ok": True,
            },
            current_epoch={
                "current_epoch_id": "00006",
                "current_target": "/var/lib/noemaforge/contracts/epochs/00006",
            },
            gateway_health={
                "ok": False,
                "socket": "/run/noemaforge/llm/gateway.sock",
                "protocol": "http_over_unix_socket",
            },
            backend_health={"ok": True},
        )

        self.assertFalse(report["post_gateway_ok"])
        self.assertTrue(report["post_gateway_health_conflict"])
        self.assertIn("post_gateway_health_conflict", report["blockers"])
        self.assertFalse(report["ok"])
        self.assertNotEqual("post_apply_state_reconciled", report["determination"])

    def test_reconcile_post_apply_treats_missing_gateway_probe_metadata_as_unrecorded(self) -> None:
        # Regression for CodeRabbit finding: an empty/missing observed socket and
        # protocol must not silently satisfy the canonical-probe check as if the
        # canonical probe had actually been confirmed used.
        report = uatfix.reconcile_post_apply_forensics(
            apply_summary={"applied_epoch_id": "00006", "post_backend_ok": True, "post_gateway_ok": False},
            current_epoch={
                "current_epoch_id": "00006",
                "current_target": "/var/lib/noemaforge/contracts/epochs/00006",
            },
            gateway_health={"ok": False},
            backend_health={"ok": True},
        )

        self.assertFalse(report["canonical_gateway_probe_used"])
        self.assertEqual("unrecorded", report["gateway_probe_evidence"])
        self.assertEqual("wrong_smoke_path_or_protocol", report["determination"])

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
            {"model_id": "slow", "reason": "TimeoutError('timed out')"},
            {"model_id": "bad-api", "selection_status": "invalid_backend_calls"},
            {"model_id": "bad-api-2", "reason": "invalid_backend_calls"},
        ]
        summary = uatfix.summarize_model_run_records(records)
        self.assertEqual(summary["model_runs"], 10)
        self.assertEqual(summary["models_started"], 3)
        self.assertEqual(summary["classification_counts"]["completed"], 1)
        self.assertEqual(summary["classification_counts"]["partial_valid"], 1)
        self.assertEqual(summary["classification_counts"]["warmup_failed"], 1)
        self.assertEqual(summary["classification_counts"]["systemctl_start_failed"], 1)
        self.assertEqual(summary["classification_counts"]["timeout"], 2)
        self.assertEqual(summary["classification_counts"]["invalid_backend_calls"], 2)
        self.assertEqual(summary["classification_counts"]["safety-filtered"], 1)
        self.assertEqual(summary["classification_counts"]["unknown"], 1)
        self.assertEqual(summary["failed_model_ids"], ["bad-api", "bad-api-2", "old", "slow", "svc", "warm"])
        self.assertEqual(
            summary["failure_groups_by_model"],
            [
                {
                    "model_id": "bad-api",
                    "logical_model_id": "",
                    "classifications": ["invalid_backend_calls"],
                    "reasons": ["invalid_backend_calls"],
                },
                {
                    "model_id": "bad-api-2",
                    "logical_model_id": "",
                    "classifications": ["invalid_backend_calls"],
                    "reasons": ["invalid_backend_calls"],
                },
                {
                    "model_id": "old",
                    "logical_model_id": "",
                    "classifications": ["unknown"],
                    "reasons": ["previously_failed_runtime"],
                },
                {
                    "model_id": "slow",
                    "logical_model_id": "",
                    "classifications": ["timeout"],
                    "reasons": ["TimeoutError('timed out')"],
                },
                {
                    "model_id": "svc",
                    "logical_model_id": "",
                    "classifications": ["systemctl_start_failed"],
                    "reasons": ["systemctl_start_failed:1"],
                },
                {
                    "model_id": "warm",
                    "logical_model_id": "",
                    "classifications": ["warmup_failed"],
                    "reasons": ["warmup_failed"],
                },
            ],
        )
        self.assertEqual(
            summary["failure_groups_by_reason"],
            [
                {
                    "classification": "invalid_backend_calls",
                    "reason": "invalid_backend_calls",
                    "count": 2,
                    "model_ids": ["bad-api", "bad-api-2"],
                },
                {
                    "classification": "systemctl_start_failed",
                    "reason": "systemctl_start_failed:1",
                    "count": 1,
                    "model_ids": ["svc"],
                },
                {
                    "classification": "timeout",
                    "reason": "TimeoutError('timed out')",
                    "count": 2,
                    "model_ids": ["slow"],
                },
                {
                    "classification": "unknown",
                    "reason": "previously_failed_runtime",
                    "count": 1,
                    "model_ids": ["old"],
                },
                {
                    "classification": "warmup_failed",
                    "reason": "warmup_failed",
                    "count": 1,
                    "model_ids": ["warm"],
                },
            ],
        )

    def test_never_started_record_without_reason_is_not_classified_completed(self) -> None:
        # A model run that never started and has no reason/selection_status
        # recorded is genuinely unknown, not "completed". It must not be
        # silently reported with a "completed" reason inside the
        # failure/incomplete grouping used for triage output.
        records = [{"model_id": "ghost"}]
        summary = uatfix.summarize_model_run_records(records)
        self.assertEqual(summary["classification_counts"]["unknown"], 1)
        self.assertEqual(summary["reason_counts"], {"unknown": 1})
        self.assertEqual(len(summary["failed_or_incomplete"]), 1)
        self.assertEqual(summary["failed_or_incomplete"][0]["classification"], "unknown")
        self.assertEqual(summary["failed_or_incomplete"][0]["reason"], "unknown")
        self.assertNotEqual(summary["failed_or_incomplete"][0]["reason"], "completed")

    def test_started_record_without_reason_is_still_classified_completed(self) -> None:
        # The legitimate "completed" shape (a record that DID start and
        # finished with no explicit reason field) must keep working.
        records = [{"model_id": "ok", "started": True}]
        summary = uatfix.summarize_model_run_records(records)
        self.assertEqual(summary["classification_counts"]["completed"], 1)
        self.assertEqual(summary["reason_counts"], {"completed": 1})
        self.assertEqual(summary["failed_or_incomplete"], [])

    def test_model_id_less_failed_records_are_not_merged_into_one_group(self) -> None:
        # Multiple failed records that all lack a model_id must not collapse
        # into a single ""-keyed group: each record's classification/reason
        # would otherwise be silently merged as if it came from one model.
        records = [
            {"reason": "warmup_failed"},
            {"reason": "invalid_backend_calls"},
        ]
        summary = uatfix.summarize_model_run_records(records)
        self.assertEqual(len(summary["failure_groups_by_model"]), 2)
        self.assertEqual(
            sorted(group["reasons"][0] for group in summary["failure_groups_by_model"]),
            ["invalid_backend_calls", "warmup_failed"],
        )
        for group in summary["failure_groups_by_model"]:
            self.assertEqual(group["model_id"], "")
        # Empty model_id groups still don't leak into failed_model_ids.
        self.assertEqual(summary["failed_model_ids"], [])

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
            self.assertEqual(summary["failed_model_ids"], ["m2"])
            self.assertEqual(summary["failure_groups_by_model"][0]["reasons"], ["warmup_failed"])

    def test_summarize_artifacts_counts_generator_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_artifact_summary_") as td:
            root = Path(td)
            one = root / "one.json"
            two = root / "two.json"
            one.write_text(json.dumps({"records": [{"model_id": "m1", "started": True}]}), encoding="utf-8")
            two.write_text(json.dumps({"records": [{"model_id": "m2", "reason": "warmup_failed"}]}), encoding="utf-8")

            summary = uatfix.summarize_artifacts(path for path in (one, two))

            self.assertEqual(summary["artifact_count"], 2)
            self.assertEqual(summary["model_runs"], 2)
            self.assertEqual(summary["failed_model_ids"], ["m2"])

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


if __name__ == "__main__":
    unittest.main()
