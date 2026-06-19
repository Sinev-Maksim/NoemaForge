"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_d009_d010.py
Zone: tests/gui
Version: 0.33.0
Created: 2026-06-19
Purpose: Verify D-009 (pipeline persona greeting on launch) and D-010
  (repeat-launch guard with Start new / Continue existing / Cancel).
Inputs: Source files under noemaforge/templates/pipeline-dashboard/ and
  noemaforge/src/admin_gui_server.py.
Outputs: Pass/fail assertions.
Tests: py -3 -m unittest noemaforge/tests/test_pipeline_d009_d010.py -v
=== End NoemaForge File Header ===
"""
import re
import sys
import types
import unittest
from pathlib import Path

DASH = Path(__file__).resolve().parents[1] / "templates" / "pipeline-dashboard"
APP_JS = DASH / "app.js"
INDEX_HTML = DASH / "index.html"
SRC = Path(__file__).resolve().parents[1] / "src" / "admin_gui_server.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# D-009: persona greeting
# ---------------------------------------------------------------------------

class TestD009PersonaGreeting(unittest.TestCase):
    """D-009: every pipeline declares a default persona; dialog shows it."""

    def setUp(self):
        self.src = _read(APP_JS)
        self.html = _read(INDEX_HTML)

    def test_launch_history_map_declared(self):
        self.assertIn("_launchHistory", self.src)

    def test_confirm_pipeline_id_declared(self):
        self.assertIn("_confirmPipelineId", self.src)

    def test_persona_element_in_html(self):
        self.assertIn('id="pipeline-confirm-persona"', self.html)

    def test_startpipeline_sets_persona_text(self):
        m = re.search(r'function startPipeline\(id\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m, "startPipeline function not found")
        body = m.group(1)
        self.assertIn("pipeline-confirm-persona", body,
                      "startPipeline must set the persona element")
        self.assertIn("codename", body,
                      "startPipeline must reference persona codename")

    def test_startpipeline_reads_persona_codename(self):
        m = re.search(r'function startPipeline\(id\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("persona_codename", body)

    def test_startpipeline_sets_confirm_id(self):
        m = re.search(r'function startPipeline\(id\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("_confirmPipelineId", body)

    def test_ok_handler_records_launch_time(self):
        ok_idx = self.src.find("pipeline-confirm-ok")
        region = self.src[ok_idx: ok_idx + 400]
        self.assertIn("_launchHistory.set", region,
                      "OK handler must record launch timestamp")
        self.assertIn("Date.now()", region)


class TestD009BackendPersonaField(unittest.TestCase):
    """D-009: pipeline_catalog_api() adds persona and persona_codename fields."""

    def setUp(self):
        self.backend = _read(SRC)

    def test_persona_key_in_pipeline_item(self):
        # The catalog builder must include 'persona' key in each item dict.
        m = re.search(r'items\.append\(\{(.+?)\}\)', self.backend, re.DOTALL)
        self.assertIsNotNone(m, "items.append not found in pipeline_catalog_api")
        body = m.group(1)
        self.assertIn('"persona"', body)

    def test_persona_codename_in_pipeline_item(self):
        m = re.search(r'items\.append\(\{(.+?)\}\)', self.backend, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn('"persona_codename"', body)

    def test_team_persona_map_declared(self):
        self.assertIn("_TEAM_PERSONA_MAP", self.backend)

    def test_pipeline_persona_classmethod(self):
        self.assertIn("_pipeline_persona", self.backend)

    def test_known_team_mapped_to_dedal(self):
        self.assertIn("development_evolution_team", self.backend)
        self.assertIn("Дедал", self.backend)

    def test_known_team_mapped_to_atlas(self):
        self.assertIn("public_onboarding_team", self.backend)
        self.assertIn("Атлас", self.backend)

    def test_sirin_for_book_team(self):
        self.assertIn("book_team", self.backend)
        self.assertIn("Сирин", self.backend)


# ---------------------------------------------------------------------------
# D-010: repeat-launch guard
# ---------------------------------------------------------------------------

class TestD010RepeatLaunchGuard(unittest.TestCase):
    """D-010: launching the same pipeline twice within 60 s shows repeat UI."""

    def setUp(self):
        self.src = _read(APP_JS)
        self.html = _read(INDEX_HTML)

    def test_repeat_window_constant_declared(self):
        self.assertIn("_REPEAT_WINDOW_MS", self.src)

    def test_repeat_window_is_60_seconds(self):
        self.assertIn("60_000", self.src)

    def test_repeat_warning_element_in_html(self):
        self.assertIn('id="pipeline-confirm-repeat"', self.html)

    def test_continue_button_in_html(self):
        self.assertIn('id="pipeline-confirm-continue"', self.html)

    def test_continue_button_starts_hidden(self):
        idx = self.html.index('id="pipeline-confirm-continue"')
        surrounding = self.html[max(0, idx - 10): idx + 100]
        self.assertIn("hidden", surrounding,
                      "continue button must start hidden (shown only on repeat)")

    def test_startpipeline_toggles_repeat_warning(self):
        m = re.search(r'function startPipeline\(id\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("pipeline-confirm-repeat", body)
        self.assertIn("classList.toggle", body)

    def test_startpipeline_toggles_continue_button(self):
        m = re.search(r'function startPipeline\(id\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("pipeline-confirm-continue", body)

    def test_startpipeline_checks_launch_history(self):
        m = re.search(r'function startPipeline\(id\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("_launchHistory.has(id)", body)
        self.assertIn("_REPEAT_WINDOW_MS", body)

    def test_continue_handler_inserts_continue_request(self):
        cont_idx = self.src.find("pipeline-confirm-continue")
        # Find the event listener registration (second occurrence)
        cont_listener_idx = self.src.find("pipeline-confirm-continue", cont_idx + 1)
        self.assertGreater(cont_listener_idx, 0)
        region = self.src[cont_listener_idx: cont_listener_idx + 300]
        self.assertIn("admin-message", region)
        self.assertIn("Продолжи", region)

    def test_continue_handler_no_launch_history_update(self):
        # Continue should NOT record a new start in launch history.
        cont_idx = self.src.find("pipeline-confirm-continue")
        cont_listener_idx = self.src.find("pipeline-confirm-continue", cont_idx + 1)
        region = self.src[cont_listener_idx: cont_listener_idx + 300]
        self.assertNotIn("_launchHistory.set", region,
                         "Continue handler must not mark a new launch start")


if __name__ == "__main__":
    unittest.main()
