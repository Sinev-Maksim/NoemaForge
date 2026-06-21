#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/admin_gui_routes/telemetry_routes.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-06-11
Modified: 2026-06-11
Purpose: Admin GUI route handlers for the dashboard/telemetry/health/runtime/
  locales/usecases/code-evolution-status/device-policy cluster. Each function
  reproduces the original inline do_GET/do_POST branch verbatim behind the
  shared route table — no behaviour change.
Inputs: AdminGuiHandler instances; POST handlers also receive the parsed body.
Outputs: JSON responses written via handler._send_json.
Side effects: Delegates to handler.server.* methods (which own all side effects).
Tests: python3 -m py_compile noemaforge/src/admin_gui_routes/telemetry_routes.py.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from typing import Any, Dict


# --- GET handlers ----------------------------------------------------------------
def health(handler: Any) -> None:
    handler._send_json(handler.server.health())


def gui_state(handler: Any) -> None:
    handler._send_json(handler.server.gui_state())


def dashboard(handler: Any) -> None:
    handler._send_json(handler.server.dashboard_api())


def locales(handler: Any) -> None:
    handler._send_json(handler.server.locales())


def runtime_status(handler: Any) -> None:
    handler._send_json(handler.server.runtime_status())


def runtime_observer_cards(handler: Any) -> None:
    handler._send_json(handler.server.runtime_observer_cards())


def device_policy(handler: Any) -> None:
    handler._send_json(handler.server.device_policy())


def telemetry_status(handler: Any) -> None:
    handler._send_json(handler.server.telemetry_status())


def usecases(handler: Any) -> None:
    handler._send_json(handler.server.usecases())


def public_showcase_scenario(handler: Any) -> None:
    handler._send_json(handler.server.public_showcase_scenario())


def code_evolution_status(handler: Any) -> None:
    handler._send_json(handler.server.code_evolution_status())


# --- POST handlers ---------------------------------------------------------------
def code_evolution_propose(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.code_evolution_propose())


def code_evolution_status_post(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.code_evolution_status())


def device_policy_set(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.device_policy_set(str(body.get("policy") or body.get("mode") or "auto")))


def workflow_stop(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.workflow_stop(str(body.get("reason") or "operator_requested_stop")))


def get_routes() -> Dict[str, Any]:
    return {
        "/api/health": health,
        "/api/state": gui_state,
        "/api/gui/state": gui_state,
        "/api/dashboard": dashboard,
        "/api/dashboard/state": dashboard,
        "/api/locales": locales,
        "/api/runtime/status": runtime_status,
        "/api/runtime/observer-cards": runtime_observer_cards,
        "/api/runtime/device-policy": device_policy,
        "/api/telemetry/status": telemetry_status,
        "/api/usecases": usecases,
        "/api/public-showcase/scenario": public_showcase_scenario,
        "/api/code-evolution/status": code_evolution_status,
    }


def post_routes() -> Dict[str, Any]:
    return {
        "/api/code-evolution/propose": code_evolution_propose,
        "/api/code-evolution/status": code_evolution_status_post,
        "/api/runtime/device-policy": device_policy_set,
        "/api/workflow/stop": workflow_stop,
    }
