#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/admin_gui_routes/job_routes.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-06-11
Modified: 2026-06-11
Purpose: Admin GUI route handlers for the jobs registry / SSE stream cluster.
  Each function reproduces the original inline do_GET branch verbatim behind the
  shared route table.
  NOTE: the GET /api/jobs/<job_id> prefix branch, the POST /api/jobs/<id>/cancel
  prefix branch, and POST /api/shutdown (which schedules a threading.Timer)
  keep their inline bodies inside AdminGuiHandler.do_GET/do_POST; only the
  exact-path simple branches move here.
Inputs: AdminGuiHandler instances.
Outputs: JSON / Server-Sent-Events responses via handler._send_json/_send_sse.
Side effects: Delegates to handler.server.* methods (which own all side effects).
Tests: python3 -m py_compile noemaforge/src/admin_gui_routes/job_routes.py.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from typing import Any, Dict


# --- GET handlers ----------------------------------------------------------------
def jobs_list(handler: Any) -> None:
    handler._send_json(handler.server.jobs_list())


def jobs_stream(handler: Any) -> None:
    handler._send_sse(handler.server.job_stream_events())


def get_routes() -> Dict[str, Any]:
    return {
        "/api/jobs": jobs_list,
        "/api/jobs/stream": jobs_stream,
    }


def post_routes() -> Dict[str, Any]:
    return {}
