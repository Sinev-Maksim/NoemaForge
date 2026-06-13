#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/admin_gui_routes/pipeline_routes.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-06-11
Modified: 2026-06-11
Purpose: Admin GUI route handlers for the pipelines / drafts / artifacts /
  dev-team cluster. Each function reproduces the original inline do_GET/do_POST
  branch verbatim behind the shared route table.
  NOTE: GET /api/artifacts/download keeps its inline byte-streaming body and the
  GET /api/pipelines/<id>/<action> prefix branch keeps its inline path parsing
  inside AdminGuiHandler.do_GET (they are not simple single-call dispatches);
  only the simple branches move here.
Inputs: AdminGuiHandler instances; POST handlers also receive the parsed body.
Outputs: JSON responses written via handler._send_json.
Side effects: Delegates to handler.server.* methods (which own all side effects).
Tests: python3 -m py_compile noemaforge/src/admin_gui_routes/pipeline_routes.py.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

from typing import Any, Dict

from .common import query_first


# --- GET handlers ----------------------------------------------------------------
def artifact_open(handler: Any) -> None:
    handler._send_json(handler.server.artifact_open(query_first(handler, "path")))


def pipeline_catalog(handler: Any) -> None:
    handler._send_json(handler.server.pipeline_catalog_api())


# --- POST handlers ---------------------------------------------------------------
def modify_pipeline(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.modify_pipeline(
        str(body.get("pipeline") or body.get("pipeline_id") or "public_mwp"),
        add_stage=str(body.get("add_stage") or ""),
        after=str(body.get("after") or ""),
        before=str(body.get("before") or ""),
        description=str(body.get("description") or ""),
        team=str(body.get("team") or ""),
        apply=bool(body.get("apply", False)),
        create=bool(body.get("create", False)),
    ))


def pipeline_run(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.pipeline_run(str(body.get("pipeline") or body.get("pipeline_id") or "public_mwp"), str(body.get("request") or "GUI pipeline request"), allow_degraded=bool(body.get("allow_degraded", False))))


def pipeline_approve(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.pipeline_action("approve", str(body.get("run_id") or ""), body))


def pipeline_advance(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.pipeline_action("advance", str(body.get("run_id") or ""), body))


def pipeline_draft(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.pipeline_draft(body))


def dev_team_run(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.dev_team_run(str(body.get("request") or "GUI dev-team task"), allow_degraded=bool(body.get("allow_degraded", False))))


def dev_team_write_file(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.dev_team_write_file(project=str(body.get("project") or ""), rel_path=str(body.get("path") or ""), content=str(body.get("content") or ""), apply=bool(body.get("apply", False))))


def dev_team_replace(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.dev_team_replace(project=str(body.get("project") or ""), rel_path=str(body.get("path") or ""), old=str(body.get("old") or ""), new=str(body.get("new") or ""), once=bool(body.get("once", True)), apply=bool(body.get("apply", False))))


def dev_team_set_version(handler: Any, body: Dict[str, Any]) -> None:
    handler._send_json(handler.server.dev_team_set_version(project=str(body.get("project") or ""), version=str(body.get("version") or ""), apply=bool(body.get("apply", False))))


def get_routes() -> Dict[str, Any]:
    return {
        "/api/artifacts/open": artifact_open,
        "/api/pipelines/catalog": pipeline_catalog,
    }


def post_routes() -> Dict[str, Any]:
    return {
        "/api/admin/modify-pipeline": modify_pipeline,
        "/api/pipeline/run": pipeline_run,
        "/api/pipelines/start": pipeline_run,
        "/api/pipeline/approve": pipeline_approve,
        "/api/pipeline/advance": pipeline_advance,
        "/api/pipelines/draft": pipeline_draft,
        "/api/dev-team/run": dev_team_run,
        "/api/dev-team/write-file": dev_team_write_file,
        "/api/dev-team/replace": dev_team_replace,
        "/api/dev-team/set-version": dev_team_set_version,
    }
