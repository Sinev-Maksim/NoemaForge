#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/admin_gui_routes/__init__.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-06-11
Modified: 2026-06-11
Purpose: Package init for the Admin GUI HTTP routing surface. Re-exports the
  per-area route-table builders so admin_gui_server.py can assemble explicit
  GET/POST dispatch tables (path -> callable) without changing any behaviour.
Inputs: None at import time.
Outputs: get_routes()/post_routes() builders aggregated from area modules.
Side effects: None.
Tests: python3 -m py_compile noemaforge/src/admin_gui_routes/__init__.py.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from . import job_routes, model_routes, pipeline_routes, session_routes, telemetry_routes

# A GET route handler takes the AdminGuiHandler instance and performs the full
# response (re-parse query from handler.path, call the server method, send the
# JSON/bytes/SSE response).  A POST route handler additionally receives the
# already-parsed JSON body dict that do_POST read once at the top of dispatch.
# Returning is implicit; the handler is responsible for writing the response.
RouteHandler = Callable[..., None]


def get_routes() -> Dict[str, "RouteHandler"]:
    """Assemble the exact-path GET dispatch table from all area modules.

    Order of update() calls is irrelevant because every key is a distinct
    absolute path; collisions would be a packaging bug surfaced by the
    route-parity check.
    """
    table: Dict[str, RouteHandler] = {}
    table.update(telemetry_routes.get_routes())
    table.update(session_routes.get_routes())
    table.update(pipeline_routes.get_routes())
    table.update(job_routes.get_routes())
    table.update(model_routes.get_routes())
    return table


def post_routes() -> Dict[str, "RouteHandler"]:
    """Assemble the exact-path POST dispatch table from all area modules."""
    table: Dict[str, RouteHandler] = {}
    table.update(telemetry_routes.post_routes())
    table.update(session_routes.post_routes())
    table.update(pipeline_routes.post_routes())
    table.update(job_routes.post_routes())
    table.update(model_routes.post_routes())
    return table
