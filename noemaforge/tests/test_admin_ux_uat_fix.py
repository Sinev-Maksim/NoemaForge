#!/usr/bin/env python3
from __future__ import annotations

import json
import contextlib
import io
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import admin_gui_server as ags  # noqa: E402
import pipeline_runtime  # noqa: E402


APP_JS = ROOT / "templates" / "pipeline-dashboard" / "app.js"
INDEX_HTML = ROOT / "templates" / "pipeline-dashboard" / "index.html"
VERIFY_ALL = ROOT / "tools" / "ops" / "verify-all-pipelines-local.sh"
ADMIN_GUI = ROOT / "src" / "admin_gui_server.py"


def _server(tmp: Path) -> ags.AdminGuiServer:
    srv = object.__new__(ags.AdminGuiServer)
    srv.root = ROOT
    srv.state = tmp / "pipelines"
    srv.data_root = tmp / "data"
    srv.gui_state_dir = srv.data_root / "gui"
    srv.runtime_dir = srv.data_root / "runtime"
    srv.persona_state = tmp / "persona"
    srv.model_selection_state = tmp / "model-selection"
    srv.evolution_state = tmp / "model-evolution"
    srv.dev_team_state = tmp / "dev-team"
    srv.modelstore_dir = tmp / "modelstore"
    srv.bootstrap_dir = tmp / "bootstrap"
    srv.llm_gateway_socket = tmp / "gateway.sock"
    srv.llm_main_backend_socket = tmp / "main.sock"
    srv.legacy_llm_gateway_socket = None
    srv.review_dir = srv.data_root / "review"
    srv._conv_lock = threading.Lock()
    for path in [
        srv.state,
        srv.gui_state_dir,
        srv.runtime_dir,
        srv.persona_state,
        srv.model_selection_state,
        srv.evolution_state,
        srv.dev_team_state,
        srv.modelstore_dir,
        srv.bootstrap_dir,
        srv.review_dir / "sr" / "inbox",
        srv.review_dir / "ssr" / "inbox",
    ]:
        path.mkdir(parents=True, exist_ok=True)
    from session_store import SessionStore
    srv.session_store = SessionStore(srv.gui_state_dir / "sessions")
    return srv


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_ready_main(srv: ags.AdminGuiServer, tmp: Path) -> None:
    main = srv.modelstore_dir / "models" / "main"
    main.mkdir(parents=True)
    artifact = tmp / "selected.gguf"
    artifact.write_bytes(b"model")
    (main / "model.gguf").symlink_to(artifact)
    _write_json(main / "noemaforge-model.json", {"model_id": "qwen-0-5b", "display_name": "Qwen 0.5B", "source": str(artifact)})


def _write_july_firstboot_selection(srv: ags.AdminGuiServer) -> None:
    _write_json(
        srv.bootstrap_dir / "candidate-selection-plan.json",
        {
            "kind": "CandidateSelectionPlan",
            "created_at": "2026-07-03T12:00:00Z",
            "dry_run": False,
        },
    )
    _write_json(
        srv.bootstrap_dir / "model-selection-decision.json",
        {
            "kind": "ModelSelectionDecision",
            "created_at": "2026-07-03T12:00:01Z",
            "ready_to_apply": True,
            "requires_confirmation_before_epoch_switch": True,
        },
    )


class AdminUxRoutingTests(unittest.TestCase):
    def test_continue_dialogue_is_conversation_not_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            srv = _server(Path(td))
            with mock.patch.object(srv, "save_message"), \
                    mock.patch.object(srv, "conversational_admin_reply", return_value={"reply": "Продолжаю диалог.", "backend": "deterministic_fallback"}), \
                    mock.patch.object(srv, "pipeline_run") as pipeline_run:
                result = srv.admin_message("Продолжи диалог", execute=False, prepare_media=False, allow_degraded=False, apply=False)
            self.assertEqual("conversation", result["mode"])
            pipeline_run.assert_not_called()

    def test_continue_dialogue_uses_natural_fallback_even_without_model(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            srv = _server(Path(td))
            with mock.patch.object(srv, "save_message"), mock.patch.object(srv, "pipeline_run") as pipeline_run:
                result = srv.admin_message("Продолжи диалог", execute=False, prepare_media=False, allow_degraded=False, apply=False)
            self.assertEqual("conversation", result["mode"])
            self.assertEqual("deterministic_continue", result["conversation_backend"])
            self.assertIn("Продолжаю диалог", result["reply"])
            self.assertFalse(result["model_selection_required"])
            pipeline_run.assert_not_called()

    def test_capabilities_query_returns_help_even_without_model(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            srv = _server(Path(td))
            with mock.patch.object(srv, "save_message"), mock.patch.object(srv, "pipeline_run") as pipeline_run:
                result = srv.admin_message("Что ты умеешь?", execute=False, prepare_media=False, allow_degraded=False, apply=False)
            self.assertEqual("conversation", result["mode"])
            self.assertEqual("deterministic_capabilities", result["conversation_backend"])
            self.assertIn("Могу вести диалог", result["reply"])
            self.assertFalse(result["model_selection_required"])
            pipeline_run.assert_not_called()

    def test_explicit_book_pipeline_command_routes_to_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            srv = _server(Path(td))
            with mock.patch.object(srv, "save_message"), \
                    mock.patch.object(srv, "pipeline_catalog_api", return_value={"pipelines": [{"id": "book", "stages": ["intake"]}]}), \
                    mock.patch.object(srv, "pipeline_run", return_value={"ok": True, "stdout": {"run_id": "run_book", "pipeline_id": "book", "status": "ready_for_admin_approval", "artifacts": []}}) as pipeline_run:
                result = srv.admin_message("запусти book", execute=False, prepare_media=False, allow_degraded=False, apply=False)
            self.assertEqual("pipeline_run", result["mode"])
            pipeline_run.assert_called_once()

    def test_pending_clarification_captures_next_message_before_pipeline_router(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            srv = _server(Path(td))
            srv._set_pending_clarification("run_1", "book", "Уточните тему книги")
            with mock.patch.object(srv, "save_message"), mock.patch.object(srv, "pipeline_run") as pipeline_run:
                with mock.patch.object(srv, "pipeline_action", return_value={"ok": True}) as pipeline_action:
                    result = srv.admin_message("тема: локальный AI OS", execute=False, prepare_media=False, allow_degraded=False, apply=False)
            self.assertEqual("pipeline_clarification_response", result["mode"])
            pipeline_action.assert_called_once_with("advance", "run_1", {"note": "тема: локальный AI OS", "clarification": "тема: локальный AI OS", "operator_reply": "тема: локальный AI OS"})
            pipeline_run.assert_not_called()
            self.assertFalse(srv.conversation_history()["pending_intent"])

    def test_pending_clarification_failure_is_visible_and_kept_pending(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            srv = _server(Path(td))
            srv._set_pending_clarification("run_1", "book", "Уточните тему книги")
            with mock.patch.object(srv, "save_message"), mock.patch.object(srv, "pipeline_action", return_value={"ok": False, "error": "runtime unavailable"}) as pipeline_action:
                result = srv.admin_message("тема: локальный AI OS", execute=False, prepare_media=False, allow_degraded=False, apply=False)
            self.assertEqual("pipeline_clarification_response", result["mode"])
            self.assertFalse(result["ok"])
            self.assertFalse(result["forwarded"])
            self.assertIn("runtime unavailable", result["reply"])
            pipeline_action.assert_called_once()
            self.assertEqual("pipeline_clarification", srv.conversation_history()["pending_intent"])


class EpochManifestSyncTests(unittest.TestCase):
    def test_same_inode_different_symlink_paths_is_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            artifact = tmp / "models" / "selected.gguf"
            artifact.parent.mkdir()
            artifact.write_bytes(b"model")
            source_link = tmp / "source-link.gguf"
            model_link = tmp / "main" / "model.gguf"
            model_link.parent.mkdir()
            source_link.symlink_to(artifact)
            model_link.symlink_to(artifact)

            result = ags.model_metadata_consistency({"model_id": "selected", "source": str(source_link)}, tmp / "main" / "noemaforge-model.json", model_link)

            self.assertTrue(result["ok"])
            self.assertEqual("consistent", result["state"])

    def test_different_artifacts_fail_consistency(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            artifact_a = tmp / "a.gguf"
            artifact_b = tmp / "b.gguf"
            artifact_a.write_bytes(b"a")
            artifact_b.write_bytes(b"b")
            model_link = tmp / "model.gguf"
            model_link.symlink_to(artifact_b)

            result = ags.model_metadata_consistency({"model_id": "selected", "source": str(artifact_a)}, tmp / "noemaforge-model.json", model_link)

            self.assertFalse(result["ok"])
            self.assertIn("source_realpath_mismatch", result["mismatches"])

    def test_missing_manifest_source_fails_consistency(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            artifact = tmp / "model.gguf"
            artifact.write_bytes(b"model")

            result = ags.model_metadata_consistency({"model_id": "selected"}, tmp / "noemaforge-model.json", artifact)

            self.assertFalse(result["ok"])
            self.assertIn("source_missing", result["mismatches"])

    def test_already_applied_epoch_has_no_apply_available(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            srv = _server(tmp)
            _write_ready_main(srv, tmp)
            _write_json(srv.bootstrap_dir / "firstboot-status.json", {"state": "applied_no_reboot", "applied_epoch_id": "00006"})
            _write_json(srv.bootstrap_dir / "candidate-selection-plan.json", {"kind": "CandidateSelectionPlan", "dry_run": False, "proposed_epoch_id": "00006"})
            _write_json(srv.bootstrap_dir / "model-selection-decision.json", {"kind": "ModelSelectionDecision", "ready_to_apply": True, "epoch_id": "00006"})

            status = srv.epoch_status()

            self.assertFalse(status["apply_available"])
            self.assertEqual("selection_epoch_already_applied", status["apply_actionability"]["reason"])

    def test_newer_unapplied_epoch_has_apply_available(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            srv = _server(tmp)
            _write_ready_main(srv, tmp)
            _write_json(srv.bootstrap_dir / "firstboot-status.json", {"state": "applied_no_reboot", "applied_epoch_id": "00006"})
            run = srv.model_selection_state / "runs" / "msel_20260713T120000Z_normal"
            _write_json(run / "candidate-selection-plan.json", {"kind": "CandidateSelectionPlan", "dry_run": False, "proposed_epoch_id": "00007"})
            _write_json(run / "model-selection-decision.json", {"kind": "ModelSelectionDecision", "ready_to_apply": True, "epoch_id": "00007"})

            status = srv.epoch_status()

            self.assertTrue(status["apply_available"])
            self.assertEqual("newer_unapplied_selection", status["apply_actionability"]["reason"])

    def test_non_numeric_epoch_id_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            srv = _server(tmp)
            _write_ready_main(srv, tmp)
            _write_json(srv.bootstrap_dir / "firstboot-status.json", {"state": "applied_no_reboot", "applied_epoch_id": "00006"})
            run = srv.model_selection_state / "runs" / "msel_20260713T120000Z_normal"
            _write_json(run / "candidate-selection-plan.json", {"kind": "CandidateSelectionPlan", "dry_run": False, "proposed_epoch_id": "epoch-7"})
            _write_json(run / "model-selection-decision.json", {"kind": "ModelSelectionDecision", "ready_to_apply": True, "epoch_id": "epoch-7"})

            status = srv.epoch_status()

            self.assertFalse(status["apply_available"])
            self.assertEqual("selection_epoch_not_newer", status["apply_actionability"]["reason"])

    def test_july_firstboot_ready_without_epoch_is_actionable_before_apply(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            srv = _server(tmp)
            _write_ready_main(srv, tmp)
            _write_json(srv.bootstrap_dir / "firstboot-status.json", {"state": "selection_ready_no_apply"})
            _write_july_firstboot_selection(srv)

            status = srv.epoch_status()

            self.assertTrue(status["apply_available"])
            self.assertEqual("ready_selection_without_epoch_id", status["apply_actionability"]["reason"])
            self.assertEqual("firstboot", status["apply_actionability"]["source"])

    def test_july_firstboot_ready_without_epoch_is_not_actionable_after_apply(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            srv = _server(tmp)
            _write_ready_main(srv, tmp)
            _write_json(srv.bootstrap_dir / "firstboot-status.json", {"state": "applied_no_reboot", "applied_epoch_id": "00006"})
            _write_july_firstboot_selection(srv)

            status = srv.epoch_status()

            self.assertFalse(status["apply_available"])
            self.assertEqual("selection_without_epoch_already_applied", status["apply_actionability"]["reason"])

    def test_current_contract_epoch_blocks_equal_selection_when_status_lacks_applied_epoch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            srv = _server(tmp)
            _write_ready_main(srv, tmp)
            epochs = srv.data_root / "contracts" / "epochs"
            (epochs / "00006").mkdir(parents=True)
            (epochs / "current_epoch.txt").write_text("00006\n", encoding="utf-8")
            _write_json(srv.bootstrap_dir / "firstboot-status.json", {"state": "applied_no_reboot"})
            run = srv.model_selection_state / "runs" / "msel_20260713T120000Z_normal"
            _write_json(run / "candidate-selection-plan.json", {"kind": "CandidateSelectionPlan", "dry_run": False, "proposed_epoch_id": "00006"})
            _write_json(run / "model-selection-decision.json", {"kind": "ModelSelectionDecision", "ready_to_apply": True, "epoch_id": "00006"})

            status = srv.epoch_status()

            self.assertFalse(status["apply_available"])
            self.assertEqual("selection_epoch_already_applied", status["apply_actionability"]["reason"])
            self.assertEqual("00006", status["current_epoch"]["contract_current_epoch_id"])

    def test_epoch_apply_refuses_when_authoritative_selection_is_not_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            srv = _server(tmp)
            _write_ready_main(srv, tmp)
            _write_json(srv.bootstrap_dir / "firstboot-status.json", {"state": "applied_no_reboot", "applied_epoch_id": "00006"})
            _write_json(srv.bootstrap_dir / "candidate-selection-plan.json", {"kind": "CandidateSelectionPlan", "dry_run": False, "proposed_epoch_id": "00006"})
            _write_json(srv.bootstrap_dir / "model-selection-decision.json", {"kind": "ModelSelectionDecision", "ready_to_apply": True, "epoch_id": "00006"})

            with mock.patch.object(srv, "create_job") as create_job, mock.patch.object(srv, "save_message"):
                result = srv.epoch_apply({})

            self.assertFalse(result["ok"])
            self.assertEqual("selection_epoch_already_applied", result["reason"])
            create_job.assert_not_called()

    def test_old_may_candidate_selection_requested_does_not_resurrect_applied_firstboot(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            srv = _server(tmp)
            _write_ready_main(srv, tmp)
            _write_json(srv.bootstrap_dir / "firstboot-status.json", {"state": "applied_no_reboot", "applied_epoch_id": "00006"})
            _write_july_firstboot_selection(srv)
            run = srv.model_selection_state / "runs" / "msel_20260501T090000Z_normal"
            _write_json(run / "candidate-selection-plan.json", {"kind": "CandidateSelectionPlan", "created_at": "2026-05-01T09:00:00Z", "dry_run": False})
            _write_json(run / "model-selection-decision.json", {"kind": "ChatModelSelectionDecision", "created_at": "2026-05-01T09:00:01Z", "status": "candidate_selection_requested"})

            status = srv.epoch_status()

            self.assertFalse(status["apply_available"])
            self.assertEqual("firstboot", status["apply_actionability"]["source"])

    def test_newer_not_ready_selection_blocks_fallback_to_older_firstboot(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            srv = _server(tmp)
            _write_ready_main(srv, tmp)
            _write_json(srv.bootstrap_dir / "firstboot-status.json", {"state": "selection_ready_no_apply"})
            _write_july_firstboot_selection(srv)
            run = srv.model_selection_state / "runs" / "msel_20260713T120000Z_normal"
            _write_json(run / "candidate-selection-plan.json", {"kind": "CandidateSelectionPlan", "created_at": "2026-07-13T12:00:00Z", "dry_run": False})
            _write_json(run / "model-selection-decision.json", {"kind": "ChatModelSelectionDecision", "created_at": "2026-07-13T12:00:01Z", "status": "rejected", "ready_to_apply": False})

            status = srv.epoch_status()

            self.assertFalse(status["apply_available"])
            self.assertEqual("selection_not_ready_to_apply", status["apply_actionability"]["reason"])
            self.assertEqual("latest_model_selection", status["apply_actionability"]["source"])
            self.assertFalse(status["firstboot"]["authoritative"])

    def test_newer_explicit_ready_selection_is_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            srv = _server(tmp)
            _write_ready_main(srv, tmp)
            _write_json(srv.bootstrap_dir / "firstboot-status.json", {"state": "applied_no_reboot", "applied_epoch_id": "00006"})
            _write_july_firstboot_selection(srv)
            run = srv.model_selection_state / "runs" / "msel_20260713T120000Z_normal"
            _write_json(run / "candidate-selection-plan.json", {"kind": "CandidateSelectionPlan", "created_at": "2026-07-13T12:00:00Z", "dry_run": False, "proposed_epoch_id": "00007"})
            _write_json(run / "model-selection-decision.json", {"kind": "ChatModelSelectionDecision", "created_at": "2026-07-13T12:00:01Z", "status": "apply_command_ready", "epoch_id": "00007"})

            status = srv.epoch_status()

            self.assertTrue(status["apply_available"])
            self.assertEqual("newer_unapplied_selection", status["apply_actionability"]["reason"])
            self.assertEqual("latest_model_selection", status["apply_actionability"]["source"])


class PipelineStatusAndArtifactTests(unittest.TestCase):
    def _pipeline_cli(self, argv: list[str]) -> dict:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = pipeline_runtime.main(argv)
        self.assertEqual(0, rc)
        return json.loads(buf.getvalue())

    def test_real_pipeline_runtime_run_placeholder_stage_returns_handoff_and_reply_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            state = tmp / "pipelines"
            run = self._pipeline_cli([
                "--root", str(ROOT),
                "--state", str(state),
                "run", "evolution",
                "--request", "UAT stage handoff",
                "--run-id", "run_stage_handoff_v2",
                "--allow-degraded",
            ])
            self.assertEqual("run_stage_handoff_v2", run["run_id"])
            srv = _server(tmp)
            srv.state = state

            visible = srv.pipeline_run_status("run_stage_handoff_v2")
            self.assertTrue(visible["ok"])
            self.assertEqual("intake", visible["current_stage"])

            self._pipeline_cli([
                "--root", str(ROOT),
                "--state", str(state),
                "advance", "run_stage_handoff_v2",
                "--next",
                "--allow-degraded",
            ])
            status = srv.pipeline_run_status("run_stage_handoff_v2")

            self.assertTrue(status["ok"])
            self.assertEqual("current_state", status["current_stage"])
            self.assertTrue(status["clarification_required"])
            self.assertEqual("stage_handoff_required", status["waiting_reason"])
            self.assertTrue(status["questions"])
            handoff = status["stage_handoff"]
            self.assertEqual("run_stage_handoff_v2", handoff["run_id"])

            reply = srv.pipeline_stage_reply("run_stage_handoff_v2", {
                "stage": "current_state",
                "message": "Operator decision: keep local-first handoff explicit.",
                "action": "reply",
            })

            self.assertTrue(reply["ok"])
            decisions = Path(reply["decisions_path"]).read_text(encoding="utf-8")
            jsonl = Path(reply["stage_input_path"]).read_text(encoding="utf-8")
            self.assertIn("Operator decision: keep local-first handoff explicit.", decisions)
            self.assertIn("Operator decision: keep local-first handoff explicit.", jsonl)

    def test_pipeline_catalog_discovery_includes_known_pipelines(self) -> None:
        catalog = pipeline_runtime.load_pipeline_catalog(ROOT)
        for pipeline_id in ["public_mwp", "evolution", "book", "knowledge_graph", "release_prep", "persona_evolution", "image.metadata_and_caption"]:
            self.assertIn(pipeline_id, catalog)

    def test_dotted_media_pipeline_id_is_launchable_and_status_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            state = tmp / "pipelines"
            created = self._pipeline_cli([
                "--root", str(ROOT),
                "--state", str(state),
                "run", "image.metadata_and_caption",
                "--request", "dotted id smoke",
                "--allow-degraded",
            ])
            srv = _server(tmp)
            srv.state = state
            status = srv.pipeline_run_status(created["run_id"])
        self.assertEqual("image.metadata_and_caption", status["pipeline_id"])
        self.assertEqual(created["run_id"], status["run_id"])
        self.assertIn("image.metadata_and_caption", created["run_id"])
        self.assertEqual("mvp", status["current_stage"])

    def test_placeholder_output_quality_detection(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "placeholder.md"
            path.write_text("# intake\n\nStatus: pending\n\nDecision:\n\nRisk:\n\nNext handoff:\n", encoding="utf-8")
            quality = pipeline_runtime.stage_output_quality(path)
        self.assertTrue(quality["looks_placeholder"])
        self.assertTrue(quality["pending"])

    def test_reply_changes_operator_reply_state_and_handoff_version(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            state = tmp / "pipelines"
            self._pipeline_cli([
                "--root", str(ROOT),
                "--state", str(state),
                "run", "evolution",
                "--request", "reply state test",
                "--run-id", "run_reply_state",
                "--allow-degraded",
            ])
            self._pipeline_cli(["--root", str(ROOT), "--state", str(state), "advance", "run_reply_state", "--next", "--allow-degraded"])
            srv = _server(tmp)
            srv.state = state
            before = srv.pipeline_run_status("run_reply_state")
            self.assertEqual("current_state", before["current_stage"])
            before_version = before["stage_handoff"]["handoff_version"]
            reply = srv.pipeline_stage_reply("run_reply_state", {"stage": "current_state", "message": "operator decision", "action": "reply"})
            after = srv.pipeline_run_status("run_reply_state")
        self.assertEqual("operator_reply_recorded", reply["operator_reply_state"]["state"])
        self.assertEqual("operator_reply_recorded", after["operator_reply_state"]["state"])
        self.assertNotEqual(before_version, after["stage_handoff"]["handoff_version"])

    def test_degraded_handoff_reply_state_is_visible_and_traceable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            state = tmp / "pipelines"
            self._pipeline_cli([
                "--root", str(ROOT),
                "--state", str(state),
                "run", "evolution",
                "--request", "degraded handoff state",
                "--run-id", "run_degraded_handoff_reply",
                "--allow-degraded",
            ])
            self._pipeline_cli([
                "--root", str(ROOT),
                "--state", str(state),
                "advance", "run_degraded_handoff_reply",
                "--next",
                "--allow-degraded",
            ])
            srv = _server(tmp)
            srv.state = state
            (srv.bootstrap_dir / "firstboot-staffing-summary.json").write_text(json.dumps({
                "staffing_state": "degraded_selected",
                "warnings": ["below threshold"],
            }), encoding="utf-8")

            before = srv.pipeline_run_status("run_degraded_handoff_reply")
            self.assertEqual("degraded_readonly", before["handoff_reply_mode"])
            self.assertEqual("record_operator_reply", before["handoff_next_action"])
            self.assertIn("continuing still requires explicit degraded approval", before["handoff_reply_limitation"])

            reply = srv.pipeline_stage_reply("run_degraded_handoff_reply", {
                "stage": "current_state",
                "message": "chat input reply: continue with explicit degraded approval",
                "action": "reply",
                "source": "chat_input",
            })
            after = srv.pipeline_run_status("run_degraded_handoff_reply")
            jsonl = Path(reply["stage_input_path"]).read_text(encoding="utf-8")
            decisions = Path(reply["decisions_path"]).read_text(encoding="utf-8")

        self.assertTrue(reply["ok"])
        self.assertEqual("operator_reply_recorded", after["operator_reply_state"]["state"])
        self.assertEqual("degraded_readonly", after["handoff_reply_mode"])
        self.assertEqual("continue_after_reply", after["handoff_next_action"])
        self.assertIn('"source": "chat_input"', jsonl)
        self.assertIn("chat input reply: continue with explicit degraded approval", jsonl)
        self.assertIn("- Source: `chat_input`", decisions)

    def test_continue_without_worker_returns_actionable_blocker_not_fake_success(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            state = tmp / "pipelines"
            self._pipeline_cli(["--root", str(ROOT), "--state", str(state), "run", "evolution", "--request", "blocker test", "--run-id", "run_blocker", "--allow-degraded"])
            self._pipeline_cli(["--root", str(ROOT), "--state", str(state), "advance", "run_blocker", "--next", "--allow-degraded"])
            result = self._pipeline_cli(["--root", str(ROOT), "--state", str(state), "advance", "run_blocker", "--allow-degraded", "--note", "continue without worker"])
        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked_missing_worker"])
        self.assertEqual("blocked_missing_worker", result["actionable_blocker"]["state"])

    def test_skip_stage_records_explicit_skip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            state = tmp / "pipelines"
            self._pipeline_cli(["--root", str(ROOT), "--state", str(state), "run", "book", "--request", "skip test", "--run-id", "run_skip", "--allow-degraded"])
            result = self._pipeline_cli(["--root", str(ROOT), "--state", str(state), "advance", "run_skip", "--skip", "--allow-degraded", "--note", "operator skip"])
            skip_path = Path(result["skip_record"]["path"])
            self.assertTrue(result["skipped_by_operator"])
            self.assertTrue(skip_path.exists())
            self.assertEqual("skipped_by_operator", json.loads(skip_path.read_text(encoding="utf-8"))["state"])

    def test_admin_env_passes_selection_refresh_mapping_to_pipeline_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            srv = _server(tmp)
            refresh_dir = tmp / "selection-refresh"
            mapping_path = refresh_dir / "refreshed-role-mapping.json"
            with mock.patch.dict(
                "os.environ",
                {
                    "NOEMAFORGE_SELECTION_REFRESH_DIR": str(refresh_dir),
                    "NOEMAFORGE_REFRESHED_ROLE_MAPPING": str(mapping_path),
                },
            ):
                env = srv.env()
        self.assertEqual(str(refresh_dir), env["NOEMAFORGE_SELECTION_REFRESH_DIR"])
        self.assertEqual(str(mapping_path), env["NOEMAFORGE_REFRESHED_ROLE_MAPPING"])

    def test_all_pipeline_verifier_source_covers_catalog_and_completed_placeholder_failure(self) -> None:
        src = VERIFY_ALL.read_text(encoding="utf-8")
        self.assertIn("/api/pipelines/catalog", src)
        self.assertIn("known = {\"public_mwp\", \"evolution\", \"book\", \"knowledge_graph\", \"release_prep\", \"persona_evolution\"}", src)
        self.assertIn("create_response", src)
        self.assertIn("completed pipeline has placeholder outputs", src)
        self.assertIn("2 * int(stage_counts.get(pipeline_id)", src)
        self.assertIn("NOEMAFORGE_SELECTION_REFRESH_DIR", src)
        self.assertIn("noemaforge-selection-refresh-preserve", src)

    def test_all_pipeline_verifier_uses_strict_acceptance_semantics(self) -> None:
        src = VERIFY_ALL.read_text(encoding="utf-8")
        self.assertIn('"triage_ok": False', src)
        self.assertIn('"acceptance_ok": False', src)
        self.assertIn('report["ok"] = report["acceptance_ok"]', src)
        self.assertIn('report["blocking_pipelines"] = []', src)
        self.assertIn('"hang_or_loop_count": 0', src)
        self.assertIn('"completed_degraded_scope_count": 0', src)
        self.assertIn('"blocked_backend_required_count": 0', src)
        self.assertIn('"excluded_from_prod_scope_count": 0', src)
        self.assertIn('elif verdict == "COMPLETED_DEGRADED_PLAN_PACKAGE":', src)
        self.assertIn('elif verdict == "DEGRADED_PLAN_ONLY_DEFERRED":', src)
        self.assertIn('elif verdict == "OUT_OF_PROD_SCOPE":', src)
        self.assertIn('degraded-plan-only pipeline did not produce a real final_degraded_plan_package.json artifact', src)
        self.assertIn('"verdict": "DEGRADED_PLAN_ONLY_DEFERRED"', src)
        self.assertIn('elif verdict in {"FAIL_ACTIONABLY", "BLOCKED_WORKER_CANNOT_EXECUTE", "BLOCKED_BACKEND_REQUIRED"}:', src)
        self.assertIn('elif verdict == "BLOCKED_MISSING_WORKER":', src)
        self.assertIn('"BLOCKED_WORKER_CANNOT_EXECUTE"', src)
        self.assertIn('elif verdict == "INCOMPLETE":', src)
        self.assertIn('elif verdict == "HANG_OR_LOOP":', src)
        self.assertIn('counts["hang_or_loop_count"] += 1', src)
        self.assertIn('elif verdict in {"COMPLETED_WITH_PLACEHOLDER", "PLACEHOLDER_OUTPUT"}:', src)
        self.assertIn('"blocking_pipelines": []', src)
        self.assertIn('"remediation_backlog": []', src)
        self.assertIn('"acceptance_failure_count"', src)
        self.assertIn('report["acceptance_failure_count"] = (', src)
        self.assertIn('counts["fail_actionably_count"]', src)
        self.assertIn('+ counts["placeholder_count"]', src)
        self.assertIn('+ counts["blocked_missing_worker_count"]', src)
        self.assertIn('report.get("verify_scope") != "degraded"', src)
        self.assertIn('report["triage_ok"] = not report.get("failures") and counts["unknown_count"] == 0', src)
        self.assertIn('entry["verdict"] = "HANG_OR_LOOP"', src)
        self.assertIn('mark_hang_or_loop(report, entry, "max iteration count exceeded", status)', src)
        self.assertIn('"status_history"', src)
        self.assertIn('"worker_resolution"', src)
        self.assertIn('"output_quality"', src)
        self.assertNotIn('mark_hang_or_loop(report, entry, "max iteration count exceeded", status)\\n        fail(', src)

    def test_all_pipeline_verifier_unwraps_runtime_stdout_payload(self) -> None:
        src = VERIFY_ALL.read_text(encoding="utf-8")
        self.assertIn("def unwrap_runtime_payload(response):", src)
        self.assertIn('isinstance(response.get("stdout"), dict)', src)
        self.assertIn('return response["stdout"], wrapper_metadata', src)
        self.assertIn("payload, wrapper_metadata = unwrap_runtime_payload(status)", src)
        self.assertIn('payload.get("actionable_blocker")', src)
        self.assertIn('payload.get("worker_resolution")', src)
        self.assertIn('payload.get("output_quality") or payload.get("stage_output_quality") or {}', src)
        self.assertIn('payload.get("stage_progress_changed")', src)
        self.assertIn('payload.get("last_worker_execution_state")', src)
        self.assertIn('payload.get("produced_output")', src)

    def test_all_pipeline_verifier_nested_stdout_actionable_blocker_stops_loop(self) -> None:
        src = VERIFY_ALL.read_text(encoding="utf-8")
        continue_idx = src.index("continued_payload, continued_wrapper_metadata = unwrap_runtime_payload(continued)")
        blocker_idx = src.index('if continued_payload.get("actionable_blocker"):', continue_idx)
        verdict_idx = src.index('entry["verdict"] = classify_actionable(continued_payload)', blocker_idx)
        break_idx = src.index("break", verdict_idx)
        hang_idx = src.index('mark_hang_or_loop(report, entry, "continue after reply did not progress', continue_idx)
        self.assertLess(break_idx, hang_idx)
        self.assertIn('entry["actionable_blocker"] = continued_payload.get("actionable_blocker")', src)
        self.assertIn('continued_snapshot = status_snapshot(continued)', src)

    def test_all_pipeline_verifier_nested_blocker_is_triaged_acceptance_failure(self) -> None:
        src = VERIFY_ALL.read_text(encoding="utf-8")
        self.assertIn('if code == "adapter_required_for_pipeline":', src)
        self.assertIn('def adapter_policy_requires_backend(policy):', src)
        self.assertIn('def policy_only_verdict(policy, scope):', src)
        self.assertIn('DETERMINISTIC_LOCAL_STAGE_CAPABILITIES = {', src)
        self.assertIn('pipeline_scope == "adapter_required" and adapter_policy_requires_backend(policy or {})', src)
        self.assertIn('"verdict": "ADAPTER_REQUIRED_DEFERRED"', src)
        self.assertIn('required_adapter = str((policy or {}).get("required_adapter")', src)
        self.assertIn('required_capability = str((policy or {}).get("required_capability")', src)
        self.assertIn('"stage_capabilities": (policy or {}).get("stage_capabilities") or []', src)
        self.assertIn('"backend_required_capabilities": (policy or {}).get("backend_required_capabilities") or []', src)
        self.assertIn('"required_adapter": required_adapter', src)
        self.assertIn('"required_capability": required_capability', src)
        self.assertNotIn('str(policy.get("scope") or "") == "adapter_required":\n        entry["verdict"] = "BLOCKED_WORKER_CANNOT_EXECUTE"', src)
        self.assertIn('if code == "blocked_worker_cannot_execute":', src)
        self.assertIn('return "BLOCKED_WORKER_CANNOT_EXECUTE"', src)
        self.assertIn('return "BLOCKED_BACKEND_REQUIRED"', src)
        self.assertIn('elif verdict == "ADAPTER_REQUIRED_DEFERRED":', src)
        self.assertIn('elif verdict in {"FAIL_ACTIONABLY", "BLOCKED_WORKER_CANNOT_EXECUTE", "BLOCKED_BACKEND_REQUIRED"}:', src)
        self.assertIn('counts["blocked_backend_required_count"] += 1', src)
        self.assertIn('report["acceptance_ok"] = report["acceptance_failure_count"] == 0 and not report.get("failures")', src)
        self.assertIn('report["triage_ok"] = not report.get("failures") and counts["unknown_count"] == 0', src)
        self.assertIn('raise SystemExit(2)', src)

    def test_all_pipeline_verifier_backend_blocker_remediation_is_precise(self) -> None:
        src = VERIFY_ALL.read_text(encoding="utf-8")
        self.assertIn('def append_remediation(report, entry, action):', src)
        self.assertIn('backend required: configure {required_adapter} and grant {required_capability}', src)
        self.assertIn('adapter_required: configure {required_adapter} and grant {required_capability}', src)
        branch_idx = src.index('if verdict == "BLOCKED_BACKEND_REQUIRED":')
        precise_idx = src.index('append_acceptance_failure(report, entry, "")', branch_idx)
        generic_idx = src.index('append_acceptance_failure(report, entry, "pipeline failed actionably; triage is mapped but prod acceptance failed")', branch_idx)
        self.assertLess(precise_idx, generic_idx)

    def test_all_pipeline_verifier_hang_or_loop_requires_no_actionable_blocker(self) -> None:
        src = VERIFY_ALL.read_text(encoding="utf-8")
        actionable_idx = src.index('actionable = bool(continued_payload.get("actionable_blocker") or status2.get("actionable_blocker"))')
        hang_guard_idx = src.index("if not (progressed or changed_version or became_real or explicit_skip or actionable):", actionable_idx)
        hang_mark_idx = src.index('mark_hang_or_loop(report, entry, "continue after reply did not progress', hang_guard_idx)
        self.assertLess(actionable_idx, hang_guard_idx)
        self.assertLess(hang_guard_idx, hang_mark_idx)

    def test_all_pipeline_verifier_counters_separate_loop_and_actionable_failures(self) -> None:
        src = VERIFY_ALL.read_text(encoding="utf-8")
        fail_count_idx = src.index('elif verdict in {"FAIL_ACTIONABLY", "BLOCKED_WORKER_CANNOT_EXECUTE", "BLOCKED_BACKEND_REQUIRED"}:')
        hang_count_idx = src.index('elif verdict == "HANG_OR_LOOP":')
        self.assertIn('counts["fail_actionably_count"] += 1', src[fail_count_idx:hang_count_idx])
        self.assertIn('counts["blocked_backend_required_count"] += 1', src[fail_count_idx:hang_count_idx])
        self.assertIn('counts["hang_or_loop_count"] += 1', src[hang_count_idx:])
        self.assertIn('if verdict == "COMPLETED_REAL_OUTPUT":', src)
        self.assertIn('counts["completed_real_count"] += 1', src)
        self.assertIn('counts["fail_actionably_count"]', src)
        self.assertIn('+ counts["placeholder_count"]', src)
        self.assertIn('+ counts["blocked_missing_worker_count"]', src)

    def test_all_pipeline_verifier_exit_2_is_triaged_acceptance_failure(self) -> None:
        src = VERIFY_ALL.read_text(encoding="utf-8")
        self.assertIn('if report["acceptance_ok"]:', src)
        self.assertIn('if report["triage_ok"]:', src)
        self.assertIn('raise SystemExit(2)', src)
        self.assertIn('if [[ "$audit_rc" -eq 2 ]]; then', src)
        self.assertIn('exit 2', src)
        self.assertNotIn('PASS_WAITING', src)
        self.assertNotIn('PASS_COMPLETED', src)

    def test_pipeline_run_status_uses_stdout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            srv = _server(tmp)
            run_dir = tmp / "pipelines" / "runs" / "run_1"
            (run_dir / "outputs").mkdir(parents=True)
            (run_dir / "outputs" / "final.md").write_text("final\n", encoding="utf-8")
            manifest = {"pipeline_id": "book", "current_stage": "drafting", "pipeline": {"stages": ["intake", "drafting", "review"]}}
            (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            payload = {"ok": True, "stdout": {"ok": True, "run_id": "run_1", "pipeline_id": "book", "status": "in_progress", "current_stage": "drafting", "run_dir": str(run_dir), "manifest": manifest, "events": []}}
            with mock.patch.object(ags, "run_json", return_value=payload):
                status = srv.pipeline_run_status("run_1")
            self.assertTrue(status["ok"])
            self.assertEqual("in_progress", status["status"])
            self.assertEqual("drafting", status["current_stage"])
            self.assertEqual(["intake", "drafting", "review"], status["stages"])
            self.assertEqual("active", {s["stage"]: s["state"] for s in status["stage_states"]}["drafting"])
            self.assertEqual("outputs/final.md", status["artifacts"][0]["label"])

    def test_pipeline_run_status_sets_pending_clarification_when_needs_clarification(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            srv = _server(Path(td))
            payload = {
                "ok": True,
                "stdout": {
                    "ok": True,
                    "run_id": "run_2",
                    "pipeline_id": "book",
                    "status": "needs_clarification",
                    "question": "Какую тему раскрыть?",
                    "manifest": {"pipeline": {"stages": ["intake", "drafting"]}},
                    "events": [],
                    "artifacts": [],
                },
            }
            with mock.patch.object(ags, "run_json", return_value=payload):
                status = srv.pipeline_run_status("run_2")
            self.assertTrue(status["clarification_required"])
            self.assertEqual(["Какую тему раскрыть?"], status["questions"])
            history = srv.conversation_history()
            self.assertEqual("pipeline_clarification", history["pending_intent"])
            self.assertEqual("run_2", history["pending_payload"]["run_id"])
            self.assertEqual("book", history["pending_payload"]["pipeline_id"])
            self.assertTrue(any("Какую тему раскрыть?" in msg["text"] for msg in history["messages"]))

    def test_pipeline_run_status_missing_run_includes_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            srv = _server(Path(td))
            status = srv.pipeline_run_status("missing_run")
            self.assertFalse(status["ok"])
            self.assertEqual("missing_run", status["diagnostics"]["run_id"])
            self.assertIn("state_root", status["diagnostics"])
            self.assertTrue(status["diagnostics"]["searched_paths"])
            self.assertIn("registry", status["diagnostics"]["registry_hint"])

    def test_promote_final_artifacts_before_context_and_run_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run = Path(td) / "run_book"
            for rel, text in {
                "manifest.json": json.dumps({"pipeline_id": "book"}),
                "outputs/book.md": "book\n",
                "context_packets/context.md": "ctx\n",
            }.items():
                path = run / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            cards = ags.promote_run_artifacts(str(run))
            self.assertEqual("outputs/book.md", cards[0]["label"])
            self.assertTrue(cards[0]["primary"])
            self.assertNotEqual("run_dir", cards[0]["label"])

    def test_media_final_artifact_is_primary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run = Path(td) / "run_video"
            (run / "outputs").mkdir(parents=True)
            (run / "manifest.json").write_text(json.dumps({"pipeline_id": "video"}), encoding="utf-8")
            (run / "outputs" / "clip.mp4").write_bytes(b"mp4")
            cards = ags.promote_run_artifacts(str(run))
            self.assertEqual("outputs/clip.mp4", cards[0]["label"])
            self.assertTrue(cards[0]["primary"])


class PersonaAndPolicyTests(unittest.TestCase):
    def test_persona_rules_payload_contains_required_sections(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            srv = _server(Path(td))
            rules = srv.persona_rules()["rules"]
            self.assertIn("current_persona", rules)
            self.assertIn("role", rules)
            self.assertIn("allowed_actions", rules)
            self.assertIn("output_rules", rules)
            self.assertIn("command_routing_rules", rules)
            self.assertIn("model_behavior", rules)

    def test_runtime_device_policy_is_readable_object(self) -> None:
        with tempfile.TemporaryDirectory() as td, mock.patch.object(ags, "run_json", return_value={"ok": False, "stdout": "inactive", "returncode": 3}):
            srv = _server(Path(td))
            policy = srv.runtime_status()["device_policy"]
            self.assertIsInstance(policy, dict)
            self.assertEqual("cpu", policy["policy"])
            card = [c for c in srv.runtime_status()["observer_cards"] if c["id"] == "device-policy"][0]
            self.assertIn("source=", card["state"])
            self.assertIn("pending=", card["state"])

    def test_runtime_degraded_status_exposes_readonly_staffing_summary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            srv = _server(Path(td))
            (srv.bootstrap_dir / "firstboot-staffing-summary.json").write_text(json.dumps({
                "staffing_state": "degraded_selected",
                "warnings": ["below threshold"],
                "degraded_roles": ["writer"],
                "unstaffed_roles": ["critic"],
                "thresholds": {"quality": 0.7},
                "selected_model_ids": ["local-main"],
            }), encoding="utf-8")
            (srv.bootstrap_dir / "firstboot-status.json").write_text(json.dumps({
                "checks": ["staffing_degraded"],
                "next_actions": ["continue model selection"],
            }), encoding="utf-8")

            status = srv.runtime_degraded_status()

            self.assertTrue(status["degraded_readonly"]["active"])
            self.assertEqual("degraded_selected", status["degraded_readonly"]["state"])
            self.assertEqual("degraded_selected", status["staffing"]["staffing_state"])
            self.assertEqual(["local-main"], status["staffing"]["selected_model_ids"])
            self.assertEqual(["staffing_degraded"], status["checks"])

    def test_pipeline_action_allow_degraded_appends_flag(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            srv = _server(Path(td))
            with mock.patch.object(ags, "run_json", return_value={"ok": True}) as run_json:
                result = srv.pipeline_action("advance", "run_1", {"next": True, "allow_degraded": True, "note": "approved"})

            self.assertTrue(result["ok"])
            cmd = run_json.call_args.args[0]
            self.assertIn("--allow-degraded", cmd)


class FrontendSourceGuards(unittest.TestCase):
    def test_pipeline_card_runs_api_directly(self) -> None:
        src = APP_JS.read_text(encoding="utf-8")
        self.assertIn("async function runPipelineDirect", src)
        self.assertIn("api('/api/pipeline/run'", src)
        self.assertIn("btn.addEventListener('click', ()=>startPipeline(p.id))", src)

    def test_confirm_ok_no_longer_prefills_chat(self) -> None:
        src = APP_JS.read_text(encoding="utf-8")
        start = src.index("el('pipeline-confirm-ok').addEventListener")
        end = src.index("const pipelineConfirmContinue", start)
        body = src[start:end]
        self.assertIn("runPipelineDirect(id, req)", body)
        self.assertNotIn("el('admin-message').value = req", body)

    def test_persona_rules_ui_is_wired(self) -> None:
        src = APP_JS.read_text(encoding="utf-8")
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn('id="persona-rules"', html)
        self.assertIn("/api/persona/rules", src)
        self.assertIn("showPersonaRules", src)

    def test_telemetry_blocks_are_readable_not_raw_json(self) -> None:
        src = APP_JS.read_text(encoding="utf-8")
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn('id="software-metrics"', html)
        self.assertIn("function _fmtSoftware", src)
        self.assertIn("Git branch:", src)
        self.assertIn("'not available'", src)
        self.assertIn("function _fmtRuntimeState", src)
        self.assertIn("'Device policy'", src)
        self.assertIn("'Sockets'", src)
        self.assertIn("'Active model'", src)
        self.assertIn("pending_apply", src)
        self.assertIn("applies_on", src)
        self.assertIn("updated_at", src)
        self.assertIn("manifest_exists", src)
        self.assertIn("manifest_path", src)
        self.assertIn("model_realpath", src)
        self.assertIn("metadata_consistency", src)
        self.assertIn("selection_required", src)
        self.assertIn("/run/noemaforge/llm/backends/main.sock", src)
        self.assertNotIn("runtime-fingerprint", html)
        self.assertNotIn("JSON.stringify({device_policy:", src)

    def test_header_version_comes_from_health(self) -> None:
        src = APP_JS.read_text(encoding="utf-8")
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertNotIn("NoemaForge / 0.32.2", html)
        self.assertIn("version mismatch", src)
        self.assertIn("health.version", src)

    def test_per_message_run_mode_source_guards(self) -> None:
        src = APP_JS.read_text(encoding="utf-8")
        html = INDEX_HTML.read_text(encoding="utf-8")
        routes = (ROOT / "src" / "admin_gui_routes" / "session_routes.py").read_text(encoding="utf-8")

        self.assertIn('id="message-run-mode"', html)
        self.assertIn("Next message run mode", html)
        self.assertIn("function messageRunModePayload", src)
        self.assertIn("if(mode === 'normal') return {};", src)
        self.assertIn("...runModePayload", src)
        self.assertIn("_resetMessageRunMode()", src)
        self.assertIn("message_metadata", (ROOT / "src" / "admin_gui_server.py").read_text(encoding="utf-8"))
        self.assertIn("run_mode=str(body.get(\"run_mode\") or \"\")", routes)

    def test_product_metrics_gets_wider_grid_track(self) -> None:
        css = (ROOT / "templates" / "pipeline-dashboard" / "style.css").read_text(encoding="utf-8")
        self.assertIn("minmax(340px,1.6fr)", css)
        self.assertIn(".product-card", css)
        self.assertIn("max-height:min(44vh,520px)", css)

    def test_degraded_product_metrics_extract_available_values_and_missing_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            srv = _server(Path(td))
            staff = {
                "staffing_state": "degraded_selected",
                "selected_model_ids": ["dev-model", "admin-model"],
                "selected_model_count": 2,
                "total_roles": 4,
                "selected_roles": 3,
                "target_met_roles": 2,
                "degraded_roles": ["writing.story/writer"],
                "unstaffed_roles": ["music.compose/arranger"],
                "missing_mandatory_core_roles": [],
                "warnings": ["Some selected roles are below minimal thresholds."],
            }
            decision = {
                "mode": "full_composite",
                "composite_top_n": 4,
                "chosen_by_role": {
                    "dev.work/solution_architect": {
                        "model_id": "dev-model",
                        "score": 0.72,
                        "pass_rate": 0.8,
                        "json_parse_rate": 0.9,
                        "quality_score": 0.7,
                        "avg_latency_ms": 1500,
                    },
                    "writing.story/writer": {
                        "model_id": "admin-model",
                        "score": 0.54,
                        "pass_rate": 0.6,
                        "json_parse_rate": 0.7,
                        "quality_score": 0.65,
                        "avg_latency_ms": 2500,
                    },
                },
            }
            result = srv._model_selection_product_metrics(staff, decision)

        self.assertEqual("degraded_selected", result["staffing_state"])
        self.assertIn("Mandatory core roles are staffed", result["status_explanation"])
        self.assertIn("explicit degraded approval", result["next_action"])
        self.assertEqual(0.7, result["metrics"]["pass_rate"]["value"])
        self.assertEqual(0.8, result["metrics"]["json_parse_rate"]["value"])
        self.assertEqual(0.675, result["metrics"]["quality_score"]["value"])
        self.assertEqual(2.0, result["metrics"]["avg_latency_s"]["value"])
        self.assertEqual("3/4", result["metrics"]["role_coverage"]["value"])
        self.assertIn("firstboot-staffing-summary.json", result["metrics"]["degraded_roles"]["source"])
        self.assertEqual([], result["metrics"]["missing_mandatory_core_roles"]["value"])
        self.assertNotIn("reason", result["metrics"]["missing_mandatory_core_roles"])
        self.assertIsNone(result["metrics"]["failed_tasks"]["value"])
        self.assertIn("no failed_tasks field", result["metrics"]["failed_tasks"]["reason"])

    def test_product_metrics_card_explains_degraded_sources_and_missing_reasons(self) -> None:
        src = APP_JS.read_text(encoding="utf-8")
        self.assertIn("function _metricCellRow", src)
        self.assertIn("degraded_selected", src)
        self.assertIn("Mandatory core roles are staffed", src)
        self.assertIn("Next action:", src)
        self.assertIn("missing:", src)
        self.assertIn("source artifact", src)
        self.assertIn("Degraded roles:", src)
        self.assertIn("Missing mandatory:", src)

    def test_degraded_decision_panel_source_guards(self) -> None:
        src = APP_JS.read_text(encoding="utf-8")
        self.assertIn("Continue in degraded mode", src)
        self.assertIn("/api/pipeline/advance", src)
        self.assertIn("allow_degraded:true", src)
        self.assertIn("ready_for_admin_approval", src)
        self.assertIn("/api/pipeline/run/${encodeURIComponent(runId)}/status", src)
        self.assertIn("Work toward normal mode", src)
        self.assertIn("normal-mode recovery", src)
        self.assertIn("Show degraded details", src)
        self.assertIn("/api/runtime/degraded", src)
        self.assertIn("degraded_readonly", src)
        self.assertIn("staffing_state", src)
        self.assertIn("selected_model_ids", src)

    def test_degraded_panel_does_not_show_raw_json_by_default(self) -> None:
        src = APP_JS.read_text(encoding="utf-8")
        start = src.index("function _renderDegradedSummary")
        end = src.index("async function _continuePipelineDegraded", start)
        main_panel = src[start:end]
        self.assertNotIn("JSON.stringify", main_panel)
        self.assertIn("showModal('Degraded details'", src)

    def test_stage_handoff_frontend_source_guards(self) -> None:
        src = APP_JS.read_text(encoding="utf-8")
        self.assertIn("stage_handoff", src)
        self.assertIn("postedStageHandoffKeys", src)
        self.assertIn("activeStageHandoff", src)
        self.assertIn("_sendActiveStageHandoffReply", src)
        self.assertIn("source: 'chat_input'", src)
        self.assertIn("pipeline_stage_handoff_response", src)
        self.assertIn("Reply / Provide decision", src)
        self.assertIn("Continue after reply", src)
        self.assertIn("Skip stage explicitly", src)
        self.assertIn("/api/pipeline/run/${encodeURIComponent(runId)}/reply", src)
        self.assertIn("allow_degraded:true", src)
        self.assertIn("stage_progress", src)
        self.assertIn("operator_reply_state", src)
        self.assertIn("handoff_reply_mode", src)
        self.assertIn("handoff_reply_limitation", src)
        self.assertIn("handoff_next_action", src)
        self.assertIn("actionable_blocker", src)

    def test_pipeline_status_exposes_worker_progress_contract(self) -> None:
        src = ADMIN_GUI.read_text(encoding="utf-8")
        self.assertIn("last_worker_execution_state", src)
        self.assertIn("stable_status_hash", src)
        self.assertIn("stage_progress_changed", src)
        self.assertIn("output_path", src)
        self.assertIn("output_quality", src)


if __name__ == "__main__":
    unittest.main()
