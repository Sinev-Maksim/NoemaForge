#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/admin_gui_routes/session_routes.py
Zone: gui/control-plane
Version: 0.33.0
Created: 2026-06-11
Modified: 2026-07-24
Purpose: Admin GUI route handlers for the session, conversation, task and persona cluster, including trusted trigger ingress gating.
Inputs: AdminGuiHandler instances; POST handlers also receive the parsed body.
Outputs: JSON responses written via handler._send_json.
Side effects: Delegates to handler.server methods and records trusted-trigger audit evidence before any work-item side effect.
Tests: noemaforge/tests/test_trusted_trigger_integration.py.
Notes: Trusted verification context is constructed from server/connection metadata and is never accepted from request JSON.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from trusted_trigger_integration import TrustedTriggerIntegration

_INTEGRATION_LOCK = threading.Lock()


# --- trusted ingress ---------------------------------------------------------------
def _headers(handler: Any) -> Dict[str, str]:
    raw = getattr(handler, "headers", None)
    if raw is None:
        return {}
    try:
        return {str(key): str(value) for key, value in raw.items()}
    except Exception:
        return {}


def _trusted_trigger_integration(handler: Any) -> Optional[TrustedTriggerIntegration]:
    server = getattr(handler, "server", None)
    if server is None or not hasattr(server, "data_root") or not hasattr(server, "root"):
        return None
    current = getattr(server, "_trusted_trigger_integration", None)
    if isinstance(current, TrustedTriggerIntegration):
        return current
    with _INTEGRATION_LOCK:
        current = getattr(server, "_trusted_trigger_integration", None)
        if isinstance(current, TrustedTriggerIntegration):
            return current
        integration = TrustedTriggerIntegration(
            state_dir=Path(server.data_root) / "trusted-trigger",
            policy_path=Path(server.root) / "configs" / "trusted-trigger-source-policy.json",
        )
        setattr(server, "_trusted_trigger_integration", integration)
        return integration


def _trigger_gate(handler: Any, body: Mapping[str, Any]) -> tuple[Optional[TrustedTriggerIntegration], Optional[Dict[str, Any]]]:
    integration = _trusted_trigger_integration(handler)
    if integration is None:
        # Compatibility for narrow unit-test doubles only. The production server
        # always has root/data_root and therefore always constructs the gate.
        return None, None
    server = handler.server
    try:
        session_id = str(server._active_session_id())
    except Exception:
        session_id = str(getattr(server, "current_session_id", "") or "unknown")
    client_address = getattr(handler, "client_address", ()) or ()
    gate = integration.conversation_http_gate(
        body=body,
        headers=_headers(handler),
        client_address=client_address,
        route=str(handler._route_path()),
        session_id=session_id,
    )
    return integration, gate


def _deny_trigger(handler: Any, integration: TrustedTriggerIntegration, gate: Mapping[str, Any]) -> None:
    status = 400 if gate.get("hard_deny") else 403
    handler._send_json(
        {
            "ok": False,
            "error": "trusted trigger denied",
            "error_class": "trusted_trigger_denied",
            "trusted_trigger": integration.public_summary(gate),
        },
        status=status,
    )


def _attach_gate(result: Any, integration: Optional[TrustedTriggerIntegration], gate: Optional[Mapping[str, Any]]) -> Any:
    if not isinstance(result, dict) or integration is None or gate is None:
        return result
    enriched = dict(result)
    enriched["trusted_trigger"] = integration.public_summary(gate)
    return enriched


# --- GET handlers ------------------------------------------------------------------
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


# --- POST handlers -----------------------------------------------------------------
def persona_switch(handler: Any, body: Dict[str, Any]) -> None:
    name = str(body.get("name") or "Admin")
    handler._send_json(handler.server.persona_switch(name))


def admin_message(handler: Any, body: Dict[str, Any]) -> None:
    path = handler._route_path()
    text = str(body.get("message") or body.get("text") or body.get("prompt") or "")
    integration, gate = _trigger_gate(handler, body)
    if integration is not None and gate is not None and not gate.get("proceed"):
        _deny_trigger(handler, integration, gate)
        return

    if integration is not None and gate is not None and gate.get("enforcement_active"):
        # Trigger authority is deliberately narrower than command authority. Once
        # activated, an external message can create only one pending work item; it
        # cannot directly start a pipeline, apply, push, merge or release.
        result = handler.server.task_create(
            {
                "title": text or "Trusted trigger work item",
                "category": "trusted_trigger",
                "priority": 50,
                "status": "pending",
                "assignee": "Admin",
                "created_by": "nf-owner:primary",
                "requires_approval": True,
            }
        )
        if isinstance(result, dict) and result.get("ok"):
            task = result.get("task") if isinstance(result.get("task"), dict) else {}
            integration.record_work_item(gate, str(task.get("task_id") or ""))
            result = dict(result)
            result["mode"] = "trusted_trigger_work_item"
            result["reply"] = f"Trusted trigger accepted as pending work item: {task.get('task_id') or 'created'}"
        handler._send_json(_attach_gate(result, integration, gate))
        return

    result = handler.server.admin_message(
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
    )
    handler._send_json(_attach_gate(result, integration, gate))


def conversation_reset(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.conversation_reset())


def task_create(handler: Any, body: Dict[str, Any]) -> None:
    integration, gate = _trigger_gate(handler, body)
    if integration is not None and gate is not None and not gate.get("proceed"):
        _deny_trigger(handler, integration, gate)
        return
    task_body = dict(body)
    if integration is not None and gate is not None and gate.get("enforcement_active"):
        task_body.update(
            {
                "status": "pending",
                "created_by": "nf-owner:primary",
                "requires_approval": True,
            }
        )
    result = handler.server.task_create(task_body)
    if (
        integration is not None
        and gate is not None
        and gate.get("enforcement_active")
        and isinstance(result, dict)
        and result.get("ok")
    ):
        task = result.get("task") if isinstance(result.get("task"), dict) else {}
        integration.record_work_item(gate, str(task.get("task_id") or ""))
    handler._send_json(_attach_gate(result, integration, gate))


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
