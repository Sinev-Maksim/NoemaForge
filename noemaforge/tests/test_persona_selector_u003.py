"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_persona_selector_u003.py
Zone: tests/gui
Version: 0.33.0
Created: 2026-06-20
Purpose: Verify U-003 fix — explicit persona selector in topbar, persona switch
  logged to chat, and completion offers return-to-admin button.
Inputs: Source files under noemaforge/templates/pipeline-dashboard/ and
  noemaforge/src/admin_gui_routes/session_routes.py.
Outputs: Pass/fail assertions.
Tests: py -3 -m unittest noemaforge/tests/test_persona_selector_u003.py -v
=== End NoemaForge File Header ===
"""
import ast
import re
import unittest
from pathlib import Path

DASH = Path(__file__).resolve().parents[1] / "templates" / "pipeline-dashboard"
APP_JS = DASH / "app.js"
INDEX_HTML = DASH / "index.html"
ROUTES_PY = Path(__file__).resolve().parents[1] / "src" / "admin_gui_routes" / "session_routes.py"
SERVER_PY = Path(__file__).resolve().parents[1] / "src" / "admin_gui_server.py"


def _src():
    return APP_JS.read_text(encoding="utf-8")


def _html():
    return INDEX_HTML.read_text(encoding="utf-8")


class TestPersonaSelectorHTML(unittest.TestCase):
    """HTML must declare the persona selector element in the topbar."""

    def setUp(self):
        self.html = _html()

    def test_persona_select_element_present(self):
        self.assertIn('id="persona-select"', self.html)

    def test_persona_select_in_toolbar(self):
        toolbar_start = self.html.index('class="toolbar"')
        select_idx = self.html.index('id="persona-select"')
        self.assertGreater(select_idx, toolbar_start, "persona-select must be inside .toolbar")

    def test_persona_select_before_device_policy(self):
        select_idx = self.html.index('id="persona-select"')
        device_idx = self.html.index('id="device-policy"')
        self.assertLess(select_idx, device_idx, "persona-select should appear before device-policy")


class TestPersonaRoleMap(unittest.TestCase):
    """_PERSONA_ROLE_TO_NAME must map known role_keys to display names."""

    def setUp(self):
        self.src = _src()

    def test_role_map_declared(self):
        self.assertIn("_PERSONA_ROLE_TO_NAME", self.src)

    def test_admin_role_mapped(self):
        self.assertIn("operator.admin/administrator", self.src)
        self.assertIn("'Admin'", self.src)

    def test_dev_team_role_mapped(self):
        self.assertIn("dev.work/dev", self.src)
        self.assertIn("'Dev Team'", self.src)

    def test_optimizer_role_mapped(self):
        self.assertIn("system.guard/sr", self.src)
        self.assertIn("'Optimizer'", self.src)


class TestLoadPersonaSelect(unittest.TestCase):
    """_loadPersonaSelect() must fetch catalog and populate the select."""

    def setUp(self):
        self.src = _src()
        m = re.search(
            r'async function _loadPersonaSelect\(\)\s*\{(.+?)^\}',
            self.src, re.DOTALL | re.MULTILINE
        )
        self.body = m.group(1) if m else self.src

    def test_function_declared(self):
        self.assertIn("async function _loadPersonaSelect(", self.src)

    def test_fetches_persona_catalog(self):
        self.assertIn("/api/persona/catalog", self.body)

    def test_populates_select_options(self):
        self.assertIn("persona-select", self.body)
        # Options built via DOM (createElement+textContent), not innerHTML
        self.assertIn("createElement('option')", self.body.replace(" ", "").replace('"', "'"))

    def test_wires_onchange_to_switchpersona(self):
        self.assertIn("switchPersona", self.body)
        self.assertIn("onchange", self.body)

    def test_calls_update_select_after_load(self):
        self.assertIn("_updatePersonaSelect", self.body)


class TestUpdatePersonaSelect(unittest.TestCase):
    """_updatePersonaSelect(name) must sync the select value."""

    def setUp(self):
        self.src = _src()

    def test_function_declared(self):
        self.assertIn("function _updatePersonaSelect(", self.src)

    def test_iterates_options(self):
        m = re.search(
            r'function _updatePersonaSelect\(.+?\)\s*\{(.+?)^\}',
            self.src, re.DOTALL | re.MULTILINE
        )
        body = m.group(1) if m else self.src
        self.assertIn("options", body)
        self.assertIn(".selected", body)


class TestSwitchPersonaFunction(unittest.TestCase):
    """switchPersona(name) must POST to /api/persona/switch and update the UI."""

    def setUp(self):
        self.src = _src()
        m = re.search(
            r'async function switchPersona\(.+?\)\s*\{(.+?)^\}',
            self.src, re.DOTALL | re.MULTILINE
        )
        self.body = m.group(1) if m else self.src

    def test_function_declared(self):
        self.assertIn("async function switchPersona(", self.src)

    def test_posts_to_switch_endpoint(self):
        self.assertIn("/api/persona/switch", self.body)

    def test_calls_setpersona_on_success(self):
        self.assertIn("setPersona", self.body)

    def test_calls_update_select(self):
        self.assertIn("_updatePersonaSelect", self.body)

    def test_adds_system_line_on_switch(self):
        self.assertIn("addSystemLine", self.body)
        self.assertIn("switch_line", self.body)

    def test_offers_return_to_admin(self):
        self.assertIn("_addReturnToAdminLine", self.body)

    def test_return_to_admin_conditional_not_admin(self):
        """Must only add return-to-admin when new persona is not Admin."""
        self.assertIn("!== 'Admin'", self.body)


class TestReturnToAdminLine(unittest.TestCase):
    """_addReturnToAdminLine() must add a Return to Admin button to chat."""

    def setUp(self):
        self.src = _src()
        m = re.search(
            r'function _addReturnToAdminLine\(\)\s*\{(.+?)^\}',
            self.src, re.DOTALL | re.MULTILINE
        )
        self.body = m.group(1) if m else self.src

    def test_function_declared(self):
        self.assertIn("function _addReturnToAdminLine(", self.src)

    def test_creates_button(self):
        self.assertIn("createElement", self.body)
        self.assertIn("button", self.body.lower())

    def test_button_calls_switch_persona_admin(self):
        self.assertIn("switchPersona('Admin')", self.body)

    def test_appends_to_chat_log(self):
        self.assertIn("chat-log", self.body)
        self.assertIn("appendChild", self.body)

    def test_return_label_present(self):
        self.assertIn("Return to Admin", self.body)


class TestAbsorbResultUpdatesPersona(unittest.TestCase):
    """absorbResult() must sync persona selector and show return button on pipeline switch."""

    def setUp(self):
        self.src = _src()
        m = re.search(
            r'function absorbResult\(.+?\)\s*\{(.+?)^\}',
            self.src, re.DOTALL | re.MULTILINE
        )
        self.body = m.group(1) if m else self.src

    def test_absorb_calls_update_select(self):
        self.assertIn("_updatePersonaSelect", self.body)

    def test_absorb_calls_return_to_admin(self):
        self.assertIn("_addReturnToAdminLine", self.body)


class TestPersonaSwitchLoaded(unittest.TestCase):
    """startup() must call _loadPersonaSelect() as part of initial load."""

    def setUp(self):
        self.src = _src()
        start = self.src.index("async function startup()")
        end = self.src.index("if (typeof window", start)
        self.startup = self.src[start:end]

    def test_startup_calls_load_persona_select(self):
        idx = self.startup.find("Promise.allSettled")
        self.assertGreater(idx, 0)
        surrounding = self.startup[idx: idx + 500]
        self.assertIn("_loadPersonaSelect", surrounding)


class TestBackendPersonaSwitch(unittest.TestCase):
    """Backend: persona_switch method must exist in admin_gui_server.py."""

    def setUp(self):
        self.src = SERVER_PY.read_text(encoding="utf-8")

    def test_persona_switch_method_declared(self):
        self.assertIn("def persona_switch(self, name:", self.src)

    def test_saves_switch_line_message(self):
        m = re.search(
            r'def persona_switch\(self, name.+?\n    def ',
            self.src, re.DOTALL
        )
        body = m.group(0) if m else self.src
        self.assertIn("save_message", body)
        self.assertIn("persona_switch", body)

    def test_returns_switch_line(self):
        m = re.search(
            r'def persona_switch\(self, name.+?\n    def ',
            self.src, re.DOTALL
        )
        body = m.group(0) if m else self.src
        self.assertIn("switch_line", body)

    def test_returns_portrait_url(self):
        m = re.search(
            r'def persona_switch\(self, name.+?\n    def ',
            self.src, re.DOTALL
        )
        body = m.group(0) if m else self.src
        self.assertIn("portrait_url", body)

    def test_noop_when_same_persona(self):
        m = re.search(
            r'def persona_switch\(self, name.+?\n    def ',
            self.src, re.DOTALL
        )
        body = m.group(0) if m else self.src
        self.assertIn("prev == name", body)


class TestBackendPersonaSwitchRoute(unittest.TestCase):
    """session_routes.py must expose POST /api/persona/switch."""

    def setUp(self):
        self.src = ROUTES_PY.read_text(encoding="utf-8")

    def test_switch_handler_declared(self):
        self.assertIn("def persona_switch(", self.src)

    def test_route_registered(self):
        self.assertIn("/api/persona/switch", self.src)

    def test_calls_server_persona_switch(self):
        self.assertIn("server.persona_switch", self.src)


if __name__ == "__main__":
    unittest.main()
