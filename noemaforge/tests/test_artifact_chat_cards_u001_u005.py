"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_artifact_chat_cards_u001_u005.py
Zone: tests/gui
Version: 0.33.0
Created: 2026-06-19
Purpose: Verify U-001/U-005 — artifact metadata returned by the API is rendered
  as result cards with open/download/copy actions inline in the chat log.
  Also verifies the U-002 no-silent-no-op fallback: ok=false without a reply
  shows a readable error message.
Inputs: Source file noemaforge/templates/pipeline-dashboard/app.js.
Outputs: Pass/fail assertions.
Tests: py -3 -m unittest noemaforge/tests/test_artifact_chat_cards_u001_u005.py -v
=== End NoemaForge File Header ===
"""
import re
import unittest
from pathlib import Path

APP_JS = (Path(__file__).resolve().parents[1]
          / "templates" / "pipeline-dashboard" / "app.js")


def _src():
    return APP_JS.read_text(encoding="utf-8")


class TestArtifactChatCardHelper(unittest.TestCase):
    """_artifactChatCard() builds a DOM element with open/download/copy actions."""

    def setUp(self):
        self.src = _src()

    def test_helper_declared(self):
        self.assertIn("function _artifactChatCard(", self.src)

    def test_artifact_inline_card_class(self):
        m = re.search(r'function _artifactChatCard\(a\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m, "_artifactChatCard body not found")
        body = m.group(1)
        self.assertIn("artifact-inline-card", body)

    def test_open_button_in_card(self):
        m = re.search(r'function _artifactChatCard\(a\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("data-inline-open", body)

    def test_copy_button_in_card(self):
        m = re.search(r'function _artifactChatCard\(a\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("data-inline-copy", body)

    def test_download_link_in_card(self):
        m = re.search(r'function _artifactChatCard\(a\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("download", body)
        self.assertIn("artifactDownloadUrl", body)

    def test_open_handler_calls_api(self):
        m = re.search(r'function _artifactChatCard\(a\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("artifactPreviewUrl", body)
        self.assertIn("showModal", body)

    def test_copy_handler_uses_clipboard(self):
        m = re.search(r'function _artifactChatCard\(a\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("navigator.clipboard", body)

    def test_htmlescape_used_for_label(self):
        m = re.search(r'function _artifactChatCard\(a\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("htmlEscape", body)

    def test_no_innerhtml_on_artifact_path(self):
        # path text must be htmlEscaped before being written to innerHTML.
        m = re.search(r'function _artifactChatCard\(a\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("htmlEscape(artifactPath", body)


class TestPostArtifactsToChat(unittest.TestCase):
    """postArtifactsToChat() appends artifact cards into the chat log."""

    def setUp(self):
        self.src = _src()

    def test_function_declared(self):
        self.assertIn("function postArtifactsToChat(", self.src)

    def test_appends_to_chat_log(self):
        m = re.search(r'function postArtifactsToChat\(artifacts\)\s*\{(.+?)\n\}',
                      self.src, re.DOTALL)
        self.assertIsNotNone(m, "postArtifactsToChat body not found")
        body = m.group(1)
        self.assertIn("chat-log", body)
        self.assertIn("_artifactChatCard", body)

    def test_scrolls_to_bottom(self):
        m = re.search(r'function postArtifactsToChat\(artifacts\)\s*\{(.+?)\n\}',
                      self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("scrollTop", body)

    def test_guards_empty_array(self):
        m = re.search(r'function postArtifactsToChat\(artifacts\)\s*\{(.+?)\n\}',
                      self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("!artifacts.length", body)


class TestAbsorbResultCallsPostArtifacts(unittest.TestCase):
    """absorbResult() calls postArtifactsToChat when artifacts are present."""

    def setUp(self):
        self.src = _src()

    def test_absorb_calls_post_artifacts(self):
        m = re.search(r'function absorbResult\(result\)\s*\{(.+?)\n\}',
                      self.src, re.DOTALL)
        self.assertIsNotNone(m, "absorbResult body not found")
        body = m.group(1)
        self.assertIn("postArtifactsToChat", body)

    def test_absorb_also_calls_render_artifacts(self):
        m = re.search(r'function absorbResult\(result\)\s*\{(.+?)\n\}',
                      self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("renderArtifacts", body)

    def test_render_and_post_in_same_branch(self):
        # Both calls must be guarded by the same Array.isArray check.
        m = re.search(r'if\(Array\.isArray\(result\.artifacts\)\)\s*\{(.+?)\}',
                      self.src, re.DOTALL)
        self.assertIsNotNone(m, "Array.isArray(result.artifacts) guard not found")
        branch = m.group(1)
        self.assertIn("renderArtifacts", branch)
        self.assertIn("postArtifactsToChat", branch)


class TestNoSilentNoOpFallback(unittest.TestCase):
    """U-002 aspect: ok=false without a reply shows a readable error in chat."""

    def setUp(self):
        self.src = _src()

    def test_ok_false_no_reply_shows_error(self):
        m = re.search(r'function absorbResult\(result\)\s*\{(.+?)\n\}',
                      self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("result.ok === false", body)
        # Must call addMessage with an error string when no reply is present.
        self.assertIn("Error:", body)


if __name__ == "__main__":
    unittest.main()
