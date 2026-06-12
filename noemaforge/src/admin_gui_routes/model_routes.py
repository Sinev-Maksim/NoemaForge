#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/admin_gui_routes/model_routes.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-06-11
Modified: 2026-06-11
Purpose: Admin GUI route handlers for the model-selection / epoch / vault
  cluster. Each function reproduces the original inline do_GET/do_POST branch
  verbatim behind the shared route table.
Inputs: AdminGuiHandler instances; POST handlers also receive the parsed body.
Outputs: JSON responses written via handler._send_json.
Side effects: Delegates to handler.server.* methods (which own all side effects).
Tests: python3 -m py_compile noemaforge/src/admin_gui_routes/model_routes.py.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from typing import Any, Dict


# --- GET handlers ----------------------------------------------------------------
def epoch_status(handler: Any) -> None:
    handler._send_json(handler.server.epoch_status())


# --- POST handlers ---------------------------------------------------------------
def model_evolution(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.model_evolution(str(body.get("request") or "GUI model evolution"), target_role=str(body.get("target_role") or "dev.work/dev"), apply=bool(body.get("apply", False))))


def model_selection(handler: Any, body: Dict[str, Any]) -> None:
    path = handler._route_path()
    handler._send_json(handler.server.model_selection(
        str(body.get("request") or body.get("message") or "GUI model selection"),
        mode=str(body.get("mode") or "normal"),
        scope=str(body.get("scope") or "active runtime"),
        composite_top_n=int(body.get("composite_top_n") or body.get("n") or 0),
        apply=bool(body.get("apply", False)) or path.endswith("/apply"),
    ))


def model_selection_continue(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.model_selection_continue(body))


def epoch_apply(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.epoch_apply(body))


def vault_reinventory(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.vault_reinventory())


def get_routes() -> Dict[str, Any]:
    return {
        "/api/epoch/status": epoch_status,
    }


def post_routes() -> Dict[str, Any]:
    return {
        "/api/model-evolution/run": model_evolution,
        "/api/model-selection/plan": model_selection,
        "/api/model-selection/apply": model_selection,
        "/api/model-selection/continue": model_selection_continue,
        "/api/epoch/apply": epoch_apply,
        "/api/vault/reinventory": vault_reinventory,
    }
