"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_no_silent_noop_u002.py
Zone: tests/gui
Version: 0.33.0
Created: 2026-06-19
Purpose: Verify U-002 — no silent no-ops: every user command produces a visible
  response in chat. Covers pending indicator, ok=false-no-reply error fallback,
  and sendAdmin() wiring.
Inputs: noemaforge/templates/pipeline-dashboard/app.js.
Outputs: Pass/fail assertions.
Tests: py -3 -m unittest noemaforge/tests/test_no_silent_noop_u002.py -v
=== End NoemaForge File Header ===
"""
import re
import unittest
from pathlib import Path

DASH = Path(__file__).resolve().parents[1] / "templates" / "pipeline-dashboard"
APP_JS = DASH / "app.js"
STYLE_CSS = DASH / "style.css"


def _src():
    return APP_JS.read_text(encoding="utf-8")


class TestPendingIndicator(unittest.TestCase):
    """_addPendingBubble() creates a loading indicator that is removed on result."""

    def setUp(self):
        self.src = _src()

    def test_add_pending_bubble_declared(self):
        self.assertIn("function _addPendingBubble(", self.src)

    def test_pending_indicator_class_applied(self):
        m = re.search(r'function _addPendingBubble\(\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m, "_addPendingBubble body not found")
        body = m.group(1)
        self.assertIn("pending-indicator", body)

    def test_pending_bubble_returns_element(self):
        m = re.search(r'function _addPendingBubble\(\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("return div", body)

    def test_pending_bubble_appends_to_chat_log(self):
        m = re.search(r'function _addPendingBubble\(\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("chat-log", body)

    def test_send_admin_creates_pending_bubble(self):
        m = re.search(r'async function sendAdmin\(\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m, "sendAdmin body not found")
        body = m.group(1)
        self.assertIn("_addPendingBubble", body)

    def test_send_admin_removes_pending_on_success(self):
        m = re.search(r'async function sendAdmin\(\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("pendingBubble.remove()", body)

    def test_send_admin_removes_pending_on_error(self):
        m = re.search(r'async function sendAdmin\(\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        # Both try and catch branches must call remove
        remove_count = body.count("pendingBubble.remove()")
        self.assertGreaterEqual(remove_count, 2, "pendingBubble.remove() must appear in both success and error paths")


class TestOkFalseNoReplyFallback(unittest.TestCase):
    """absorbResult() must show an error when ok=false and no reply is present."""

    def setUp(self):
        self.src = _src()

    def test_absorb_result_has_ok_false_fallback(self):
        m = re.search(r'function absorbResult\(result\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m, "absorbResult body not found")
        body = m.group(1)
        self.assertIn("result.ok === false", body)
        # Must show an error message when ok=false and no reply
        self.assertIn("error", body.lower())

    def test_absorb_result_else_branch_for_error(self):
        m = re.search(r'function absorbResult\(result\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        # The else branch catches ok=false with no reply
        self.assertRegex(body, r'else if\s*\(result\.ok === false\)')


class TestNoSilentNoOpFallback(unittest.TestCase):
    """End-to-end: sendAdmin error path uses addMessage with error class."""

    def setUp(self):
        self.src = _src()

    def test_send_admin_catch_uses_add_message(self):
        m = re.search(r'async function sendAdmin\(\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("addMessage", body)
        self.assertIn("'error'", body)

    def test_absorb_result_always_produces_chat_entry(self):
        # Any result with ok=false + no reply must produce an entry via addMessage
        m = re.search(r'function absorbResult\(result\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        # Both reply branch and ok=false-fallback call addMessage
        add_count = body.count("addMessage")
        self.assertGreaterEqual(add_count, 2)


class TestPendingIndicatorCSS(unittest.TestCase):
    def setUp(self):
        self.css = STYLE_CSS.read_text(encoding="utf-8")

    def test_pending_indicator_class_defined(self):
        self.assertIn(".pending-indicator", self.css)

    def test_pending_dots_class_defined(self):
        self.assertIn(".pending-dots", self.css)


if __name__ == "__main__":
    unittest.main()
