#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_dashboard_api_endpoint_qa.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA coverage for dashboard API endpoint documentation, registry and UI wiring.
Inputs: Canonical docs, Unified Registry, Admin GUI source and dashboard UI source.
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


class DashboardApiEndpointQaTests(unittest.TestCase):
    def test_registry_and_docs_reference_contract(self) -> None:
        registry = json.loads((ROOT / "configs" / "unified-registry.json").read_text(encoding="utf-8"))
        text = json.dumps(registry, sort_keys=True)

        self.assertIn("dashboard-api-endpoint-core", text)
        self.assertIn("configs/dashboard-api-endpoint-policy.json", text)
        self.assertIn("src/dashboard_api_endpoint_runtime.py", text)

        for rel in [
            "noemaforge/docs/README.md",
            "noemaforge/docs/TODO.md",
            "noemaforge/docs/backlog/ROADMAP_AND_TODO.md",
            "noemaforge/docs/reference/PROJECT_CONTEXT.md",
            "noemaforge/docs/history/CHANGELOG.md",
        ]:
            body = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("dashboard-api-endpoint-core", body, rel)

    def test_frontend_prefers_dashboard_endpoint_with_gui_state_fallback(self) -> None:
        app_js = (ROOT / "templates" / "pipeline-dashboard" / "app.js").read_text(encoding="utf-8")
        server = (ROOT / "src" / "admin_gui_server.py").read_text(encoding="utf-8")

        self.assertIn("loadDashboardBackendState", app_js)
        self.assertLess(app_js.find("/api/dashboard"), app_js.find("/api/gui/state"))
        self.assertIn("def dashboard_api", server)
        self.assertIn("/api/dashboard/state", server)
        self.assertIn("dashboard_backend", server)


if __name__ == "__main__":
    unittest.main()
