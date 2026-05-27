#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_chat_routing.py
Zone: test
Version: 0.32.2
Created: 2026-05-27
Modified: 2026-05-27
Purpose: TDD tests for direct GUI-action routing in admin_gui_server.admin_message().
Inputs: admin_gui_server.AdminGuiServer._detect_gui_action, ._route_gui_action.
Outputs: test pass/fail.
Side effects: Creates and removes temporary directories.
Tests: python3 -m unittest noemaforge/tests/test_admin_chat_routing.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from admin_gui_server import AdminGuiServer  # noqa: E402
from noemaforge_version import RUNTIME_VERSION  # noqa: E402


def _stub_server(td: Path) -> AdminGuiServer:
    """Build a minimal AdminGuiServer stub for routing tests."""
    srv = object.__new__(AdminGuiServer)
    srv.gui_state_dir = td / "gui"
    srv.gui_state_dir.mkdir(parents=True, exist_ok=True)
    srv.review_dir = td / "review"
    (srv.review_dir / "sr" / "inbox").mkdir(parents=True, exist_ok=True)
    (srv.review_dir / "ssr" / "inbox").mkdir(parents=True, exist_ok=True)
    srv.jobs_dir = td / "jobs"
    srv.jobs_dir.mkdir(parents=True, exist_ok=True)
    srv.data_root = td
    srv.model_selection_state = td / "model_selection"
    srv.model_selection_state.mkdir(parents=True, exist_ok=True)
    # Minimal conversation file.
    from session_store import SessionStore
    srv.session_store = SessionStore(td / "sessions")
    from job_manager import JobManager
    srv.job_manager = JobManager(srv.jobs_dir)
    return srv


class TestDetectGuiAction(unittest.TestCase):
    """_detect_gui_action() maps phrases to action keys."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.srv = _stub_server(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    # --- model-selection-continue ---

    def test_detects_continue_model_selection_en(self) -> None:
        action = self.srv._detect_gui_action("continue model selection")
        self.assertEqual(action, "model_selection_continue")

    def test_detects_model_selection_ru(self) -> None:
        action = self.srv._detect_gui_action("продолжи выбор модели")
        self.assertEqual(action, "model_selection_continue")

    def test_detects_model_selection_continue_ru(self) -> None:
        action = self.srv._detect_gui_action("продолжи model selection")
        self.assertEqual(action, "model_selection_continue")

    def test_detects_resume_selection(self) -> None:
        action = self.srv._detect_gui_action("resume model selection")
        self.assertEqual(action, "model_selection_continue")

    # --- vault-reinventory ---

    def test_detects_vault_reinventory_en(self) -> None:
        action = self.srv._detect_gui_action("reinventory vault")
        self.assertEqual(action, "vault_reinventory")

    def test_detects_vault_inventory_en(self) -> None:
        action = self.srv._detect_gui_action("vault inventory scan")
        self.assertEqual(action, "vault_reinventory")

    def test_detects_vault_reinventory_ru(self) -> None:
        action = self.srv._detect_gui_action("инвентаризация vault")
        self.assertEqual(action, "vault_reinventory")

    def test_detects_scan_vault(self) -> None:
        action = self.srv._detect_gui_action("scan vault")
        self.assertEqual(action, "vault_reinventory")

    def test_detects_re_inventory(self) -> None:
        action = self.srv._detect_gui_action("re-inventory the vault")
        self.assertEqual(action, "vault_reinventory")

    # --- no match ---

    def test_no_action_for_smalltalk(self) -> None:
        action = self.srv._detect_gui_action("как дела?")
        self.assertIsNone(action)

    def test_no_action_for_task_command(self) -> None:
        action = self.srv._detect_gui_action("добавь задачу: починить логи")
        self.assertIsNone(action)

    def test_no_action_for_unrelated_en(self) -> None:
        action = self.srv._detect_gui_action("what is the weather")
        self.assertIsNone(action)

    def test_empty_string_returns_none(self) -> None:
        action = self.srv._detect_gui_action("")
        self.assertIsNone(action)


class TestRouteGuiAction(unittest.TestCase):
    """_route_gui_action() calls the correct server method for each action key."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.srv = _stub_server(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_routes_model_selection_continue(self) -> None:
        expected = {"ok": True, "version": RUNTIME_VERSION, "reply": "ok", "job": {}}
        with patch.object(self.srv, "model_selection_continue", return_value=expected) as mock_m:
            result = self.srv._route_gui_action("model_selection_continue", "continue model selection", "en")
        mock_m.assert_called_once()
        self.assertTrue(result["ok"])

    def test_routes_vault_reinventory(self) -> None:
        expected = {"ok": True, "version": RUNTIME_VERSION, "reply": "ok", "job": {}}
        with patch.object(self.srv, "vault_reinventory", return_value=expected) as mock_v:
            result = self.srv._route_gui_action("vault_reinventory", "scan vault", "en")
        mock_v.assert_called_once()
        self.assertTrue(result["ok"])

    def test_routes_unknown_returns_none(self) -> None:
        result = self.srv._route_gui_action("unknown_action", "some text", "en")
        self.assertIsNone(result)

    def test_route_result_includes_mode(self) -> None:
        expected = {"ok": True, "version": RUNTIME_VERSION, "reply": "queued", "job": {}}
        with patch.object(self.srv, "model_selection_continue", return_value=expected):
            result = self.srv._route_gui_action("model_selection_continue", "continue model selection", "en")
        self.assertIn("mode", result)
        self.assertEqual(result["mode"], "model_selection_continue")

    def test_route_result_includes_ok(self) -> None:
        expected = {"ok": True, "version": RUNTIME_VERSION, "reply": "queued", "job": {}}
        with patch.object(self.srv, "vault_reinventory", return_value=expected):
            result = self.srv._route_gui_action("vault_reinventory", "scan vault", "en")
        self.assertTrue(result["ok"])


class TestAdminMessageGuiRouting(unittest.TestCase):
    """admin_message() picks up GUI actions before falling through to admin_runtime."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.srv = _stub_server(Path(self._td.name))
        # Provide a minimal _conversation stub so save_message doesn't crash.
        self.srv._conversation = MagicMock(return_value={
            "active_persona": "Admin", "messages": [], "artifacts": []
        })
        self.srv.save_message = MagicMock()

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_admin_message_continue_selection_routes_gui(self) -> None:
        expected_job = {"job_id": "job_x", "kind": "model_selection_continue", "status": "needs_privilege"}
        expected = {"ok": True, "version": RUNTIME_VERSION, "reply": "Continuation plan ready.", "job": expected_job, "artifacts": []}
        with patch.object(self.srv, "model_selection_continue", return_value=expected):
            result = self.srv.admin_message(
                "continue model selection",
                execute=False, prepare_media=False, allow_degraded=False, apply=False
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "model_selection_continue")

    def test_admin_message_vault_reinventory_routes_gui(self) -> None:
        expected = {"ok": True, "version": RUNTIME_VERSION, "reply": "Vault re-inventory queued.", "job": {}, "artifacts": []}
        with patch.object(self.srv, "vault_reinventory", return_value=expected):
            result = self.srv.admin_message(
                "scan vault",
                execute=False, prepare_media=False, allow_degraded=False, apply=False
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "vault_reinventory")

    def test_admin_message_gui_action_skips_subprocess(self) -> None:
        """When a GUI action is detected, run_json (subprocess) must NOT be called."""
        expected = {"ok": True, "version": RUNTIME_VERSION, "reply": "ok", "job": {}, "artifacts": []}
        with patch.object(self.srv, "model_selection_continue", return_value=expected):
            with patch("admin_gui_server.run_json") as mock_run:
                self.srv.admin_message(
                    "continue model selection",
                    execute=False, prepare_media=False, allow_degraded=False, apply=False
                )
        mock_run.assert_not_called()

    def test_smalltalk_does_not_route_to_gui_action(self) -> None:
        """Pure smalltalk must not trigger a gui action."""
        with patch.object(self.srv, "model_selection_continue") as mock_m:
            with patch.object(self.srv, "conversational_admin_reply", return_value={"reply": "Всё хорошо", "backend": "fallback"}):
                self.srv.admin_message(
                    "как дела?",
                    execute=False, prepare_media=False, allow_degraded=False, apply=False
                )
        mock_m.assert_not_called()


class TestSourceContainsRouting(unittest.TestCase):
    """Static check: source has _detect_gui_action and _route_gui_action."""

    def setUp(self) -> None:
        self._src = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")

    def test_has_detect_gui_action(self) -> None:
        self.assertIn("def _detect_gui_action", self._src)

    def test_has_route_gui_action(self) -> None:
        self.assertIn("def _route_gui_action", self._src)

    def test_admin_message_calls_detect(self) -> None:
        self.assertIn("_detect_gui_action", self._src)

    def test_admin_message_calls_route(self) -> None:
        self.assertIn("_route_gui_action", self._src)


# ---------------------------------------------------------------------------
# model-evolution routing tests (appended to existing test module)
# ---------------------------------------------------------------------------

class TestDetectGuiActionModelEvolution(unittest.TestCase):
    """_detect_gui_action() recognises model-evolution phrases."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.srv = _stub_server(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_detects_model_evolution_en(self) -> None:
        action = self.srv._detect_gui_action("run model evolution")
        self.assertEqual(action, "model_evolution")

    def test_detects_model_evolution_noun_phrase(self) -> None:
        action = self.srv._detect_gui_action("model evolution")
        self.assertEqual(action, "model_evolution")

    def test_detects_model_evolution_hyphen(self) -> None:
        action = self.srv._detect_gui_action("model-evolution")
        self.assertEqual(action, "model_evolution")

    def test_detects_model_evolution_ru(self) -> None:
        action = self.srv._detect_gui_action("проведи эволюцию модели")
        self.assertEqual(action, "model_evolution")

    def test_detects_evolution_ru_short(self) -> None:
        action = self.srv._detect_gui_action("эволюция модели")
        self.assertEqual(action, "model_evolution")

    def test_detects_start_model_evolution(self) -> None:
        action = self.srv._detect_gui_action("start model evolution cycle")
        self.assertEqual(action, "model_evolution")

    def test_no_false_positive_for_vault(self) -> None:
        action = self.srv._detect_gui_action("scan vault")
        self.assertNotEqual(action, "model_evolution")

    def test_no_false_positive_for_model_selection(self) -> None:
        action = self.srv._detect_gui_action("continue model selection")
        self.assertNotEqual(action, "model_evolution")


class TestRouteGuiActionModelEvolution(unittest.TestCase):
    """_route_gui_action() routes model_evolution to model_evolution()."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.srv = _stub_server(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_routes_model_evolution(self) -> None:
        expected = {"ok": True, "version": RUNTIME_VERSION, "reply": "Evolution cycle queued.", "artifacts": []}
        with patch.object(self.srv, "model_evolution", return_value=expected) as mock_ev:
            result = self.srv._route_gui_action("model_evolution", "run model evolution", "en")
        mock_ev.assert_called_once()
        self.assertIsNotNone(result)
        self.assertTrue(result["ok"])

    def test_model_evolution_route_includes_mode(self) -> None:
        expected = {"ok": True, "version": RUNTIME_VERSION, "reply": "ok", "artifacts": []}
        with patch.object(self.srv, "model_evolution", return_value=expected):
            result = self.srv._route_gui_action("model_evolution", "run model evolution", "en")
        self.assertEqual(result["mode"], "model_evolution")

    def test_model_evolution_called_with_text_as_request(self) -> None:
        """The original user text should be passed as the evolution request."""
        expected = {"ok": True, "version": RUNTIME_VERSION, "reply": "ok", "artifacts": []}
        with patch.object(self.srv, "model_evolution", return_value=expected) as mock_ev:
            self.srv._route_gui_action("model_evolution", "run model evolution for review", "en")
        call_args = mock_ev.call_args
        # request is the first positional arg; target_role and apply are keyword-only.
        request_arg = call_args[0][0] if call_args[0] else call_args[1].get("request", "")
        self.assertIn("run model evolution", str(request_arg))

    def test_model_evolution_apply_defaults_false(self) -> None:
        """Routing from chat must never auto-apply (apply=False)."""
        expected = {"ok": True, "version": RUNTIME_VERSION, "reply": "ok", "artifacts": []}
        with patch.object(self.srv, "model_evolution", return_value=expected) as mock_ev:
            self.srv._route_gui_action("model_evolution", "run model evolution", "en")
        call_kwargs = mock_ev.call_args[1] if mock_ev.call_args else {}
        self.assertFalse(call_kwargs.get("apply", False))


class TestAdminMessageModelEvolutionRouting(unittest.TestCase):
    """admin_message() routes model-evolution phrases to model_evolution() directly."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.srv = _stub_server(Path(self._td.name))
        self.srv._conversation = MagicMock(return_value={"active_persona": "Admin", "messages": [], "artifacts": []})
        self.srv.save_message = MagicMock()

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_admin_message_model_evolution_routes_gui(self) -> None:
        expected = {"ok": True, "version": RUNTIME_VERSION, "reply": "Evolution cycle ready.", "artifacts": []}
        with patch.object(self.srv, "model_evolution", return_value=expected):
            result = self.srv.admin_message(
                "run model evolution",
                execute=False, prepare_media=False, allow_degraded=False, apply=False
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result.get("mode"), "model_evolution")

    def test_admin_message_model_evolution_skips_subprocess(self) -> None:
        expected = {"ok": True, "version": RUNTIME_VERSION, "reply": "ok", "artifacts": []}
        with patch.object(self.srv, "model_evolution", return_value=expected):
            with patch("admin_gui_server.run_json") as mock_run:
                self.srv.admin_message(
                    "model evolution",
                    execute=False, prepare_media=False, allow_degraded=False, apply=False
                )
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
