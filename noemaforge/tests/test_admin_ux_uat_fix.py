#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import admin_gui_server as ags  # noqa: E402


APP_JS = ROOT / "templates" / "pipeline-dashboard" / "app.js"
INDEX_HTML = ROOT / "templates" / "pipeline-dashboard" / "index.html"


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


class PipelineStatusAndArtifactTests(unittest.TestCase):
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
            self.assertIn("gpu=", card["state"])


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
        self.assertNotIn("runtime-fingerprint", html)
        self.assertNotIn("JSON.stringify({device_policy:", src)

    def test_header_version_comes_from_health(self) -> None:
        src = APP_JS.read_text(encoding="utf-8")
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertNotIn("NoemaForge / 0.32.2", html)
        self.assertIn("version mismatch", src)
        self.assertIn("health.version", src)

    def test_product_metrics_gets_wider_grid_track(self) -> None:
        css = (ROOT / "templates" / "pipeline-dashboard" / "style.css").read_text(encoding="utf-8")
        self.assertIn("minmax(340px,1.6fr)", css)
        self.assertIn(".product-card", css)


if __name__ == "__main__":
    unittest.main()
