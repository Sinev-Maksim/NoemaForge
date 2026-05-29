#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_locale_main_chat_surface_runtime.py
Zone: gui/i18n
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate /api/locales messages and localized main chat GUI labels.
Inputs: Locale main chat runtime and policy.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import locale_main_chat_surface_runtime as lmcsr


class LocaleMainChatSurfaceRuntimeTests(unittest.TestCase):
    def test_policy_validates_against_workspace(self) -> None:
        report = lmcsr.validate_locale_main_chat_surface_policy(
            lmcsr.load_json(ROOT / "configs" / "locale-main-chat-surface-policy.json"),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=ROOT / "configs" / "unified-registry.json",
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(10, report["metrics"]["locales"])
        self.assertGreaterEqual(report["metrics"]["required_keys"], 16)

    def test_api_locales_payload_contains_messages_for_main_chat_surface(self) -> None:
        payload = lmcsr.build_offline_locale_server(package_root=ROOT).locales()
        self.assertTrue(payload["ok"])
        self.assertIn("messages", payload)
        self.assertIn("ru", payload["messages"])
        ru = payload["messages"]["ru"]
        self.assertEqual("Основной чат", ru["section.main_chat"])
        self.assertEqual("Отправить", ru["chat.send"])
        self.assertEqual("Скачать", ru["artifact.download"])
        self.assertEqual("Пользователь", ru["role.user"])
        for fragment in ["Ready.", "Download", "Stop loop", "Pipeline Dock", "User"]:
            self.assertNotIn(fragment, "\n".join(str(ru.get(k, "")) for k in ru))


if __name__ == "__main__":
    unittest.main()
