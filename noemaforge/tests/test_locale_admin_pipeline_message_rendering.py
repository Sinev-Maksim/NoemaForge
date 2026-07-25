#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import admin_gui_server as ags  # noqa: E402
from i18n_runtime import localized_message  # noqa: E402
from session_store import SessionStore  # noqa: E402


def _server(tmp: Path, locale: str) -> ags.AdminGuiServer:
    srv = object.__new__(ags.AdminGuiServer)
    srv.root = ROOT
    srv.state = tmp / "pipelines"
    srv.data_root = tmp / "data"
    srv.gui_state_dir = srv.data_root / "gui"
    srv.review_dir = srv.data_root / "review"
    srv._conv_lock = threading.Lock()
    for path in [
        srv.state,
        srv.gui_state_dir,
        srv.review_dir / "sr" / "inbox",
        srv.review_dir / "ssr" / "inbox",
    ]:
        path.mkdir(parents=True, exist_ok=True)
    srv.session_store = SessionStore(srv.gui_state_dir / "sessions")
    conv = srv._conversation()
    conv["locale"] = locale
    srv._save_conversation(conv)
    return srv


class LocaleAdminPipelineMessageRenderingTests(unittest.TestCase):
    def test_english_admin_message_remains_source_text(self) -> None:
        msg = localized_message(
            ROOT,
            "admin.reply.smalltalk",
            "I am here. NoemaForge is running locally: I can chat, open Dev Team, prepare model evolution, or show epoch status.",
            locale="en",
            role="admin",
            style="admin_note",
        )

        self.assertEqual("en", msg["source_locale"])
        self.assertEqual("en", msg["target_locale"])
        self.assertEqual(msg["original_text"], msg["rendered_text"])
        self.assertFalse(msg["localized"])

    def test_non_english_admin_messages_render_in_active_locale(self) -> None:
        cases = {
            "es": "Estoy aquí",
            "de": "Ich bin da",
        }
        for locale, expected in cases.items():
            with self.subTest(locale=locale):
                msg = localized_message(
                    ROOT,
                    "admin.reply.smalltalk",
                    "I am here. NoemaForge is running locally: I can chat, open Dev Team, prepare model evolution, or show epoch status.",
                    locale=locale,
                    role="admin",
                    style="admin_note",
                )

                self.assertEqual("en", msg["source_locale"])
                self.assertEqual(locale, msg["target_locale"])
                self.assertEqual("admin", msg["role"])
                self.assertEqual("admin_note", msg["style"])
                self.assertIn(expected, msg["rendered_text"])
                self.assertIn("I am here", msg["original_text"])
                self.assertNotEqual(msg["original_text"], msg["rendered_text"])

    def test_stage_handoff_payload_has_distinct_styles_and_audit_original(self) -> None:
        cases = {
            "es": "Handoff",
            "de": "Handoff",
        }
        for locale, expected in cases.items():
            with self.subTest(locale=locale):
                with tempfile.TemporaryDirectory() as td:
                    tmp = Path(td)
                    srv = _server(tmp, locale)
                    run_dir = tmp / "run"
                    output_dir = run_dir / "outputs"
                    output_dir.mkdir(parents=True)
                    (output_dir / "current_state.md").write_text("Status: pending\n", encoding="utf-8")

                    handoff = srv._stage_handoff_from_status(
                        {"run_dir": str(run_dir), "pipeline_id": "evolution"},
                        "run_locale",
                        "current_state",
                        "active",
                    )

                self.assertIsNotNone(handoff)
                assert handoff is not None
                self.assertIn(expected, handoff["message"])
                self.assertEqual("en", handoff["message_metadata"]["source_locale"])
                self.assertEqual(locale, handoff["message_metadata"]["target_locale"])
                self.assertEqual("pipeline", handoff["message_metadata"]["role"])
                self.assertEqual("system_payload", handoff["message_metadata"]["style"])
                self.assertIn("handoff required", handoff["original_text"])
                styles = {part["style"] for part in handoff["message_parts"]}
                roles = {part["role"] for part in handoff["message_parts"]}
                self.assertIn("system_payload", styles)
                self.assertIn("admin_note", styles)
                self.assertIn("pipeline", roles)
                self.assertIn("admin", roles)
                self.assertTrue(handoff["questions"])
                self.assertEqual(locale, handoff["question_parts"][0]["target_locale"])

    def test_frontend_declares_distinct_rendering_classes(self) -> None:
        app = (ROOT / "templates" / "pipeline-dashboard" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "templates" / "pipeline-dashboard" / "style.css").read_text(encoding="utf-8")

        self.assertIn("message_parts", app)
        self.assertIn("message-original", app)
        self.assertIn("system_payload", css)
        self.assertIn("admin_note", css)


if __name__ == "__main__":
    unittest.main()
