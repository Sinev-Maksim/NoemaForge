"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_confirm_d005.py
Zone: tests/gui
Version: 0.33.0
Created: 2026-06-19
Purpose: Verify D-005 fix — pipeline launch dialog inserts request into chat input
  instead of calling prompt() and sending directly via /api/pipeline/run.
Inputs: Source files under noemaforge/templates/pipeline-dashboard/.
Outputs: Pass/fail assertions.
Tests: py -3 -m unittest noemaforge/tests/test_pipeline_confirm_d005.py -v
=== End NoemaForge File Header ===
"""
import re
import unittest
from pathlib import Path

DASH = Path(__file__).resolve().parents[1] / "templates" / "pipeline-dashboard"
APP_JS = DASH / "app.js"
INDEX_HTML = DASH / "index.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestPipelineConfirmDialogExists(unittest.TestCase):
    """HTML must declare all elements the D-005 confirm dialog needs."""

    def setUp(self):
        self.html = _read(INDEX_HTML)

    def test_confirm_overlay_element(self):
        self.assertIn('id="pipeline-confirm"', self.html)

    def test_confirm_title_element(self):
        self.assertIn('id="pipeline-confirm-title"', self.html)

    def test_confirm_desc_element(self):
        self.assertIn('id="pipeline-confirm-desc"', self.html)

    def test_confirm_request_textarea(self):
        self.assertIn('id="pipeline-confirm-req"', self.html)

    def test_confirm_ok_button(self):
        self.assertIn('id="pipeline-confirm-ok"', self.html)
        self.assertIn("Insert request", self.html)

    def test_confirm_cancel_button(self):
        self.assertIn('id="pipeline-confirm-cancel"', self.html)

    def test_confirm_close_button(self):
        self.assertIn('id="pipeline-confirm-close"', self.html)

    def test_dialog_starts_hidden(self):
        # The overlay must start hidden so it doesn't block the UI.
        idx = self.html.index('id="pipeline-confirm"')
        surrounding = self.html[max(0, idx - 10):idx + 100]
        self.assertIn("hidden", surrounding)


class TestStartPipelineNoLongerCallsPrompt(unittest.TestCase):
    """startPipeline() must not use prompt() — D-005 requires the dialog instead."""

    def setUp(self):
        self.src = _read(APP_JS)

    def test_startpipeline_no_prompt(self):
        # Extract the startPipeline function body (up to the closing brace).
        m = re.search(r'function startPipeline\(id\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m, "startPipeline function not found")
        body = m.group(1)
        self.assertNotIn("prompt(", body, "startPipeline must not use prompt()")

    def test_startpipeline_shows_confirm_dialog(self):
        m = re.search(r'function startPipeline\(id\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m, "startPipeline function not found")
        body = m.group(1)
        self.assertIn("pipeline-confirm", body,
                      "startPipeline must reference the confirm dialog")

    def test_startpipeline_not_async(self):
        # No direct API call means no need for async.
        self.assertNotIn("async function startPipeline", self.src,
                         "startPipeline should not be async (no direct API call)")

    def test_startpipeline_no_direct_api_call(self):
        m = re.search(r'function startPipeline\(id\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m, "startPipeline function not found")
        body = m.group(1)
        self.assertNotIn("/api/pipeline/run", body,
                         "startPipeline must not call /api/pipeline/run directly")


class TestConfirmOkInsertsIntoChat(unittest.TestCase):
    """OK handler must populate #admin-message, not fire an API call."""

    def setUp(self):
        self.src = _read(APP_JS)

    def test_ok_handler_sets_admin_message_value(self):
        # OK handler must assign to admin-message.value.
        self.assertIn("admin-message", self.src)
        # Find the ok click handler block.
        ok_idx = self.src.find("pipeline-confirm-ok")
        self.assertGreater(ok_idx, 0)
        region = self.src[ok_idx: ok_idx + 500]
        self.assertIn("stagePipelineRequestFromConfirm", region,
                      "OK handler must stage the request into the chat composer")
        helper_idx = self.src.find("function stagePipelineRequestFromConfirm")
        self.assertGreater(helper_idx, 0)
        helper = self.src[helper_idx: helper_idx + 500]
        self.assertIn("admin-message", helper,
                      "OK helper must reference admin-message")
        self.assertIn(".value", helper,
                      "OK handler must set .value on admin-message")
        self.assertIn("addMessage", helper,
                      "OK handler must show a visible confirmation")

    def test_ok_handler_no_direct_api_run(self):
        ok_idx = self.src.find("pipeline-confirm-ok")
        region = self.src[ok_idx: ok_idx + 500]
        self.assertNotIn("/api/pipeline/run", region,
                         "OK handler must not call /api/pipeline/run")
        self.assertNotIn("runPipelineDirect", region,
                         "OK handler must not start the pipeline directly")

    def test_cancel_handler_closes_dialog(self):
        cancel_idx = self.src.find("pipeline-confirm-cancel")
        self.assertGreater(cancel_idx, 0)
        region = self.src[cancel_idx: cancel_idx + 200]
        self.assertIn("_closePipelineConfirm", region)

    def test_escape_key_closes_dialog(self):
        self.assertIn("Escape", self.src)
        self.assertIn("_closePipelineConfirm", self.src)


if __name__ == "__main__":
    unittest.main()
