#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_persona_rules_renderer.py
Zone: tests/gui
Version: 0.33.0
Created: 2026-07-04
Purpose: Verify Persona Rules readable rendering, visual descriptors and raw
  audit availability for issue #185.
Inputs: persona_rules_renderer.py, admin_gui_server.py and pipeline dashboard JS.
Outputs: unittest assertions only.
Side effects: None.
Tests: python3 -m unittest noemaforge/tests/test_persona_rules_renderer.py -v.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

from admin_gui_server import AdminGuiServer  # noqa: E402
from persona_rules_renderer import render_persona_rules  # noqa: E402


class PersonaRulesRendererTests(unittest.TestCase):
    def test_renderer_translates_rules_to_readable_sections_and_visuals(self) -> None:
        payload = {
            "current_persona": "Admin",
            "role": "operator.admin/administrator",
            "codename": "Atlas",
            "description": "operator/admin coordinator",
            "allowed_actions": ["normal dialogue", "task/job/status review"],
            "output_rules": ["keep GUI answers operator-readable"],
            "model_behavior": {"llm_mode": "switchable", "max_active_llms": 1},
            "render_hints": [
                {"type": "Gauge", "title": "Active LLM limit", "value": 1, "max": 1},
                {"type": "Table", "title": "Routing rules", "rows": [["Pipeline", "explicit click"]]},
            ],
        }

        rendered = render_persona_rules(payload)

        self.assertEqual("noemaforge.persona-rules.rendered/v1", rendered["format"])
        self.assertIn("Persona: Admin", rendered["text"])
        self.assertIn("Allowed actions", rendered["text"])
        self.assertEqual(["Gauge", "Table"], [item["type"] for item in rendered["visuals"]])
        self.assertTrue(rendered["raw_json_available"])

    def test_renderer_ignores_unsupported_hints_gracefully(self) -> None:
        rendered = render_persona_rules({
            "current_persona": "Admin",
            "render_hints": [
                {"type": "Graph", "title": "Flow", "points": [{"x": 1, "y": 2}]},
                {"type": "UnsupportedFancyCanvas", "title": "Do not render"},
            ],
        })

        self.assertEqual(["Graph"], [item["type"] for item in rendered["visuals"]])
        self.assertEqual(["UnsupportedFancyCanvas"], rendered["ignored_render_hints"])


class PersonaRulesPayloadTests(unittest.TestCase):
    def test_admin_gui_persona_rules_payload_contains_rendered_and_raw_views(self) -> None:
        server = object.__new__(AdminGuiServer)
        server.persona_current = lambda: {
            "ok": True,
            "active_persona": "Admin",
            "persona": {
                "role_key": "operator.admin/administrator",
                "codename": "Atlas",
                "description": "operator/admin coordinator",
                "safety": {"max_active_llms": 1},
            },
            "portrait_url": "",
        }

        payload = AdminGuiServer.persona_rules(server)

        self.assertTrue(payload["ok"])
        self.assertIn("rules", payload)
        self.assertIn("rendered_rules", payload)
        self.assertIn("Persona: Admin", payload["rendered_rules"]["text"])
        self.assertTrue(payload["raw_json_available"])
        self.assertEqual("rules", payload["audit"]["raw_rules_field"])
        self.assertIn("StatusCard", [item["type"] for item in payload["visuals"]])


class PersonaRulesDashboardSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app_js = (ROOT / "templates" / "pipeline-dashboard" / "app.js").read_text(encoding="utf-8")
        self.index_html = (ROOT / "templates" / "pipeline-dashboard" / "index.html").read_text(encoding="utf-8")

    def test_dashboard_uses_structured_renderer_not_raw_rules_as_default(self) -> None:
        self.assertIn("function showPersonaRulesModal(", self.app_js)
        self.assertIn("payload.rendered_rules", self.app_js)
        self.assertIn("persona-rules-view", self.app_js)
        self.assertIn("Raw JSON audit", self.app_js)
        self.assertNotIn("showModal('Persona rules', st.rules || st)", self.app_js)

    def test_modal_body_accepts_rendered_nodes_for_persona_rules(self) -> None:
        self.assertIn('id="modal-body" class="modal-body"', self.index_html)
        self.assertIn("replaceWithNodes(el('modal-body'), [root])", self.app_js)


if __name__ == "__main__":
    unittest.main()
