#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/admin_gui_routes/session_routes.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-06-11
Modified: 2026-06-11
Purpose: Admin GUI route handlers for the session / conversation / tasks /
  persona cluster. Each function reproduces the original inline do_GET/do_POST
  branch verbatim behind the shared route table.
  NOTE: GET /api/events and GET /api/session/current keep their inline
  query-validation/clamping bodies inside AdminGuiHandler.do_GET, and POST
  /api/session/mode keeps its inline composite_top_n validation inside
  do_POST (those blocks are pinned by source-guard tests and must stay
  textually in the handler methods). The same physical dispatch behaviour is
  preserved; only the simple single-call branches move here.
Inputs: AdminGuiHandler instances; POST handlers also receive the parsed body.
Outputs: JSON responses written via handler._send_json.
Side effects: Delegates to handler.server.* methods (which own all side effects).
Tests: python3 -m py_compile noemaforge/src/admin_gui_routes/session_routes.py.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from typing import Any, Dict


# --- GET handlers ----------------------------------------------------------------
def conversation_current(handler: Any) -> None:
    handler._send_json(handler.server.conversation_current())


def conversation_history(handler: Any) -> None:
    handler._send_json(handler.server.conversation_history())


def tasks_list(handler: Any) -> None:
    handler._send_json(handler.server.tasks_list())


def inactivity_status(handler: Any) -> None:
    handler._send_json(handler.server.inactivity_status())


def persona_current(handler: Any) -> None:
    handler._send_json(handler.server.persona_current())


def persona_catalog(handler: Any) -> None:
    handler._send_json(handler.server.persona_catalog_api())


def persona_rules(handler: Any) -> None:
    handler._send_json(handler.server.persona_rules())


# --- POST handlers ---------------------------------------------------------------
def persona_switch(handler: Any, body: Dict[str, Any]) -> None:
    name = str(body.get("name") or "Admin")
    handler._send_json(handler.server.persona_switch(name))



def admin_message(handler: Any, body: Dict[str, Any]) -> None:
    path = handler._route_path()
    text = str(body.get("message") or body.get("text") or body.get("prompt") or "")
    handler._send_json(handler.server.admin_message(
        text,
        execute=bool(body.get("execute")) or path == "/api/admin/start",
        prepare_media=bool(body.get("prepare_media", True)),
        allow_degraded=bool(body.get("allow_degraded", False)),
        apply=bool(body.get("apply", False)),
        locale=str(body.get("locale") or body.get("lang") or ""),
        max_steps=int(body.get("max_steps") or 0),
        time_budget_minutes=int(body.get("time_budget_minutes") or 0),
        until_stop=bool(body.get("until_stop", False)),
        run_mode=str(body.get("run_mode") or ""),
        composite_top_n=int(body.get("composite_top_n") or 0),
    ))


def conversation_reset(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.conversation_reset())


def task_create(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.task_create(body))


def task_update(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.task_update(body))


def task_block(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.task_block(body))


def task_complete(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.task_complete(body))


def task_prioritize(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.task_prioritize(body))


def get_routes() -> Dict[str, Any]:
    return {
        "/api/conversation/current": conversation_current,
        "/api/conversation/history": conversation_history,
        "/api/tasks": tasks_list,
        "/api/inactivity/status": inactivity_status,
        "/api/persona/current": persona_current,
        "/api/persona/catalog": persona_catalog,
        "/api/persona/rules": persona_rules,
    }


def post_routes() -> Dict[str, Any]:
    return {
        "/api/admin/message": admin_message,
        "/api/admin/ask": admin_message,
        "/api/admin/start": admin_message,
        "/api/conversation/message": admin_message,
        "/api/conversation/reset": conversation_reset,
        "/api/tasks/create": task_create,
        "/api/tasks/update": task_update,
        "/api/tasks/edit": task_update,
        "/api/tasks/block": task_block,
        "/api/tasks/complete": task_complete,
        "/api/tasks/prioritize": task_prioritize,
        "/api/persona/switch": persona_switch,
    }
