#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_do_get_safety.py
Zone: tests
Version: 0.32.2
Created: 2026-05-31
Modified: 2026-05-31
Purpose: Tests for task-67 (do_GET outer try/except) and task-68
         (/api/events limit clamp in do_GET):
           - task-67: AdminGuiHandler.do_GET() now wraps all handler dispatch
             in try/except Exception — an uncaught exception returns JSON 500
             instead of crashing the connection (matches do_POST behaviour).
           - task-68: ?limit= parameter in /api/events is clamped to [1, 1000]
             before passing to events_api(); prevents DoS via huge limit values.
         Tests are source-guard checks on admin_gui_server.py (no HTTP server
         needed).
Inputs: admin_gui_server.py source text.
Outputs: pytest pass/fail.
Side effects: None.
Tests: python3 -m unittest noemaforge/tests/test_do_get_safety.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import re
import sys
import types
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _install_stubs() -> None:
    import noemaforge_version as real_version
    sys.modules.setdefault("noemaforge_version", real_version)

    stub_orch = types.ModuleType("orchestration_state")
    stub_orch.nowz = lambda: "2026-05-31T00:00:00Z"
    stub_orch.normalize_session_record = lambda r: r
    stub_orch.is_active_job = lambda job: False
    sys.modules.setdefault("orchestration_state", stub_orch)

    stub_prod = types.ModuleType("production_ai_contracts")
    sys.modules.setdefault("production_ai_contracts", stub_prod)

    stub_priv = types.ModuleType("privileged_gui_job_runner")
    stub_priv.enrich_privileged_job = lambda job, **_kw: job
    sys.modules.setdefault("privileged_gui_job_runner", stub_priv)


_install_stubs()

_SOURCE = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")


def _do_get_body() -> str:
    """Extract the source text of AdminGuiHandler.do_GET."""
    start = _SOURCE.index("def do_GET(self)")
    try:
        end = _SOURCE.index("\n    def ", start + 1)
    except ValueError:
        end = len(_SOURCE)
    return _SOURCE[start:end]


def _do_get_events_block() -> str:
    """Extract the /api/events block from do_GET."""
    body = _do_get_body()
    start = body.index('"/api/events"')
    # Grab a window up to the next route to capture the limit clamping
    next_route = body.index('"/api/session/current"', start)
    return body[start:next_route]


class TestDoGetOuterTryExcept(unittest.TestCase):
    """do_GET must wrap all handler logic in try/except Exception."""

    def test_has_outer_try_block(self) -> None:
        """do_GET must contain a try: block wrapping all dispatch logic."""
        body = _do_get_body()
        self.assertIn("try:", body,
                      "do_GET must have an outer try: block to catch handler exceptions")

    def test_has_except_exception_block(self) -> None:
        """do_GET must have except Exception to catch uncaught handler errors."""
        body = _do_get_body()
        self.assertIn("except Exception", body,
                      "do_GET must catch Exception in the outer safety net")

    def test_except_sends_json_500(self) -> None:
        """The except block must call _send_json with status=500."""
        body = _do_get_body()
        # Use 'except Exception as exc' to target the OUTER safety-net block.
        # The nested guard block uses plain 'except Exception:' (no 'as exc'),
        # so rindex("except Exception as exc") uniquely identifies the outer block.
        exc_idx = body.rindex("except Exception as exc")
        # Window of 500 chars to cover the comment lines before _send_json.
        tail = body[exc_idx:exc_idx + 500]
        self.assertIn("500", tail,
                      "do_GET except block must return HTTP 500")
        self.assertIn("_send_json", tail,
                      "do_GET except block must use _send_json to respond")

    def test_except_includes_error_field(self) -> None:
        """The 500 response must include an 'error' field."""
        body = _do_get_body()
        exc_idx = body.rindex("except Exception as exc")
        tail = body[exc_idx:exc_idx + 500]
        self.assertIn('"error"', tail,
                      "do_GET except block 500 response must include 'error' field")

    def test_do_get_outer_try_matches_do_post_pattern(self) -> None:
        """do_GET safety net comment must indicate parity with do_POST."""
        body = _do_get_body()
        exc_idx = body.rindex("except Exception as exc")
        tail = body[exc_idx:exc_idx + 500]
        # Both do_GET and do_POST use '# pragma: no cover - server safety net'
        self.assertIn("safety net", tail,
                      "do_GET safety-net comment must be present (matches do_POST pattern)")

    def test_do_post_also_has_safety_net(self) -> None:
        """do_POST must still have its existing safety net (regression guard)."""
        start = _SOURCE.index("def do_POST(self)")
        try:
            end = _SOURCE.index("\n    def ", start + 1)
        except ValueError:
            end = len(_SOURCE)
        body = _SOURCE[start:end]
        self.assertIn("except Exception", body,
                      "do_POST safety net must still be present")
        self.assertIn("500", body,
                      "do_POST must still return 500 in its safety net")


class TestEventsLimitClamp(unittest.TestCase):
    """/api/events limit parameter must be clamped before use."""

    def test_clamp_expression_present(self) -> None:
        """do_GET /api/events block must contain min(max(1, limit), 1000)."""
        block = _do_get_events_block()
        self.assertIn("min(max(1, limit), 1000)", block,
                      "/api/events limit must be clamped with min(max(1, limit), 1000)")

    def test_clamp_applied_before_events_api_call(self) -> None:
        """The clamp must appear in the source before the events_api() call."""
        block = _do_get_events_block()
        clamp_idx = block.index("min(max(1, limit), 1000)")
        api_idx = block.index("events_api(")
        self.assertLess(clamp_idx, api_idx,
                        "limit clamp must appear before events_api() call")

    def test_limit_upper_bound_is_1000(self) -> None:
        """Upper bound in the clamp must be 1000."""
        block = _do_get_events_block()
        # Regex: min(max(1, limit), N) — N must be 1000
        match = re.search(r"min\(max\(1,\s*limit\),\s*(\d+)\)", block)
        self.assertIsNotNone(match, "clamp expression not found")
        self.assertEqual(int(match.group(1)), 1000,
                         "events limit upper bound must be 1000")

    def test_limit_lower_bound_is_1(self) -> None:
        """Lower bound in the clamp must be 1."""
        block = _do_get_events_block()
        match = re.search(r"min\(max\((\d+),\s*limit\),\s*\d+\)", block)
        self.assertIsNotNone(match, "clamp expression not found")
        self.assertEqual(int(match.group(1)), 1,
                         "events limit lower bound must be 1")

    def test_limit_comment_explains_rationale(self) -> None:
        """A comment explaining the limit clamp must be present."""
        block = _do_get_events_block()
        self.assertIn("Clamp", block,
                      "A comment explaining the limit clamp must be present")

    def test_clamp_is_assignment(self) -> None:
        """limit must be reassigned to the clamped value."""
        block = _do_get_events_block()
        # Must be: limit = min(max(1, limit), 1000)
        self.assertIn("limit = min(", block,
                      "limit must be reassigned to the clamped value")


class TestSafetyNetDoubleWriteGuard(unittest.TestCase):
    """Safety-net except blocks must not propagate double-write errors (task-72)."""

    def _get_do_get_except_block(self) -> str:
        body = _do_get_body()
        idx = body.rindex("except Exception as exc")
        return body[idx:]

    def _get_do_post_except_block(self) -> str:
        start = _SOURCE.index("def do_POST(self)")
        try:
            end = _SOURCE.index("\n    def ", start + 1)
        except ValueError:
            end = len(_SOURCE)
        body = _SOURCE[start:end]
        idx = body.rindex("except Exception as exc")
        return body[idx:]

    def test_do_get_except_wraps_send_json_in_try(self) -> None:
        """do_GET safety-net block must guard _send_json in a nested try/except.

        If wfile.write() already raised (e.g. BrokenPipeError on client
        disconnect), the second _send_json call would also raise and propagate
        up to process_request_thread. The nested try/except suppresses it.
        """
        block = self._get_do_get_except_block()
        # The nested try should appear INSIDE the outer except block
        self.assertIn("try:", block,
                      "do_GET safety-net except block must have a nested try:")

    def test_do_get_except_has_pass_guard(self) -> None:
        """do_GET safety-net block must silently swallow the nested exception."""
        block = self._get_do_get_except_block()
        self.assertIn("pass", block,
                      "do_GET safety-net nested except must have 'pass' to suppress error")

    def test_do_post_except_also_guarded(self) -> None:
        """do_POST safety-net block must also guard _send_json in a nested try/except."""
        block = self._get_do_post_except_block()
        self.assertIn("try:", block,
                      "do_POST safety-net except block must have a nested try:")
        self.assertIn("pass", block,
                      "do_POST safety-net nested except must have 'pass'")


if __name__ == "__main__":
    unittest.main()
