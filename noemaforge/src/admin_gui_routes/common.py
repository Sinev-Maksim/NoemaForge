#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/admin_gui_routes/common.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-06-11
Modified: 2026-06-11
Purpose: Shared helpers for the Admin GUI route modules. Centralises the small
  query-string parsing utilities used by multiple area handlers so the dispatch
  functions stay one-liners that mirror the original inline do_GET/do_POST code.
Inputs: AdminGuiHandler instances (handler.path query strings).
Outputs: Parsed query dictionaries / first-value lookups.
Side effects: None.
Tests: python3 -m py_compile noemaforge/src/admin_gui_routes/common.py.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

Calling convention
------------------
- GET route handlers are ``fn(handler)``.  They re-parse the query string from
  ``handler.path`` (identical to the original inline branches) and call the
  matching ``handler.server.*`` method, then ``handler._send_json(...)``.
- POST route handlers are ``fn(handler, body)`` where ``body`` is the JSON dict
  already read once by ``do_POST`` (which keeps the body-too-large / bad-JSON
  400 handling in one place, exactly as before).
"""
from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse


def query_dict(handler: Any) -> Dict[str, List[str]]:
    """Return parse_qs(urlparse(handler.path).query) — the original inline form."""
    return parse_qs(urlparse(handler.path).query)


def query_first(handler: Any, key: str, default: str = "") -> str:
    """Return the first value for ``key`` in the request query, else ``default``.

    Mirrors the ``(query.get(key) or [default])[0]`` idiom used inline in the
    original do_GET branches.
    """
    return str((query_dict(handler).get(key) or [default])[0])
