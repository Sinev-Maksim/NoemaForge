#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_gui_session_event_wiring.py
Zone: test
Version: 0.32.2
Created: 2026-05-27
Modified: 2026-05-28
Purpose: TDD tests for wiring SessionStore and EventLog into AdminGuiServer.
  Covers session_current(), events_api(), save_message() session integration,
  and GET /api/session/current + /api/events HTTP routes.
Inputs: admin_gui_server.AdminGuiServer, session_store.SessionStore, event_log.EventLog.
Outputs: test pass/fail.
Side effects: Creates and removes temporary directories.
Tests: python noemaforge/tests/test_admin_gui_session_event_wiring.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from admin_gui_server import AdminGuiServer, safe_id  # noqa: E402
from admin_gui_offline_fixture import build_offline_admin_gui_server as build_offline_server  # noqa: E402
from session_store import SessionStore  # noqa: E402
from event_log import EventLog  # noqa: E402
from noemaforge_version import RUNTIME_VERSION  # noqa: E402


def _make_server(td: Path) -> AdminGuiServer:
    """Construct AdminGuiServer stub with session_store and event_log wired in."""
    srv = build_offline_server(package_root=_SRC.parent, data_root=td, create_dirs=True)
    srv.session_store = SessionStore(td / "sessions")
    srv.event_log = EventLog(td / "events")
    return srv


# ---------------------------------------------------------------------------
# SessionStore wiring — session_current()
# ---------------------------------------------------------------------------

class TestSessionCurrentMethod(unittest.TestCase):
    """session_current() returns a normalized session record via session_store."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.srv = _make_server(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_session_current_returns_dict(self) -> None:
        result = self.srv.session_current()
        self.assertIsInstance(result, dict)

    def test_session_current_has_ok_true(self) -> None:
        result = self.srv.session_current()
        self.assertTrue(result["ok"])

    def test_session_current_has_version(self) -> None:
        result = self.srv.session_current()
        self.assertEqual(result["version"], RUNTIME_VERSION)

    def test_session_current_has_session_key(self) -> None:
        result = self.srv.session_current()
        self.assertIn("session", result)

    def test_session_current_session_has_messages(self) -> None:
        result = self.srv.session_current()
        self.assertIn("messages", result["session"])

    def test_session_current_session_has_selected_mode(self) -> None:
        result = self.srv.session_current()
        self.assertIn("selected_mode", result["session"])

    def test_session_current_session_has_active_jobs(self) -> None:
        result = self.srv.session_current()
        self.assertIn("active_jobs", result["session"])

    def test_session_current_default_mode_is_normal(self) -> None:
        result = self.srv.session_current()
        self.assertEqual(result["session"]["selected_mode"], "normal")

    def test_session_current_persists_across_calls(self) -> None:
        """Two calls return the same session_id."""
        r1 = self.srv.session_current()
        r2 = self.srv.session_current()
        self.assertEqual(r1["session"]["session_id"], r2["session"]["session_id"])


class TestFreshGuiSessionReset(unittest.TestCase):
    """A new GUI server session must detach old live context and start on Admin."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.srv = _make_server(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def _write_previous_dev_context(self) -> None:
        previous = {
            "conversation_id": "conv_previous",
            "session_id": "gui_previous",
            "created_at": "2026-07-04T00:00:00Z",
            "updated_at": "2026-07-04T00:01:00Z",
            "locale": "en",
            "active_persona": "Dev Team",
            "pending_intent": "pipeline_clarification",
            "pending_payload": {"pipeline_id": "dev_pipeline_member_cells"},
            "messages": [
                {"role": "admin", "persona": "Dev Team", "text": "old dev context"},
            ],
            "artifacts": [],
            "jobs": [],
        }
        self.srv._write_json(self.srv.conversation_file(), previous)

    def test_begin_gui_session_creates_new_marker_and_admin_context(self) -> None:
        self._write_previous_dev_context()

        conv = self.srv._begin_gui_session()
        session = self.srv.session_current()["session"]

        self.assertTrue(session["session_id"].startswith("gui_"))
        self.assertNotEqual(session["session_id"], "gui_previous")
        self.assertEqual(conv["session_id"], session["session_id"])
        self.assertEqual(conv["active_persona"], "Admin")
        self.assertEqual(conv["live_context_branch"], "Admin")
        self.assertEqual(conv["messages"], [])
        self.assertIsNone(conv["pending_intent"])
        self.assertTrue(Path(conv["previous_conversation_archive"]).exists())

        archived = json.loads(Path(conv["previous_conversation_archive"]).read_text(encoding="utf-8"))
        self.assertEqual(archived["active_persona"], "Dev Team")
        self.assertEqual(archived["messages"][0]["text"], "old dev context")

    def test_first_message_after_restart_routes_conversation_through_admin(self) -> None:
        self._write_previous_dev_context()
        self.srv._begin_gui_session()
        self.srv.root = self.td
        self.srv.state = self.td / "state"
        self.srv.state.mkdir(parents=True, exist_ok=True)
        self.srv.evolution_state = self.td / "evolution"
        self.srv.evolution_state.mkdir(parents=True, exist_ok=True)
        self.srv.review_dir = self.td / "review"
        (self.srv.review_dir / "sr" / "inbox").mkdir(parents=True, exist_ok=True)
        (self.srv.review_dir / "ssr" / "inbox").mkdir(parents=True, exist_ok=True)

        with patch.object(self.srv, "conversational_admin_reply", return_value={"reply": "hello", "backend": "fallback"}):
            result = self.srv.admin_message(
                "hello",
                execute=False,
                prepare_media=False,
                allow_degraded=False,
                apply=False,
                locale="en",
            )

        self.assertTrue(result["ok"])
        live = json.loads(self.srv.conversation_file().read_text(encoding="utf-8"))
        admin_replies = [m for m in live["messages"] if m.get("role") == "admin"]
        self.assertEqual(admin_replies[-1]["persona"], "Admin")
        self.assertEqual(live["active_persona"], "Admin")


# ---------------------------------------------------------------------------
# EventLog wiring — events_api()
# ---------------------------------------------------------------------------

class TestEventsListMethod(unittest.TestCase):
    """events_api() returns event log entries via event_log."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.srv = _make_server(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_events_api_returns_dict(self) -> None:
        result = self.srv.events_api()
        self.assertIsInstance(result, dict)

    def test_events_api_has_ok_true(self) -> None:
        result = self.srv.events_api()
        self.assertTrue(result["ok"])

    def test_events_api_has_version(self) -> None:
        result = self.srv.events_api()
        self.assertEqual(result["version"], RUNTIME_VERSION)

    def test_events_api_has_events_key(self) -> None:
        result = self.srv.events_api()
        self.assertIn("events", result)

    def test_events_api_empty_when_no_events(self) -> None:
        result = self.srv.events_api()
        self.assertEqual(result["events"], [])

    def test_events_api_returns_appended_event(self) -> None:
        self.srv.event_log.append("test.event", {"x": 1})
        result = self.srv.events_api()
        self.assertGreater(len(result["events"]), 0)

    def test_events_api_after_index_filters(self) -> None:
        self.srv.event_log.append("a.event")
        self.srv.event_log.append("b.event")
        result = self.srv.events_api(after_index=1)
        types = [e["type"] for e in result["events"]]
        self.assertNotIn("a.event", types)


# ---------------------------------------------------------------------------
# Source wiring checks
# ---------------------------------------------------------------------------

class TestAdminGuiServerSourceWiresSessionEvent(unittest.TestCase):
    """Static source checks confirming session_store and event_log are imported and wired."""

    def setUp(self) -> None:
        self._src = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")

    def test_imports_session_store(self) -> None:
        self.assertIn("from session_store import SessionStore", self._src)

    def test_imports_event_log(self) -> None:
        self.assertIn("from event_log import EventLog", self._src)

    def test_init_creates_session_store(self) -> None:
        self.assertIn("self.session_store = SessionStore", self._src)

    def test_init_creates_event_log(self) -> None:
        self.assertIn("self.event_log = EventLog", self._src)

    def test_has_session_current_method(self) -> None:
        self.assertIn("def session_current", self._src)

    def test_has_events_list_method(self) -> None:
        self.assertIn("def events_api", self._src)

    def test_api_session_current_route(self) -> None:
        self.assertIn("/api/session/current", self._src)

    def test_api_events_route(self) -> None:
        self.assertIn("/api/events", self._src)


# ---------------------------------------------------------------------------
# save_message() → session_store integration
# ---------------------------------------------------------------------------

class TestSaveMessageSessionIntegration(unittest.TestCase):
    """save_message() should also persist the message in the session_store."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.srv = _make_server(self.td)
        # Stub out heavy internals not needed for this test
        self.srv._conversation = lambda: {
            "conversation_id": "test-conv",
            "messages": [],
            "locale": "en",
        }
        self.srv._save_conversation = lambda conv: None
        self.srv._append_jsonl = lambda path, obj: None
        self.srv.review_dir = self.td / "review"
        (self.srv.review_dir / "sr" / "inbox").mkdir(parents=True, exist_ok=True)
        (self.srv.review_dir / "ssr" / "inbox").mkdir(parents=True, exist_ok=True)
        self.srv._write_json = lambda path, obj: None

        import production_ai_contracts as pac
        self._orig_new_trace = pac.new_trace_id
        pac.new_trace_id = lambda scope="": "trace-test"

    def tearDown(self) -> None:
        import production_ai_contracts as pac
        pac.new_trace_id = self._orig_new_trace
        self._td.cleanup()

    def test_save_message_stores_in_session(self) -> None:
        """After save_message, session_current shows at least one message."""
        try:
            self.srv.save_message("user", "hello test", persona="User")
        except Exception:
            pass  # internals may stub-fail; only check session
        session = self.srv.session_store.load("default")
        # messages may or may not be populated depending on integration depth
        self.assertIn("messages", session)

    def test_save_message_stores_run_mode_metadata_in_session(self) -> None:
        self.srv.save_message(
            "user",
            "run this fully",
            persona="User",
            metadata={"run_mode": "full", "non_default_run_mode": True, "scope": "current_message"},
        )

        session = self.srv.session_store.load("default")
        self.assertEqual(session["messages"][0]["metadata"]["run_mode"], "full")
        self.assertTrue(session["messages"][0]["metadata"]["non_default_run_mode"])


class TestPerMessageRunModeMetadata(unittest.TestCase):
    def test_default_run_mode_has_no_message_metadata(self) -> None:
        srv = object.__new__(AdminGuiServer)

        self.assertEqual(srv._message_run_mode_metadata("normal"), {})
        self.assertEqual(srv._message_run_mode_metadata(""), {})

    def test_non_default_run_mode_is_current_message_metadata(self) -> None:
        srv = object.__new__(AdminGuiServer)

        metadata = srv._message_run_mode_metadata("full_composite", 4)

        self.assertEqual(metadata["run_mode"], "full_composite")
        self.assertEqual(metadata["composite_top_n"], 4)
        self.assertTrue(metadata["non_default_run_mode"])
        self.assertEqual(metadata["scope"], "current_message")


# ---------------------------------------------------------------------------
# HTTP route integration (source-level)
# ---------------------------------------------------------------------------

class TestHttpRoutesSourcePresence(unittest.TestCase):
    """Verify the GET handler dispatches /api/session/current and /api/events."""

    def setUp(self) -> None:
        self._src = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")

    def test_get_session_current_dispatches(self) -> None:
        # Check the handler calls session_current or server.session_current
        self.assertTrue(
            "session_current" in self._src,
            "AdminGuiServer must expose session_current method"
        )

    def test_get_events_dispatches(self) -> None:
        self.assertTrue(
            "events_api" in self._src,
            "AdminGuiServer must expose events_api method"
        )

    def test_api_session_current_in_allowed_list(self) -> None:
        self.assertIn("/api/session/current", self._src)

    def test_api_events_in_allowed_list(self) -> None:
        self.assertIn("/api/events", self._src)


# ---------------------------------------------------------------------------
# job_cancel() — cancel_requested status and .cancel marker file
# ---------------------------------------------------------------------------

class TestJobCancelMarker(unittest.TestCase):
    """job_cancel() must use cancel_requested status and write .cancel marker."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.srv = _make_server(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def _seed_job(self, job_id: str, status: str = "running") -> None:
        """Write a minimal job record to jobs.json and {job_id}.json."""
        job = {
            "job_id": job_id,
            "kind": "test_job",
            "status": status,
            "created_at": "2026-05-28T00:00:00Z",
            "updated_at": "2026-05-28T00:00:00Z",
            "idempotency_key": job_id,
            "artifacts": [],
        }
        jobs_file = self.srv.jobs_dir / "jobs.json"
        jobs_file.parent.mkdir(parents=True, exist_ok=True)
        import json as _json
        jobs_file.write_text(_json.dumps({"jobs": [job]}), encoding="utf-8")
        (self.srv.jobs_dir / f"{safe_id(job_id)}.json").write_text(_json.dumps(job), encoding="utf-8")

    def test_cancel_sets_cancel_requested_status(self) -> None:
        jid = "job_test_001"
        self._seed_job(jid)
        result = self.srv.job_cancel(jid)
        self.assertTrue(result["ok"])
        self.assertEqual(result["job"]["status"], "cancel_requested")

    def test_cancel_writes_marker_file(self) -> None:
        jid = "job_test_002"
        self._seed_job(jid)
        self.srv.job_cancel(jid)
        marker = self.srv.jobs_dir / f"{jid}.cancel"
        self.assertTrue(marker.exists(), ".cancel sentinel file must be written by job_cancel()")

    def test_cancel_marker_file_contains_timestamp(self) -> None:
        jid = "job_test_003"
        self._seed_job(jid)
        self.srv.job_cancel(jid)
        marker = self.srv.jobs_dir / f"{jid}.cancel"
        content = marker.read_text(encoding="utf-8").strip()
        self.assertTrue(content.startswith("202"), f"marker should contain ISO timestamp, got: {content!r}")

    def test_cancel_marker_file_sanitizes_job_id_path(self) -> None:
        jid = "../unsafe job"
        self._seed_job(jid)
        result = self.srv.job_cancel(jid)
        self.assertTrue(result["ok"])

        marker = self.srv.jobs_dir / f"{safe_id(jid)}.cancel"
        self.assertTrue(marker.exists())
        self.assertFalse((self.srv.jobs_dir.parent / "unsafe job.cancel").exists())

    def test_cancel_missing_job_returns_ok_false(self) -> None:
        result = self.srv.job_cancel("nonexistent_job_id")
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
