#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pipeline_runtime as prt  # noqa: E402
import selection_refresh_runtime as srr  # noqa: E402
from noemaforge_version import RUNTIME_VERSION  # noqa: E402


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def selection_fixture(path: Path, *, incompatible: bool = False) -> None:
    valid_candidate = {
        "model_id": "smollm2-360m-instruct-q8-0",
        "logical_model_id": "smollm2-360m-instruct-q8-0",
        "role_key": "dev.work/solution_architect",
        "score": 0.8453,
        "selection_status": "valid_measured",
        "pass_rate": 0.7,
        "json_parse_rate": 1.0,
        "quality_score": 0.925,
        "avg_latency_ms": 1113.5,
    }
    admin_candidate = {
        **valid_candidate,
        "role_key": "operator.admin/administrator",
    }
    invalid_candidate = {
        "model_id": "" if incompatible else "smollm2-360m-instruct-q8-0",
        "role_key": "dev.work/qa",
        "selection_status": "invalid_schema" if incompatible else "valid_measured",
    }
    write_json(path / "model-selection-decision.json", {
        "apiVersion": "noemaforge.model-selection/v1",
        "kind": "ModelSelectionDecision",
        "version": "0.32.2",
        "mode": "full_composite",
        "composite_top_n": 3,
        "staffing_state": "degraded_selected",
        "chosen_by_role": {"dev.work/solution_architect": valid_candidate, "operator.admin/administrator": admin_candidate},
    })
    write_json(path / "firstboot-staffing-summary.json", {
        "apiVersion": "noemaforge.firstbootstaffing/v1",
        "kind": "FirstbootStaffingSummary",
        "staffing_state": "degraded_selected",
        "unstaffed_roles": ["dev.work/dev"],
        "selected_model_ids": ["smollm2-360m-instruct-q8-0"],
        "selected_model_count": 1,
    })
    write_json(path / "role-candidate-map.json", {
        "apiVersion": "noemaforge.roles/v1",
        "kind": "RoleCandidateMap",
        "roles": {
            "dev.work/solution_architect": {"chosen": valid_candidate, "selected": [valid_candidate]},
            "operator.admin/administrator": {"chosen": admin_candidate, "selected": [admin_candidate]},
            "dev.work/dev": {"chosen": None, "selected": []},
            "dev.work/qa": {"chosen": invalid_candidate, "selected": [invalid_candidate]},
        },
    })
    write_json(path / "role-tournament-results.json", {
        "apiVersion": "noemaforge.tournament/v1",
        "kind": "RoleTournamentResults",
        "selection_mode": "full_composite",
    })
    write_json(path / "main_manifest.json", {
        "model_id": "qwen2-5-coder-3b-instruct-q4-k-m",
        "source": "/models/qwen2.5-coder-3b-instruct-q4_k_m.gguf",
    })
    write_json(path / "runtime-status-compact.json", {
        "active_model": {
            "manifest_exists": True,
            "model_id": "smollm2-360m-instruct-q8-0",
            "model_realpath": "/models/smollm2-360m-instruct-q8_0.gguf",
        },
        "gateway": {"ok": False, "stdout": "inactive", "returncode": 3},
        "main_backend": {"ok": True, "stdout": "active", "returncode": 0},
        "sockets": {
            "/run/noemaforge/llm/gateway.sock": False,
            "/run/noemaforge/llm/backends/main.sock": True,
        },
    })


def call_pipeline(argv: list[str]) -> dict:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        try:
            prt.main(argv)
        except SystemExit as exc:
            if int(exc.code or 0) != 0:
                raise
    return json.loads(stdout.getvalue())


class SelectionRefreshRuntimeTests(unittest.TestCase):
    def test_stage_capability_classification_and_development_split(self) -> None:
        self.assertEqual("dev_plan", srr.classify_stage_capability("development_plan"))
        self.assertEqual("dev_execute", srr.classify_stage_capability("development_execute"))
        self.assertEqual("dev_plan", srr.classify_stage_capability("development", permission_mode="plan_only"))
        self.assertEqual("dev_execute", srr.classify_stage_capability("development", permission_mode="ask_before_write"))
        self.assertEqual("media_plan", srr.classify_stage_capability("image_generation_plan"))
        self.assertEqual("media_execute", srr.classify_stage_capability("image_generation"))
        self.assertEqual("voice_execute", srr.classify_stage_capability("voice_capture"))
        self.assertEqual("vision_execute", srr.classify_stage_capability("camera_analysis"))
        self.assertEqual("video_execute", srr.classify_stage_capability("video_render"))
        self.assertEqual("external_io", srr.classify_stage_capability("remote_upload"))
        self.assertEqual("unknown", srr.classify_stage_capability("opaque_stage_xyz"))

    def test_deterministic_local_worker_allowlist_matches_capability_contract(self) -> None:
        allowed = {
            "text_plan",
            "text_review",
            "text_status",
            "text_documentation",
            "audit",
            "handoff",
            "dev_plan",
            "media_plan",
        }
        for capability in srr.STAGE_CAPABILITIES:
            self.assertEqual(capability in allowed, srr.deterministic_local_worker_allowed(capability), capability)

    def test_old_0322_selection_imports_into_current_partial_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "old"
            out = Path(td) / "refreshed"
            selection_fixture(source)

            report = srr.refresh_selection_artifacts(source, out)
            decision = json.loads((out / "model-selection-decision.json").read_text(encoding="utf-8"))

            self.assertEqual("0.32.2", report["source_selection_version"])
            self.assertEqual(RUNTIME_VERSION, report["target_runtime_version"])
            self.assertEqual("partial", report["refresh_mode"])
            self.assertEqual(RUNTIME_VERSION, decision["version"])
            self.assertIn("stale_selection_artifacts", report["diagnostics"])
            self.assertIn("selection_schema_mismatch", report["diagnostics"])

    def test_compatible_role_score_is_reused_and_null_role_recomputed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "old"
            out = Path(td) / "refreshed"
            selection_fixture(source)

            report = srr.refresh_selection_artifacts(source, out)
            role_map = json.loads((out / "refreshed-role-mapping.json").read_text(encoding="utf-8"))

            self.assertIn("dev.work/solution_architect", role_map["roles"])
            self.assertEqual(0.8453, role_map["roles"]["dev.work/solution_architect"]["score"])
            self.assertIn("dev.work/dev", role_map["needs_recompute"])
            self.assertEqual("needs_recompute", report["role_classifications"]["dev.work/dev"]["classification"])
            self.assertIn("role_unstaffed", report["role_classifications"]["dev.work/dev"]["reasons"])

    def test_incompatible_artifact_is_invalidated_and_manifest_mismatch_diagnosed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "old"
            out = Path(td) / "refreshed"
            selection_fixture(source, incompatible=True)

            report = srr.refresh_selection_artifacts(source, out)
            invalidations = json.loads((out / "selection-refresh-invalidations.json").read_text(encoding="utf-8"))

            self.assertEqual("invalidated", report["role_classifications"]["dev.work/qa"]["classification"])
            self.assertIn("model_manifest_realpath_mismatch", report["diagnostics"])
            self.assertIn("gateway_missing", report["diagnostics"])
            self.assertIn("backend_available_gateway_missing", report["diagnostics"])
            self.assertTrue(invalidations["invalidated"])

    def test_partial_refresh_writes_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "old"
            out = Path(td) / "refreshed"
            selection_fixture(source)

            report = srr.refresh_selection_artifacts(source, out)
            provenance = json.loads((out / "selection-refresh-provenance.json").read_text(encoding="utf-8"))

            self.assertTrue(Path(report["artifacts"]["provenance"]).exists())
            self.assertEqual("full_composite", provenance["source_selection_mode"])
            self.assertIn("dev.work/solution_architect", provenance["preserved_measurements"])
            self.assertIn("dev.work/dev", provenance["requires_recompute"])

    def test_worker_resolver_uses_refreshed_role_mapping_with_declared_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "old"
            out = Path(td) / "refreshed"
            selection_fixture(source)
            srr.refresh_selection_artifacts(source, out)
            mapping = json.loads((out / "refreshed-role-mapping.json").read_text(encoding="utf-8"))

            resolved = srr.resolve_stage_worker(mapping, pipeline_id="evolution", stage="development")

            self.assertTrue(resolved["ok"])
            self.assertEqual("dev.work/dev", resolved["requested_role"])
            self.assertEqual("dev.work/solution_architect", resolved["resolved_role"])
            self.assertEqual("explicit", resolved["fallback_policy"])

    def test_pipeline_advance_can_use_refreshed_mapping_but_missing_worker_still_fails(self) -> None:
        old_mapping = os.environ.pop("NOEMAFORGE_REFRESHED_ROLE_MAPPING", None)
        old_dir = os.environ.pop("NOEMAFORGE_SELECTION_REFRESH_DIR", None)
        try:
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td)
                state = tmp / "pipelines"
                call_pipeline(["--root", str(ROOT), "--state", str(state), "run", "evolution", "--request", "worker test", "--run-id", "run_worker", "--allow-degraded"])
                call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_worker", "--next", "--allow-degraded"])
                blocked = call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_worker", "--allow-degraded"])
                self.assertFalse(blocked["ok"])
                self.assertTrue(blocked["blocked_missing_worker"])

                source = tmp / "old"
                out = tmp / "refreshed"
                selection_fixture(source)
                srr.refresh_selection_artifacts(source, out)
                os.environ["NOEMAFORGE_SELECTION_REFRESH_DIR"] = str(out)
                resolved = call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_worker", "--allow-degraded"])
                self.assertTrue(resolved["ok"])
                self.assertTrue(resolved["worker_resolution"]["ok"])
                self.assertEqual("registered_from_refreshed_selection", resolved["worker_resolution"]["worker_status"])
                self.assertTrue(resolved["produced_output"])
                self.assertTrue(resolved["stage_progress_changed"])
                self.assertEqual("executed", resolved["last_worker_execution_state"]["state"])
                self.assertEqual("real", resolved["output_quality"]["quality"])
                self.assertTrue(Path(resolved["output_path"]).exists())
                self.assertNotEqual("architecture_clarification", resolved["stage"])
                text = Path(resolved["output_path"]).read_text(encoding="utf-8")
                self.assertIn("## Decision", text)
                self.assertIn("## Evidence/Input summary", text)
                self.assertIn("## Next handoff", text)
        finally:
            if old_mapping is not None:
                os.environ["NOEMAFORGE_REFRESHED_ROLE_MAPPING"] = old_mapping
            if old_dir is not None:
                os.environ["NOEMAFORGE_SELECTION_REFRESH_DIR"] = old_dir

    def test_public_mwp_status_check_refreshed_worker_produces_output_and_progress(self) -> None:
        old_mapping = os.environ.pop("NOEMAFORGE_REFRESHED_ROLE_MAPPING", None)
        old_dir = os.environ.pop("NOEMAFORGE_SELECTION_REFRESH_DIR", None)
        try:
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td)
                source = tmp / "old"
                out = tmp / "refreshed"
                selection_fixture(source)
                srr.refresh_selection_artifacts(source, out)
                os.environ["NOEMAFORGE_SELECTION_REFRESH_DIR"] = str(out)
                state = tmp / "pipelines"
                call_pipeline(["--root", str(ROOT), "--state", str(state), "run", "public_mwp", "--request", "public status", "--run-id", "run_public", "--allow-degraded"])
                call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_public", "--next", "--allow-degraded"])
                result = call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_public", "--allow-degraded", "--note", "continue status_check"])

                self.assertTrue(result["ok"])
                self.assertEqual("status_check", result["completed_stage"])
                self.assertEqual("safe_runtime", result["stage"])
                self.assertEqual("registered_from_refreshed_selection", result["worker_resolution"]["worker_status"])
                self.assertEqual("operator.admin/administrator", result["worker_resolution"]["resolved_role"])
                self.assertEqual("exact", result["worker_resolution"]["fallback_policy"])
                self.assertEqual("real", result["output_quality"]["quality"])
                self.assertTrue(result["stage_progress_changed"])
                output = Path(result["output_path"]).read_text(encoding="utf-8")
                self.assertIn("# status_check", output)
                self.assertIn("completed_by_deterministic_local_worker", output)
                self.assertNotIn("Status: pending", output)
        finally:
            if old_mapping is not None:
                os.environ["NOEMAFORGE_REFRESHED_ROLE_MAPPING"] = old_mapping
            if old_dir is not None:
                os.environ["NOEMAFORGE_SELECTION_REFRESH_DIR"] = old_dir

    def test_placeholder_output_is_replaced_before_stage_completion(self) -> None:
        old_mapping = os.environ.pop("NOEMAFORGE_REFRESHED_ROLE_MAPPING", None)
        old_dir = os.environ.pop("NOEMAFORGE_SELECTION_REFRESH_DIR", None)
        try:
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td)
                source = tmp / "old"
                out = tmp / "refreshed"
                selection_fixture(source)
                srr.refresh_selection_artifacts(source, out)
                os.environ["NOEMAFORGE_SELECTION_REFRESH_DIR"] = str(out)
                state = tmp / "pipelines"
                call_pipeline(["--root", str(ROOT), "--state", str(state), "run", "public_mwp", "--request", "placeholder replacement", "--run-id", "run_placeholder", "--allow-degraded"])
                call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_placeholder", "--next", "--allow-degraded"])
                output = state / "runs" / "run_placeholder" / "outputs" / "status_check.md"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("# status_check\n\nStatus: pending\n\nDecision:\n\nRisk:\n\nNext handoff:\n", encoding="utf-8")

                result = call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_placeholder", "--allow-degraded"])

                self.assertTrue(result["ok"])
                self.assertEqual("status_check", result["completed_stage"])
                self.assertEqual("real", result["output_quality"]["quality"])
                self.assertFalse(result["output_quality"]["looks_placeholder"])
                self.assertNotIn("Status: pending", output.read_text(encoding="utf-8"))
        finally:
            if old_mapping is not None:
                os.environ["NOEMAFORGE_REFRESHED_ROLE_MAPPING"] = old_mapping
            if old_dir is not None:
                os.environ["NOEMAFORGE_SELECTION_REFRESH_DIR"] = old_dir

    def test_public_mwp_review_completes_with_refreshed_worker_without_loop(self) -> None:
        old_mapping = os.environ.pop("NOEMAFORGE_REFRESHED_ROLE_MAPPING", None)
        old_dir = os.environ.pop("NOEMAFORGE_SELECTION_REFRESH_DIR", None)
        try:
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td)
                source = tmp / "old"
                out = tmp / "refreshed"
                selection_fixture(source)
                srr.refresh_selection_artifacts(source, out)
                os.environ["NOEMAFORGE_SELECTION_REFRESH_DIR"] = str(out)
                state = tmp / "pipelines"
                call_pipeline(["--root", str(ROOT), "--state", str(state), "run", "public_mwp", "--request", "public final", "--run-id", "run_public_final", "--allow-degraded"])
                call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_public_final", "--next", "--allow-degraded"])

                result = {}
                for _ in range(10):
                    result = call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_public_final", "--allow-degraded", "--note", "continue public"])
                    if result.get("status") == "completed":
                        break

                self.assertTrue(result["ok"])
                self.assertEqual("completed", result["status"])
                self.assertEqual("review", result["completed_stage"])
                self.assertEqual("review", result["stage"])
                self.assertTrue(result["produced_output"])
                self.assertEqual("real", result["output_quality"]["quality"])
                self.assertTrue(Path(result["output_path"]).exists())
                run_dir = state / "runs" / "run_public_final"
                placeholder_outputs = [
                    path.name
                    for path in sorted((run_dir / "outputs").glob("*.md"))
                    if prt.stage_output_quality(path)["looks_placeholder"]
                ]
                self.assertEqual([], placeholder_outputs)
                conn = prt.db_connect(state)
                run = prt.get_run(conn, "run_public_final")
                self.assertEqual([], prt.completion_output_issues(run, "review"))
                self.assertNotIn("actionable_blocker", result)
        finally:
            if old_mapping is not None:
                os.environ["NOEMAFORGE_REFRESHED_ROLE_MAPPING"] = old_mapping
            if old_dir is not None:
                os.environ["NOEMAFORGE_SELECTION_REFRESH_DIR"] = old_dir

    def test_completed_transition_is_blocked_when_final_output_stays_placeholder(self) -> None:
        old_mapping = os.environ.pop("NOEMAFORGE_REFRESHED_ROLE_MAPPING", None)
        old_dir = os.environ.pop("NOEMAFORGE_SELECTION_REFRESH_DIR", None)
        try:
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td)
                state = tmp / "pipelines"
                call_pipeline(["--root", str(ROOT), "--state", str(state), "run", "public_mwp", "--request", "placeholder guard", "--run-id", "run_placeholder_guard", "--allow-degraded"])
                conn = prt.db_connect(state)
                run = prt.get_run(conn, "run_placeholder_guard")
                ready, blocker = prt.ensure_completion_outputs_ready(conn, run, "orient")

                self.assertFalse(ready)
                self.assertIsNotNone(blocker)
                self.assertEqual("blocked_placeholder_output", blocker["status"])
                self.assertEqual("placeholder_output_before_completion", blocker["code"])
                self.assertEqual("orient", blocker["stage"])
                self.assertEqual("placeholder", blocker["output_quality"]["quality"])
        finally:
            if old_mapping is not None:
                os.environ["NOEMAFORGE_REFRESHED_ROLE_MAPPING"] = old_mapping
            if old_dir is not None:
                os.environ["NOEMAFORGE_SELECTION_REFRESH_DIR"] = old_dir

    def test_development_plan_produces_real_output_and_execute_requires_backend(self) -> None:
        old_mapping = os.environ.pop("NOEMAFORGE_REFRESHED_ROLE_MAPPING", None)
        old_dir = os.environ.pop("NOEMAFORGE_SELECTION_REFRESH_DIR", None)
        try:
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td)
                source = tmp / "old"
                out = tmp / "refreshed"
                selection_fixture(source)
                srr.refresh_selection_artifacts(source, out)
                os.environ["NOEMAFORGE_SELECTION_REFRESH_DIR"] = str(out)
                state = tmp / "pipelines"
                call_pipeline(["--root", str(ROOT), "--state", str(state), "run", "evolution", "--request", "evolution development", "--run-id", "run_evolution_dev", "--allow-degraded"])
                call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_evolution_dev", "--next", "--allow-degraded"])
                call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_evolution_dev", "--allow-degraded", "--note", "continue architecture"])
                plan = call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_evolution_dev", "--allow-degraded", "--note", "continue development plan"])

                self.assertTrue(plan["ok"])
                self.assertEqual("development_plan", plan["completed_stage"])
                self.assertEqual("development_execute", plan["stage"])
                self.assertTrue(plan["produced_output"])
                self.assertEqual("real", plan["output_quality"]["quality"])
                self.assertEqual("dev_plan", plan["worker_resolution"]["stage_capability"])
                self.assertEqual("dev.work/dev", plan["worker_resolution"]["requested_role"])
                self.assertEqual("dev.work/solution_architect", plan["worker_resolution"]["resolved_role"])
                self.assertNotIn("actionable_blocker", plan)

                execute = call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_evolution_dev", "--allow-degraded", "--note", "continue development execute"])

                self.assertFalse(execute["ok"])
                self.assertEqual("blocked_backend_required", execute["status"])
                self.assertEqual("backend_required_for_dev_execute", execute["actionable_blocker"]["code"])
                self.assertEqual("dev_execute", execute["actionable_blocker"]["stage_capability"])
                self.assertIn("required_backend", execute["actionable_blocker"])
                self.assertTrue(execute["actionable_blocker"]["next_actions"])
                status = call_pipeline(["--root", str(ROOT), "--state", str(state), "show", "run_evolution_dev"])
                self.assertNotEqual("completed", status["status"])
        finally:
            if old_mapping is not None:
                os.environ["NOEMAFORGE_REFRESHED_ROLE_MAPPING"] = old_mapping
            if old_dir is not None:
                os.environ["NOEMAFORGE_SELECTION_REFRESH_DIR"] = old_dir

    def test_allowed_media_plan_and_forbidden_media_execute_semantics(self) -> None:
        self.assertTrue(srr.deterministic_local_worker_allowed(srr.classify_stage_capability("media_backend_plan")))
        self.assertFalse(srr.deterministic_local_worker_allowed(srr.classify_stage_capability("media_backend_execute")))
        self.assertEqual(
            "explicit media generation adapter/backend",
            srr.required_backend_for_capability(srr.classify_stage_capability("media_backend_execute")),
        )

    def test_pipeline_scope_policy_classifies_catalog_shapes(self) -> None:
        self.assertEqual(
            "prod_launchable",
            srr.pipeline_scope_policy({"id": "docs", "stages": ["intake", "review"], "permission_mode": "plan_only"})["scope"],
        )
        degraded = srr.pipeline_scope_policy({"id": "dev", "stages": ["development_plan", "development_execute"], "permission_mode": "ask_before_write"})
        self.assertEqual("degraded_plan_only", degraded["scope"])
        self.assertIn("dev_execute", degraded["backend_required_capabilities"])
        self.assertEqual(
            "adapter_required",
            srr.pipeline_scope_policy({"id": "music", "stages": ["generation_plan"], "permission_mode": "explicit_only"})["scope"],
        )
        self.assertEqual(
            "out_of_prod_scope",
            srr.pipeline_scope_policy({"id": "research", "pipeline_scope": "out_of_prod_scope", "stages": ["collect"]})["scope"],
        )

    def test_adapter_required_prod_blockers_have_explicit_metadata(self) -> None:
        pipeline_ids = [
            "music_generation",
            "voice_generation",
            "photo_generation",
            "video_generation",
            "image_analysis",
            "camera_mask_bridge",
            "image.metadata_and_caption",
            "audio.tts_generate",
            "audio.music_generate",
            "image.photo_generate",
            "video.generate",
            "video_call.masks_virtual_camera",
            "gui.persona_portraits",
            "gui.admin_console_api",
            "admin.route_music_generation",
            "admin.route_model_evolution",
        ]
        for pipeline_id in pipeline_ids:
            policy = srr.pipeline_scope_policy(
                {"id": pipeline_id, "stages": ["prepared"], "permission_mode": "plan_only", "source_catalog": "media-pipeline-catalog"},
                pipeline_id=pipeline_id,
            )
            self.assertEqual("adapter_required", policy["scope"], pipeline_id)
            self.assertTrue(policy["required_adapter"], pipeline_id)
            self.assertTrue(policy["required_capability"], pipeline_id)
            self.assertIn(policy["required_adapter"], policy["required_adapters"], pipeline_id)
            self.assertIn(policy["required_capability"], policy["required_capabilities"], pipeline_id)
            self.assertTrue(policy["next_actions"], pipeline_id)

    def test_degraded_plan_only_creates_final_real_plan_package(self) -> None:
        old_mapping = os.environ.pop("NOEMAFORGE_REFRESHED_ROLE_MAPPING", None)
        old_dir = os.environ.pop("NOEMAFORGE_SELECTION_REFRESH_DIR", None)
        try:
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td)
                source = tmp / "old"
                out = tmp / "refreshed"
                selection_fixture(source)
                srr.refresh_selection_artifacts(source, out)
                os.environ["NOEMAFORGE_SELECTION_REFRESH_DIR"] = str(out)
                state = tmp / "pipelines"
                call_pipeline(["--root", str(ROOT), "--state", str(state), "run", "evolution", "--request", "degraded package", "--run-id", "run_degraded_package", "--allow-degraded"])
                call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_degraded_package", "--next", "--allow-degraded"])
                call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_degraded_package", "--allow-degraded"])
                call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_degraded_package", "--allow-degraded"])
                blocked = call_pipeline(["--root", str(ROOT), "--state", str(state), "advance", "run_degraded_package", "--allow-degraded"])

                self.assertFalse(blocked["ok"])
                self.assertEqual("blocked_backend_required", blocked["status"])
                package = blocked["actionable_blocker"]["degraded_plan_package"]
                package_path = Path(package["path"])
                self.assertTrue(package_path.exists())
                self.assertGreater(package_path.stat().st_size, 80)
                payload = json.loads(package_path.read_text(encoding="utf-8"))
                self.assertEqual("degraded_plan_only", payload["scope"])
                self.assertIn("does not claim that backend execute stages ran", payload["statement"])
                self.assertTrue(payload["stage_outputs"])
        finally:
            if old_mapping is not None:
                os.environ["NOEMAFORGE_REFRESHED_ROLE_MAPPING"] = old_mapping
            if old_dir is not None:
                os.environ["NOEMAFORGE_SELECTION_REFRESH_DIR"] = old_dir

    def test_scope_aware_verifier_counters(self) -> None:
        entries = [
            {"verdict": "COMPLETED_REAL_OUTPUT", "pipeline_scope_policy": {"scope": "prod_launchable"}},
            {"verdict": "COMPLETED_DEGRADED_PLAN_PACKAGE", "pipeline_scope_policy": {"scope": "degraded_plan_only"}},
            {"verdict": "BLOCKED_BACKEND_REQUIRED", "pipeline_scope_policy": {"scope": "prod_launchable"}},
            {"verdict": "ADAPTER_REQUIRED_DEFERRED", "pipeline_scope_policy": {"scope": "adapter_required"}},
            {"verdict": "DEGRADED_PLAN_ONLY_DEFERRED", "pipeline_scope_policy": {"scope": "degraded_plan_only"}},
            {"verdict": "OUT_OF_PROD_SCOPE", "pipeline_scope_policy": {"scope": "out_of_prod_scope"}},
        ]
        degraded = srr.verifier_acceptance_counts([], entries, verify_scope="degraded")
        self.assertEqual(1, degraded["completed_real_count"])
        self.assertEqual(1, degraded["completed_degraded_scope_count"])
        self.assertEqual(2, degraded["blocked_backend_required_count"])
        self.assertEqual(0, degraded["blocked_worker_cannot_execute_count"])
        self.assertEqual(3, degraded["excluded_from_prod_scope_count"])
        self.assertEqual(2, degraded["acceptance_failure_count"])

        prod = srr.verifier_acceptance_counts([], entries, verify_scope="prod")
        self.assertEqual(3, prod["excluded_from_prod_scope_count"])
        self.assertEqual(2, prod["acceptance_failure_count"])

    def test_degraded_scope_requires_real_plan_package_not_deferred(self) -> None:
        entries = [
            {"verdict": "DEGRADED_PLAN_ONLY_DEFERRED", "pipeline_scope_policy": {"scope": "degraded_plan_only"}},
            {"verdict": "OUT_OF_PROD_SCOPE", "pipeline_scope_policy": {"scope": "out_of_prod_scope"}},
            {"verdict": "ADAPTER_REQUIRED_DEFERRED", "pipeline_scope_policy": {"scope": "adapter_required"}},
        ]
        degraded = srr.verifier_acceptance_counts([], entries, verify_scope="degraded")
        self.assertEqual(3, degraded["excluded_from_prod_scope_count"])
        self.assertEqual(1, degraded["fail_actionably_count"])
        self.assertEqual(1, degraded["blocked_backend_required_count"])
        self.assertEqual(1, degraded["acceptance_failure_count"])

        prod = srr.verifier_acceptance_counts([], entries, verify_scope="prod")
        self.assertEqual(3, prod["excluded_from_prod_scope_count"])
        self.assertEqual(1, prod["blocked_backend_required_count"])
        self.assertEqual(0, prod["acceptance_failure_count"])

    def test_completed_placeholder_quality_and_verifier_counter_consistency(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "placeholder.md"
            path.write_text("# done\n\nStatus: pending\n\nDecision:\n\nRisk:\n\nNext handoff:\n", encoding="utf-8")
            quality = prt.stage_output_quality(path)
            self.assertTrue(quality["looks_placeholder"])
            self.assertEqual("placeholder", quality["quality"])

        counts = srr.verifier_acceptance_counts([
            "COMPLETED_REAL_OUTPUT",
            "BLOCKED_WORKER_CANNOT_EXECUTE",
            "BLOCKED_BACKEND_REQUIRED",
            "COMPLETED_WITH_PLACEHOLDER",
            "INCOMPLETE",
            "UNKNOWN",
            "HANG_OR_LOOP",
        ])
        self.assertEqual(1, counts["completed_real_count"])
        self.assertEqual(2, counts["fail_actionably_count"])
        self.assertEqual(1, counts["blocked_backend_required_count"])
        self.assertEqual(1, counts["blocked_worker_cannot_execute_count"])
        self.assertEqual(1, counts["placeholder_count"])
        self.assertEqual(6, counts["acceptance_failure_count"])
        self.assertEqual(0, counts["blocked_missing_worker_count"])

        normal_counts = srr.verifier_acceptance_counts(["COMPLETED_REAL_OUTPUT", "BLOCKED_BACKEND_REQUIRED"])
        self.assertEqual(0, normal_counts["placeholder_count"])
        self.assertEqual(0, normal_counts["blocked_missing_worker_count"])


if __name__ == "__main__":
    unittest.main()
