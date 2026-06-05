#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_runtime_unit.py
Zone: tests
Version: 0.32.2
Created: 2026-06-04
Modified: 2026-06-04
Purpose: Unit tests for admin_runtime.py pure functions:
         safe_id, score_route, route_request, extract_improvement_budget,
         extract_selection_mode, is_smalltalk, has_explicit_control_request,
         is_conversational_smalltalk, detect_locale, request_has_project_context,
         sh_quote, collect_artifacts, artifact_card, persona_switch_for,
         read_json_obj, write_json_obj.
         These functions do not require subprocess or HTTP servers.
Inputs: admin_runtime module functions.
Outputs: pytest/unittest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_admin_runtime_unit.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
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
    # decide_abstention stub: always return a permissive dict
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


# ---------------------------------------------------------------------------
# Tests for safe_id()
# ---------------------------------------------------------------------------

class TestAdminRuntimeSafeId(unittest.TestCase):
    """admin_runtime.safe_id() (72-char limit, underscore normalization)."""

    def test_alphanumeric_passthrough(self) -> None:
        """Normal alphanumeric characters pass through unchanged."""
        self.assertEqual(admin_runtime.safe_id("task123"), "task123")

    def test_dots_and_hyphens_preserved(self) -> None:
        """Dots and hyphens are allowed characters and are preserved."""
        result = admin_runtime.safe_id("task-1.0")
        self.assertIn("-", result)
        self.assertIn(".", result)

    def test_spaces_replaced_with_underscore(self) -> None:
        """Spaces are replaced with underscores."""
        result = admin_runtime.safe_id("hello world")
        self.assertNotIn(" ", result)
        self.assertIn("_", result)

    def test_slashes_replaced(self) -> None:
        """Slashes are replaced (not retained)."""
        result = admin_runtime.safe_id("path/to/file")
        self.assertNotIn("/", result)

    def test_empty_string_uses_prefix(self) -> None:
        """Empty string returns the prefix value."""
        result = admin_runtime.safe_id("")
        self.assertEqual(result, "task")

    def test_whitespace_only_uses_prefix(self) -> None:
        """Whitespace-only string returns the prefix."""
        result = admin_runtime.safe_id("   ")
        self.assertEqual(result, "task")

    def test_custom_prefix(self) -> None:
        """Custom prefix is used when value collapses to empty."""
        result = admin_runtime.safe_id("", prefix="pipeline")
        self.assertEqual(result, "pipeline")

    def test_limit_72_truncates_long_input(self) -> None:
        """Inputs over 72 characters are truncated to 72."""
        long_value = "x" * 200
        result = admin_runtime.safe_id(long_value)
        self.assertLessEqual(len(result), 72)

    def test_exactly_72_chars_not_truncated(self) -> None:
        """A 72-character input is returned verbatim."""
        exact = "a" * 72
        result = admin_runtime.safe_id(exact)
        self.assertEqual(len(result), 72)
        self.assertEqual(result, exact)

    def test_special_only_uses_prefix(self) -> None:
        """A string of only special chars collapses to prefix."""
        result = admin_runtime.safe_id("!@#$%^&*()")
        self.assertEqual(result, "task")

    def test_non_empty_result_never_empty(self) -> None:
        """safe_id always returns a non-empty string."""
        for val in ["", "   ", "///", "___", "...", "!@#"]:
            with self.subTest(val=val):
                result = admin_runtime.safe_id(val)
                self.assertTrue(result, f"safe_id({val!r}) must not return empty string")

    def test_leading_trailing_underscores_stripped(self) -> None:
        """Leading/trailing underscores are stripped from result."""
        result = admin_runtime.safe_id("  hello  ")
        self.assertFalse(result.startswith("_"), f"Got: {result!r}")
        self.assertFalse(result.endswith("_"), f"Got: {result!r}")


# ---------------------------------------------------------------------------
# Tests for score_route()
# ---------------------------------------------------------------------------

class TestScoreRoute(unittest.TestCase):
    """score_route() assigns keyword-based scores to route candidates."""

    def test_zero_score_for_empty_text(self) -> None:
        """Empty text scores zero against any route."""
        route = admin_runtime.ROUTES[0]
        score = admin_runtime.score_route("", route)
        self.assertEqual(score, 0)

    def test_music_route_scores_for_music_keyword(self) -> None:
        """'музык' triggers a positive score for the music route."""
        music_route = next(r for r in admin_runtime.ROUTES if r["id"] == "music")
        score = admin_runtime.score_route("создай музыку для проекта", music_route)
        self.assertGreater(score, 0)

    def test_code_route_scores_for_code_keyword(self) -> None:
        """'python' triggers a positive score for the code route."""
        code_route = next(r for r in admin_runtime.ROUTES if r["id"] == "code")
        score = admin_runtime.score_route("напиши python скрипт", code_route)
        self.assertGreater(score, 0)

    def test_greeting_route_scores_for_hello(self) -> None:
        """'hello' triggers a score for the greeting route."""
        greeting_route = next(r for r in admin_runtime.ROUTES if r["id"] == "greeting")
        score = admin_runtime.score_route("hello", greeting_route)
        self.assertGreater(score, 0)

    def test_long_keyword_scores_higher_than_short(self) -> None:
        """Keywords over 4 chars score 3; those at or under score 1."""
        # "голос" is 5 chars → score 3 per match
        voice_route = next(r for r in admin_runtime.ROUTES if r["id"] == "voice")
        score = admin_runtime.score_route("запусти голос", voice_route)
        self.assertGreaterEqual(score, 3)

    def test_no_match_returns_zero(self) -> None:
        """Text with no route keywords scores zero."""
        code_route = next(r for r in admin_runtime.ROUTES if r["id"] == "code")
        score = admin_runtime.score_route("что такое погода", code_route)
        self.assertEqual(score, 0)


# ---------------------------------------------------------------------------
# Tests for route_request()
# ---------------------------------------------------------------------------

class TestRouteRequest(unittest.TestCase):
    """route_request() selects the best matching route for a natural-language request."""

    def test_music_request_routes_to_music(self) -> None:
        """'музык' routes to the music pipeline."""
        result = admin_runtime.route_request("создай музыку")
        self.assertEqual(result["id"], "music")
        self.assertEqual(result["pipeline_id"], "music_generation")

    def test_model_evolution_routes_correctly(self) -> None:
        """'эволюция модели' routes to model_evolution, not code."""
        result = admin_runtime.route_request("запусти эволюцию модели")
        self.assertEqual(result["id"], "model_evolution")

    def test_code_request_routes_to_code(self) -> None:
        """'python bug' routes to the dev pipeline."""
        result = admin_runtime.route_request("fix python bug in my code")
        self.assertEqual(result["id"], "code")

    def test_empty_text_returns_fallback(self) -> None:
        """Empty string falls back to the general pipeline."""
        result = admin_runtime.route_request("")
        self.assertEqual(result["id"], "general")
        self.assertEqual(result["score"], 0)

    def test_result_has_required_keys(self) -> None:
        """route_request() must include id, score, confidence, operator_request."""
        result = admin_runtime.route_request("create music")
        for key in ("id", "score", "confidence", "operator_request"):
            with self.subTest(key=key):
                self.assertIn(key, result)

    def test_confidence_between_zero_and_one(self) -> None:
        """Confidence must be in [0.0, 1.0]."""
        result = admin_runtime.route_request("эволюция модели")
        self.assertGreaterEqual(result["confidence"], 0.0)
        self.assertLessEqual(result["confidence"], 1.0)

    def test_greeting_exact_routes_to_greeting(self) -> None:
        """Pure greeting 'привет' without domain keywords routes to greeting."""
        result = admin_runtime.route_request("привет")
        self.assertEqual(result["id"], "greeting")

    def test_model_selection_routes_correctly(self) -> None:
        """'выбор модели' routes to model_selection."""
        result = admin_runtime.route_request("выбор модели для dev team")
        self.assertEqual(result["id"], "model_selection")

    def test_code_with_evolution_intent_not_stolen_by_code(self) -> None:
        """'model evolution' with code mention must not route to code."""
        result = admin_runtime.route_request("улучши модель с помощью lora adapter")
        self.assertNotEqual(result["id"], "code")

    def test_operator_request_preserved(self) -> None:
        """operator_request field must match the input text."""
        text = "generate a voice audio file"
        result = admin_runtime.route_request(text)
        self.assertEqual(result["operator_request"], text)

    def test_zero_score_falls_back_to_general(self) -> None:
        """Text with no route keywords returns general fallback with score 0."""
        result = admin_runtime.route_request("something completely unrelated xyz")
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["id"], "general")

    def test_code_without_project_context_has_missing_context(self) -> None:
        """Code request without file/project context includes missing_context."""
        result = admin_runtime.route_request("fix the bug in python")
        if result["id"] == "code":
            self.assertIn("missing_context", result)
            self.assertTrue(len(result["missing_context"]) > 0)

    def test_code_with_project_path_no_missing_context(self) -> None:
        """Code request with a file path does not have missing_context."""
        result = admin_runtime.route_request("fix bug in /home/user/project/main.py")
        if result["id"] == "code":
            self.assertNotIn("missing_context", result)


# ---------------------------------------------------------------------------
# Tests for extract_improvement_budget()
# ---------------------------------------------------------------------------

class TestExtractImprovementBudget(unittest.TestCase):
    """extract_improvement_budget() parses bounded improvement depth from text."""

    def test_no_budget_returns_inactive(self) -> None:
        """Text without improvement hints returns active=False."""
        budget = admin_runtime.extract_improvement_budget("оптимизируй модель")
        self.assertFalse(budget["active"])

    def test_steps_parsed_from_english(self) -> None:
        """'5 steps' is parsed as max_steps=5."""
        budget = admin_runtime.extract_improvement_budget("run 5 steps of improvement")
        self.assertEqual(budget["max_steps"], 5)
        self.assertTrue(budget["active"])

    def test_steps_parsed_from_russian(self) -> None:
        """'3 шага' is parsed as max_steps=3."""
        budget = admin_runtime.extract_improvement_budget("сделай 3 шага улучшения")
        self.assertEqual(budget["max_steps"], 3)
        self.assertTrue(budget["active"])

    def test_minutes_parsed_from_english(self) -> None:
        """'30 minutes' is parsed as time_budget_minutes=30."""
        budget = admin_runtime.extract_improvement_budget("run for 30 minutes")
        self.assertEqual(budget["time_budget_minutes"], 30)
        self.assertTrue(budget["active"])

    def test_minutes_parsed_from_russian(self) -> None:
        """'10 минут' is parsed as time_budget_minutes=10."""
        budget = admin_runtime.extract_improvement_budget("улучшай 10 минут")
        self.assertEqual(budget["time_budget_minutes"], 10)
        self.assertTrue(budget["active"])

    def test_cycles_parsed(self) -> None:
        """'7 cycles' is parsed as max_steps=7."""
        budget = admin_runtime.extract_improvement_budget("run 7 cycles")
        self.assertEqual(budget["max_steps"], 7)

    def test_explicit_until_stop_flag(self) -> None:
        """Passing until_stop=True sets until_stop in result."""
        budget = admin_runtime.extract_improvement_budget("", until_stop=True)
        self.assertTrue(budget["until_stop"])
        self.assertTrue(budget["active"])

    def test_explicit_max_steps_override(self) -> None:
        """max_steps kwarg overrides parsing."""
        budget = admin_runtime.extract_improvement_budget("no hint here", max_steps=10)
        self.assertEqual(budget["max_steps"], 10)
        self.assertTrue(budget["active"])

    def test_kind_field_present(self) -> None:
        """Result always has kind='bounded_improvement'."""
        budget = admin_runtime.extract_improvement_budget("")
        self.assertEqual(budget["kind"], "bounded_improvement")

    def test_operator_rule_steps(self) -> None:
        """When steps parsed, operator_rule describes step count."""
        budget = admin_runtime.extract_improvement_budget("run 2 steps")
        self.assertIn("2", budget.get("operator_rule", ""))

    def test_operator_rule_minutes(self) -> None:
        """When minutes parsed, operator_rule describes time budget."""
        budget = admin_runtime.extract_improvement_budget("run for 15 minutes")
        self.assertIn("15", budget.get("operator_rule", ""))


# ---------------------------------------------------------------------------
# Tests for extract_selection_mode()
# ---------------------------------------------------------------------------

class TestExtractSelectionMode(unittest.TestCase):
    """extract_selection_mode() extracts mode and optional composite_top_n."""

    def test_fast_mode(self) -> None:
        mode, n = admin_runtime.extract_selection_mode("use fast mode")
        self.assertEqual(mode, "fast")
        self.assertEqual(n, -1)

    def test_normal_mode(self) -> None:
        mode, n = admin_runtime.extract_selection_mode("run normal optimization")
        self.assertEqual(mode, "normal")

    def test_full_mode(self) -> None:
        mode, n = admin_runtime.extract_selection_mode("full model selection")
        self.assertEqual(mode, "full")

    def test_full_composite_with_number(self) -> None:
        mode, n = admin_runtime.extract_selection_mode("full_composite 3")
        self.assertEqual(mode, "full_composite")
        self.assertEqual(n, 3)

    def test_full_composite_without_number(self) -> None:
        mode, n = admin_runtime.extract_selection_mode("full composite optimization")
        self.assertEqual(mode, "full_composite")
        self.assertEqual(n, 0)

    def test_no_mode_returns_empty(self) -> None:
        mode, n = admin_runtime.extract_selection_mode("run optimization please")
        self.assertEqual(mode, "")

    def test_case_insensitive(self) -> None:
        mode, n = admin_runtime.extract_selection_mode("FAST optimization")
        self.assertEqual(mode, "fast")

    def test_empty_string_returns_empty(self) -> None:
        mode, n = admin_runtime.extract_selection_mode("")
        self.assertEqual(mode, "")


# ---------------------------------------------------------------------------
# Tests for is_smalltalk()
# ---------------------------------------------------------------------------

class TestIsSmallTalk(unittest.TestCase):
    """is_smalltalk() detects short conversational messages."""

    def test_thanks_is_smalltalk(self) -> None:
        self.assertTrue(admin_runtime.is_smalltalk("спасибо"))

    def test_hello_is_smalltalk(self) -> None:
        self.assertTrue(admin_runtime.is_smalltalk("hello"))

    def test_how_are_you_is_smalltalk(self) -> None:
        self.assertTrue(admin_runtime.is_smalltalk("как ты"))

    def test_ok_is_smalltalk(self) -> None:
        self.assertTrue(admin_runtime.is_smalltalk("ок"))

    def test_ok_en_is_smalltalk(self) -> None:
        self.assertTrue(admin_runtime.is_smalltalk("ok"))

    def test_complex_request_is_not_smalltalk(self) -> None:
        self.assertFalse(admin_runtime.is_smalltalk("запусти dev team pipeline для разработки"))

    def test_empty_string_is_not_smalltalk(self) -> None:
        self.assertFalse(admin_runtime.is_smalltalk(""))

    def test_domain_keyword_is_not_smalltalk(self) -> None:
        self.assertFalse(admin_runtime.is_smalltalk("оптимизируй модель для продакшна"))


# ---------------------------------------------------------------------------
# Tests for has_explicit_control_request()
# ---------------------------------------------------------------------------

class TestHasExplicitControlRequest(unittest.TestCase):
    """has_explicit_control_request() detects explicit operator control commands."""

    def test_zapusti_triggers_control(self) -> None:
        self.assertTrue(admin_runtime.has_explicit_control_request("запусти pipeline"))

    def test_run_triggers_control(self) -> None:
        self.assertTrue(admin_runtime.has_explicit_control_request("run the pipeline"))

    def test_start_triggers_control(self) -> None:
        self.assertTrue(admin_runtime.has_explicit_control_request("start gui"))

    def test_pipeline_triggers_control(self) -> None:
        self.assertTrue(admin_runtime.has_explicit_control_request("open pipeline"))

    def test_model_evolution_triggers_control(self) -> None:
        self.assertTrue(admin_runtime.has_explicit_control_request("model evolution"))

    def test_pure_smalltalk_does_not_trigger(self) -> None:
        self.assertFalse(admin_runtime.has_explicit_control_request("спасибо"))

    def test_empty_does_not_trigger(self) -> None:
        self.assertFalse(admin_runtime.has_explicit_control_request(""))

    def test_vault_triggers_control(self) -> None:
        self.assertTrue(admin_runtime.has_explicit_control_request("инвентаризация vault"))


# ---------------------------------------------------------------------------
# Tests for is_conversational_smalltalk()
# ---------------------------------------------------------------------------

class TestIsConversationalSmallTalk(unittest.TestCase):
    """is_conversational_smalltalk() = is_smalltalk AND NOT has_explicit_control."""

    def test_thanks_is_conversational(self) -> None:
        self.assertTrue(admin_runtime.is_conversational_smalltalk("спасибо"))

    def test_hello_run_is_not_conversational(self) -> None:
        """'hello start gui' has explicit control — not conversational."""
        self.assertFalse(admin_runtime.is_conversational_smalltalk("hello start gui"))

    def test_complex_request_is_not_conversational(self) -> None:
        self.assertFalse(admin_runtime.is_conversational_smalltalk("запусти dev team для проекта"))

    def test_empty_is_not_conversational(self) -> None:
        self.assertFalse(admin_runtime.is_conversational_smalltalk(""))


# ---------------------------------------------------------------------------
# Tests for detect_locale()
# ---------------------------------------------------------------------------

class TestDetectLocale(unittest.TestCase):
    """detect_locale() detects language from message content."""

    def setUp(self) -> None:
        # Remove env vars that might influence detection
        self._orig_env = {k: os.environ.pop(k, None) for k in
                         ("NOEMAFORGE_LANG", "LC_ALL", "LANG")}

    def tearDown(self) -> None:
        for k, v in self._orig_env.items():
            if v is not None:
                os.environ[k] = v

    def test_cyrillic_detects_russian(self) -> None:
        locale = admin_runtime.detect_locale("привет, как дела")
        self.assertEqual(locale, "ru")

    def test_ukrainian_chars_detect_ukrainian(self) -> None:
        # Ukrainian-specific chars: І, ї, є, ґ
        locale = admin_runtime.detect_locale("Привіт із України")
        self.assertEqual(locale, "uk")

    def test_latin_falls_back_to_en(self) -> None:
        locale = admin_runtime.detect_locale("hello how are you")
        self.assertIn(locale, ("en", ""))

    def test_explicit_locale_override(self) -> None:
        locale = admin_runtime.detect_locale("hello", requested="ru")
        self.assertEqual(locale, "ru")

    def test_empty_message_latin_default(self) -> None:
        locale = admin_runtime.detect_locale("")
        # Without env vars, should return "en" or ""
        self.assertIsInstance(locale, str)


# ---------------------------------------------------------------------------
# Tests for request_has_project_context()
# ---------------------------------------------------------------------------

class TestRequestHasProjectContext(unittest.TestCase):
    """request_has_project_context() detects file/project paths in requests."""

    def test_path_with_slash_has_context(self) -> None:
        self.assertTrue(admin_runtime.request_has_project_context("/home/user/myproject/main.py"))

    def test_py_extension_has_context(self) -> None:
        self.assertTrue(admin_runtime.request_has_project_context("fix bug in admin.py"))

    def test_md_extension_has_context(self) -> None:
        self.assertTrue(admin_runtime.request_has_project_context("update README.md"))

    def test_json_extension_has_context(self) -> None:
        self.assertTrue(admin_runtime.request_has_project_context("edit config.json"))

    def test_project_keyword_has_context(self) -> None:
        self.assertTrue(admin_runtime.request_has_project_context("fix bug in project"))

    def test_repo_keyword_has_context(self) -> None:
        self.assertTrue(admin_runtime.request_has_project_context("update the repo"))

    def test_ru_project_keyword_has_context(self) -> None:
        self.assertTrue(admin_runtime.request_has_project_context("обнови файл в проекте"))

    def test_generic_request_no_context(self) -> None:
        self.assertFalse(admin_runtime.request_has_project_context("оптимизируй модель"))

    def test_empty_no_context(self) -> None:
        self.assertFalse(admin_runtime.request_has_project_context(""))

    def test_tilde_path_has_context(self) -> None:
        self.assertTrue(admin_runtime.request_has_project_context("edit ~/myfile.py"))


# ---------------------------------------------------------------------------
# Tests for sh_quote()
# ---------------------------------------------------------------------------

class TestShQuote(unittest.TestCase):
    """sh_quote() produces safely single-quoted shell strings."""

    def test_simple_string_quoted(self) -> None:
        self.assertEqual(admin_runtime.sh_quote("hello"), "'hello'")

    def test_string_with_spaces_quoted(self) -> None:
        result = admin_runtime.sh_quote("hello world")
        self.assertEqual(result, "'hello world'")

    def test_string_with_single_quote_escaped(self) -> None:
        """Embedded single quotes must be properly escaped."""
        result = admin_runtime.sh_quote("it's here")
        self.assertIn("'\\''", result)
        self.assertNotIn("'it's'", result)

    def test_empty_string(self) -> None:
        self.assertEqual(admin_runtime.sh_quote(""), "''")

    def test_path_quoted(self) -> None:
        result = admin_runtime.sh_quote("/var/lib/noemaforge/file.json")
        self.assertTrue(result.startswith("'"))
        self.assertTrue(result.endswith("'"))
        self.assertIn("/var/lib/noemaforge/file.json", result)


# ---------------------------------------------------------------------------
# Tests for artifact_card()
# ---------------------------------------------------------------------------

class TestArtifactCard(unittest.TestCase):
    """artifact_card() creates artifact metadata dicts."""

    def test_required_fields_present(self) -> None:
        card = admin_runtime.artifact_card("file", "/tmp/report.txt")
        for key in ("type", "status", "label", "path", "open_command"):
            with self.subTest(key=key):
                self.assertIn(key, card)

    def test_type_is_set(self) -> None:
        card = admin_runtime.artifact_card("plan", "/tmp/plan.json")
        self.assertEqual(card["type"], "plan")

    def test_label_defaults_to_filename(self) -> None:
        card = admin_runtime.artifact_card("file", "/tmp/report.txt")
        self.assertEqual(card["label"], "report.txt")

    def test_custom_label_used(self) -> None:
        card = admin_runtime.artifact_card("file", "/tmp/report.txt", label="My Report")
        self.assertEqual(card["label"], "My Report")

    def test_status_defaults_to_ready(self) -> None:
        card = admin_runtime.artifact_card("file", "/tmp/x.json")
        self.assertEqual(card["status"], "ready")

    def test_custom_status(self) -> None:
        card = admin_runtime.artifact_card("plan", "/tmp/plan.json", status="planned_only")
        self.assertEqual(card["status"], "planned_only")

    def test_path_stored(self) -> None:
        card = admin_runtime.artifact_card("file", "/tmp/output.txt")
        self.assertEqual(card["path"], "/tmp/output.txt")

    def test_open_command_includes_path(self) -> None:
        card = admin_runtime.artifact_card("file", "/tmp/output.txt")
        self.assertIn("/tmp/output.txt", card["open_command"])


# ---------------------------------------------------------------------------
# Tests for collect_artifacts()
# ---------------------------------------------------------------------------

class TestCollectArtifacts(unittest.TestCase):
    """collect_artifacts() recursively extracts artifact references from nested dicts."""

    def test_empty_dict_returns_empty(self) -> None:
        self.assertEqual(admin_runtime.collect_artifacts({}), [])

    def test_none_returns_empty(self) -> None:
        self.assertEqual(admin_runtime.collect_artifacts(None), [])

    def test_run_dir_extracted(self) -> None:
        obj = {"run_dir": "/tmp/runs/run_001", "status": "ready"}
        result = admin_runtime.collect_artifacts(obj)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "run_dir")

    def test_plan_path_extracted(self) -> None:
        obj = {"plan_path": "/tmp/plans/plan.json"}
        result = admin_runtime.collect_artifacts(obj)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "plan")
        self.assertEqual(result[0]["status"], "planned_only")

    def test_diff_extracted(self) -> None:
        obj = {"diff": "/tmp/diff/changes.diff"}
        result = admin_runtime.collect_artifacts(obj)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "diff")

    def test_nested_stdout_walked(self) -> None:
        obj = {"stdout": {"run_dir": "/tmp/runs/nested"}}
        result = admin_runtime.collect_artifacts(obj)
        self.assertEqual(len(result), 1)

    def test_nested_list_walked(self) -> None:
        obj = [{"run_dir": "/tmp/runs/a"}, {"run_dir": "/tmp/runs/b"}]
        result = admin_runtime.collect_artifacts(obj)
        self.assertEqual(len(result), 2)

    def test_deduplication_by_path_label_type(self) -> None:
        """Duplicate path+label+type combos are deduplicated."""
        obj = [
            {"run_dir": "/tmp/runs/dup", "status": "ready"},
            {"run_dir": "/tmp/runs/dup", "status": "ready"},
        ]
        result = admin_runtime.collect_artifacts(obj)
        self.assertEqual(len(result), 1, "Duplicates must be deduplicated")

    def test_artifacts_dict_extracted(self) -> None:
        obj = {"artifacts": {"report": "/tmp/report.txt"}}
        result = admin_runtime.collect_artifacts(obj)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["label"], "report")
        self.assertEqual(result[0]["path"], "/tmp/report.txt")

    def test_path_key_extracted(self) -> None:
        obj = {"path": "/tmp/output/result.json"}
        result = admin_runtime.collect_artifacts(obj)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "file")


# ---------------------------------------------------------------------------
# Tests for persona_switch_for()
# ---------------------------------------------------------------------------

class TestPersonaSwitchFor(unittest.TestCase):
    """persona_switch_for() returns persona switch info for known route IDs."""

    def test_code_returns_dev_team(self) -> None:
        result = admin_runtime.persona_switch_for("code")
        self.assertIsNotNone(result)
        self.assertEqual(result["to"], "Dev Team")
        self.assertEqual(result["from"], "Admin")

    def test_music_returns_music_team(self) -> None:
        result = admin_runtime.persona_switch_for("music")
        self.assertIsNotNone(result)
        self.assertEqual(result["to"], "Music Team")

    def test_model_evolution_returns_model_evolution(self) -> None:
        result = admin_runtime.persona_switch_for("model_evolution")
        self.assertIsNotNone(result)
        self.assertEqual(result["to"], "Model Evolution")

    def test_model_selection_returns_optimizer(self) -> None:
        result = admin_runtime.persona_switch_for("model_selection")
        self.assertIsNotNone(result)
        self.assertEqual(result["to"], "Optimizer")

    def test_greeting_returns_none(self) -> None:
        """Greeting route has no persona switch."""
        result = admin_runtime.persona_switch_for("greeting")
        self.assertIsNone(result)

    def test_general_returns_none(self) -> None:
        result = admin_runtime.persona_switch_for("general")
        self.assertIsNone(result)

    def test_unknown_route_returns_none(self) -> None:
        result = admin_runtime.persona_switch_for("nonexistent_route")
        self.assertIsNone(result)

    def test_switch_line_key_present(self) -> None:
        result = admin_runtime.persona_switch_for("code")
        self.assertIn("switch_line_key", result)


# ---------------------------------------------------------------------------
# Tests for read_json_obj() and write_json_obj()
# ---------------------------------------------------------------------------

class TestReadWriteJsonObj(unittest.TestCase):
    """read_json_obj and write_json_obj provide safe JSON file I/O."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_write_and_read_roundtrip(self) -> None:
        """Write a dict and read it back correctly."""
        path = Path(self._tmpdir) / "data.json"
        obj = {"key": "value", "number": 42}
        admin_runtime.write_json_obj(path, obj)
        result = admin_runtime.read_json_obj(path, {})
        self.assertEqual(result["key"], "value")
        self.assertEqual(result["number"], 42)

    def test_write_creates_parent_dirs(self) -> None:
        """write_json_obj creates missing parent directories."""
        path = Path(self._tmpdir) / "nested" / "dir" / "data.json"
        admin_runtime.write_json_obj(path, {"ok": True})
        self.assertTrue(path.exists())

    def test_read_missing_file_returns_default(self) -> None:
        """read_json_obj returns default when file does not exist."""
        path = Path(self._tmpdir) / "nonexistent.json"
        result = admin_runtime.read_json_obj(path, {"default": True})
        self.assertTrue(result["default"])

    def test_read_corrupt_file_returns_default(self) -> None:
        """read_json_obj returns default when file content is invalid JSON."""
        path = Path(self._tmpdir) / "corrupt.json"
        path.write_text("NOT VALID JSON {{{{", encoding="utf-8")
        result = admin_runtime.read_json_obj(path, "fallback")
        self.assertEqual(result, "fallback")

    def test_write_uses_atomic_rename(self) -> None:
        """write_json_obj writes to a temp file first, then renames atomically."""
        path = Path(self._tmpdir) / "atomic.json"
        admin_runtime.write_json_obj(path, {"v": 1})
        # The tmp file should not exist after successful write
        tmp = path.with_name(f".{path.name}.tmp")
        self.assertFalse(tmp.exists(), "Temp file must be removed after atomic rename")

    def test_write_output_is_valid_json(self) -> None:
        """write_json_obj output can be parsed as JSON."""
        path = Path(self._tmpdir) / "valid.json"
        admin_runtime.write_json_obj(path, {"list": [1, 2, 3], "nested": {"ok": True}})
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        self.assertEqual(parsed["list"], [1, 2, 3])


# ---------------------------------------------------------------------------
# Tests for nowz()
# ---------------------------------------------------------------------------

class TestNowz(unittest.TestCase):
    """nowz() returns ISO8601 UTC timestamp ending with Z."""

    def test_ends_with_z(self) -> None:
        ts = admin_runtime.nowz()
        self.assertTrue(ts.endswith("Z"), f"Expected Z suffix, got: {ts!r}")

    def test_no_microseconds(self) -> None:
        ts = admin_runtime.nowz()
        self.assertNotIn(".", ts, "nowz() must not include microseconds")

    def test_is_string(self) -> None:
        self.assertIsInstance(admin_runtime.nowz(), str)


# ---------------------------------------------------------------------------
# Tests for json_dumps()
# ---------------------------------------------------------------------------

class TestJsonDumps(unittest.TestCase):
    """json_dumps() produces pretty-printed, sorted, UTF-8 friendly JSON."""

    def test_dict_sorted_keys(self) -> None:
        result = admin_runtime.json_dumps({"z": 1, "a": 2})
        parsed = json.loads(result)
        self.assertEqual(parsed["a"], 2)
        self.assertEqual(parsed["z"], 1)
        # Check keys are sorted in the raw output
        a_idx = result.index('"a"')
        z_idx = result.index('"z"')
        self.assertLess(a_idx, z_idx)

    def test_non_ascii_preserved(self) -> None:
        result = admin_runtime.json_dumps({"msg": "привет"})
        self.assertIn("привет", result, "Non-ASCII chars must not be escaped")

    def test_is_valid_json(self) -> None:
        result = admin_runtime.json_dumps({"x": [1, 2, None]})
        parsed = json.loads(result)
        self.assertEqual(parsed["x"], [1, 2, None])


if __name__ == "__main__":
    unittest.main()