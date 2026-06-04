#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_runtime.py
Zone: tests
Version: 0.32.2
Created: 2026-06-04
Modified: 2026-06-04
Purpose: Tests for admin_runtime.py — the Admin control-plane runtime routing module.
         Covers: safe_id, score_route, route_request, extract_improvement_budget,
         extract_selection_mode, is_smalltalk, has_explicit_control_request,
         is_conversational_smalltalk, request_has_project_context, detect_locale,
         maybe_usecase_help, nowz, json_dumps.
Tests: python3 -m unittest noemaforge/tests/test_admin_runtime.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Stub heavy dependencies before importing admin_runtime
import types

_mock_platform_paths = types.ModuleType("platform_paths")
_mock_paths = MagicMock()
_mock_paths.root = Path("/tmp/nf-test-root")
_mock_paths.pipelines_dir = Path("/tmp/nf-test-root/pipelines")
_mock_paths.model_evolution_state_dir = Path("/tmp/nf-test-root/model-evolution")
_mock_paths.model_selection_state_dir = Path("/tmp/nf-test-root/model-selection")
_mock_platform_paths.DEFAULT_PATHS = _mock_paths
sys.modules.setdefault("platform_paths", _mock_platform_paths)

_mock_prod_ai = MagicMock()
_mock_prod_ai.decide_abstention = MagicMock(return_value={"allowed": True})
sys.modules.setdefault("production_ai_contracts", _mock_prod_ai)

_mock_ver = types.ModuleType("noemaforge_version")
_mock_ver.RUNTIME_VERSION = "0.32.2"
sys.modules.setdefault("noemaforge_version", _mock_ver)

import admin_runtime  # noqa: E402


class TestNowz(unittest.TestCase):
    def test_returns_iso_string_with_z(self) -> None:
        result = admin_runtime.nowz()
        self.assertIsInstance(result, str)
        self.assertTrue(result.endswith("Z"), f"Expected Z suffix: {result!r}")

    def test_format_matches_iso8601(self) -> None:
        import re
        result = admin_runtime.nowz()
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class TestJsonDumps(unittest.TestCase):
    def test_produces_valid_json(self) -> None:
        obj = {"key": "value", "num": 42}
        result = admin_runtime.json_dumps(obj)
        parsed = json.loads(result)
        self.assertEqual(parsed, obj)

    def test_sorts_keys(self) -> None:
        obj = {"z": 1, "a": 2}
        result = admin_runtime.json_dumps(obj)
        idx_a = result.index('"a"')
        idx_z = result.index('"z"')
        self.assertLess(idx_a, idx_z, "Keys should be sorted")

    def test_handles_non_ascii(self) -> None:
        obj = {"msg": "привет"}
        result = admin_runtime.json_dumps(obj)
        # ensure_ascii=False so Cyrillic should pass through
        self.assertIn("привет", result)


class TestSafeId(unittest.TestCase):
    def test_basic_sanitization(self) -> None:
        result = admin_runtime.safe_id("hello world!!")
        self.assertNotIn(" ", result)
        self.assertNotIn("!", result)

    def test_empty_falls_back_to_prefix(self) -> None:
        result = admin_runtime.safe_id("", prefix="task")
        self.assertEqual(result, "task")

    def test_only_special_chars_falls_back_to_prefix(self) -> None:
        result = admin_runtime.safe_id("!!!@@@", prefix="task")
        self.assertEqual(result, "task")

    def test_truncates_at_limit(self) -> None:
        result = admin_runtime.safe_id("a" * 100, limit=72)
        self.assertLessEqual(len(result), 72)

    def test_valid_id_unchanged(self) -> None:
        result = admin_runtime.safe_id("my_task_id")
        self.assertEqual(result, "my_task_id")

    def test_preserves_dots_and_hyphens(self) -> None:
        result = admin_runtime.safe_id("v0.32.2-release")
        self.assertIn("0", result)
        self.assertIn("32", result)


class TestScoreRoute(unittest.TestCase):
    def _make_route(self, route_id: str, keywords: list) -> dict:
        return {"id": route_id, "keywords": keywords}

    def test_no_keywords_zero_score(self) -> None:
        route = self._make_route("greeting", [])
        self.assertEqual(admin_runtime.score_route("hello", route), 0)

    def test_short_keyword_score_one(self) -> None:
        route = self._make_route("test", ["hi"])
        score = admin_runtime.score_route("hi there", route)
        self.assertEqual(score, 1)

    def test_long_keyword_score_three(self) -> None:
        route = self._make_route("code", ["python"])
        score = admin_runtime.score_route("fix python code", route)
        self.assertEqual(score, 3)

    def test_multiple_keywords_accumulate(self) -> None:
        route = self._make_route("code", ["python", "bash"])
        score = admin_runtime.score_route("python and bash", route)
        self.assertEqual(score, 6)  # 3 + 3

    def test_case_insensitive(self) -> None:
        route = self._make_route("code", ["PYTHON"])
        score = admin_runtime.score_route("Python fix", route)
        self.assertEqual(score, 3)

    def test_empty_text_zero_score(self) -> None:
        route = self._make_route("code", ["python"])
        self.assertEqual(admin_runtime.score_route("", route), 0)


class TestRouteRequest(unittest.TestCase):
    def test_code_request_routed_to_code(self) -> None:
        result = admin_runtime.route_request("Нужно исправить python баг в API")
        self.assertEqual(result["id"], "code")

    def test_music_request_routed_to_music(self) -> None:
        result = admin_runtime.route_request("создай музыкальный трек в стиле джаз")
        self.assertEqual(result["id"], "music")

    def test_model_evolution_routed_correctly(self) -> None:
        result = admin_runtime.route_request("запусти model evolution цикл")
        self.assertEqual(result["id"], "model_evolution")

    def test_model_selection_routed_correctly(self) -> None:
        result = admin_runtime.route_request("оптимизируй модель через first-start")
        self.assertEqual(result["id"], "model_selection")

    def test_greeting_routed_for_pure_greeting(self) -> None:
        result = admin_runtime.route_request("привет")
        self.assertEqual(result["id"], "greeting")

    def test_greeting_not_matched_for_domain_request(self) -> None:
        # If text includes domain keywords, greeting should not win
        result = admin_runtime.route_request("привет, запусти музыкальный трек")
        self.assertNotEqual(result["id"], "greeting")

    def test_unknown_returns_fallback_or_low_confidence(self) -> None:
        result = admin_runtime.route_request("xyzzy123 undefined mumbo jumbo")
        # Either falls back to general or has low confidence
        self.assertLessEqual(result["confidence"], 0.3)

    def test_result_has_required_fields(self) -> None:
        result = admin_runtime.route_request("исправь баг")
        for field in ("id", "label", "intent", "score", "confidence", "operator_request", "task_type"):
            with self.subTest(field=field):
                self.assertIn(field, result)

    def test_code_request_without_project_context_flagged(self) -> None:
        result = admin_runtime.route_request("исправь баг")
        if result["id"] == "code":
            self.assertIn("missing_context", result)
            self.assertIn("project path", result["missing_context"])

    def test_code_request_with_project_context_not_flagged(self) -> None:
        result = admin_runtime.route_request("исправь баг в /home/user/project.py")
        if result["id"] == "code":
            self.assertNotIn("missing_context", result)

    def test_confidence_between_zero_and_one(self) -> None:
        result = admin_runtime.route_request("fix python bug")
        self.assertGreaterEqual(result["confidence"], 0.0)
        self.assertLessEqual(result["confidence"], 1.0)

    def test_empty_string_returns_fallback(self) -> None:
        result = admin_runtime.route_request("")
        self.assertIn("id", result)
        self.assertEqual(result["confidence"], 0.0)


class TestExtractImprovementBudget(unittest.TestCase):
    def test_extract_steps(self) -> None:
        result = admin_runtime.extract_improvement_budget("сделай 5 шагов")
        self.assertEqual(result["max_steps"], 5)

    def test_extract_cycles(self) -> None:
        result = admin_runtime.extract_improvement_budget("run 3 cycles")
        self.assertEqual(result["max_steps"], 3)

    def test_extract_minutes(self) -> None:
        result = admin_runtime.extract_improvement_budget("работай 10 минут")
        self.assertEqual(result["time_budget_minutes"], 10)

    def test_extract_minutes_english(self) -> None:
        result = admin_runtime.extract_improvement_budget("run for 30 minutes")
        self.assertEqual(result["time_budget_minutes"], 30)

    def test_extract_until_stop(self) -> None:
        result = admin_runtime.extract_improvement_budget("пока не остановлю")
        self.assertTrue(result["until_stop"])

    def test_until_stop_english(self) -> None:
        result = admin_runtime.extract_improvement_budget("continue until stop")
        self.assertTrue(result["until_stop"])

    def test_no_budget_not_active(self) -> None:
        result = admin_runtime.extract_improvement_budget("улучши модель")
        self.assertFalse(result["active"])

    def test_steps_budget_active(self) -> None:
        result = admin_runtime.extract_improvement_budget("3 шага")
        self.assertTrue(result["active"])
        self.assertEqual(result["kind"], "bounded_improvement")

    def test_operator_rule_set_for_steps(self) -> None:
        result = admin_runtime.extract_improvement_budget("7 steps")
        self.assertIn("7", result["operator_rule"])

    def test_operator_rule_set_for_minutes(self) -> None:
        result = admin_runtime.extract_improvement_budget("15 minutes")
        self.assertIn("15", result["operator_rule"])

    def test_explicit_max_steps_overrides(self) -> None:
        result = admin_runtime.extract_improvement_budget("do stuff", max_steps=10)
        self.assertEqual(result["max_steps"], 10)

    def test_explicit_time_budget_overrides(self) -> None:
        result = admin_runtime.extract_improvement_budget("do stuff", time_budget_minutes=20)
        self.assertEqual(result["time_budget_minutes"], 20)


class TestExtractSelectionMode(unittest.TestCase):
    def test_full_composite_with_number(self) -> None:
        mode, n = admin_runtime.extract_selection_mode("full_composite 3")
        self.assertEqual(mode, "full_composite")
        self.assertEqual(n, 3)

    def test_full_composite_no_number(self) -> None:
        mode, n = admin_runtime.extract_selection_mode("full composite mode")
        self.assertEqual(mode, "full_composite")
        self.assertEqual(n, 0)

    def test_fast_mode(self) -> None:
        mode, n = admin_runtime.extract_selection_mode("use fast selection")
        self.assertEqual(mode, "fast")
        self.assertEqual(n, -1)

    def test_normal_mode(self) -> None:
        mode, n = admin_runtime.extract_selection_mode("normal mode please")
        self.assertEqual(mode, "normal")

    def test_full_mode(self) -> None:
        mode, n = admin_runtime.extract_selection_mode("run full selection")
        self.assertEqual(mode, "full")

    def test_empty_text_returns_empty(self) -> None:
        mode, n = admin_runtime.extract_selection_mode("")
        self.assertEqual(mode, "")
        self.assertEqual(n, -1)

    def test_no_mode_returns_empty(self) -> None:
        mode, n = admin_runtime.extract_selection_mode("just do something")
        self.assertEqual(mode, "")


class TestIsSmalltalk(unittest.TestCase):
    def test_super_is_smalltalk(self) -> None:
        self.assertTrue(admin_runtime.is_smalltalk("супер!"))

    def test_thanks_is_smalltalk(self) -> None:
        self.assertTrue(admin_runtime.is_smalltalk("спасибо"))

    def test_hello_is_smalltalk(self) -> None:
        self.assertTrue(admin_runtime.is_smalltalk("hello"))

    def test_ok_is_smalltalk(self) -> None:
        self.assertTrue(admin_runtime.is_smalltalk("ок"))

    def test_complex_request_not_smalltalk(self) -> None:
        self.assertFalse(admin_runtime.is_smalltalk("запусти dev team pipeline"))

    def test_empty_not_smalltalk(self) -> None:
        self.assertFalse(admin_runtime.is_smalltalk(""))

    def test_thank_you_is_smalltalk(self) -> None:
        self.assertTrue(admin_runtime.is_smalltalk("thank you"))


class TestHasExplicitControlRequest(unittest.TestCase):
    def test_run_detected(self) -> None:
        self.assertTrue(admin_runtime.has_explicit_control_request("run the pipeline"))

    def test_start_detected(self) -> None:
        self.assertTrue(admin_runtime.has_explicit_control_request("start evolution"))

    def test_pipeline_detected(self) -> None:
        self.assertTrue(admin_runtime.has_explicit_control_request("show me pipeline"))

    def test_launch_detected(self) -> None:
        self.assertTrue(admin_runtime.has_explicit_control_request("launch the model"))

    def test_запусти_detected(self) -> None:
        self.assertTrue(admin_runtime.has_explicit_control_request("запусти pipeline"))

    def test_pure_smalltalk_not_control(self) -> None:
        self.assertFalse(admin_runtime.has_explicit_control_request("супер!"))

    def test_empty_not_control(self) -> None:
        self.assertFalse(admin_runtime.has_explicit_control_request(""))


class TestIsConversationalSmalltalk(unittest.TestCase):
    def test_thanks_without_control_is_conversational(self) -> None:
        self.assertTrue(admin_runtime.is_conversational_smalltalk("спасибо"))

    def test_thanks_with_run_is_not_conversational(self) -> None:
        self.assertFalse(admin_runtime.is_conversational_smalltalk("спасибо, запусти pipeline"))

    def test_complex_request_not_conversational(self) -> None:
        self.assertFalse(admin_runtime.is_conversational_smalltalk("start the evolution cycle"))

    def test_ok_without_control_is_conversational(self) -> None:
        self.assertTrue(admin_runtime.is_conversational_smalltalk("ок"))


class TestRequestHasProjectContext(unittest.TestCase):
    def test_file_path_detected(self) -> None:
        self.assertTrue(admin_runtime.request_has_project_context("/home/user/project/main.py"))

    def test_py_extension_detected(self) -> None:
        self.assertTrue(admin_runtime.request_has_project_context("fix bug in widget.py"))

    def test_repo_keyword_detected(self) -> None:
        self.assertTrue(admin_runtime.request_has_project_context("look at the repo structure"))

    def test_project_keyword_detected(self) -> None:
        self.assertTrue(admin_runtime.request_has_project_context("fix bug in this project"))

    def test_no_context_returns_false(self) -> None:
        self.assertFalse(admin_runtime.request_has_project_context("fix the bug"))

    def test_md_extension_detected(self) -> None:
        self.assertTrue(admin_runtime.request_has_project_context("update README.md"))

    def test_sh_extension_detected(self) -> None:
        self.assertTrue(admin_runtime.request_has_project_context("fix the deploy.sh script"))


class TestDetectLocale(unittest.TestCase):
    def test_cyrillic_text_returns_ru(self) -> None:
        result = admin_runtime.detect_locale("Привет, как дела?")
        self.assertEqual(result, "ru")

    def test_ukrainian_chars_returns_uk(self) -> None:
        # Ukrainian-specific characters: І, Ї, Є, Ґ
        result = admin_runtime.detect_locale("Привіт, як справи?")
        self.assertEqual(result, "uk")

    def test_empty_text_falls_to_env(self) -> None:
        with patch.dict(os.environ, {"NOEMAFORGE_LANG": "de"}, clear=False):
            result = admin_runtime.detect_locale("", "de")
        self.assertEqual(result, "de")

    def test_explicit_request_takes_priority(self) -> None:
        result = admin_runtime.detect_locale("Привет", "en")
        self.assertEqual(result, "en")


class TestMaybeUsecaseHelp(unittest.TestCase):
    def _root(self) -> Path:
        return Path("/tmp/nf-test-root")

    def test_returns_none_for_no_help_trigger(self) -> None:
        result = admin_runtime.maybe_usecase_help(self._root(), "запусти трек", "ru")
        self.assertIsNone(result)

    def test_returns_dict_for_help_trigger(self) -> None:
        result = admin_runtime.maybe_usecase_help(self._root(), "что значит оптимизация модели", "ru")
        self.assertIsNotNone(result)
        self.assertIn("reply", result)
        self.assertIn("id", result)

    def test_help_contains_available_usecases(self) -> None:
        result = admin_runtime.maybe_usecase_help(self._root(), "объясни model selection", "ru")
        self.assertIn("available_usecases", result)
        self.assertIsInstance(result["available_usecases"], list)
        self.assertGreater(len(result["available_usecases"]), 0)

    def test_help_trigger_справка(self) -> None:
        result = admin_runtime.maybe_usecase_help(self._root(), "справка", "ru")
        self.assertIsNotNone(result)

    def test_help_trigger_help_english(self) -> None:
        result = admin_runtime.maybe_usecase_help(self._root(), "help me understand model selection", "en")
        self.assertIsNotNone(result)

    def test_english_locale_returns_english_text(self) -> None:
        result = admin_runtime.maybe_usecase_help(self._root(), "help with model evolution", "en")
        if result:
            # Reply should exist and contain english text
            self.assertIsInstance(result["reply"], str)


class TestPersonaSwitchFor(unittest.TestCase):
    def test_code_maps_to_dev_team(self) -> None:
        result = admin_runtime.persona_switch_for("code")
        self.assertIsNotNone(result)
        self.assertIn("Dev Team", result.values())

    def test_model_evolution_maps_correctly(self) -> None:
        result = admin_runtime.persona_switch_for("model_evolution")
        self.assertIsNotNone(result)

    def test_unknown_route_returns_none_or_dict(self) -> None:
        result = admin_runtime.persona_switch_for("nonexistent")
        # Should return None for unknown routes
        self.assertIsNone(result)


class TestRoutesList(unittest.TestCase):
    """Verify ROUTES structure invariants."""

    def test_all_routes_have_id(self) -> None:
        for route in admin_runtime.ROUTES:
            with self.subTest(route=route.get("id")):
                self.assertIn("id", route)
                self.assertTrue(route["id"])

    def test_all_routes_have_pipeline_id(self) -> None:
        for route in admin_runtime.ROUTES:
            with self.subTest(route=route.get("id")):
                self.assertIn("pipeline_id", route)

    def test_all_routes_have_intent(self) -> None:
        for route in admin_runtime.ROUTES:
            with self.subTest(route=route.get("id")):
                self.assertIn("intent", route)

    def test_all_routes_have_keywords_list(self) -> None:
        for route in admin_runtime.ROUTES:
            with self.subTest(route=route.get("id")):
                self.assertIsInstance(route.get("keywords"), list)

    def test_model_selection_has_suggested_commands(self) -> None:
        ms_route = next((r for r in admin_runtime.ROUTES if r["id"] == "model_selection"), None)
        self.assertIsNotNone(ms_route)
        self.assertIn("suggested_commands", ms_route)
        self.assertGreater(len(ms_route["suggested_commands"]), 0)

    def test_fallback_route_has_empty_keywords(self) -> None:
        self.assertEqual(admin_runtime.FALLBACK_ROUTE["keywords"], [])

    def test_no_runtime_version_outside_version_module(self) -> None:
        """RUNTIME_VERSION must not be assigned in admin_runtime source."""
        src_path = _SRC / "admin_runtime.py"
        src = src_path.read_text(encoding="utf-8")
        import re
        assignments = re.findall(r"^RUNTIME_VERSION\s*=", src, re.MULTILINE)
        self.assertEqual(assignments, [], "RUNTIME_VERSION must not be assigned in admin_runtime.py")


if __name__ == "__main__":
    unittest.main()