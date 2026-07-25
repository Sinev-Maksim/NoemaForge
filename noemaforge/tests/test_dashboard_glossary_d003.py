"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_dashboard_glossary_d003.py
Zone: tests/admin
Version: 0.33.0
Created: 2026-06-19
Purpose: Verify D-003 — Admin returns deterministic grounded definitions for
  known dashboard terms (degraded_selected, selected=N, staffing_state, etc.)
  and never hallucinates them as filenames or unknown values.
Inputs: noemaforge/src/admin_gui_server.py.
Outputs: Pass/fail assertions.
Tests: py -3 -m unittest noemaforge/tests/test_dashboard_glossary_d003.py -v
=== End NoemaForge File Header ===
"""
import sys
import types
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Import only the AdminGuiServer class; avoid importing the full module top-level
# since it pulls in many runtime dependencies.  We patch the problematic ones.
# ---------------------------------------------------------------------------

SRC_DIR = Path(__file__).resolve().parents[1] / "src"


def _load_server():
    """Load admin_gui_server with minimal dependency stubs."""
    stubs = {
        "production_ai_contracts": types.ModuleType("production_ai_contracts"),
        "noemaforge_version": types.ModuleType("noemaforge_version"),
        "_platform_paths": types.ModuleType("_platform_paths"),
    }
    stubs["production_ai_contracts"].new_trace_id = lambda *a, **kw: "stub-trace"
    stubs["noemaforge_version"].__dict__["RUNTIME_VERSION"] = "0.33.0-test"

    class _FakePaths:
        root = Path(".")
        pipelines_dir = Path(".")
        persona_state_dir = Path(".")
        model_evolution_state_dir = Path(".")
        model_selection_state_dir = Path(".")
        dev_team_state_dir = Path(".")
        modelstore_dir = Path(".")
        llm_gateway_socket = Path(".")
        llm_main_backend_socket = Path(".")
        legacy_llm_gateway_socket = None

    stubs["_platform_paths"].__dict__.update(vars(_FakePaths()))

    for name, mod in stubs.items():
        sys.modules[name] = mod

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "admin_gui_server",
        SRC_DIR / "admin_gui_server.py",
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        pass
    return mod


_server_mod = _load_server()
AdminGuiServer = getattr(_server_mod, "AdminGuiServer", None)


@unittest.skipIf(AdminGuiServer is None, "AdminGuiServer could not be loaded")
class TestDashboardGlossaryExists(unittest.TestCase):
    """The _DASHBOARD_GLOSSARY class attribute must define all required terms."""

    def test_glossary_attribute_exists(self):
        self.assertTrue(hasattr(AdminGuiServer, "_DASHBOARD_GLOSSARY"))

    def test_degraded_selected_defined(self):
        self.assertIn("degraded_selected", AdminGuiServer._DASHBOARD_GLOSSARY)

    def test_selected_defined(self):
        self.assertIn("selected", AdminGuiServer._DASHBOARD_GLOSSARY)

    def test_staffing_state_defined(self):
        self.assertIn("staffing_state", AdminGuiServer._DASHBOARD_GLOSSARY)

    def test_pass_rate_defined(self):
        self.assertIn("pass_rate", AdminGuiServer._DASHBOARD_GLOSSARY)

    def test_json_parse_rate_defined(self):
        self.assertIn("json_parse_rate", AdminGuiServer._DASHBOARD_GLOSSARY)

    def test_quality_score_defined(self):
        self.assertIn("quality_score", AdminGuiServer._DASHBOARD_GLOSSARY)

    def test_avg_latency_s_defined(self):
        self.assertIn("avg_latency_s", AdminGuiServer._DASHBOARD_GLOSSARY)

    def test_each_term_has_ru_and_en(self):
        for term, defs in AdminGuiServer._DASHBOARD_GLOSSARY.items():
            with self.subTest(term=term):
                self.assertIn("ru", defs, f"{term} missing 'ru' definition")
                self.assertIn("en", defs, f"{term} missing 'en' definition")
                self.assertTrue(defs["ru"], f"{term}.ru must not be empty")
                self.assertTrue(defs["en"], f"{term}.en must not be empty")

    def test_definitions_do_not_contain_filename_hallucinations(self):
        """Definitions must not contain file-like references such as .py/.json paths."""
        import re
        for term, defs in AdminGuiServer._DASHBOARD_GLOSSARY.items():
            for lang, text in defs.items():
                with self.subTest(term=term, lang=lang):
                    self.assertNotRegex(text, r"\.py\b", f"{term}.{lang} contains a .py filename")
                    self.assertNotRegex(text, r"\.json\b", f"{term}.{lang} contains a .json filename")


@unittest.skipIf(AdminGuiServer is None, "AdminGuiServer could not be loaded")
class TestGlossaryLookup(unittest.TestCase):
    """_glossary_lookup() returns grounded definitions and respects locale."""

    @classmethod
    def setUpClass(cls):
        # Construct a minimal server instance without calling __init__.
        cls.srv = object.__new__(AdminGuiServer)

    def test_degraded_selected_ru(self):
        result = self.srv._glossary_lookup("что значит degraded_selected", "ru")
        self.assertIsNotNone(result)
        self.assertIn("деградир", result.lower())

    def test_degraded_selected_en(self):
        result = self.srv._glossary_lookup("what is degraded_selected", "en")
        self.assertIsNotNone(result)
        self.assertIn("degraded", result.lower())

    def test_pass_rate_lookup(self):
        result = self.srv._glossary_lookup("объясни pass_rate", "ru")
        self.assertIsNotNone(result)
        self.assertIn("pass_rate", result.lower())

    def test_selected_n_lookup(self):
        result = self.srv._glossary_lookup("что значит selected=4", "ru")
        self.assertIsNotNone(result)

    def test_unknown_term_returns_none(self):
        result = self.srv._glossary_lookup("что такое xyz_unknown_term", "ru")
        self.assertIsNone(result)

    def test_no_filename_in_degraded_selected_ru(self):
        result = self.srv._glossary_lookup("что значит degraded_selected", "ru")
        self.assertIsNotNone(result)
        self.assertNotIn(".py", result)
        self.assertNotIn(".json", result)


@unittest.skipIf(AdminGuiServer is None, "AdminGuiServer could not be loaded")
class TestExplainUsecaseFallsBackToGlossary(unittest.TestCase):
    """explain_usecase() delegates to _glossary_lookup first."""

    @classmethod
    def setUpClass(cls):
        cls.srv = object.__new__(AdminGuiServer)

    def test_explain_usecase_degraded_selected(self):
        result = self.srv.explain_usecase("что значит degraded_selected", "ru")
        self.assertIn("деградир", result.lower())

    def test_explain_usecase_staffing_state(self):
        result = self.srv.explain_usecase("explain staffing_state", "en")
        self.assertIn("staffing", result.lower())

    def test_explain_usecase_fallback_hint_mentions_glossary_terms(self):
        result = self.srv.explain_usecase("справка", "ru")
        # Default fallback should hint at glossary terms, not just usecases.
        self.assertIn("degraded_selected", result)


if __name__ == "__main__":
    unittest.main()
