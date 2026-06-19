#!/usr/bin/env python3
"""NoemaForge local Admin GUI server.

=== NoemaForge File Header ===
File: src/admin_gui_server.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-05-11
Modified: 2026-05-25
Purpose: Serve the localhost Admin GUI and JSON APIs for conversation memory,
  persona portraits, epoch/model-selection status, telemetry, task governance,
  job registry, pipeline catalog/diagrams/stats, and safe control-plane actions.
Inputs:
  - HTTP GET/POST localhost requests from the packaged GUI.
  - NoemaForge catalogs/configs under ROOT/configs.
  - Runtime/bootstrap state resolved through platform_paths.py.
  - Optional system telemetry commands such as sensors, nvidia-smi, upower.
Outputs:
  - JSON API responses.
  - Persistent conversation, task, job, SR/SSR review, and GUI state records.
  - Plan-first artifacts for privileged actions.
Safety notes:
  - No LLM, media backend, camera, microphone, model-selection or epoch switch is
    started implicitly by loading the GUI.
  - Privileged actions are represented as whitelisted job/plan records unless a
    separate operator-approved sudo or polkit job-runner action is executed
    outside the browser.
Tests:
  - python3 -m py_compile src/admin_gui_server.py
  - curl http://127.0.0.1:8765/api/health
  - curl http://127.0.0.1:8765/api/gui/state
  - curl http://127.0.0.1:8765/api/telemetry/status
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, quote, unquote, urlparse

import production_ai_contracts
import admin_gui_routes
from privileged_gui_job_runner import enrich_privileged_job
from noemaforge_version import RUNTIME_VERSION
from event_log import EventLog
from job_manager import JobManager
from session_store import SessionStore
from orchestration_state import is_active_job, FINAL_JOB_STATES, normalize_job_record
# Platform-aware path resolution — replaces hardcoded /opt/noemaforge defaults.
# All DEFAULT_* constants below now delegate to platform_paths so the server
# starts correctly on Linux, Windows, and macOS without any env-var pre-setting.
from platform_paths import DEFAULT_PATHS as _platform_paths

PRIVILEGED_GUI_POLKIT_ACTION = "org.noemaforge.privileged-jobs.run"
DEFAULT_ROOT = _platform_paths.root
DEFAULT_STATE = _platform_paths.pipelines_dir
DEFAULT_PERSONA_STATE = _platform_paths.persona_state_dir
DEFAULT_EVOLUTION_STATE = _platform_paths.model_evolution_state_dir
DEFAULT_MODEL_SELECTION_STATE = _platform_paths.model_selection_state_dir
DEFAULT_DEV_TEAM_STATE = _platform_paths.dev_team_state_dir
DEFAULT_DATA_ROOT = _platform_paths.data_root
DEFAULT_BOOTSTRAP_DIR = _platform_paths.bootstrap_dir
DEFAULT_MODELSTORE_DIR = _platform_paths.modelstore_dir
DEFAULT_LLM_GATEWAY_SOCKET = _platform_paths.llm_gateway_socket
DEFAULT_LLM_MAIN_BACKEND_SOCKET = _platform_paths.llm_main_backend_socket
DEFAULT_LEGACY_LLM_GATEWAY_SOCKET = _platform_paths.legacy_brainos_gateway_socket
MAX_BODY = 512 * 1024
MAX_ARTIFACT_PREVIEW_BYTES = 64 * 1024


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def safe_id(text: str, default: str = "item") -> str:
    raw = re.sub(r"[^A-Za-z0-9_.-]+", "-", text.strip()).strip("-._")
    return raw[:96] or default


def artifact_action_url(action: str, path: str) -> str:
    clean_action = safe_id(action, "open")
    clean_path = str(path or "").strip()
    return f"/api/artifacts/{clean_action}?path={quote(clean_path, safe='')}" if clean_path else ""


def enrich_artifact_card(card: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(card)
    path = str(out.get("path") or "").strip()
    if path:
        out.setdefault("open_url", artifact_action_url("open", path))
        out.setdefault("preview_url", out["open_url"])
        out.setdefault("download_url", artifact_action_url("download", path))
        out.setdefault("can_download", True)
    else:
        out.setdefault("can_download", False)
    return out


def enrich_artifact_cards(items: Optional[Iterable[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    return [enrich_artifact_card(item) for item in (items or []) if isinstance(item, dict)]


def _service_state(result: Dict[str, Any]) -> str:
    stdout = str(result.get("stdout") or "").strip()
    if stdout == "active":
        return "active"
    if result.get("available") is False:
        return "command_unavailable"
    if stdout:
        return stdout.splitlines()[0][:80]
    if result.get("returncode") == 0:
        return "ok"
    return "inactive"


def _path_key(path: Path) -> str:
    return str(path)


def _socket_present(sockets: Dict[str, Any], path: Path, *fallbacks: Optional[Path]) -> bool:
    keys = {_path_key(path), _path_key(path).replace("\\", "/")}
    for fallback in fallbacks:
        if fallback is not None:
            keys.add(_path_key(fallback))
            keys.add(_path_key(fallback).replace("\\", "/"))
    return any(bool(sockets.get(key)) for key in keys)


def build_runtime_observer_cards(runtime: Dict[str, Any]) -> List[Dict[str, Any]]:
    sockets = runtime.get("sockets") if isinstance(runtime.get("sockets"), dict) else {}
    gateway_state = _service_state(runtime.get("gateway") if isinstance(runtime.get("gateway"), dict) else {})
    backend_state = _service_state(runtime.get("main_backend") if isinstance(runtime.get("main_backend"), dict) else {})
    gateway_socket = _socket_present(
        sockets,
        DEFAULT_LLM_GATEWAY_SOCKET,
        DEFAULT_LEGACY_LLM_GATEWAY_SOCKET,
    )
    backend_socket = _socket_present(sockets, DEFAULT_LLM_MAIN_BACKEND_SOCKET)
    manifest = runtime.get("main_manifest") if isinstance(runtime.get("main_manifest"), dict) else {}
    model_name = str(manifest.get("model_id") or manifest.get("name") or "").strip()
    policy = runtime.get("device_policy") if isinstance(runtime.get("device_policy"), dict) else {}
    device_policy = str(policy.get("policy") or policy or "auto")
    return [
        {"id": "gateway-service", "title": "Gateway service", "kind": "systemd_service", "state": gateway_state, "status": "ok" if gateway_state == "active" else "warn", "smoke_affirmation": "affirmed" if gateway_state == "active" else "not_affirmed", "evidence": "systemctl is-active noemaforge-llm-gateway.service"},
        {"id": "gateway-socket", "title": "Gateway socket", "kind": "socket", "state": "present" if gateway_socket else "missing", "status": "ok" if gateway_socket else "warn", "smoke_affirmation": "affirmed" if gateway_socket else "not_affirmed", "evidence": _path_key(DEFAULT_LLM_GATEWAY_SOCKET)},
        {"id": "main-backend-service", "title": "Main backend service", "kind": "systemd_service", "state": backend_state, "status": "ok" if backend_state == "active" else "warn", "smoke_affirmation": "affirmed" if backend_state == "active" else "not_affirmed", "evidence": "systemctl is-active noemaforge-llama@main.service"},
        {"id": "main-backend-socket", "title": "Main backend socket", "kind": "socket", "state": "present" if backend_socket else "missing", "status": "ok" if backend_socket else "warn", "smoke_affirmation": "affirmed" if backend_socket else "not_affirmed", "evidence": _path_key(DEFAULT_LLM_MAIN_BACKEND_SOCKET)},
        {"id": "main-model-manifest", "title": "Main model manifest", "kind": "model_manifest", "state": model_name or "missing", "status": "ok" if model_name else "warn", "smoke_affirmation": "affirmed" if model_name else "not_affirmed", "evidence": "modelstore main manifest"},
        {"id": "device-policy", "title": "Device policy", "kind": "runtime_policy", "state": device_policy, "status": "ok", "smoke_affirmation": "observed", "evidence": "runtime device-policy.json"},
    ]


def normalize_pipeline_editor_draft(body: Dict[str, Any]) -> Dict[str, Any]:
    raw_stages = body.get("stages") if isinstance(body.get("stages"), list) else []
    stages: List[str] = []
    for item in raw_stages[:32]:
        stage = safe_id(str(item), "stage")
        if stage and stage not in stages:
            stages.append(stage)
    if not stages:
        stages = ["intake", "plan", "review"]
    title = str(body.get("title") or body.get("id") or "Pipeline draft").strip()[:120]
    draft_id = "draft_" + safe_id(str(body.get("id") or title or now_iso()), "pipeline")
    return {
        "id": safe_id(str(body.get("id") or title), "pipeline"),
        "title": title,
        "description": str(body.get("description") or "").strip()[:1000],
        "stages": stages,
        "editor_mode": "drag_drop_pipeline_editor",
        "activation_state": "draft_only",
        "review_required": True,
        "review_gate": "Scary/Architecture/Admin approval required before catalog append",
        "draft_id": draft_id,
    }


def build_public_showcase_scenario(locale: str = "") -> Dict[str, Any]:
    steps = [
        {
            "id": "health",
            "title": "Confirm local Admin health",
            "surface": "topbar",
            "endpoint": "/api/health",
            "request": "Show local health without starting a backend.",
            "expected": "Admin GUI reports localhost control-plane health.",
        },
        {
            "id": "admin_greeting",
            "title": "Greet Admin",
            "surface": "main_chat",
            "endpoint": "/api/admin/message",
            "request": "Првиет!",
            "expected": "Admin answers conversationally and keeps control routing available.",
        },
        {
            "id": "routed_pipeline",
            "title": "Stage the public pipeline",
            "surface": "pipeline_dock",
            "endpoint": "/api/pipeline/run",
            "pipeline_id": "public_mwp",
            "request": "Запусти public_mwp по стандартному сценарию",
            "expected": "Pipeline run is routed with artifacts and reviewable state.",
        },
        {
            "id": "dev_team_plan",
            "title": "Ask Dev Team for a plan",
            "surface": "main_chat",
            "endpoint": "/api/admin/message",
            "request": "доработай код через dev team: summarize the next safe patch",
            "expected": "Admin routes to Dev Team planning without hidden auto-apply.",
        },
        {
            "id": "model_evolution_plan",
            "title": "Stage model-evolution review",
            "surface": "main_chat",
            "endpoint": "/api/admin/message",
            "request": "проведи эволюцию модели для ревью кода",
            "expected": "Model Evolution produces review artifacts and rollback context.",
        },
    ]
    return {
        "ok": True,
        "version": RUNTIME_VERSION,
        "scenario_id": "admin_gui_guided_scenario",
        "selection": "polished_admin_gui_guided_scenario",
        "status": "selected_local_first",
        "locale": locale or "default",
        "live_backend_demo_enabled": False,
        "requires_live_target": False,
        "requires_packaging": False,
        "operator_note": "Use this guided Admin GUI path as the public 0.32.2 polish scenario; run the final live replay separately on the target machine.",
        "steps": steps,
        "expected_ui_surfaces": ["topbar", "main_chat", "pipeline_dock", "artifacts", "jobs", "runtime_cards"],
        "safety": {
            "no_network_required": True,
            "no_hidden_backend_start": True,
            "no_auto_apply": True,
            "final_target_replay_required": True,
        },
    }


def sse_event(event: str, data: Dict[str, Any], *, event_id: str = "") -> str:
    lines: List[str] = []
    if event_id:
        lines.append(f"id: {safe_id(event_id)}")
    lines.append(f"event: {safe_id(event, 'message')}")
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
    for line in payload.splitlines() or ["{}"]:
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


def run_json(cmd: Sequence[str], *, env: Optional[Dict[str, str]] = None, timeout: int = 60) -> Dict[str, Any]:
    try:
        proc = subprocess.run(list(cmd), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "returncode": 124, "cmd": list(cmd), "stdout": exc.stdout or "", "stderr": (exc.stderr or "") + "\ncommand timeout"}
    except Exception as exc:  # pragma: no cover - host-specific safety net
        return {"ok": False, "returncode": None, "cmd": list(cmd), "stdout": "", "stderr": repr(exc)}
    stdout: Any = proc.stdout.strip()
    if stdout:
        try:
            stdout = json.loads(stdout)
        except Exception:
            pass
    return {"ok": proc.returncode == 0, "returncode": proc.returncode, "cmd": list(cmd), "stdout": stdout, "stderr": proc.stderr.strip()}


def tail_text(path: Path, limit: int = 4096) -> str:
    try:
        data = path.read_bytes()
        return data[-limit:].decode("utf-8", errors="replace")
    except Exception:
        return ""


class AdminGuiHandler(BaseHTTPRequestHandler):
    server: "AdminGuiServer"  # type: ignore[assignment]

    # Explicit dispatch tables (path -> route handler) assembled once from the
    # per-area admin_gui_routes modules.  do_GET/do_POST consult these for the
    # simple single-call endpoints, then fall through to the special-case
    # branches below (prefix matches and routes with inline request validation).
    # Built lazily on first request so test stubs can import the class without a
    # populated table; cached on the class to avoid rebuilding per request.
    _GET_ROUTES: "Optional[Dict[str, Any]]" = None
    _POST_ROUTES: "Optional[Dict[str, Any]]" = None

    @classmethod
    def _get_route_table(cls) -> Dict[str, Any]:
        if cls._GET_ROUTES is None:
            cls._GET_ROUTES = admin_gui_routes.get_routes()
        return cls._GET_ROUTES

    @classmethod
    def _post_route_table(cls) -> Dict[str, Any]:
        if cls._POST_ROUTES is None:
            cls._POST_ROUTES = admin_gui_routes.post_routes()
        return cls._POST_ROUTES

    def _route_path(self) -> str:
        """Return the request path without query string (urlparse(self.path).path)."""
        return urlparse(self.path).path

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[noemaforge-admin-gui] " + fmt % args + "\n")

    @property
    def root(self) -> Path:
        return self.server.root

    @property
    def ui_dir(self) -> Path:
        return self.server.ui_dir

    def _send_json(self, obj: Any, status: int = 200) -> None:
        data = (json_dumps(obj) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_sse(self, events: Sequence[Dict[str, Any]], status: int = 200) -> None:
        text = "retry: 3000\n\n" + "".join(
            sse_event(str(item.get("event") or "message"), item.get("data") if isinstance(item.get("data"), dict) else {}, event_id=str(item.get("id") or ""))
            for item in events
        )
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, data: bytes, content_type: str = "application/octet-stream", status: int = 200, *, head_only: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > MAX_BODY:
            raise ValueError("body too large")
        raw = self.rfile.read(length) if length else b"{}"
        if not raw.strip():
            return {}
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("body must be a JSON object")
        return data

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib API
        self._serve_static(urlparse(self.path).path, head_only=True)

    def do_GET(self) -> None:  # noqa: N802 - stdlib API
        path = urlparse(self.path).path
        try:
            # Explicit GET route table: simple single-call endpoints
            # (health/state/dashboard/locales/epoch-status/runtime/telemetry/
            # usecases/showcase/code-evolution-status, conversation, tasks,
            # inactivity, jobs list+stream, persona current/catalog, artifacts
            # open, pipelines catalog).  Checked before the special-case
            # branches below so exact matches still win over the startswith
            # prefixes (same effective ordering as the original if-chain).
            route = self._get_route_table().get(path)
            if route is not None:
                route(self)
                return

            if path == "/api/events":
                query = parse_qs(urlparse(self.path).query)
                try:
                    after = int((query.get("after_index") or ["0"])[0])
                except (TypeError, ValueError):
                    self._send_json({"ok": False, "error": "after_index must be an integer"}, status=400)
                    return
                if after < 0:
                    self._send_json({"ok": False, "error": "after_index must be >= 0"}, status=400)
                    return
                try:
                    limit = int((query.get("limit") or ["200"])[0])
                except (TypeError, ValueError):
                    limit = 200
                # Clamp limit: prevent DoS via huge values; file bounded by MAX_EVENT_LINES
                # but response serialisation of 10 000 rows is still ~3 MB per request.
                limit = min(max(1, limit), 1000)
                self._send_json(self.server.events_api(after_index=after, limit=limit))
                return
            if path == "/api/session/current":
                query = parse_qs(urlparse(self.path).query)
                # Clamp session_id to 128 chars to prevent unbounded JSON growth in
                # the stored session record (matches POST /api/session/mode clamping).
                session_id = str((query.get("session_id") or ["default"])[0])[:128]
                self._send_json(self.server.session_current(session_id))
                return
            if path == "/api/artifacts/download":
                query = parse_qs(urlparse(self.path).query)
                payload = self.server.artifact_download_payload(str((query.get("path") or [""])[0]))
                if not payload.get("ok"):
                    self._send_json(payload, status=404 if payload.get("error") == "artifact not found" else 403)
                    return
                data = payload.get("data") if isinstance(payload.get("data"), bytes) else b""
                self.send_response(200)
                self.send_header("Content-Type", str(payload.get("content_type") or "application/octet-stream"))
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", f"attachment; filename=\"{safe_id(str(payload.get('filename') or 'artifact'), 'artifact')}\"")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            if path.startswith("/api/persona/fallback-avatar/"):
                name = safe_id(path.rsplit("/", 1)[-1].replace(".svg", "")) + ".svg"
                candidate = (self.server.data_root / "personas" / "avatars" / "fallback" / name).resolve()
                if candidate.exists():
                    self._send_bytes(candidate.read_bytes(), "image/svg+xml")
                else:
                    self._send_json({"ok": False, "error": "fallback avatar not found"}, status=404)
                return
            if path.startswith("/api/pipelines/"):
                parts = path.split("/")
                if len(parts) >= 5:
                    pipeline_id = unquote(parts[3])
                    action = parts[4]
                    if action == "diagram":
                        self._send_json(self.server.pipeline_diagram(pipeline_id))
                        return
                    if action == "stats":
                        self._send_json(self.server.pipeline_stats(pipeline_id))
                        return
                self._send_json({"ok": False, "error": "unknown pipeline API path"}, status=404)
                return
            if path.startswith("/api/jobs/"):
                job_id = unquote(path.rsplit("/", 1)[-1])
                self._send_json(self.server.job_get(job_id))
                return
            self._serve_static(path)
        except Exception as exc:  # pragma: no cover - server safety net
            # Guard against double-response: if wfile.write() already failed (e.g.
            # BrokenPipeError on client disconnect mid-stream), the second _send_json
            # call would also raise — suppress it to avoid propagating to the server.
            try:
                self._send_json({"ok": False, "error": repr(exc)}, status=500)
            except Exception:
                pass

    def do_POST(self) -> None:  # noqa: N802 - stdlib API
        path = urlparse(self.path).path
        try:
            body = self._read_json_body()
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        try:
            if path == "/api/session/mode":
                try:
                    composite_top_n = int(body.get("composite_top_n") or 0)
                except (TypeError, ValueError):
                    self._send_json({"ok": False, "error": "composite_top_n must be an integer"}, status=400)
                    return
                self._send_json(self.server.session_mode(
                    str(body.get("mode") or "normal"),
                    composite_top_n=composite_top_n,
                ))
                return
            # Explicit POST route table: simple single-call endpoints
            # (admin/message family, conversation/reset, tasks/*, pipeline/draft/
            # run/approve/advance, modify-pipeline, model-evolution/run,
            # model-selection plan/apply/continue, epoch/apply, vault/reinventory,
            # code-evolution propose/status, runtime/device-policy, workflow/stop,
            # dev-team/*).  Checked after the inline /api/session/mode branch
            # (which keeps its composite_top_n validation) and before the
            # /api/jobs/<id>/cancel prefix + /api/shutdown special cases, so the
            # effective dispatch order is unchanged from the original if-chain.
            route = self._post_route_table().get(path)
            if route is not None:
                route(self, body)
                return
            if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                job_id = unquote(path.split("/")[-2])
                self._send_json(self.server.job_cancel(job_id))
                return
            if path == "/api/shutdown":
                self.server.record_system_event("shutdown", {"reason": body.get("reason") or "operator"})
                self._send_json({"ok": True, "message": "NoemaForge Admin GUI shutdown requested"})
                threading.Timer(0.25, self.server.shutdown).start()
                return
            self._send_json({"ok": False, "error": f"unknown API endpoint: {path}"}, status=404)
        except Exception as exc:  # pragma: no cover - server safety net
            try:
                self._send_json({"ok": False, "error": repr(exc)}, status=500)
            except Exception:
                pass

    def _serve_static(self, path: str, *, head_only: bool = False) -> None:
        rel = unquote(path).lstrip("/") or "index.html"
        if rel.startswith("api/"):
            self._send_json({"ok": False, "error": "not found"}, status=404)
            return
        if rel.startswith("ui/"):
            candidate = (self.root / rel).resolve()
            allowed = self.root in candidate.parents or candidate == self.root
            if not allowed or not candidate.exists() or candidate.is_dir():
                self._send_json({"ok": False, "error": "static asset not found", "path": rel}, status=404)
                return
        else:
            candidate = (self.ui_dir / rel).resolve()
            if not (candidate == self.ui_dir or self.ui_dir in candidate.parents) or not candidate.exists() or candidate.is_dir():
                candidate = self.ui_dir / "index.html"
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        self._send_bytes(candidate.read_bytes(), content_type, head_only=head_only)


class AdminGuiServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], root: Path, state: Path, persona_state: Path, evolution_state: Path, model_selection_state: Path, dev_team_state: Path):
        self.root = root.resolve()
        self.state = state.resolve()
        self.persona_state = persona_state.resolve()
        self.evolution_state = evolution_state.resolve()
        self.model_selection_state = model_selection_state.resolve()
        self.dev_team_state = dev_team_state.resolve()
        self.data_root = DEFAULT_DATA_ROOT
        self.gui_state_dir = self.data_root / "gui"
        self.event_log = EventLog(self.data_root / "events")
        self.session_store = SessionStore(self.gui_state_dir / "sessions")
        self.jobs_dir = self.data_root / "jobs"
        self.job_manager = JobManager(self.jobs_dir)
        self.tasks_dir = self.data_root / "tasks"
        self.review_dir = self.data_root / "review"
        # Protect job read-modify-write cycles from concurrent request threads.
        # ThreadingHTTPServer dispatches each request on its own thread;
        # _upsert_job(), _persist_job(), and job_cancel() all do jobs_data()
        # + _write_json() without atomicity — the last writer wins otherwise.
        self._jobs_lock = threading.Lock()
        # Protect task read-modify-write cycles from concurrent request threads
        # (same pattern as _jobs_lock above — task_create and task_update both
        # do tasks_data() + _write_json() without a lock otherwise).
        self._tasks_lock = threading.Lock()
        # Protect conversation read-modify-write cycles (save_message).
        # Lock order: _tasks_lock → _conv_lock (task_create holds _tasks_lock
        # then calls save_message which acquires _conv_lock — never reversed).
        self._conv_lock = threading.Lock()
        self.runtime_dir = self.data_root / "runtime"
        self.bootstrap_dir = DEFAULT_BOOTSTRAP_DIR
        self.modelstore_dir = DEFAULT_MODELSTORE_DIR
        self.llm_gateway_socket = DEFAULT_LLM_GATEWAY_SOCKET
        self.llm_main_backend_socket = DEFAULT_LLM_MAIN_BACKEND_SOCKET
        self.legacy_llm_gateway_socket = DEFAULT_LEGACY_LLM_GATEWAY_SOCKET
        self.ui_dir = self.root / "templates" / "pipeline-dashboard"
        if not self.ui_dir.exists():
            raise SystemExit(f"missing dashboard UI: {self.ui_dir}")
        for d in [self.gui_state_dir, self.jobs_dir, self.tasks_dir, self.review_dir / "sr" / "inbox", self.review_dir / "ssr" / "inbox", self.runtime_dir, self.model_selection_state]:
            d.mkdir(parents=True, exist_ok=True)
        super().__init__(address, AdminGuiHandler)

    def env(self, locale: str = "") -> Dict[str, str]:
        env = os.environ.copy()
        env["NOEMAFORGE_ROOT"] = str(self.root)
        env["NOEMAFORGE_PIPELINE_STATE"] = str(self.state)
        env["NOEMAFORGE_PERSONA_STATE"] = str(self.persona_state)
        env["NOEMAFORGE_MODEL_EVOLUTION_STATE"] = str(self.evolution_state)
        env["NOEMAFORGE_MODEL_SELECTION_STATE"] = str(self.model_selection_state)
        env["NOEMAFORGE_DEV_TEAM_STATE"] = str(self.dev_team_state)
        env["NOEMAFORGE_BOOTSTRAP_DIR"] = str(self.bootstrap_dir)
        env["NOEMAFORGE_MODELSTORE_DIR"] = str(self.modelstore_dir)
        env["NOEMAFORGE_GATEWAY_SOCKET"] = str(self.llm_gateway_socket)
        env["NOEMAFORGE_MAIN_BACKEND_SOCKET"] = str(self.llm_main_backend_socket)
        if locale:
            env["NOEMAFORGE_LANG"] = locale
        return env

    def _read_json(self, path: Path, default: Any) -> Any:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - fallback is intentional
            # Surface file corruption to the operator log without disrupting
            # availability.  Callers receive the safe default and continue.
            import sys as _sys
            _sys.stderr.write(f"[NoemaForge] _read_json: corrupt or unreadable {path}: {exc}\n")
            return default
        return default

    def _write_json(self, path: Path, obj: Any) -> None:
        """Write obj as pretty JSON to path atomically via a tmp-then-replace.

        The tmp-then-replace pattern prevents partial reads of a half-written file
        (consistent with SessionStore._write_atomic() and EventLog copy-then-truncate).
        On Windows, os.replace() can replace a file that is open for reading.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            tmp.write_text(json_dumps(obj), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _append_jsonl(self, path: Path, obj: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")

    def artifact_allowed_roots(self) -> List[Path]:
        roots = [self.data_root, self.state, self.model_selection_state, self.evolution_state, self.dev_team_state]
        return [root.resolve() for root in roots if str(root)]

    def resolve_artifact_path(self, raw_path: str) -> Dict[str, Any]:
        text = str(raw_path or "").strip()
        if not text or text.startswith("~"):
            return {"ok": False, "error": "artifact path is required", "path": text}
        candidate = Path(text)
        if not candidate.is_absolute():
            return {"ok": False, "error": "artifact path must be absolute", "path": text}
        try:
            resolved = candidate.resolve()
        except Exception as exc:
            return {"ok": False, "error": f"artifact path resolution failed: {exc}", "path": text}
        allowed = any(resolved == root or root in resolved.parents for root in self.artifact_allowed_roots())
        if not allowed:
            return {"ok": False, "error": "artifact path outside allowed roots", "path": str(resolved)}
        if not resolved.exists():
            return {"ok": False, "error": "artifact not found", "path": str(resolved)}
        return {"ok": True, "path": str(resolved), "is_dir": resolved.is_dir(), "size": resolved.stat().st_size if resolved.is_file() else 0}

    def artifact_open(self, raw_path: str) -> Dict[str, Any]:
        resolved = self.resolve_artifact_path(raw_path)
        if not resolved.get("ok"):
            return {"ok": False, "version": RUNTIME_VERSION, **resolved}
        path = Path(str(resolved["path"]))
        if path.is_dir():
            children = [{"name": child.name, "is_dir": child.is_dir()} for child in sorted(path.iterdir(), key=lambda item: item.name.lower())[:80]]
            return {"ok": True, "version": RUNTIME_VERSION, "kind": "directory", "path": str(path), "children": children, "download_url": ""}
        data = path.read_bytes()[:MAX_ARTIFACT_PREVIEW_BYTES]
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        preview = data.decode("utf-8", errors="replace") if content_type.startswith("text/") or path.suffix.lower() in {".json", ".md", ".txt", ".log", ".yaml", ".yml"} else ""
        return {
            "ok": True,
            "version": RUNTIME_VERSION,
            "kind": "file",
            "path": str(path),
            "filename": path.name,
            "content_type": content_type,
            "size": resolved.get("size", 0),
            "truncated": int(resolved.get("size", 0)) > len(data),
            "preview": preview,
            "download_url": artifact_action_url("download", str(path)),
        }

    def artifact_download_payload(self, raw_path: str) -> Dict[str, Any]:
        resolved = self.resolve_artifact_path(raw_path)
        if not resolved.get("ok"):
            return {"ok": False, "version": RUNTIME_VERSION, **resolved}
        path = Path(str(resolved["path"]))
        if path.is_dir():
            return {"ok": False, "version": RUNTIME_VERSION, "error": "directory download is not supported", "path": str(path)}
        return {
            "ok": True,
            "version": RUNTIME_VERSION,
            "path": str(path),
            "filename": path.name,
            "content_type": mimetypes.guess_type(str(path))[0] or "application/octet-stream",
            "data": path.read_bytes(),
        }

    def health(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "version": RUNTIME_VERSION,
            "mode": "admin_gui",
            "inside_gui_supported": True,
            "root": str(self.root),
            "state": str(self.state),
            "api": [
                "/api/admin/message", "/api/events",
                "/api/conversation/current", "/api/conversation/history",
                "/api/session/current", "/api/session/mode",
                "/api/dashboard", "/api/dashboard/state",
                "/api/artifacts/open", "/api/artifacts/download",
                "/api/tasks", "/api/inactivity/status", "/api/jobs", "/api/jobs/{job_id}/cancel", "/api/jobs/stream", "/api/pipelines/catalog",
                "/api/persona/current", "/api/telemetry/status", "/api/runtime/status",
                "/api/runtime/observer-cards", "/api/runtime/device-policy", "/api/model-evolution/run", "/api/model-selection/plan",
                "/api/model-selection/continue", "/api/epoch/status", "/api/epoch/apply",
                "/api/vault/reinventory",
                "/api/usecases", "/api/public-showcase/scenario", "/api/locales", "/api/shutdown",
            ],
        }

    # --- event log -----------------------------------------------------------------
    def events_api(self, after_index: int = 0, limit: int = 200) -> Dict[str, Any]:
        """Return append-only event log entries for GUI polling.

        Includes server_epoch and rotation_count so browser pollers can detect
        server restarts and in-process rotations and reset lastEventIndex=0.
        server_epoch: opaque token that changes on every server restart; pollers
          must reset lastEventIndex when this value changes.
        rotation_count: increments on each in-process log rotation.
        """
        try:
            events = self.event_log.read(after_index=int(after_index or 0), limit=int(limit or 200))
        except Exception as exc:
            return {
                "ok": False,
                "version": RUNTIME_VERSION,
                "events": [],
                "count": 0,
                "server_epoch": "",
                "rotation_count": 0,
                "error": str(exc),
            }
        # status() is best-effort: if it fails, still return the events we already
        # fetched rather than discarding them.
        try:
            st = self.event_log.status()
            server_epoch = st.get("server_epoch", "")
            rotation_count = int(st.get("rotation_count", 0))
        except Exception:
            server_epoch = ""
            rotation_count = 0
        return {
            "ok": True,
            "version": RUNTIME_VERSION,
            "events": events,
            "count": len(events),
            "server_epoch": server_epoch,
            "rotation_count": rotation_count,
        }

    # --- session state ----------------------------------------------------------------
    def session_mode(self, mode: str, composite_top_n: int = 0) -> Dict[str, Any]:
        """Persist the selected model-selection mode across browser refreshes."""
        session = self.session_store.set_mode("default", mode, composite_top_n)
        return {"ok": True, "version": RUNTIME_VERSION, "session": session}

    # --- conversation/review state -------------------------------------------------
    def conversation_file(self) -> Path:
        return self.gui_state_dir / "conversation-current.json"

    def _conversation(self) -> Dict[str, Any]:
        conv = self._read_json(self.conversation_file(), {})
        if not isinstance(conv, dict) or not conv.get("conversation_id"):
            conv = {"conversation_id": "conv_default", "created_at": now_iso(), "updated_at": now_iso(), "locale": "ru", "active_persona": "Admin", "pending_intent": None, "pending_payload": {}, "messages": [], "artifacts": [], "jobs": []}
            self._write_json(self.conversation_file(), conv)
        return conv

    def _save_conversation(self, conv: Dict[str, Any]) -> None:
        conv["updated_at"] = now_iso()
        self._write_json(self.conversation_file(), conv)

    def save_message(self, role: str, text: str, *, persona: str = "Admin", locale: str = "", intent: str = "", artifacts: Optional[List[Dict[str, Any]]] = None, raw: Optional[Dict[str, Any]] = None, system_event: bool = False, trace_id: str = "") -> Dict[str, Any]:
        # Acquire _conv_lock to serialise concurrent save_message() calls on
        # the conversation R-M-W cycle (_conversation + _save_conversation).
        # Lock order: _tasks_lock → _conv_lock (task_create holds _tasks_lock
        # first, then calls save_message — never the other way around).
        with self._conv_lock:
            conv = self._conversation()
            idx = len(conv.get("messages", [])) + 1
            raw_trace = raw.get("trace_id") if isinstance(raw, dict) else ""
            tid = str(trace_id or raw_trace or production_ai_contracts.new_trace_id("gui-msg"))
            affordance_artifacts = enrich_artifact_cards(artifacts)
            msg = {
                "message_id": f"msg_{int(time.time())}_{idx}",
                "trace_id": tid,
                "conversation_id": conv["conversation_id"],
                "ts": now_iso(),
                "role": role,
                "persona": persona,
                "locale": locale or conv.get("locale", "ru"),
                "intent": intent,
                "text": text,
                "artifacts": affordance_artifacts,
                "system_event": bool(system_event),
            }
            conv.setdefault("messages", []).append(msg)
            if affordance_artifacts:
                conv.setdefault("artifacts", []).extend(affordance_artifacts)
            if locale:
                conv["locale"] = locale
            if persona:
                conv["active_persona"] = persona
            self._save_conversation(conv)
        self._append_jsonl(self.gui_state_dir / "messages.jsonl", msg)
        review = dict(msg)
        review["raw_ref"] = None
        if raw is not None:
            raw_path = self.gui_state_dir / "raw" / f"{msg['message_id']}.json"
            self._write_json(raw_path, raw)
            review["raw_ref"] = str(raw_path)
        review["sr_review"] = {"required": True, "status": "pending"}
        review["ssr_review"] = {"required": intent in {"epoch_apply", "model_selection", "model_evolution", "task_update", "pipeline_modify"}, "status": "pending" if intent else "not_required"}
        self._write_json(self.review_dir / "sr" / "inbox" / f"{msg['message_id']}.json", review)
        if review["ssr_review"]["required"]:
            self._write_json(self.review_dir / "ssr" / "inbox" / f"{msg['message_id']}.json", review)
        # Also persist in session_store for browser-refresh restore.
        try:
            self.session_store.append_message("default", msg)
        except Exception:
            pass
        return msg

    def record_system_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        self.save_message("system", f"System event: {event_type}", persona="System", intent=event_type, artifacts=payload.get("artifacts") or [], raw=payload, system_event=True)

    def conversation_current(self) -> Dict[str, Any]:
        conv = self._conversation()
        conv = dict(conv)
        conv["artifacts"] = enrich_artifact_cards(conv.get("artifacts") if isinstance(conv.get("artifacts"), list) else [])
        conv["messages"] = [
            {**msg, "artifacts": enrich_artifact_cards(msg.get("artifacts") if isinstance(msg.get("artifacts"), list) else [])}
            for msg in conv.get("messages", [])
            if isinstance(msg, dict)
        ]
        return {"ok": True, "version": RUNTIME_VERSION, "conversation": conv}

    def conversation_history(self) -> Dict[str, Any]:
        conv = self._conversation()
        messages = [
            {**msg, "artifacts": enrich_artifact_cards(msg.get("artifacts") if isinstance(msg.get("artifacts"), list) else [])}
            for msg in conv.get("messages", [])
            if isinstance(msg, dict)
        ]
        artifacts = enrich_artifact_cards(conv.get("artifacts") if isinstance(conv.get("artifacts"), list) else [])
        return {"ok": True, "version": RUNTIME_VERSION, "conversation_id": conv.get("conversation_id"), "messages": messages, "artifacts": artifacts, "pending_intent": conv.get("pending_intent"), "pending_payload": conv.get("pending_payload", {})}

    def conversation_reset(self) -> Dict[str, Any]:
        old = self._conversation()
        archive = self.gui_state_dir / "archive" / f"{old.get('conversation_id','conv')}_{int(time.time())}.json"
        self._write_json(archive, old)
        self.conversation_file().unlink(missing_ok=True)
        new = self._conversation()
        return {"ok": True, "version": RUNTIME_VERSION, "archived": str(archive), "conversation": new}

    # --- persona --------------------------------------------------------------------
    def persona_catalog(self) -> Dict[str, Any]:
        return self._read_json(self.root / "configs" / "persona-catalog.json", {"personas": {}})

    def persona_catalog_api(self) -> Dict[str, Any]:
        catalog = self.persona_catalog()
        personas = catalog.get("personas") or {}
        items = []
        for role_key, p in personas.items():
            item = dict(p)
            item["role_key"] = role_key
            portrait = str(item.get("portrait") or "")
            item["portrait_url"] = "/" + portrait.lstrip("/") if portrait else self.fallback_avatar_url(role_key)
            items.append(item)
        return {"ok": True, "version": RUNTIME_VERSION, "personas": items}

    def persona_for_name(self, name: str) -> Dict[str, Any]:
        mapping = {
            "Admin": "operator.admin/administrator",
            "Optimizer": "system.guard/sr",
            "Model Evolution": "system.guard/ssr",
            "Dev Team": "dev.work/dev",
            "Music Team": "writing.story/writer",
            "Video Team": "video.generator",
            "Vision Team": "vision.segmenter",
            "Camera Mask Team": "vision.segmenter",
        }
        role_key = mapping.get(name, name if "/" in name else "operator.admin/administrator")
        personas = self.persona_catalog().get("personas") or {}
        p = dict(personas.get(role_key) or personas.get("operator.admin/administrator") or {})
        p.setdefault("role_key", role_key)
        return p

    def fallback_avatar_url(self, role_key: str) -> str:
        """Return a stable per-person fallback avatar URL without requiring runtime writes to /opt."""
        name = safe_id(role_key) + ".svg"
        fallback = self.root / "ui" / "personas" / "avatars" / "fallback" / name
        if fallback.exists():
            return "/" + str(fallback.relative_to(self.root)).replace(os.sep, "/")
        color = "#" + __import__("hashlib").sha256(role_key.encode()).hexdigest()[:6]
        initials = "".join([part[:1].upper() for part in re.split(r"[./_-]+", role_key) if part])[:3] or "NF"
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256"><rect width="256" height="256" rx="44" fill="#07111d"/><circle cx="128" cy="104" r="70" fill="{color}" opacity="0.85"/><text x="128" y="148" text-anchor="middle" font-family="Inter,Arial" font-size="54" font-weight="700" fill="#e8f2ff">{initials}</text><text x="128" y="222" text-anchor="middle" font-family="Inter,Arial" font-size="18" fill="#95a7bd">NoemaForge</text></svg>'''
        try:
            fallback.parent.mkdir(parents=True, exist_ok=True)
            fallback.write_text(svg, encoding="utf-8")
            return "/" + str(fallback.relative_to(self.root)).replace(os.sep, "/")
        except Exception:
            data_fallback = self.data_root / "personas" / "avatars" / "fallback" / name
            data_fallback.parent.mkdir(parents=True, exist_ok=True)
            data_fallback.write_text(svg, encoding="utf-8")
            return "/api/persona/fallback-avatar/" + name

    def persona_current(self) -> Dict[str, Any]:
        conv = self._conversation()
        persona_name = conv.get("active_persona") or "Admin"
        p = self.persona_for_name(str(persona_name))
        portrait = str(p.get("portrait") or "")
        path = self.root / portrait if portrait else Path("/missing")
        portrait_url = "/" + portrait.lstrip("/") if portrait and path.exists() else self.fallback_avatar_url(str(p.get("role_key") or persona_name))
        return {"ok": True, "version": RUNTIME_VERSION, "active_persona": persona_name, "persona": p, "portrait_url": portrait_url, "fallback": not (portrait and path.exists())}

    # --- tasks/jobs ------------------------------------------------------------------
    def task_store_file(self) -> Path:
        return self.tasks_dir / "tasks.json"

    def tasks_data(self) -> Dict[str, Any]:
        data = self._read_json(self.task_store_file(), {"tasks": []})
        if not isinstance(data, dict):
            data = {"tasks": []}
        data.setdefault("tasks", [])
        return data

    def tasks_list(self) -> Dict[str, Any]:
        # Acquire _tasks_lock so reads are consistent with concurrent
        # task_create()/task_update() writes (same pattern as jobs_list/_jobs_lock).
        with self._tasks_lock:
            data = self.tasks_data()
            tasks = data.get("tasks", [])
            categories = {}
            for t in tasks:
                categories[t.get("category", "uncategorized")] = categories.get(t.get("category", "uncategorized"), 0) + 1
        return {"ok": True, "version": RUNTIME_VERSION, "tasks": tasks, "summary": {"total": len(tasks), "by_category": categories, "pending": sum(1 for t in tasks if t.get("status") == "pending"), "blocked": sum(1 for t in tasks if t.get("status") == "blocked")}}

    def task_create(self, body: Dict[str, Any]) -> Dict[str, Any]:
        with self._tasks_lock:
            data = self.tasks_data()
            title = str(body.get("title") or body.get("task") or body.get("request") or "Untitled task")
            task = {
                "task_id": "task_" + safe_id(str(int(time.time())) + "_" + title, "task"),
                "title": title,
                "category": str(body.get("category") or "general"),
                "priority": int(body.get("priority") or 50),
                "status": str(body.get("status") or "pending"),
                "assignee": str(body.get("assignee") or "Admin"),
                "created_by": str(body.get("created_by") or "Admin"),
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "requires_approval": bool(body.get("requires_approval", True)),
                "artifacts": [],
            }
            data.setdefault("tasks", []).append(task)
            self._write_json(self.task_store_file(), data)
        self.save_message("system", f"Task created: {task['title']}", persona="Task Manager", intent="task_create", raw=task)
        return {"ok": True, "version": RUNTIME_VERSION, "task": task, "reply": f"Task created: {task['title']}"}

    def task_update(self, body: Dict[str, Any]) -> Dict[str, Any]:
        task_id = str(body.get("task_id") or body.get("id") or "")
        with self._tasks_lock:
            data = self.tasks_data()
            found = None
            for t in data.get("tasks", []):
                if t.get("task_id") == task_id:
                    found = t
                    break
            if not found:
                return {"ok": False, "version": RUNTIME_VERSION, "error": "task not found", "task_id": task_id}
            for key in ["title", "category", "priority", "status", "assignee", "deadline", "notes"]:
                if key in body:
                    found[key] = body[key]
            found["updated_at"] = now_iso()
            self._write_json(self.task_store_file(), data)
        self.save_message("system", f"Task updated: {task_id}", persona="Task Manager", intent="task_update", raw=found)
        return {"ok": True, "version": RUNTIME_VERSION, "task": found, "reply": f"Task updated: {task_id}"}

    def task_block(self, body: Dict[str, Any]) -> Dict[str, Any]:
        update = dict(body)
        update["status"] = "blocked"
        if body.get("reason") and not body.get("notes"):
            update["notes"] = "Blocked: " + str(body.get("reason"))
        result = self.task_update(update)
        if result.get("ok"):
            result["reply"] = f"Task blocked: {result['task']['task_id']}"
        return result

    def task_complete(self, body: Dict[str, Any]) -> Dict[str, Any]:
        update = dict(body)
        update["status"] = "completed"
        result = self.task_update(update)
        if result.get("ok"):
            result["reply"] = f"Task completed: {result['task']['task_id']}"
        return result

    def task_prioritize(self, body: Dict[str, Any]) -> Dict[str, Any]:
        update = dict(body)
        if "priority" not in update:
            update["priority"] = 80
        result = self.task_update(update)
        if result.get("ok"):
            result["reply"] = f"Task priority updated: {result['task']['task_id']} -> {result['task']['priority']}"
        return result

    def jobs_file(self) -> Path:
        return self.jobs_dir / "jobs.json"

    def job_file(self, job_id: str) -> Path:
        return self.jobs_dir / f"{safe_id(str(job_id))}.json"

    def job_cancel_marker_file(self, job_id: str) -> Path:
        return self.jobs_dir / f"{safe_id(str(job_id))}.cancel"

    def jobs_data(self) -> Dict[str, Any]:
        manager = getattr(self, "job_manager", None)
        if manager is not None:
            return manager._read_index()
        data = self._read_json(self.jobs_file(), {"jobs": []})
        if not isinstance(data, dict):
            data = {"jobs": []}
        data.setdefault("jobs", [])
        return data

    def _upsert_job(self, job: Dict[str, Any], *, idempotency_key: str = "") -> Dict[str, Any]:
        manager = getattr(self, "job_manager", None)
        if manager is not None:
            return manager._save(dict(job))
        with self._jobs_lock:
            data = self.jobs_data()
            if idempotency_key:
                for existing in data.get("jobs", []):
                    if existing.get("idempotency_key") == idempotency_key and existing.get("status") in {"queued", "starting", "running", "needs_privilege", "cancel_requested"}:
                        return existing
            data.setdefault("jobs", []).append(job)
            self._write_json(self.jobs_file(), data)
            # Write the normalized schema to the per-job file so job_get()
            # always reads a schema-complete record regardless of which code
            # path created the job.
            self._write_json(self.job_file(str(job["job_id"])), normalize_job_record(dict(job)))
            return job

    def create_job(self, kind: str, *, status: str = "queued", progress: Optional[Dict[str, Any]] = None, command: str = "", artifacts: Optional[List[Dict[str, Any]]] = None, idempotency_key: str = "", trace_id: str = "") -> Dict[str, Any]:
        if hasattr(self, "job_manager"):
            return self.job_manager.create(
                kind,
                status=status,
                progress=progress or {},
                command=command,
                artifacts=enrich_artifact_cards(artifacts),
                idempotency_key=idempotency_key,
                trace_id=trace_id or production_ai_contracts.new_trace_id(f"job-{kind}"),
            )
        job_id = "job_" + now_iso().replace(":", "").replace("-", "").replace("Z", "Z_") + safe_id(kind)
        job = {"job_id": job_id, "trace_id": trace_id or production_ai_contracts.new_trace_id(f"job-{kind}"), "kind": kind, "status": status, "created_at": now_iso(), "updated_at": now_iso(), "progress": progress or {}, "command": command, "artifacts": enrich_artifact_cards(artifacts), "idempotency_key": idempotency_key}
        return self._upsert_job(job, idempotency_key=idempotency_key)

    def _persist_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        manager = getattr(self, "job_manager", None)
        if manager is not None:
            return manager._save(dict(job))
        with self._jobs_lock:
            data = self.jobs_data()
            jobs = data.setdefault("jobs", [])
            replaced = False
            for index, existing in enumerate(jobs):
                if existing.get("job_id") == job.get("job_id"):
                    jobs[index] = job
                    replaced = True
                    break
            if not replaced:
                jobs.append(job)
            self._write_json(self.jobs_file(), data)
            # Write normalized schema for schema-consistency with job_get().
            self._write_json(self.job_file(str(job["job_id"])), normalize_job_record(dict(job)))
            return job

    def jobs_list(self) -> Dict[str, Any]:
        manager = getattr(self, "job_manager", None)
        if manager is not None:
            jobs = []
            for job in manager.list_all():
                item = normalize_job_record(dict(job))
                item.update({key: value for key, value in job.items() if key not in item})
                item["artifacts"] = enrich_artifact_cards(item.get("artifacts") if isinstance(item.get("artifacts"), list) else [])
                jobs.append(item)
            try:
                active = [j for j in jobs if is_active_job(j)]
                self.session_store.attach_active_jobs("default", active)
            except Exception:
                pass
            return {"ok": True, "version": RUNTIME_VERSION, "jobs": jobs}
        # Acquire _jobs_lock so the read-then-copy cycle is consistent with
        # _upsert_job()/_persist_job()/job_cancel() which all write inside the
        # same lock.  The lock is released before the session_store sync to
        # avoid holding it during the (potentially slow) JSONL write.
        with self._jobs_lock:
            data = self.jobs_data()
            jobs = []
            for job in data.get("jobs", []):
                if isinstance(job, dict):
                    # normalize_job_record() guarantees all schema fields are
                    # present with safe defaults, then enrich_artifact_cards()
                    # adds GUI-specific display metadata on top.
                    item = normalize_job_record(dict(job))
                    # Preserve non-schema fields (idempotency_key, safe_command,
                    # real_command_requires_operator_terminal, privileged_runner
                    # metadata, ...) so a browser refresh restores the same enriched
                    # job the GUI showed — mirrors the job_manager branch above.
                    item.update({key: value for key, value in job.items() if key not in item})
                    item["artifacts"] = enrich_artifact_cards(item.get("artifacts") if isinstance(item.get("artifacts"), list) else [])
                    jobs.append(item)
        # Sync active jobs into session store for browser-refresh restore.
        # This is intentionally outside _jobs_lock to avoid holding the lock
        # during the session_store JSONL write.
        try:
            active = [j for j in jobs if is_active_job(j)]
            self.session_store.attach_active_jobs("default", active)
        except Exception:
            pass
        return {"ok": True, "version": RUNTIME_VERSION, "jobs": jobs}

    def session_current(self, session_id: str = "default") -> Dict[str, Any]:
        """Return the current session record from SessionStore."""
        try:
            session = self.session_store.load(session_id)
            return {"ok": True, "version": RUNTIME_VERSION, "session": session}
        except Exception as exc:
            return {"ok": False, "version": RUNTIME_VERSION, "session": {}, "error": str(exc)}

    def session_set_mode(self, session_id: str, mode: str, composite_top_n: int = 0) -> Dict[str, Any]:
        """Persist selected model-selection mode in session."""
        try:
            session = self.session_store.set_mode(session_id, mode, composite_top_n)
            return {"ok": True, "version": RUNTIME_VERSION, "session": session}
        except Exception as exc:
            return {"ok": False, "version": RUNTIME_VERSION, "error": str(exc)}

    def job_stream_events(self) -> List[Dict[str, Any]]:
        jobs = self.jobs_list().get("jobs", [])
        snapshot = {
            "ok": True,
            "version": RUNTIME_VERSION,
            "stream": "job_progress_sse",
            "created_at": now_iso(),
            "jobs": jobs,
        }
        events: List[Dict[str, Any]] = [{"event": "jobs_snapshot", "id": "jobs-snapshot", "data": snapshot}]
        for job in jobs[-20:]:
            if not isinstance(job, dict):
                continue
            events.append({
                "event": "job_progress",
                "id": f"{job.get('updated_at') or job.get('created_at') or now_iso()}-{job.get('job_id') or 'job'}",
                "data": {
                    "ok": True,
                    "version": RUNTIME_VERSION,
                    "stream": "job_progress_sse",
                    "job": job,
                    "progress": job.get("progress") if isinstance(job.get("progress"), dict) else {},
                },
            })
        return events

    def job_get(self, job_id: str) -> Dict[str, Any]:
        manager = getattr(self, "job_manager", None)
        if manager is not None:
            job = manager.get(job_id)
            if isinstance(job, dict):
                norm = normalize_job_record(dict(job))
                norm.update({key: value for key, value in job.items() if key not in norm})
                norm["artifacts"] = enrich_artifact_cards(norm.get("artifacts") if isinstance(norm.get("artifacts"), list) else [])
                job = norm
            return {"ok": bool(job), "version": RUNTIME_VERSION, "job": job or {}, "error": "job not found" if not job else ""}
        # Acquire _jobs_lock so reads are consistent with concurrent
        # _upsert_job()/_persist_job()/job_cancel() writes.
        with self._jobs_lock:
            job = self._read_json(self.job_file(job_id), None)
            if not job:
                for j in self.jobs_data().get("jobs", []):
                    if j.get("job_id") == job_id:
                        job = j
                        break
        if isinstance(job, dict):
            # normalize_job_record() guarantees all schema fields have safe
            # defaults; enrich_artifact_cards() adds GUI display metadata.
            job = normalize_job_record(dict(job))
            job["artifacts"] = enrich_artifact_cards(job.get("artifacts") if isinstance(job.get("artifacts"), list) else [])
        return {"ok": bool(job), "version": RUNTIME_VERSION, "job": job or {}, "error": "job not found" if not job else ""}

    def job_cancel(self, job_id: str) -> Dict[str, Any]:
        if hasattr(self, "job_manager"):
            existing = self.job_manager.get(job_id)
            if existing and existing.get("status") in FINAL_JOB_STATES:
                norm = normalize_job_record(dict(existing))
                norm.update({key: value for key, value in existing.items() if key not in norm})
                norm["artifacts"] = enrich_artifact_cards(norm.get("artifacts") if isinstance(norm.get("artifacts"), list) else [])
                return {"ok": False, "version": RUNTIME_VERSION, "job": norm, "reply": f"Job already in terminal state: {existing['status']}"}
            target = self.job_manager.cancel(job_id)
            if target:
                marker = self.job_cancel_marker_file(str(target["job_id"]))
                try:
                    marker.write_text(now_iso() + "\n", encoding="utf-8")
                except OSError:
                    pass
                norm = normalize_job_record(dict(target))
                norm.update({key: value for key, value in target.items() if key not in norm})
                norm["artifacts"] = enrich_artifact_cards(norm.get("artifacts") if isinstance(norm.get("artifacts"), list) else [])
                return {"ok": True, "version": RUNTIME_VERSION, "job": norm, "reply": "Cancel requested"}
            return {"ok": False, "version": RUNTIME_VERSION, "job": {}, "reply": "Job not found"}
        with self._jobs_lock:
            data = self.jobs_data()
            target = None
            for j in data.get("jobs", []):
                if j.get("job_id") == job_id:
                    if j.get("status") in FINAL_JOB_STATES:
                        # Job is already done/failed/cancelled — do not revert it.
                        # Return the normalized record so the UI can refresh its state.
                        norm = normalize_job_record(dict(j))
                        norm["artifacts"] = enrich_artifact_cards(norm.get("artifacts") if isinstance(norm.get("artifacts"), list) else [])
                        return {"ok": False, "version": RUNTIME_VERSION, "job": norm, "reply": f"Job already in terminal state: {j['status']}"}
                    # Use cancel_requested so running subprocesses can detect the
                    # request before the orchestrator confirms the final cancelled state.
                    j["status"] = "cancel_requested"
                    j["updated_at"] = now_iso()
                    target = j
            # Only write jobs.json when a job was actually mutated (task-84).
            # Skipping the write for not-found avoids a no-op disk round-trip
            # while holding _jobs_lock under concurrency.
            if target is not None:
                self._write_json(self.jobs_file(), data)
        # Initialize norm_target before the conditional so the ternary on the
        # final return line is always defined regardless of branch taken.
        norm_target: Dict[str, Any] = {}
        if target:
            jid = target["job_id"]
            # Intentionally outside _jobs_lock: the status update is already
            # committed to jobs.json under the lock above; these two writes are
            # supplementary (per-job JSON + cancel sentinel).  Both writes are
            # idempotent, so a concurrent duplicate call produces the same bytes.
            # _write_json() uses tmp-then-replace atomicity, so readers always
            # see a complete file even without the lock.
            norm_target = normalize_job_record(dict(target))
            norm_target["artifacts"] = enrich_artifact_cards(norm_target.get("artifacts") if isinstance(norm_target.get("artifacts"), list) else [])
            self._write_json(self.job_file(str(jid)), norm_target)
            # Write a sentinel file that long-running subprocesses can poll
            # without parsing JSON (lightweight cancel-marker check).
            marker = self.job_cancel_marker_file(str(jid))
            try:
                marker.write_text(now_iso() + "\n", encoding="utf-8")
            except OSError:
                pass
        result_job = norm_target if target else {}
        return {"ok": bool(target), "version": RUNTIME_VERSION, "job": result_job, "reply": "Cancel requested" if target else "Job not found"}

    # --- status/state ----------------------------------------------------------------
    def dashboard_state(self) -> Dict[str, Any]:
        cmd = [sys.executable, str(self.root / "src" / "pipeline_runtime.py"), "--root", str(self.root), "--state", str(self.state), "dashboard-state", "--persona-state", str(self.persona_state)]
        result = run_json(cmd, env=self.env(), timeout=60)
        if result.get("ok") and isinstance(result.get("stdout"), dict):
            doc = result["stdout"]
        else:
            doc = {"ok": False, "version": RUNTIME_VERSION, "error": "dashboard-state failed", "result": result}
        doc["admin_gui"] = self.health()
        persona = self.persona_current()
        doc["persona"] = persona.get("persona", doc.get("persona", {}))
        doc["persona"]["portrait_url"] = persona.get("portrait_url")
        conv = dict(self._conversation())
        conv["artifacts"] = enrich_artifact_cards(conv.get("artifacts") if isinstance(conv.get("artifacts"), list) else [])
        doc["conversation"] = conv
        doc["tasks"] = self.tasks_list().get("summary")
        doc["jobs"] = self.jobs_list().get("jobs", [])[-5:]
        return doc

    def dashboard_api(self) -> Dict[str, Any]:
        state = self.gui_state()
        state["endpoint"] = "/api/dashboard"
        state["dashboard_backend"] = {
            "endpoint": "/api/dashboard",
            "compatibility_endpoint": "/api/gui/state",
            "alias_endpoint": "/api/dashboard/state",
            "contract": "dashboard-api-endpoint-core",
            "state_source": "pipeline_runtime.dashboard-state",
        }
        dashboard = state.get("dashboard")
        if isinstance(dashboard, dict):
            dashboard.setdefault("backend_endpoint", "/api/dashboard")
            dashboard.setdefault("compatibility_endpoint", "/api/gui/state")
            dashboard.setdefault("backend_contract", "dashboard-api-endpoint-core")
        return state

    def gui_state(self) -> Dict[str, Any]:
        return {"ok": True, "version": RUNTIME_VERSION, "dashboard": self.dashboard_state(), "conversation": self.conversation_history(), "epoch": self.epoch_status(), "telemetry": self.telemetry_status(), "tasks": self.tasks_list(), "jobs": self.jobs_list(), "persona": self.persona_current(), "inactivity": self.inactivity_status(), "pipelines": self.pipeline_catalog_api()}

    def inactivity_status(self) -> Dict[str, Any]:
        conv = self._conversation()
        messages = conv.get("messages") or []
        last_ts = messages[-1].get("ts") if messages else conv.get("created_at")
        idle_sec = 0
        try:
            dt = datetime.fromisoformat(str(last_ts).replace("Z", "+00:00"))
            idle_sec = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
        except Exception:
            pass
        policy = self._read_json(self.root / "configs" / "inactivity-policy.json", {"mode": "manual_only", "next_idle_action": "none"})
        return {"ok": True, "version": RUNTIME_VERSION, "idle_seconds": idle_sec, "idle_human": f"{idle_sec//3600:02d}:{(idle_sec//60)%60:02d}:{idle_sec%60:02d}", "policy": policy, "status": "paused" if policy.get("mode") == "manual_only" else "active"}

    def runtime_status(self) -> Dict[str, Any]:
        sockets = [self.llm_gateway_socket, self.llm_main_backend_socket]
        if self.legacy_llm_gateway_socket is not None:
            sockets.append(self.legacy_llm_gateway_socket)
        sock_status = {_path_key(s): s.exists() for s in sockets}
        svc = run_json(["systemctl", "is-active", "noemaforge-llm-gateway.service"], timeout=10)
        main = run_json(["systemctl", "is-active", "noemaforge-llama@main.service"], timeout=10)
        main_model_dir = self.modelstore_dir / "models" / "main"
        main_manifest = self._read_json(main_model_dir / "noemaforge-model.json", {}) or self._read_json(main_model_dir / "brainos-model.json", {})
        doc = {"ok": True, "version": RUNTIME_VERSION, "sockets": sock_status, "gateway": svc, "main_backend": main, "main_manifest": main_manifest, "device_policy": self.device_policy().get("policy")}
        doc["observer_cards"] = build_runtime_observer_cards(doc)
        return doc

    def runtime_observer_cards(self) -> Dict[str, Any]:
        runtime = self.runtime_status()
        return {"ok": True, "version": RUNTIME_VERSION, "observer_cards": runtime.get("observer_cards", []), "runtime": runtime}

    def device_policy(self) -> Dict[str, Any]:
        path = self.runtime_dir / "device-policy.json"
        policy = self._read_json(path, {"policy": "cpu", "decision": "cpu_safe_always_on_with_gpu_on_demand", "pending_apply": False, "applies_on": "next_persona_or_model_switch_or_backend_restart", "gpu_policy": "explicit_on_demand", "gpu_autostart_enabled": False, "max_active_heavy_workers": 1, "updated_at": now_iso()})
        return {"ok": True, "version": RUNTIME_VERSION, "policy": policy}

    def device_policy_set(self, policy: str) -> Dict[str, Any]:
        if policy not in {"auto", "cpu", "gpu", "cuda"}:
            return {"ok": False, "version": RUNTIME_VERSION, "error": "policy must be auto|cpu|gpu"}
        normalized = "gpu" if policy == "cuda" else policy
        doc = {"policy": normalized, "pending_apply": True, "applies_on": "next_persona_or_model_switch_or_backend_restart", "updated_at": now_iso(), "note": "Changing device policy does not migrate the currently running model; it applies only on the next persona/model switch or backend restart."}
        self._write_json(self.runtime_dir / "device-policy.json", doc)
        self.save_message("system", f"Runtime device policy staged: {normalized}", persona="Runtime", intent="device_policy", raw=doc)
        return {"ok": True, "version": RUNTIME_VERSION, "reply": f"Device policy staged: {normalized}. It will apply on the next persona/model switch or backend restart.", "policy": doc}

    def _command_output(self, cmd: Sequence[str], timeout: int = 8) -> Dict[str, Any]:
        if shutil.which(cmd[0]) is None and not Path(cmd[0]).exists():
            return {"available": False, "cmd": list(cmd), "stdout": "", "stderr": "missing command"}
        r = run_json(cmd, timeout=timeout)
        return {"available": True, **r}

    def telemetry_status(self) -> Dict[str, Any]:
        meminfo = {}
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meminfo[k] = v.strip()
        except Exception:
            pass
        nvidia = self._command_output(["nvidia-smi", "--query-gpu=name,temperature.gpu,power.draw,memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"], timeout=8)
        sensors = self._command_output(["sensors"], timeout=8)
        upower = self._command_output(["upower", "-d"], timeout=8)
        runtime = self.runtime_status()
        staff = self._read_json(self.bootstrap_dir / "firstboot-staffing-summary.json", {})
        decision = self._read_json(self.bootstrap_dir / "model-selection-decision.json", {})
        hardware = {"memory": {"MemTotal": meminfo.get("MemTotal"), "MemAvailable": meminfo.get("MemAvailable"), "SwapTotal": meminfo.get("SwapTotal"), "SwapFree": meminfo.get("SwapFree")}, "nvidia_smi": nvidia, "sensors": sensors, "upower": upower}
        creative_media = {
            "quality_evaluation_state": "not_measured_without_explicit_evaluator",
            "quality_claim_policy": "metadata_and_review_required",
            "note": "Telemetry cards show availability and metadata only; creative-media quality is not claimed without an explicit evaluator or review artifact.",
        }
        product = {
            "model_selection": {"staffing_state": staff.get("staffing_state"), "selected_model_count": staff.get("selected_model_count"), "missing_mandatory_core_roles": staff.get("missing_mandatory_core_roles"), "decision": decision},
            "creative_media": creative_media,
        }
        return {"ok": True, "version": RUNTIME_VERSION, "hardware": hardware, "runtime": runtime, "product": product, "creative_metrics_policy": "creative media uses metadata/review-required metrics unless an explicit evaluator is configured"}

    # --- epoch/model-selection -------------------------------------------------------
    def model_selection_progress(self) -> Dict[str, Any]:
        inventory = self._read_json(self.bootstrap_dir / "model-inventory.json", {})
        health_path = self.bootstrap_dir / "model-health-registry.json"
        records_path = self.bootstrap_dir / "model-run-records.json"
        health = self._read_json(health_path, {})
        records = self._read_json(records_path, [])
        total = (inventory.get("summary") or {}).get("logical_models_total") or len(inventory.get("models", [])) or 0
        tested = len(records) if isinstance(records, list) else 0
        failed_models: List[str] = []
        if isinstance(health, dict):
            models = health.get("models") or {}
            if isinstance(models, dict):
                failed_models = [m for m, rec in models.items() if rec.get("exclude_from_selection") or rec.get("health_state", "").startswith("failed")]
        return {"total_models": total, "tested_models": tested, "failed_models": len(failed_models), "failed_model_ids": failed_models[:100], "remaining_models": max(0, int(total or 0) - int(tested or 0)), "records_path": str(records_path), "health_registry": str(health_path)}

    def epoch_status(self) -> Dict[str, Any]:
        main_model_dir = self.modelstore_dir / "models" / "main"
        main_manifest = self._read_json(main_model_dir / "noemaforge-model.json", {}) or self._read_json(main_model_dir / "brainos-model.json", {})
        model_link = main_model_dir / "model.gguf"
        model_realpath = str(model_link.resolve()) if model_link.exists() else ""
        status = self._read_json(self.bootstrap_dir / "firstboot-status.json", {})
        staff = self._read_json(self.bootstrap_dir / "firstboot-staffing-summary.json", {})
        decision = self._read_json(self.bootstrap_dir / "model-selection-decision.json", {})
        candidate_plan = self._read_json(self.bootstrap_dir / "candidate-selection-plan.json", {})
        latest_msel = None
        for p in sorted(self.model_selection_state.glob("runs/msel_*"), reverse=True):
            if p.is_dir():
                latest_msel = p
                break
        latest_plan = self._read_json(latest_msel / "candidate-selection-plan.json", {}) if latest_msel else {}
        latest_decision = self._read_json(latest_msel / "model-selection-decision.json", {}) if latest_msel else {}
        return {"ok": True, "version": RUNTIME_VERSION, "current_epoch": {"manifest": main_manifest, "model_realpath": model_realpath}, "firstboot": {"status": status, "staffing": staff, "decision": decision, "candidate_plan": candidate_plan}, "latest_model_selection": {"run_dir": str(latest_msel) if latest_msel else "", "plan": latest_plan, "decision": latest_decision}, "progress": self.model_selection_progress(), "apply_available": bool(latest_plan or candidate_plan)}

    def model_selection(self, request: str, *, mode: str, scope: str, composite_top_n: int, apply: bool) -> Dict[str, Any]:
        trace_id = production_ai_contracts.new_trace_id("model-selection")
        cmd = [sys.executable, str(self.root / "src" / "model_selection_runtime.py"), "--root", str(self.root), "--state", str(self.model_selection_state), "plan", "--request", request, "--mode", mode, "--scope", scope, "--composite-top-n", str(composite_top_n), "--trace-id", trace_id, "--json"]
        if apply:
            cmd.append("--apply")
        env = self.env()
        env["NOEMAFORGE_TRACE_ID"] = trace_id
        result = run_json(cmd, env=env, timeout=120)
        stdout = result.get("stdout")
        if result.get("ok") and isinstance(stdout, dict):
            stdout.setdefault("trace_id", trace_id)
            artifacts = []
            artifact_map = stdout.get("artifacts") if isinstance(stdout.get("artifacts"), dict) else {}
            for key, path in artifact_map.items():
                artifacts.append({"type": "model_selection_artifact", "status": "created", "label": str(key).replace("_", "-"), "path": str(path), "open_command": "cat " + str(path)})
            reply = f"Режим отбора выбран: {stdout.get('mode', mode)}. Область: {stdout.get('scope', scope)}. План отбора модели создан; кандидаты, решение и rollback-plan прикреплены. Эпоха не применена без отдельного approve/apply."
            out = {"ok": True, "version": RUNTIME_VERSION, "trace_id": trace_id, "reply": reply, "run_id": stdout.get("run_id"), "run_dir": stdout.get("run_dir"), "mode": stdout.get("mode", mode), "scope": stdout.get("scope", scope), "status": stdout.get("status"), "artifacts": artifacts, "raw": stdout, "api": {"inside_gui_supported": True, "endpoint": "/api/model-selection/plan", "cmd": cmd}}
            self.save_message("model", reply, persona="Optimizer", locale="ru", intent="model_selection", artifacts=artifacts, raw=out, trace_id=trace_id)
            return out
        out = {"ok": False, "version": RUNTIME_VERSION, "trace_id": trace_id, "reply": "Model-selection plan failed.", "artifacts": [], "raw": result, "api": {"inside_gui_supported": True, "endpoint": "/api/model-selection/plan", "cmd": cmd}}
        self.save_message("model", out["reply"], persona="Optimizer", intent="model_selection", raw=out, trace_id=trace_id)
        return out

    def model_selection_continue(self, body: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.model_selection_progress()
        mode = str(body.get("mode") or "full_composite")
        n = int(body.get("composite_top_n") or 4)
        idkey = f"model-selection-continue:{mode}:{n}"
        safe_command = (f"sudo noemaforge first-start --full_composite {n} --dry-run --show-candidates --show-compositions --retry-failed-models --per-model-timeout 240 --total-timeout 7200 --keep-display" if mode == "full_composite" else f"sudo noemaforge first-start --{mode} --dry-run --show-candidates --retry-failed-models --per-model-timeout 240 --total-timeout 7200 --keep-display")
        real_command = (f"sudo noemaforge first-start --full_composite {n} --show-candidates --show-compositions --retry-failed-models --per-model-timeout 240 --total-timeout 7200 --keep-display" if mode == "full_composite" else f"sudo noemaforge first-start --{mode} --show-candidates --retry-failed-models --per-model-timeout 240 --total-timeout 7200 --keep-display")
        active = self.create_job("model_selection_continue", status="needs_privilege", progress=progress, command=safe_command, idempotency_key=idkey)
        active["safe_command"] = safe_command
        active["real_command_requires_operator_terminal"] = real_command
        active["display_policy"] = "preserve_display_manager"
        out = self.model_selection_state / "continue-selection-plan.json"
        artifact = {"type": "model_selection_continue", "status": "created", "label": "continue-selection-plan.json", "path": str(out), "open_command": "cat " + str(out)}
        artifacts = active.setdefault("artifacts", [])
        if not any(item.get("type") == artifact["type"] and item.get("path") == artifact["path"] for item in artifacts if isinstance(item, dict)):
            artifacts.append(artifact)
        active = enrich_privileged_job(active, job_file=out)
        active = self._persist_job(active)
        doc = {"ok": True, "version": RUNTIME_VERSION, "created_at": now_iso(), "progress": progress, "job": active, "privileged_runner_command": active.get("privileged_runner_command"), "privileged_runner_policy": "polkit_approval_required", "polkit_action": PRIVILEGED_GUI_POLKIT_ACTION, "note": "Continuation plan created. GUI does not start a real selection process; use safe_command for dry-run or real_command_requires_operator_terminal for an operator-approved run. Display-manager is preserved by default."}
        self._write_json(out, doc)
        reply = f"Continuation plan ready: tested {progress.get('tested_models')} of {progress.get('total_models')} models; failed {progress.get('failed_models')}; remaining {progress.get('remaining_models')}."
        self.save_message("model", reply, persona="Optimizer", intent="model_selection_continue", artifacts=active.get("artifacts", []), raw=doc)
        return {"ok": True, "version": RUNTIME_VERSION, "reply": reply, "progress": progress, "job": active, "suggested_command": active.get("command"), "privileged_runner_command": active.get("privileged_runner_command"), "privileged_runner_policy": "polkit_approval_required", "polkit_action": PRIVILEGED_GUI_POLKIT_ACTION, "artifacts": active.get("artifacts", [])}

    def epoch_apply(self, body: Dict[str, Any]) -> Dict[str, Any]:
        status = self.epoch_status()
        plan = status.get("latest_model_selection", {}).get("plan") or status.get("firstboot", {}).get("candidate_plan") or {}
        mode = str(body.get("mode") or plan.get("mode") or "normal")
        scope = str(body.get("scope") or plan.get("scope") or "active runtime")
        composite_top_n = int(body.get("composite_top_n") or plan.get("composite_top_n") or 0)
        command = f"sudo noemaforge first-start --{mode} --keep-display" if mode != "full_composite" else f"sudo noemaforge first-start --full_composite {composite_top_n} --keep-display"
        job = self.create_job("epoch_apply", status="needs_privilege", progress=status.get("progress", {}), command=command, idempotency_key=f"epoch-apply:{mode}:{composite_top_n}:{scope}")
        out = self.model_selection_state / "epoch-apply-request.json"
        job = enrich_privileged_job(job, job_file=out)
        job = self._persist_job(job)
        apply_doc = {"created_at": now_iso(), "mode": mode, "scope": scope, "composite_top_n": composite_top_n, "request": body.get("request") or "GUI epoch apply request", "suggested_command": command, "privileged_runner_command": job.get("privileged_runner_command"), "privileged_runner_policy": "polkit_approval_required", "polkit_action": PRIVILEGED_GUI_POLKIT_ACTION, "job": job, "status": status}
        self._write_json(out, apply_doc)
        artifacts = [{"type": "epoch_apply_request", "status": "created", "label": "epoch-apply-request.json", "path": str(out), "open_command": "cat " + str(out)}]
        artifacts.extend(job.get("artifacts", []))
        reply = "Epoch transition request is ready. Review artifacts, then run the suggested sudo first-start apply command or approved job-runner action."
        self.save_message("system", reply, persona="Optimizer", intent="epoch_apply", artifacts=artifacts, raw=apply_doc)
        return {"ok": True, "version": RUNTIME_VERSION, "reply": reply, "job": job, "suggested_command": command, "privileged_runner_command": job.get("privileged_runner_command"), "privileged_runner_policy": "polkit_approval_required", "polkit_action": PRIVILEGED_GUI_POLKIT_ACTION, "artifacts": artifacts}

    # --- pipeline catalog ------------------------------------------------------------
    _TEAM_PERSONA_MAP: Dict[str, tuple] = {
        "development_evolution_team": ("dev.work_solution_architect", "Дедал"),
        "public_onboarding_team": ("operator.admin_administrator", "Атлас"),
        "book_team": ("writing.story_writer", "Сирин"),
        "release_team": ("operator.admin_administrator", "Атлас"),
        "knowledge_graph_team": ("knowledge.vault_researcher", "Мнемозина"),
        "media_team": ("operator.admin_administrator", "Атлас"),
        "model_evolution_team": ("operator.admin_administrator", "Атлас"),
    }

    @classmethod
    def _pipeline_persona(cls, team: str, group: str) -> tuple:
        if team in cls._TEAM_PERSONA_MAP:
            return cls._TEAM_PERSONA_MAP[team]
        low = team.lower()
        if any(x in low for x in ["dev", "code", "qa", "test"]): return ("dev.work_dev", "Гефест")
        if any(x in low for x in ["model", "epoch", "evolution"]): return ("operator.admin_administrator", "Атлас")
        if any(x in low for x in ["media", "music", "voice", "video"]): return ("operator.admin_administrator", "Атлас")
        if any(x in low for x in ["vault", "knowledge", "research"]): return ("knowledge.vault_researcher", "Мнемозина")
        if any(x in low for x in ["writing", "book", "story"]): return ("writing.story_writer", "Сирин")
        return ("operator.admin_administrator", "Атлас")

    def pipeline_catalog_api(self) -> Dict[str, Any]:
        pipelines = self._read_json(self.root / "configs" / "pipelines.json", {})
        media = self._read_json(self.root / "configs" / "media-pipeline-catalog.json", {})
        items: List[Dict[str, Any]] = []
        for pid, p in (pipelines or {}).items():
            desc = p.get("description", "") if isinstance(p, dict) else ""
            group = "Core"
            low = (pid + " " + desc).lower()
            if any(x in low for x in ["dev", "code", "qa", "test", "refactor"]): group = "Development"
            if any(x in low for x in ["model", "epoch", "evolution", "tournament"]): group = "Model"
            if any(x in low for x in ["media", "music", "voice", "photo", "video", "camera", "mask", "image"]): group = "Media"
            if any(x in low for x in ["vault", "inventory", "dataset"]): group = "Vault"
            if any(x in low for x in ["scary", "safety", "sr", "ssr", "governance"]): group = "Governance"
            team = p.get("team", "") if isinstance(p, dict) else ""
            persona_key, persona_codename = self._pipeline_persona(team, group)
            items.append({"id": pid, "description": desc, "group": group, "stages": p.get("stages", []) if isinstance(p, dict) else [], "team": team, "persona": persona_key, "persona_codename": persona_codename})
        for p in media.get("pipelines", []) if isinstance(media, dict) else []:
            pid = p.get("id")
            if pid:
                items.append({"id": pid, "description": p.get("notes", ""), "group": "Media", "stages": [p.get("stage", "prepared")], "entrypoint": p.get("entrypoint", ""), "persona": "operator.admin_administrator", "persona_codename": "Атлас"})
        groups = sorted(set(i["group"] for i in items))
        return {"ok": True, "version": RUNTIME_VERSION, "pipelines": items, "groups": groups, "new_pipeline_supported": "draft_only"}

    def pipeline_diagram(self, pipeline_id: str) -> Dict[str, Any]:
        catalog = self.pipeline_catalog_api().get("pipelines", [])
        item = next((p for p in catalog if p.get("id") == pipeline_id), None) or {"id": pipeline_id, "stages": []}
        stages = item.get("stages") or ["intake", "plan", "review"]
        if not isinstance(stages, list):
            stages = ["intake", "plan", "review"]
        nodes = [safe_id(str(s), "stage") for s in stages]
        mermaid = "flowchart LR\n" + "\n".join([f"  {nodes[i]}[{stages[i]}] --> {nodes[i+1]}[{stages[i+1]}]" for i in range(len(nodes)-1)]) if len(nodes) > 1 else f"flowchart LR\n  {nodes[0]}[{stages[0]}]"
        return {"ok": True, "version": RUNTIME_VERSION, "pipeline_id": pipeline_id, "stages": stages, "mermaid": mermaid, "editable": "drag_drop_draft_editor"}

    def pipeline_stats(self, pipeline_id: str) -> Dict[str, Any]:
        runs_dir = self.state / "runs"
        runs = []
        if runs_dir.exists():
            for p in runs_dir.iterdir():
                if p.is_dir() and pipeline_id in p.name:
                    runs.append(str(p))
        return {"ok": True, "version": RUNTIME_VERSION, "pipeline_id": pipeline_id, "stats": {"runs_total": len(runs), "last_runs": runs[-10:], "runs_passed": None, "runs_failed": None, "avg_duration_sec": None, "note": "Full pipeline metrics will be accumulated by the job/pipeline event store."}}

    def pipeline_draft(self, body: Dict[str, Any]) -> Dict[str, Any]:
        normalized = normalize_pipeline_editor_draft(body)
        draft_id = normalized["draft_id"]
        out = self.data_root / "pipelines" / "drafts" / f"{draft_id}.json"
        draft = {"draft_id": draft_id, "created_at": now_iso(), "status": "draft_only", "body": normalized, "safety": "not active until Scary/Architecture/Admin approval"}
        self._write_json(out, draft)
        return {"ok": True, "version": RUNTIME_VERSION, "reply": "New pipeline draft created; it is not active until review/approval.", "draft": draft, "artifacts": [{"type": "pipeline_draft", "status": "created", "label": f"{draft_id}.json", "path": str(out), "open_command": "cat " + str(out)}]}

    # --- GUI intent helpers ---------------------------------------------------------
    def _explicit_control_request(self, low: str) -> bool:
        """Return True when the user is asking the GUI to run or open a NoemaForge action."""
        control_verbs = [
            "запусти", "запуск", "запустить", "открой", "покажи", "проведи", "создай",
            "доработай", "оптимизируй", "переключи", "продолжи", "инвентар",
            "run", "start", "open", "execute", "launch", "continue", "inventory",
        ]
        control_terms = [
            "pipeline", "пайп", "public_mwp", "evolution", "model evolution", "model-selection",
            "model selection", "dev team", "vault", "epoch", "media", "mask", "video", "book",
        ]
        return any(v in low for v in control_verbs) or any(t in low for t in control_terms)

    def _detect_pipeline_id(self, text: str) -> str:
        """Detect an explicit pipeline id/name mentioned by the operator."""
        low = str(text or "").lower().replace("-", "_")
        try:
            catalog = self.pipeline_catalog_api().get("pipelines", [])
        except Exception:
            catalog = []
        candidates = []
        for item in catalog:
            pid = str(item.get("id") or "")
            if not pid:
                continue
            aliases = {pid.lower(), pid.lower().replace("_", " "), pid.lower().replace("_", "-")}
            if any(a and a in low for a in aliases):
                candidates.append(pid)
        if candidates:
            return sorted(candidates, key=len, reverse=True)[0]
        if "public" in low and "mwp" in low:
            return "public_mwp"
        if "evolution" in low or "эволюц" in low:
            return "evolution"
        return ""

    def _pipeline_persona(self, pipeline_id: str) -> str:
        """Map pipeline families to the persona shown in the GUI."""
        low = pipeline_id.lower()
        if "evolution" in low:
            return "Model Evolution"
        if "dev" in low or "code" in low:
            return "Dev Team"
        if "music" in low:
            return "Music Team"
        if "video" in low:
            return "Video Team"
        if "vision" in low or "image" in low or "mask" in low:
            return "Vision Team"
        if "model" in low or "epoch" in low:
            return "Optimizer"
        return "Admin"

    def _run_explicit_pipeline_from_chat(self, text: str, pipeline_id: str, locale: str, allow_degraded: bool) -> Dict[str, Any]:
        """Run an explicitly named pipeline from chat and return a GUI-friendly response."""
        result = self.pipeline_run(pipeline_id, text, allow_degraded=allow_degraded)
        stdout = result.get("stdout") if isinstance(result, dict) else {}
        run_dir = stdout.get("run_dir") if isinstance(stdout, dict) else ""
        run_id = stdout.get("run_id") if isinstance(stdout, dict) else ""
        artifacts = []
        if run_dir:
            artifacts.append({
                "type": "run_dir", "status": stdout.get("status", "created") if isinstance(stdout, dict) else "created",
                "label": "run_dir", "path": str(run_dir), "open_command": "ls -lah " + str(run_dir),
            })
        persona = self._pipeline_persona(pipeline_id)
        if locale == "ru":
            reply = f"Запускаю pipeline {pipeline_id} по стандартному сценарию. Run: {run_id or 'создан/ожидает подтверждения'}."
        else:
            reply = f"Starting pipeline {pipeline_id} with the standard scenario. Run: {run_id or 'created/waiting for approval'}."
        switch = None if persona == "Admin" else {"from": "Admin", "to": persona, "switch_line": f"-- смена персоны с Admin на {persona} --", "switch_line_key": "persona.switch_line"}
        doc = {
            "ok": bool(result.get("ok", False)),
            "version": RUNTIME_VERSION,
            "mode": "pipeline_run",
            "reply": reply,
            "route": {"id": "pipeline", "intent": "pipeline_run", "label": f"Pipeline / {pipeline_id}", "pipeline_id": pipeline_id},
            "persona_switch": switch,
            "artifacts": artifacts,
            "actions": [{"type": "pipeline_run", "pipeline_id": pipeline_id, "result": result}],
            "internal_events": [f"Admin routed explicit chat command to pipeline {pipeline_id}"],
            "raw": result,
        }
        self.save_message("admin", reply, persona=persona, locale=locale, intent="pipeline_run", artifacts=artifacts, raw=doc)
        if switch:
            conv = self._conversation()
            conv["active_persona"] = persona
            self._save_conversation(conv)
        return doc

    # --- action wrappers -------------------------------------------------------------
    def admin_message(self, text: str, *, execute: bool, prepare_media: bool, allow_degraded: bool, apply: bool, locale: str = "", max_steps: int = 0, time_budget_minutes: int = 0, until_stop: bool = False) -> Dict[str, Any]:
        locale = locale or ("ru" if re.search(r"[А-Яа-яЁё]", text) else "en")
        self.save_message("user", text, persona="User", locale=locale, intent="user_message")
        low = text.lower().strip()
        conv = self._conversation()
        budget = {"max_steps": max_steps, "time_budget_minutes": time_budget_minutes, "until_stop": until_stop, "stop_on_no_further_improvement": True}
        if any(k in low for k in ["что значит", "объясни usecase", "объясни сценар", "help", "справк"]):
            reply = self.explain_usecase(text, locale)
            self.save_message("admin", reply, persona="Admin", locale=locale, intent="help")
            return {"ok": True, "version": RUNTIME_VERSION, "reply": reply, "mode": "usecase_help", "artifacts": []}
        if self._task_intent(low):
            result = self._handle_task_intent(text, locale)
            return result
        gui_action = self._detect_gui_action(text)
        if gui_action:
            result = self._route_gui_action(gui_action, text, locale)
            if result is not None:
                return result
        if self._explicit_control_request(low):
            pipeline_id = self._detect_pipeline_id(text)
            if pipeline_id:
                return self._run_explicit_pipeline_from_chat(text, pipeline_id, locale, allow_degraded)
        if self._conversational(low):
            convo = self.conversational_admin_reply(text, locale)
            reply = convo["reply"]
            self.save_message("admin", reply, persona=conv.get("active_persona", "Admin"), locale=locale, intent="conversation")
            return {"ok": True, "version": RUNTIME_VERSION, "reply": reply, "mode": "conversation", "locale": locale, "conversation_backend": convo["backend"], "artifacts": []}
        cmd = [sys.executable, str(self.root / "src" / "admin_runtime.py"), "--root", str(self.root), "--state", str(self.state), "--evolution-state", str(self.evolution_state), "message", "--message", text, "--json"]
        if execute: cmd.append("--execute")
        if prepare_media: cmd.append("--prepare-media")
        if allow_degraded: cmd.append("--allow-degraded")
        if apply: cmd.append("--apply")
        if max_steps: cmd.extend(["--max-steps", str(max_steps)])
        if time_budget_minutes: cmd.extend(["--time-budget-minutes", str(time_budget_minutes)])
        if until_stop: cmd.append("--until-stop")
        if locale: cmd.extend(["--locale", locale])
        result = run_json(cmd, env=self.env(locale), timeout=180)
        if result.get("ok") and isinstance(result.get("stdout"), dict):
            doc = result["stdout"]
            doc.setdefault("ok", True)
            doc["api"] = {"inside_gui_supported": True, "endpoint": "/api/admin/message", "cmd": cmd}
            if budget and any(budget.values()):
                doc["improvement_budget"] = budget
            reply = str(doc.get("reply") or "Action completed.")
            persona = (doc.get("persona_switch") or {}).get("to") or conv.get("active_persona", "Admin")
            self.save_message("admin", reply, persona=persona, locale=locale, intent=str((doc.get("route") or {}).get("intent") or "admin_message"), artifacts=doc.get("artifacts") if isinstance(doc.get("artifacts"), list) else [], raw=doc)
            return doc
        self.save_message("admin", "Admin action failed.", persona="Admin", locale=locale, intent="admin_message_failed", raw=result)
        return result

    def _task_intent(self, low: str) -> bool:
        return any(k in low for k in [
            "добавь задачу", "создай задачу", "измени задачу", "обнови задачу", "переименуй задачу",
            "приоритет", "пометь задачу", "заблок", "заверши задачу", "закрой задачу", "выполни задачу",
            "задач", "add task", "create task", "update task", "edit task", "prioritize task", "block task",
            "complete task", "close task",
        ])

    def _handle_task_intent(self, text: str, locale: str) -> Dict[str, Any]:
        low = text.lower()
        priority = self._priority_from_text(low)
        category = "dev_team" if "dev" in low or "код" in low else "general"
        if any(k in low for k in ["добав", "создай", "new"]):
            title = re.sub(r"^(добавь|создай) задачу[:：]?", "", text, flags=re.I).strip() or text
            return self.task_create({"title": title, "category": category, "priority": priority, "assignee": "Dev Team" if category == "dev_team" else "Admin"})
        task_id = self._extract_task_id(text)
        if not task_id:
            return {"ok": True, "version": RUNTIME_VERSION, "reply": "Я могу добавлять, редактировать, приоритезировать, блокировать и завершать задачи. Уточни task_id или сформулируй: 'заблокируй задачу task_... причина ...'.", "tasks": self.tasks_list()}
        if any(k in low for k in ["заблок", "block"]):
            return self.task_block({"task_id": task_id, "reason": text})
        if any(k in low for k in ["заверши", "закрой", "выполни", "complete", "close", "done"]):
            return self.task_complete({"task_id": task_id})
        if any(k in low for k in ["приоритет", "priorit"]):
            return self.task_prioritize({"task_id": task_id, "priority": priority})
        if any(k in low for k in ["измени", "обнови", "переименуй", "edit", "update", "rename"]):
            title = ""
            if ":" in text:
                title = text.split(":", 1)[1].strip()
            body = {"task_id": task_id}
            if title:
                body["title"] = title
            else:
                body["notes"] = text
            return self.task_update(body)
        return {"ok": True, "version": RUNTIME_VERSION, "reply": "Task command recognized; specify add/edit/prioritize/block/complete plus task_id.", "tasks": self.tasks_list()}

    def _detect_gui_action(self, text: str) -> Optional[str]:
        """Detect direct GUI actions that should not fall through to admin_runtime."""
        low = str(text or "").lower().strip()
        if not low or self._task_intent(low):
            return None
        model_words = ("model selection", "выбор модели", "подбор модели", "подбор моделей", "отбор модели", "отбор моделей")
        continue_words = ("continue", "resume", "продолж", "возобнов")
        if any(word in low for word in model_words) and any(word in low for word in continue_words):
            return "model_selection_continue"
        if ("selection" in low and "model" in low and any(word in low for word in continue_words)):
            return "model_selection_continue"
        vault_words = ("vault", "хранилищ", "модел", "models")
        inventory_words = ("reinventory", "re-inventory", "inventory", "scan", "инвентаризац", "скан")
        if any(word in low for word in vault_words) and any(word in low for word in inventory_words):
            return "vault_reinventory"
        return None

    def _route_gui_action(self, action: str, text: str, locale: str) -> Optional[Dict[str, Any]]:
        """Route detected GUI action keys to local plan/job methods."""
        if action == "model_selection_continue":
            result = self.model_selection_continue({"request": text})
        elif action == "vault_reinventory":
            result = self.vault_reinventory()
        else:
            return None
        if not isinstance(result, dict):
            return None
        doc = dict(result)
        doc.setdefault("ok", True)
        doc.setdefault("version", RUNTIME_VERSION)
        doc["mode"] = action
        doc["locale"] = locale
        doc.setdefault("route", {"id": action, "intent": action, "label": action.replace("_", " ")})
        return doc

    def _extract_task_id(self, text: str) -> str:
        match = re.search(r"\btask_[A-Za-z0-9_.:-]+\b", str(text or ""))
        return match.group(0) if match else ""

    def _priority_from_text(self, low: str) -> int:
        match = re.search(r"(?:priority|приоритет)\D{0,12}([0-9]{1,3})", low)
        if match:
            return max(1, min(100, int(match.group(1))))
        numbers = re.findall(r"\b([0-9]{1,3})\b", low)
        if numbers:
            return max(1, min(100, int(numbers[-1])))
        if any(k in low for k in ["высок", "важн"]) or re.search(r"\b(high|urgent)\b", low):
            return 80
        if "низк" in low or re.search(r"\blow\b", low):
            return 20
        if "средн" in low or re.search(r"\bmedium\b", low):
            return 50
        return 50

    def _conversational(self, low: str) -> bool:
        """Return True for ordinary chat; explicit NoemaForge actions must route elsewhere."""
        if self._explicit_control_request(low):
            return False
        if not low:
            return False
        # Short casual messages and ordinary questions are chat. Unknown long text is
        # treated as chat too, but commands are excluded above.
        return True

    def conversational_admin_reply(self, text: str, locale: str) -> Dict[str, str]:
        """Return an LLM-backed smalltalk reply when available, otherwise deterministic fallback."""
        llm_reply = self.try_llm_admin_reply(text, locale)
        if llm_reply:
            return {"reply": llm_reply, "backend": "llm_chat"}
        return {"reply": self.fallback_conversation_reply(text, locale), "backend": "deterministic_fallback"}

    def try_llm_admin_reply(self, text: str, locale: str) -> str:
        if os.environ.get("NOEMAFORGE_GUI_DISABLE_LLM_CHAT") == "1":
            return ""
        sockets = [self.llm_gateway_socket, self.llm_main_backend_socket]
        if self.legacy_llm_gateway_socket is not None:
            sockets.append(self.legacy_llm_gateway_socket)
        if not any(sock.exists() for sock in sockets):
            return ""
        prompt = text if locale != "ru" else "Ответь по-русски как локальный Admin NoemaForge, коротко и полезно. Запрос: " + text
        cmd = [str(self.root / "bin" / "noemaforge"), "chat", "--role", "admin", "--once", prompt]
        r = run_json(cmd, env=self.env(locale), timeout=20)
        out = r.get("stdout")
        if isinstance(out, str) and out.strip() and "error" not in out.lower():
            return out.strip()[:4000]
        return ""

    def fallback_conversation_reply(self, text: str, locale: str) -> str:
        """Deterministic conversational fallback used when the local LLM chat path is unavailable."""
        runtime = self.runtime_status()
        model = (runtime.get("main_manifest") or {}).get("model_id") or (runtime.get("main_manifest") or {}).get("name") or "main"
        low = str(text or "").lower().strip()
        if locale == "ru":
            if any(x in low for x in ["привет", "здрав", "hello", "hi"]):
                return f"Привет. Я локальный Admin NoemaForge. Сейчас работаю в безопасном GUI/control-plane режиме; текущая main-модель: {model}."
            if any(x in low for x in ["познаком", "рад", "приятно"]):
                return "Взаимно. Я буду вести историю этого диалога, помогать с пайплайнами, задачами, метриками, Dev Team, подбором моделей и эволюцией — без скрытого применения изменений."
            if any(x in low for x in ["как", "жив", "оно", "дела"]):
                return f"Работаю штатно в локальном режиме. Могу отвечать в чате, но если LLM-gateway не активен, часть ответов будет deterministic fallback. Текущая main-модель: {model}."
            if len(low) <= 8 and not re.search(r"[а-яa-z0-9]", low):
                return "Я не понял сообщение. Сформулируй задачу словами или выбери пайплайн внизу."
            return "Принял. Это похоже на обычное сообщение, а не команду NoemaForge. Могу продолжить диалог или выполнить явную команду: запусти pipeline, оптимизируй модель, открой Dev Team, проведи эволюцию."
        if any(x in low for x in ["hello", "hi"]):
            return f"Hello. I am the local NoemaForge Admin. I am running in safe GUI/control-plane mode; current main model: {model}."
        return f"I am here. This looks like a conversational message rather than a NoemaForge command. Current main model: {model}."

    def explain_usecase(self, text: str, locale: str) -> str:
        low = text.lower()
        if "dev" in low and ("модель" in low or "model" in low or "оптим" in low):
            return "Оптимизируй модель для Dev Team — это отбор runtime-модели для ролей разработки. NoemaForge тестирует модели из Vault, сравнивает pass_rate/json_parse_rate/quality/latency, создаёт candidate-selection-plan, model-selection-decision и rollback-plan. Эпоха не меняется без отдельного approve/apply."
        if "эвол" in low or "evolution" in low:
            return "Эволюция модели — measured improvement cycle: baseline_snapshot, mutation_plan, candidate_profile, scorecard и rollback_plan. Это не скрытое production-обучение; результат должен пройти review."
        if "шаг" in low or "минут" in low or "depth" in low:
            return "Глубина улучшения задаёт бюджет: N шагов, M минут или until-stop. Цикл может завершиться честным no_further_improvement_found, если безопасного улучшения больше нет."
        if "подбор" in low or "continue" in low:
            return "Продолжить подбор моделей — создать continuation job/plan: сколько моделей протестировано, сколько failed, сколько осталось и какую команду надо выполнить для продолжения. Защита от дублей включается через job/idempotency key."
        return "Это справка по usecase NoemaForge. Спроси, например: 'что значит оптимизируй модель для dev team', 'что значит эволюция модели', 'что значит 10 шагов улучшения'."

    def pipeline_run(self, pipeline: str, request: str, *, allow_degraded: bool) -> Dict[str, Any]:
        trace_id = production_ai_contracts.new_trace_id("pipeline")
        cmd = [sys.executable, str(self.root / "src" / "pipeline_runtime.py"), "--root", str(self.root), "--state", str(self.state), "run", pipeline, "--request", request, "--trace-id", trace_id]
        if allow_degraded:
            cmd.append("--allow-degraded")
        env = self.env()
        env["NOEMAFORGE_TRACE_ID"] = trace_id
        result = run_json(cmd, env=env, timeout=180)
        result["trace_id"] = trace_id
        self.save_message("system", f"Pipeline requested: {pipeline}", persona="Pipeline", intent="pipeline_run", raw=result, trace_id=trace_id)
        return result

    def pipeline_action(self, action: str, run_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if not run_id:
            return {"ok": False, "error": "run_id required"}
        cmd = [sys.executable, str(self.root / "src" / "pipeline_runtime.py"), "--root", str(self.root), "--state", str(self.state), action, run_id]
        if action == "advance" and body.get("next", True): cmd.append("--next")
        if body.get("status"): cmd.extend(["--status", str(body["status"])])
        if body.get("note"): cmd.extend(["--note", str(body["note"])])
        if body.get("allow_degraded"): cmd.append("--allow-degraded")
        return run_json(cmd, env=self.env(), timeout=120)

    def modify_pipeline(self, pipeline: str, *, add_stage: str, after: str, before: str, description: str, team: str, apply: bool, create: bool) -> Dict[str, Any]:
        cmd = [sys.executable, str(self.root / "src" / "admin_runtime.py"), "--root", str(self.root), "modify-pipeline", pipeline, "--json"]
        if create: cmd.append("--create")
        if add_stage: cmd.extend(["--add-stage", add_stage])
        if after: cmd.extend(["--after", after])
        if before: cmd.extend(["--before", before])
        if description: cmd.extend(["--description", description])
        if team: cmd.extend(["--team", team])
        if apply: cmd.append("--apply")
        return run_json(cmd, env=self.env(), timeout=120)

    def vault_reinventory(self) -> Dict[str, Any]:
        progress = self.model_selection_progress()
        command = "sudo noemaforge inventory scan && sudo noemaforge datasets scan && sudo noemaforge tournament eligibility"
        privileged_steps = [
            "sudo noemaforge inventory scan",
            "sudo noemaforge datasets scan",
            "sudo noemaforge tournament eligibility",
        ]
        fallback_artifact = {
            "type": "privileged_fallback_command",
            "status": "operator_action_required",
            "label": "Vault re-inventory fallback command",
            "command": command,
            "execution_policy": "operator_terminal_or_approved_root_job_runner",
        }
        job = self.create_job("vault_reinventory", status="needs_privilege", progress=progress, command=command, artifacts=[fallback_artifact], idempotency_key="vault-reinventory")
        out = self.data_root / "vault" / "vault-reinventory-request.json"
        job["privileged_steps"] = privileged_steps
        job = enrich_privileged_job(job, job_file=out)
        job = self._persist_job(job)
        doc = {
            "ok": True,
            "version": RUNTIME_VERSION,
            "created_at": now_iso(),
            "progress": progress,
            "job": job,
            "suggested_command": command,
            "fallback_command": command,
            "privileged_runner_command": job.get("privileged_runner_command"),
            "privileged_runner_policy": "polkit_approval_required",
            "polkit_action": PRIVILEGED_GUI_POLKIT_ACTION,
            "execution_policy": "gui_plan_only_operator_terminal_or_approved_root_job_runner",
        }
        self._write_json(out, doc)
        reply = "Vault re-inventory requires privileged execution. I created a job/plan with the exact fallback command; run it in terminal or through an approved root job-runner."
        self.save_message("system", reply, persona="Vault", intent="vault_reinventory", artifacts=job.get("artifacts", []), raw=doc)
        return {
            "ok": True,
            "version": RUNTIME_VERSION,
            "reply": reply,
            "job": job,
            "suggested_command": command,
            "fallback_command": command,
            "privileged_runner_command": job.get("privileged_runner_command"),
            "privileged_runner_policy": "polkit_approval_required",
            "polkit_action": PRIVILEGED_GUI_POLKIT_ACTION,
            "artifacts": job.get("artifacts", []),
            "privilege_required": True,
            "execution_policy": "gui_plan_only_operator_terminal_or_approved_root_job_runner",
        }

    def model_evolution(self, request: str, *, target_role: str, apply: bool) -> Dict[str, Any]:
        cmd = [sys.executable, str(self.root / "src" / "model_evolution_runtime.py"), "--root", str(self.root), "--state", str(self.evolution_state), "--pipeline-state", str(self.state), "run", "--request", request, "--target-role", target_role, "--json"]
        if apply: cmd.append("--apply")
        result = run_json(cmd, env=self.env(), timeout=180)
        stdout = result.get("stdout")
        if result.get("ok") and isinstance(stdout, dict):
            artifacts = []
            for key, path in (stdout.get("artifacts") or {}).items():
                artifacts.append({"type": "model_evolution_artifact", "status": "created", "label": str(key).replace("_", "-"), "path": str(path), "open_command": "cat " + str(path)})
            reply = "Measured model-evolution cycle is ready. Baseline, mutation plan, candidate profile, scorecard and rollback artifacts are attached."
            self.save_message("model", reply, persona="Model Evolution", intent="model_evolution", artifacts=artifacts, raw=stdout)
            return {"ok": True, "version": RUNTIME_VERSION, "reply": reply, "artifacts": artifacts, "raw": stdout, "api": {"inside_gui_supported": True, "endpoint": "/api/model-evolution/run", "cmd": cmd}}
        return result

    # --- Code-evolution (autonomous self-improvement loop) ------------------

    def code_evolution_propose(self) -> Dict[str, Any]:
        """POST /api/code-evolution/propose — pick next TODO task and propose a patch.

        Never writes source files (dry_run=True always for propose endpoint).
        Returns the proposal dict so the GUI can display it for operator review.
        """
        try:
            from code_evolution_loop import CodeEvolutionLoop
            loop = CodeEvolutionLoop(project_root=self.root, dry_run=True)
            result = loop.run_one_cycle(apply=False)
            if result.get("task"):
                self.save_message(
                    "model",
                    f"Code-evolution proposal ready for task {result['task']['task_id']}: "
                    f"{result['task']['summary']}",
                    persona="Code Evolution",
                    intent="code_evolution",
                    raw=result,
                )
            return {"ok": True, "version": RUNTIME_VERSION, **result}
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "version": RUNTIME_VERSION, "error": repr(exc)}

    def code_evolution_status(self) -> Dict[str, Any]:
        """GET /api/code-evolution/status — return the last loop run summary."""
        try:
            from code_evolution_loop import CodeEvolutionLoop
            loop = CodeEvolutionLoop(project_root=self.root, dry_run=True)
            return {"ok": True, "version": RUNTIME_VERSION, **loop.last_run_summary()}
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "version": RUNTIME_VERSION, "error": repr(exc)}

    def workflow_stop(self, reason: str) -> Dict[str, Any]:
        marker = self.data_root / "control" / "stop-request.json"
        self._write_json(marker, {"ok": True, "created_at": now_iso(), "reason": reason})
        return {"ok": True, "version": RUNTIME_VERSION, "reply": "Stop marker written. Long-running loops should stop at next safe checkpoint.", "artifacts": [{"type": "control", "status": "created", "label": "stop-request.json", "path": str(marker), "open_command": "cat " + str(marker)}]}

    def usecases(self) -> Dict[str, Any]:
        cases = [
            {"id": "model_selection_dev_team", "title": "Оптимизируй модель для Dev Team", "summary": "Отбор лучшей runtime-модели для Dev Team с кандидатами, scorecard и rollback-plan; эпоха не меняется без approve/apply.", "example": "оптимизируй модель для dev team normal"},
            {"id": "model_evolution", "title": "Эволюция модели", "summary": "Measured improvement cycle: baseline, mutation_plan, candidate_profile, scorecard, rollback_plan; без скрытого production-обучения.", "example": "проведи эволюцию модели для ревью кода"},
            {"id": "dev_team", "title": "Доработай код через Dev Team", "summary": "Admin уточняет задачу и путь проекта/файла, затем Dev Team создаёт patch/diff и контекстные артефакты.", "example": "доработай код через dev team"},
            {"id": "depth", "title": "Глубина улучшения", "summary": "Ограничение по шагам, времени или until-stop: 10 шагов, 30 минут, выполнять пока не остановлю.", "example": "у тебя есть 30 минут, проведи столько циклов улучшения сколько успеешь"},
            {"id": "continue_selection", "title": "Продолжить подбор моделей", "summary": "Показывает сколько моделей протестировано/сломалось/осталось и создаёт continuation plan.", "example": "продолжи подбор моделей"},
            {"id": "smarthome_local", "title": "Умный дом локально", "summary": "Local-first управление розетками, выключателями, пылесосами, камерами и сенсорами: value your privacy, без скрытой отправки наружу.", "example": "что значит умный дом локально"},
        ]
        return {"ok": True, "version": RUNTIME_VERSION, "usecases": cases}

    def public_showcase_scenario(self) -> Dict[str, Any]:
        conv = self._conversation()
        return build_public_showcase_scenario(str(conv.get("locale") or ""))

    def locales(self) -> Dict[str, Any]:
        base = self.root / "configs" / "locales"
        locales: List[str] = []
        messages: Dict[str, Dict[str, str]] = {}
        for p in sorted(base.glob("*.json")) if base.exists() else []:
            if p.name == "aliases.json": continue
            locales.append(p.stem)
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(obj, dict): messages[p.stem] = {str(k): str(v) for k, v in obj.items()}
            except Exception:
                messages[p.stem] = {}
        aliases = self._read_json(base / "aliases.json", {"pt-PT": "pt", "pt-BR": "pt", "zh": "zh-CN"})
        return {"ok": True, "version": RUNTIME_VERSION, "locales": locales, "aliases": aliases, "messages": messages}

    def dev_team_run(self, request: str, *, allow_degraded: bool) -> Dict[str, Any]:
        cmd = [sys.executable, str(self.root / "src" / "dev_team_runtime.py"), "--root", str(self.root), "--state", str(self.dev_team_state), "--pipeline-state", str(self.state), "run", "--request", request, "--json"]
        if allow_degraded: cmd.append("--allow-degraded")
        return run_json(cmd, env=self.env(), timeout=180)

    def _require_project_args(self, project: str, rel_path: str = "") -> Optional[Dict[str, Any]]:
        if not project: return {"ok": False, "error": "project is required"}
        if rel_path is not None and not rel_path: return {"ok": False, "error": "path is required"}
        return None

    def dev_team_write_file(self, *, project: str, rel_path: str, content: str, apply: bool) -> Dict[str, Any]:
        missing = self._require_project_args(project, rel_path)
        if missing: return missing
        cmd = [sys.executable, str(self.root / "src" / "dev_team_runtime.py"), "--root", str(self.root), "--state", str(self.dev_team_state), "write-file", "--project", project, "--path", rel_path, "--content", content, "--json"]
        if apply: cmd.append("--apply")
        return run_json(cmd, env=self.env(), timeout=180)

    def dev_team_replace(self, *, project: str, rel_path: str, old: str, new: str, once: bool, apply: bool) -> Dict[str, Any]:
        missing = self._require_project_args(project, rel_path)
        if missing: return missing
        if not old: return {"ok": False, "error": "old text is required"}
        cmd = [sys.executable, str(self.root / "src" / "dev_team_runtime.py"), "--root", str(self.root), "--state", str(self.dev_team_state), "replace", "--project", project, "--path", rel_path, "--old", old, "--new", new, "--json"]
        if once: cmd.append("--once")
        if apply: cmd.append("--apply")
        return run_json(cmd, env=self.env(), timeout=180)

    def dev_team_set_version(self, *, project: str, version: str, apply: bool) -> Dict[str, Any]:
        if not project: return {"ok": False, "error": "project is required"}
        if not version: return {"ok": False, "error": "version is required"}
        cmd = [sys.executable, str(self.root / "src" / "dev_team_runtime.py"), "--root", str(self.root), "--state", str(self.dev_team_state), "set-version", "--project", project, "--version", version, "--json"]
        if apply: cmd.append("--apply")
        return run_json(cmd, env=self.env(), timeout=180)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noemaforge admin-gui-server")
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--persona-state", default=str(DEFAULT_PERSONA_STATE))
    parser.add_argument("--evolution-state", default=str(DEFAULT_EVOLUTION_STATE))
    parser.add_argument("--model-selection-state", default=str(DEFAULT_MODEL_SELECTION_STATE))
    parser.add_argument("--dev-state", default=str(DEFAULT_DEV_TEAM_STATE))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    server = AdminGuiServer((args.host, args.port), Path(args.root), Path(args.state), Path(args.persona_state), Path(args.evolution_state), Path(args.model_selection_state), Path(args.dev_state))
    print(f"NoemaForge Admin GUI: http://{args.host}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


