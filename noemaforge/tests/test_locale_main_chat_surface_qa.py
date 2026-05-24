#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_locale_main_chat_surface_qa.py
Zone: gui/i18n
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA coverage for localized main chat docs, registry and frontend wiring.
Inputs: Canonical docs, Unified Registry, dashboard UI source and locale files.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path


ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent


class LocaleMainChatSurfaceQaTests(unittest.TestCase):
    def test_docs_and_registry_reference_contract(self) -> None:
        registry = json.loads((ROOT / "configs" / "unified-registry.json").read_text(encoding="utf-8"))
        text = json.dumps(registry, sort_keys=True)
        self.assertIn("locale-main-chat-surface-core", text)
        self.assertIn("configs/locale-main-chat-surface-policy.json", text)
        self.assertIn("src/locale_main_chat_surface_runtime.py", text)

        for rel in [
            "noemaforge/docs/README.md",
            "noemaforge/docs/TODO.md",
            "noemaforge/docs/backlog/ROADMAP_AND_TODO.md",
            "noemaforge/docs/reference/PROJECT_CONTEXT.md",
            "noemaforge/docs/history/CHANGELOG.md",
        ]:
            body = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("locale-main-chat-surface-core", body, rel)

    def test_frontend_applies_locale_messages_to_main_chat_controls(self) -> None:
        app_js = (ROOT / "templates" / "pipeline-dashboard" / "app.js").read_text(encoding="utf-8")
        index_html = (ROOT / "templates" / "pipeline-dashboard" / "index.html").read_text(encoding="utf-8")

        for token in ["applyLocaleMessages", "speakerLabel", "role.user", "depth-steps-label", "pipeline-dock-title", "artifact.download"]:
            self.assertIn(token, app_js + index_html)
        main_chat = index_html.split('<section class="chat', 1)[1].split("</section>", 1)[0]
        for fragment in ["Steps", "Minutes", "until stop", "Stop loop", "Pipeline Dock", "Search pipeline"]:
            self.assertNotIn(fragment, main_chat)


if __name__ == "__main__":
    unittest.main()
