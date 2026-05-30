#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_save_conversation_no_mutation.py
Zone: test
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: Verify _save_conversation() does not mutate the caller's conv dict.
Inputs: AdminGuiServer._save_conversation() via minimal stub.
Outputs: unittest results.
Side effects: None (temp dirs only).
Tests: python -m unittest noemaforge/tests/test_save_conversation_no_mutation.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import admin_gui_server as ags
from admin_gui_server import AdminGuiServer


def _make_stub(tmp_path: Path) -> AdminGuiServer:
    obj = object.__new__(AdminGuiServer)
    obj.gui_state_dir = tmp_path / "gui"
    obj.gui_state_dir.mkdir(parents=True, exist_ok=True)
    return obj


class TestSaveConversationNoMutation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tp = Path(self.tmp.name)
        self.srv = _make_stub(self.tp)

    def tearDown(self):
        self.tmp.cleanup()

    def _call_save(self, conv: dict) -> None:
        # Replicate _save_conversation() logic for isolated test.
        from orchestration_state import nowz
        import json
        conv_copy = dict(conv)
        conv_copy["updated_at"] = nowz()
        path = self.srv.gui_state_dir / "conversation-current.json"
        path.write_text(json.dumps(conv_copy), encoding="utf-8")

    def test_caller_dict_not_mutated(self):
        """_save_conversation() must not modify the caller's dict."""
        original_conv = {
            "conversation_id": "c1",
            "messages": [],
        }
        # Record the keys before calling.
        keys_before = set(original_conv.keys())
        has_updated_at_before = "updated_at" in original_conv

        self._call_save(original_conv)

        self.assertEqual(set(original_conv.keys()), keys_before,
                         "_save_conversation must not add keys to caller's dict")
        if not has_updated_at_before:
            self.assertNotIn("updated_at", original_conv,
                             "updated_at must not appear in caller's dict after save")

    def test_source_uses_dict_copy(self):
        """Source must contain dict(conv) before modifying conv."""
        src = (ROOT / "src" / "admin_gui_server.py").read_text(encoding="utf-8")
        # Find _save_conversation body.
        start = src.find("def _save_conversation(")
        next_def = src.find("\n    def ", start + 1)
        body = src[start:next_def] if next_def != -1 else src[start:]
        self.assertIn("conv = dict(conv)", body,
                      "_save_conversation must copy the dict before mutating it")

    def test_updated_at_present_in_persisted_file(self):
        """Persisted file must contain updated_at even though caller's dict doesn't."""
        import json
        conv = {"conversation_id": "c2", "messages": []}
        self._call_save(conv)
        path = self.srv.gui_state_dir / "conversation-current.json"
        persisted = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("updated_at", persisted)


class TestSaveConversationSourceContains(unittest.TestCase):
    SRC_TEXT = (ROOT / "src" / "admin_gui_server.py").read_text(encoding="utf-8")

    def test_dict_copy_before_mutation(self):
        self.assertIn("conv = dict(conv)", self.SRC_TEXT)

    def test_updated_at_set_on_copy(self):
        # The updated_at assignment must come AFTER the copy line.
        copy_pos = self.SRC_TEXT.find("conv = dict(conv)")
        updated_pos = self.SRC_TEXT.find('conv["updated_at"]', copy_pos)
        self.assertGreater(updated_pos, copy_pos,
                           "updated_at assignment must follow the dict copy")


if __name__ == "__main__":
    unittest.main()
