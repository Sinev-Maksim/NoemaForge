"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_iteration_controls_d008.py
Zone: tests/gui
Version: 0.33.0
Created: 2026-06-20
Purpose: Verify D-008 fix — depth/iteration controls produce a visible notice
  that attaches to the next message, so the operator can see the active budget
  before sending (button label update + depth-notice element).
Inputs: Source files under noemaforge/templates/pipeline-dashboard/.
Outputs: Pass/fail assertions.
Tests: py -3 -m unittest noemaforge/tests/test_iteration_controls_d008.py -v
=== End NoemaForge File Header ===
"""
import re
import unittest
from pathlib import Path

DASH = Path(__file__).resolve().parents[1] / "templates" / "pipeline-dashboard"
APP_JS = DASH / "app.js"
INDEX_HTML = DASH / "index.html"


def _src():
    return APP_JS.read_text(encoding="utf-8")


def _html():
    return INDEX_HTML.read_text(encoding="utf-8")


class TestDepthNoticeElementExists(unittest.TestCase):
    """HTML must declare the #depth-notice element."""

    def setUp(self):
        self.html = _html()

    def test_depth_notice_element_present(self):
        self.assertIn('id="depth-notice"', self.html)

    def test_depth_notice_starts_hidden(self):
        idx = self.html.index('id="depth-notice"')
        surrounding = self.html[max(0, idx - 20):idx + 120]
        self.assertIn("hidden", surrounding)

    def test_depth_notice_has_aria_live(self):
        idx = self.html.index('id="depth-notice"')
        surrounding = self.html[max(0, idx - 20):idx + 120]
        self.assertIn("aria-live", surrounding)

    def test_depth_notice_after_depth_controls(self):
        controls_idx = self.html.index('class="depth-controls"')
        notice_idx = self.html.index('id="depth-notice"')
        self.assertGreater(notice_idx, controls_idx,
                           "depth-notice must appear after depth-controls")


class TestUpdateDepthNoticeFunction(unittest.TestCase):
    """_updateDepthNotice() must exist and implement the notice logic."""

    def setUp(self):
        self.src = _src()

    def test_function_declared(self):
        self.assertIn("function _updateDepthNotice(", self.src)

    def test_reads_depth_steps(self):
        m = re.search(r'function _updateDepthNotice\(\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m, "_updateDepthNotice body not found")
        body = m.group(1)
        self.assertIn("depth-steps", body)

    def test_reads_depth_minutes(self):
        m = re.search(r'function _updateDepthNotice\(\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("depth-minutes", body)

    def test_reads_until_stop(self):
        m = re.search(r'function _updateDepthNotice\(\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("depth-until-stop", body)

    def test_shows_notice_element(self):
        m = re.search(r'function _updateDepthNotice\(\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("depth-notice", body)
        self.assertIn("hidden", body)

    def test_updates_send_button_label(self):
        m = re.search(r'function _updateDepthNotice\(\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("admin-send", body)

    def test_mentions_steps_in_notice(self):
        m = re.search(r'function _updateDepthNotice\(\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("step", body)

    def test_mentions_until_stopped_in_notice(self):
        m = re.search(r'function _updateDepthNotice\(\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("until stop", body)

    def test_resets_send_label_when_no_budget(self):
        m = re.search(r'function _updateDepthNotice\(\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("chat.send", body)


class TestDepthNoticeEventListeners(unittest.TestCase):
    """depth controls must trigger _updateDepthNotice on change/input."""

    def setUp(self):
        self.src = _src()

    def test_steps_input_wired(self):
        self.assertIn("depth-steps", self.src)
        idx = self.src.find("depth-steps")
        while idx != -1:
            region = self.src[idx:idx + 80]
            if "_updateDepthNotice" in region:
                return
            idx = self.src.find("depth-steps", idx + 1)
        # Check globally: there should be an addEventListener for depth-steps
        self.assertIn("depth-steps", self.src)
        # Verify the update function is called in proximity to depth-steps listener
        listener_idx = self.src.find("'depth-steps'")
        if listener_idx == -1:
            listener_idx = self.src.find('"depth-steps"')
        self.assertGreater(listener_idx, 0, "depth-steps element reference not found")
        nearby = self.src[listener_idx:listener_idx + 100]
        self.assertIn("_updateDepthNotice", nearby)

    def test_minutes_input_wired(self):
        # Multiple occurrences of 'depth-minutes' exist; find the addEventListener one
        idx = 0
        found = False
        while True:
            pos = self.src.find("depth-minutes", idx)
            if pos == -1:
                break
            region = self.src[pos:pos + 120]
            if "addEventListener" in region or "_updateDepthNotice" in region:
                found = True
                break
            idx = pos + 1
        self.assertTrue(found, "No addEventListener wiring _updateDepthNotice found near depth-minutes")

    def test_until_stop_wired(self):
        listener_idx = self.src.find("'depth-until-stop'")
        if listener_idx == -1:
            listener_idx = self.src.find('"depth-until-stop"')
        self.assertGreater(listener_idx, 0)
        nearby = self.src[listener_idx:listener_idx + 100]
        self.assertIn("_updateDepthNotice", nearby)


class TestDepthNoticeCSS(unittest.TestCase):
    """style.css must define .depth-notice."""

    def setUp(self):
        self.css = (DASH / "style.css").read_text(encoding="utf-8")

    def test_depth_notice_class_defined(self):
        self.assertIn(".depth-notice", self.css)

    def test_depth_notice_has_color(self):
        idx = self.css.find(".depth-notice")
        self.assertGreater(idx, 0)
        block = self.css[idx:idx + 200]
        self.assertIn("color", block)


if __name__ == "__main__":
    unittest.main()
