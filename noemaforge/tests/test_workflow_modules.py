#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_workflow_modules.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations
# === NoemaForge Autodoc File Header ===
# File: tests/test_workflow_modules.py
# Purpose: Validate Telegram, reading-list, selfdev, and ICS workflow modules.
# Invoked by / imported from:
#   - unittest discovery
# Output formats / side effects:
#   - unittest assertions only
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===
import os, sqlite3, sys, tempfile, unittest
ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import tg_channel_workflow, readinglist_workflow, selfdev_learning, ics_import

class WorkflowModuleTests(unittest.TestCase):
    def test_tg_channel_curate(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-tgwf-') as td:
            db = os.path.join(td, 'tg.sqlite')
            con = sqlite3.connect(db)
            con.execute('CREATE TABLE messages(chat_id TEXT, msg_id INTEGER, date TEXT, sender TEXT, text_clean TEXT)')
            con.execute('CREATE TABLE links(chat_id TEXT, msg_id INTEGER, url TEXT)')
            con.execute('INSERT INTO messages VALUES(?,?,?,?,?)', ('c1', 1, '2026-04-11T10:00:00Z', 'alice', 'Check this question? http://x'))
            con.execute('INSERT INTO links VALUES(?,?,?)', ('c1', 1, 'http://x'))
            con.commit(); con.close()
            res = tg_channel_workflow.curate_channel(index_db=db, out_dir=os.path.join(td, 'out'))
            self.assertEqual(res['count'], 1)
            self.assertTrue(os.path.exists(res['json_path']))

    def test_readinglist_and_selfdev_with_ics(self) -> None:
        with tempfile.TemporaryDirectory(prefix='noemaforge-rdwf-') as td:
            db = os.path.join(td, 'tabs.sqlite')
            con = sqlite3.connect(db)
            con.execute('CREATE TABLE tabs(url TEXT, title TEXT, source_file TEXT, added_at TEXT, last_seen_at TEXT, status TEXT)')
            con.execute('INSERT INTO tabs VALUES(?,?,?,?,?,?)', ('https://example.test/a?x=1', 'Example', 'tabs.json', '2026-04-10', '2026-04-11', 'open'))
            con.execute('INSERT INTO tabs VALUES(?,?,?,?,?,?)', ('https://example.test/a?x=2', 'Example dup', 'tabs.json', '2026-04-10', '2026-04-11', 'open'))
            con.commit(); con.close()
            queue = readinglist_workflow.build_reading_queue(index_db=db, out_dir=os.path.join(td, 'reading'))
            self.assertEqual(queue['count'], 1)
            inbox = os.path.join(td, 'selfdev_inbox'); os.makedirs(inbox, exist_ok=True)
            with open(os.path.join(inbox, 'note.txt'), 'w', encoding='utf-8') as f:
                f.write('Build stronger Trixie runbook\nRemember ffmpeg and PipeWire.')
            state_path = os.path.join(td, 'learning_state.json')
            ing = selfdev_learning.ingest_learning_items(inbox, state_path)
            self.assertGreaterEqual(ing['count'], 1)
            ics = os.path.join(td, 'events.ics')
            with open(ics, 'w', encoding='utf-8') as f:
                f.write('BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:1\nSUMMARY:Meetup\nDTSTART:20260412T180000Z\nDTEND:20260412T200000Z\nEND:VEVENT\nEND:VCALENDAR\n')
            imported = ics_import.import_ics_file(ics)
            merged = selfdev_learning.merge_calendar_events(state_path, imported['events'])
            review = selfdev_learning.build_review_queue(state_path, os.path.join(td, 'review'))
            self.assertGreaterEqual(merged['count'], 2)
            self.assertTrue(os.path.exists(review['out_path']))

if __name__ == '__main__':
    unittest.main()