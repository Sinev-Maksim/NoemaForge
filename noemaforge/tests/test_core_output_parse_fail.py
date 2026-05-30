#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_core_output_parse_fail.py
Zone: test
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: TDD tests verifying that _run_role_compute() surfaces the exception from
  _load_json() via _write_event() instead of silently discarding it.
  Before the fix, 'except Exception as e: res = None' in noemaforge_core.py
  around line 2117 silently swallowed parse failures; callers received (None, out)
  with no indication of whether parsing failed or returned None by design.
Inputs: noemaforge_core._run_role_compute (via patching), noemaforge_core source text.
Outputs: test pass/fail.
Side effects: None (all I/O is patched or source-text only).
Tests: python noemaforge/tests/test_core_output_parse_fail.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


class TestSourceContainsEventOnParseFailure(unittest.TestCase):
    """Source-text assertions: _write_event must be called when _load_json raises."""

    def setUp(self) -> None:
        src_path = Path(__file__).parent.parent / "src" / "noemaforge_core.py"
        self._src = src_path.read_text(encoding="utf-8")

    def _run_role_compute_body(self) -> str:
        """Extract the body of _run_role_compute() from source."""
        start = self._src.index("def _run_role_compute(")
        # The next top-level def ends the function
        rest = self._src[start:]
        # Find the next def at the same indent level
        import re
        m = re.search(r"\ndef [a-zA-Z_]", rest[1:])
        end = start + 1 + (m.start() if m else len(rest) - 1)
        return self._src[start:end]

    def test_write_event_called_in_except_block(self) -> None:
        """_write_event is called inside the except block after _load_json fails."""
        body = self._run_role_compute_body()
        # The except block must contain _write_event
        # Check that within the except clause there is a _write_event call
        self.assertIn("ROLE_OUTPUT_PARSE_FAILED", body)

    def test_error_included_in_write_event_extra(self) -> None:
        """`error` key with str(e) is passed to _write_event extra."""
        body = self._run_role_compute_body()
        self.assertIn('"error"', body)
        self.assertIn("str(e)", body)

    def test_run_id_included_in_write_event_extra(self) -> None:
        """`run_id` is included so the event can be correlated with the run."""
        body = self._run_role_compute_body()
        self.assertIn('"run_id"', body)

    def test_res_still_set_to_none(self) -> None:
        """res is still set to None after the exception — non-fatal change."""
        body = self._run_role_compute_body()
        # The except block must still set res = None
        self.assertIn("res = None", body)

    def test_severity_s2(self) -> None:
        """Event severity is 'S2' matching the ROLE_RUN_FAILED pattern."""
        body = self._run_role_compute_body()
        # Find the ROLE_OUTPUT_PARSE_FAILED call and check severity nearby
        idx = body.index("ROLE_OUTPUT_PARSE_FAILED")
        snippet = body[max(0, idx - 200):idx + 50]
        self.assertIn('"S2"', snippet)


@unittest.skipUnless(sys.platform != "win32", "noemaforge_core requires fcntl (Linux only)")
class TestRunRoleComputeFiresEventOnBadJson(unittest.TestCase):
    """Functional test: _run_role_compute fires ROLE_OUTPUT_PARSE_FAILED when out_path is invalid JSON.

    Skipped on Windows because noemaforge_core.py imports seclog.py which
    requires fcntl (POSIX only).  Runs on the production host (BigBro-BOS/Linux).
    """

    def test_event_fired_on_invalid_json_output(self) -> None:
        """When _load_json raises, _write_event is called with ROLE_OUTPUT_PARSE_FAILED."""
        import tempfile
        import os

        # Lazily import to avoid side effects at module level.
        import noemaforge_core as core

        events: list = []

        def mock_write_event(severity, typ, actor, decision, **kwargs):
            events.append({"severity": severity, "type": typ, "actor": actor, "decision": decision, **kwargs})

        # Build a minimal RunSpec-like stub and patch the heavy machinery.
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "role_result.json")
            # Write invalid JSON to trigger _load_json failure.
            with open(out_path, "w") as f:
                f.write("{invalid json!!!")
            context_path = os.path.join(tmp, "context.json")
            import json
            with open(context_path, "w") as f:
                json.dump({}, f)

            with patch.object(core, "_write_event", side_effect=mock_write_event), \
                 patch.object(core, "run_role", return_value=(True, "runner-ok")), \
                 patch.object(core, "_issue_role_token", return_value="tok"), \
                 patch.object(core, "_save_json"), \
                 patch.object(core, "_work_root", return_value=tmp), \
                 patch.object(core, "_roles_in_roster", return_value=[]):

                # Call with a dummy roster and baton.
                res, runner_out = core._run_role_compute(
                    project_id="test-proj",
                    role_id="test-role",
                    baton={},
                    roster={},
                    backlog=None,
                )

        # The result is None (non-fatal).
        self.assertIsNone(res)
        self.assertEqual(runner_out, "runner-ok")

        # A ROLE_OUTPUT_PARSE_FAILED event must have been fired.
        parse_fail_events = [e for e in events if e.get("type") == "ROLE_OUTPUT_PARSE_FAILED"]
        self.assertEqual(len(parse_fail_events), 1, f"Expected 1 ROLE_OUTPUT_PARSE_FAILED event, got: {events}")
        evt = parse_fail_events[0]
        self.assertEqual(evt["severity"], "S2")
        self.assertIn("error", evt.get("extra", {}))

    def test_no_event_fired_on_valid_json_output(self) -> None:
        """When _load_json succeeds, no ROLE_OUTPUT_PARSE_FAILED event is fired."""
        import tempfile
        import os
        import noemaforge_core as core
        import json

        events: list = []

        def mock_write_event(severity, typ, actor, decision, **kwargs):
            events.append({"type": typ})

        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "role_result.json")
            with open(out_path, "w") as f:
                json.dump({"ok": True}, f)
            context_path = os.path.join(tmp, "context.json")
            with open(context_path, "w") as f:
                json.dump({}, f)

            with patch.object(core, "_write_event", side_effect=mock_write_event), \
                 patch.object(core, "run_role", return_value=(True, "runner-ok")), \
                 patch.object(core, "_issue_role_token", return_value="tok"), \
                 patch.object(core, "_save_json"), \
                 patch.object(core, "_work_root", return_value=tmp), \
                 patch.object(core, "_roles_in_roster", return_value=[]):

                res, runner_out = core._run_role_compute(
                    project_id="test-proj",
                    role_id="test-role",
                    baton={},
                    roster={},
                    backlog=None,
                )

        self.assertIsNotNone(res)
        parse_fail_events = [e for e in events if e.get("type") == "ROLE_OUTPUT_PARSE_FAILED"]
        self.assertEqual(len(parse_fail_events), 0)


if __name__ == "__main__":
    unittest.main()
