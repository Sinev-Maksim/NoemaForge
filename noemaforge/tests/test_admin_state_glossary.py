#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_state_glossary.py
Zone: tests
Version: 0.33.0
Created: 2026-06-13
Modified: 2026-06-13
Purpose: Unit tests for maybe_state_glossary() — the deterministic pre-LLM handler
         that answers known dashboard-state term queries (D-003 fix).
Inputs: admin_runtime.maybe_state_glossary, admin_runtime.has_explicit_control_request.
Outputs: pytest/unittest pass/fail.
Side effects: None.
Tests: python3 -m pytest noemaforge/tests/test_admin_state_glossary.py -q
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _install_stubs() -> None:
    """Install minimal stubs so admin_runtime imports cleanly without a full runtime."""
    import noemaforge_version as real_version
    sys.modules.setdefault("noemaforge_version", real_version)

    stub_prod = types.ModuleType("production_ai_contracts")
    stub_prod.decide_abstention = lambda doc, policy: {"abstain": False, "reason": "stub"}
    stub_prod.new_trace_id = lambda prefix="admin": f"{prefix}_stub_trace_id"
    sys.modules.setdefault("production_ai_contracts", stub_prod)

    stub_platform = types.ModuleType("platform_paths")
    stub_paths = types.SimpleNamespace(
        root=Path("/tmp/noemaforge_stub"),
        data_root=Path("/tmp/noemaforge_stub/data"),
        pipelines_dir=Path("/tmp/noemaforge_stub/pipelines"),
        model_evolution_state_dir=Path("/tmp/noemaforge_stub/model_evo"),
        model_selection_state_dir=Path("/tmp/noemaforge_stub/model_sel"),
    )
    stub_platform.DEFAULT_PATHS = stub_paths
    sys.modules.setdefault("platform_paths", stub_platform)

    stub_i18n = types.ModuleType("i18n_runtime")
    stub_i18n.normalize_locale = lambda value=None: str(value or os.environ.get("NOEMAFORGE_LANG") or "en").split(".", 1)[0]
    stub_i18n.tr = lambda root, key, default="", locale=None, **kwargs: (default or key)
    sys.modules.setdefault("i18n_runtime", stub_i18n)


_install_stubs()

import admin_runtime  # noqa: E402


class TestMaybeStateGlossaryRuPath(unittest.TestCase):
    """RU locale: defect D-003 scenario — query about degraded_selected and selected=N."""

    def test_degraded_selected_and_selected_n_ru(self) -> None:
        """'что значит degraded_selected · selected=1' must return RU explanations, no .txt, no file reference."""
        result = admin_runtime.maybe_state_glossary(
            "что значит degraded_selected · selected=1", "ru"
        )
        self.assertIsNotNone(result, "Expected a glossary dict, got None")
        reply = result["reply"]
        # Must explain threshold/warning nature in Russian
        self.assertTrue(
            "threshold" in reply.lower() or "порог" in reply.lower(),
            f"Expected threshold/порог mention, got: {reply!r}",
        )
        self.assertTrue(
            "warning" in reply.lower() or "warning" in reply or "предупреждени" in reply.lower(),
            f"Expected WARNING mention, got: {reply!r}",
        )
        # Must mention selected (the selected=N term)
        self.assertTrue(
            "selected" in reply.lower(),
            f"Expected 'selected' mention for selected=N term, got: {reply!r}",
        )
        # Must NOT hallucinate file references
        self.assertNotIn(".txt", reply, "Reply must not mention .txt files")
        self.assertNotIn("файл", reply.lower(), "Reply must not mention 'файл' (file)")

    def test_matched_terms_contains_both(self) -> None:
        """Both terms must appear in matched_terms."""
        result = admin_runtime.maybe_state_glossary(
            "что значит degraded_selected · selected=1", "ru"
        )
        self.assertIsNotNone(result)
        terms = result["matched_terms"]
        self.assertIn("degraded_selected", terms)
        self.assertIn("selected=N", terms)


class TestMaybeStateGlossaryEnPath(unittest.TestCase):
    """EN locale: query about applied_no_reboot."""

    def test_applied_no_reboot_en(self) -> None:
        result = admin_runtime.maybe_state_glossary(
            "what does applied_no_reboot mean", "en"
        )
        self.assertIsNotNone(result, "Expected a glossary dict, got None")
        reply = result["reply"]
        self.assertIn("reboot", reply.lower())
        self.assertIn("epoch", reply.lower())
        self.assertIn("applied_no_reboot", result["matched_terms"])

    def test_result_id_is_state_glossary(self) -> None:
        result = admin_runtime.maybe_state_glossary("applied_no_reboot", "en")
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "state_glossary")

    def test_term_field_set(self) -> None:
        result = admin_runtime.maybe_state_glossary("applied_no_reboot", "en")
        self.assertIsNotNone(result)
        self.assertIn("applied_no_reboot", result["term"])


class TestMaybeStateGlossaryControlRequestWins(unittest.TestCase):
    """Explicit control request must suppress the glossary (control wins over explanation)."""

    def test_launch_full_composite_returns_none(self) -> None:
        """'запусти full_composite 3' — contains a known term but is a control request."""
        result = admin_runtime.maybe_state_glossary("запусти full_composite 3", "ru")
        self.assertIsNone(result, "Control request with a term must return None")

    def test_run_degraded_selected_returns_none(self) -> None:
        result = admin_runtime.maybe_state_glossary("run degraded_selected pipeline", "en")
        self.assertIsNone(result, "Explicit 'run' with term must return None")

    def test_start_staffing_state_returns_none(self) -> None:
        result = admin_runtime.maybe_state_glossary("start staffing_state check", "en")
        self.assertIsNone(result, "Explicit 'start' with term must return None")


class TestMaybeStateGlossaryNoMatch(unittest.TestCase):
    """Messages without any known state term must return None."""

    def test_unrelated_message_ru(self) -> None:
        result = admin_runtime.maybe_state_glossary("привет, как дела?", "ru")
        self.assertIsNone(result)

    def test_unrelated_message_en(self) -> None:
        result = admin_runtime.maybe_state_glossary("hello, how are you?", "en")
        self.assertIsNone(result)

    def test_empty_string(self) -> None:
        result = admin_runtime.maybe_state_glossary("", "en")
        self.assertIsNone(result)

    def test_none_message(self) -> None:
        result = admin_runtime.maybe_state_glossary(None, "en")
        self.assertIsNone(result)


class TestMaybeStateGlossaryAllTerms(unittest.TestCase):
    """Smoke test: every known term is matched."""

    _TERMS_AND_EXAMPLES = [
        ("degraded_selected", "what is degraded_selected"),
        ("selected=N", "selected=5 in active coverage"),
        ("applied_no_reboot", "applied_no_reboot flag"),
        ("candidate_map_bad", "candidate_map_bad is 0"),
        ("tournament_bad", "tournament_bad counter"),
        ("unsafe_count", "unsafe_count in modelstore"),
        ("runtime_safety", "runtime_safety_ok status"),
        ("staffing_state", "staffing_state verdict"),
        ("full_composite", "что такое full_composite"),
    ]

    def test_all_terms_matched(self) -> None:
        for term, msg in self._TERMS_AND_EXAMPLES:
            with self.subTest(term=term):
                result = admin_runtime.maybe_state_glossary(msg, "en")
                self.assertIsNotNone(result, f"Term '{term}' not matched for message: {msg!r}")
                self.assertIn(term, result["matched_terms"], f"'{term}' missing from matched_terms")


if __name__ == "__main__":
    unittest.main()
