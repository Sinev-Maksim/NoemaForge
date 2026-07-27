#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/admin_gui_routes/__init__.py
Zone: gui/control-plane
Version: 0.33.0
Created: 2026-06-11
Modified: 2026-07-24
Purpose: Aggregate Admin GUI route tables and install the central owner-session HTTP-server boundary before AdminGuiServer class construction.
Inputs: None at import time.
Outputs: get_routes()/post_routes() builders aggregated from area modules.
Side effects: Replaces the Admin GUI ThreadingHTTPServer base with a narrow guarded subclass; unrelated servers are not wrapped.
Tests: noemaforge/tests/test_trusted_trigger_integration.py.
Notes: Every POST dispatch is fail-closed against the machine-readable mutation inventory before route-specific code runs.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from typing import Callable, Dict

from . import job_routes, model_routes, pipeline_routes, session_routes, telemetry_routes
from admin_gui_owner_session import install_guarded_server_base

RouteHandler = Callable[..., None]


def get_routes() -> Dict[str, "RouteHandler"]:
    table: Dict[str, RouteHandler] = {}
    table.update(telemetry_routes.get_routes())
    table.update(session_routes.get_routes())
    table.update(pipeline_routes.get_routes())
    table.update(job_routes.get_routes())
    table.update(model_routes.get_routes())
    return table


def post_routes() -> Dict[str, "RouteHandler"]:
    table: Dict[str, RouteHandler] = {}
    table.update(telemetry_routes.post_routes())
    table.update(session_routes.post_routes())
    table.update(pipeline_routes.post_routes())
    table.update(job_routes.post_routes())
    table.update(model_routes.post_routes())
    return table


# admin_gui_server imports this package before defining AdminGuiServer. Installing
# the guarded base here covers route-table and inline/prefix POST branches alike.
install_guarded_server_base()
