#!/usr/bin/env python3
"""NoemaForge local Admin GUI server.

=== NoemaForge File Header ===
File: src/admin_gui_server.py
Zone: gui/control-plane
Version: 0.31.13.alpha
Created: 2026-05-11
Modified: 2026-05-14
Purpose: Serve the localhost Admin GUI and JSON APIs for conversation memory,
  persona portraits, epoch/model-selection status, telemetry, task governance,
  job registry, pipeline catalog/diagrams/stats, and safe control-plane actions.
Inputs:
  - HTTP GET/POST localhost requests from the packaged GUI.
  - NoemaForge catalogs/configs under ROOT/configs.
  - Runtime/bootstrap state under /var/lib/noemaforge.
  - Optional system telemetry commands such as sensors, nvidia-smi, upower.
Outputs:
  - JSON API responses.
  - Persistent conversation, task, job, SR/SSR review, and GUI state records.
  - Plan-first artifacts for privileged actions.
Safety notes:
  - No LLM, media backend, camera, microphone, model-selection or epoch switch is
    started implicitly by loading the GUI.
  - Privileged actions are represented as whitelisted job/plan records unless a
    separate operator-approved sudo command is executed outside the browser.
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
from urllib.parse import unquote, urlparse

RUNTIME_VERSION = "0.31.13.alpha"
DEFAULT_ROOT = Path(os.environ.get("NOEMAFORGE_ROOT", "/opt/noemaforge"))
DEFAULT_STATE = Path(os.environ.get("NOEMAFORGE_PIPELINE_STATE", "/var/lib/noemaforge/pipelines"))
DEFAULT_PERSONA_STATE = Path(os.environ.get("NOEMAFORGE_PERSONA_STATE", "/var/lib/noemaforge/personas"))
DEFAULT_EVOLUTION_STATE = Path(os.environ.get("NOEMAFORGE_MODEL_EVOLUTION_STATE", "/var/lib/noemaforge/model-evolution"))
DEFAULT_MODEL_SELECTION_STATE = Path(os.environ.get("NOEMAFORGE_MODEL_SELECTION_STATE", os.environ.get("NOEMAFORGE_MODEL_EVOLUTION_STATE", "/var/lib/noemaforge/model-selection")))
DEFAULT_DEV_TEAM_STATE = Path(os.environ.get("NOEMAFORGE_DEV_TEAM_STATE", "/var/lib/noemaforge/dev-team"))
DEFAULT_DATA_ROOT = Path(os.environ.get("NOEMAFORGE_DATA_ROOT", "/var/lib/noemaforge"))
MAX_BODY = 512 * 1024


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def safe_id(text: str, default: str = "item") -> str:
    raw = re.sub(r"[^A-Za-z0-9_.-]+", "-", text.strip()).strip("-._")
    return raw[:96] or default


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
        if path == "/api/health":
            self._send_json(self.server.health())
            return
        if path in {"/api/state", "/api/gui/state"}:
            self._send_json(self.server.gui_state())
            return
        if path == "/api/locales":
            self._send_json(self.server.locales())
            return
        if path == "/api/epoch/status":
            self._send_json(self.server.epoch_status())
            return
        if path == "/api/runtime/status":
            self._send_json(self.server.runtime_status())
            return
        if path == "/api/runtime/device-policy":
            self._send_json(self.server.device_policy())
            return
        if path == "/api/telemetry/status":
            self._send_json(self.server.telemetry_status())
            return
        if path == "/api/usecases":
            self._send_json(self.server.usecases())
            return
        if path == "/api/conversation/current":
            self._send_json(self.server.conversation_current())
            return
        if path == "/api/conversation/history":
            self._send_json(self.server.conversation_history())
            return
        if path == "/api/tasks":
            self._send_json(self.server.tasks_list())
            return
        if path == "/api/inactivity/status":
            self._send_json(self.server.inactivity_status())
            return
        if path == "/api/jobs":
            self._send_json(self.server.jobs_list())
            return
        if path == "/api/persona/current":
            self._send_json(self.server.persona_current())
            return
        if path == "/api/persona/catalog":
            self._send_json(self.server.persona_catalog_api())
            return
        if path.startswith("/api/persona/fallback-avatar/"):
            name = safe_id(path.rsplit("/", 1)[-1].replace(".svg", "")) + ".svg"
            candidate = (self.server.data_root / "personas" / "avatars" / "fallback" / name).resolve()
            if candidate.exists():
                self._send_bytes(candidate.read_bytes(), "image/svg+xml")
            else:
                self._send_json({"ok": False, "error": "fallback avatar not found"}, status=404)
            return
        if path == "/api/pipelines/catalog":
            self._send_json(self.server.pipeline_catalog_api())
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

    def do_POST(self) -> None:  # noqa: N802 - stdlib API
        path = urlparse(self.path).path
        try:
            body = self._read_json_body()
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
            return
        try:
            if path in {"/api/admin/message", "/api/admin/ask", "/api/admin/start", "/api/conversation/message"}:
                text = str(body.get("message") or body.get("text") or body.get("prompt") or "")
                self._send_json(self.server.admin_message(
                    text,
                    execute=bool(body.get("execute")) or path == "/api/admin/start",
                    prepare_media=bool(body.get("prepare_media", True)),
                    allow_degraded=bool(body.get("allow_degraded", False)),
                    apply=bool(body.get("apply", False)),
                    locale=str(body.get("locale") or body.get("lang") or ""),
                    max_steps=int(body.get("max_steps") or 0),
                    time_budget_minutes=int(body.get("time_budget_minutes") or 0),
                    until_stop=bool(body.get("until_stop", False)),
                ))
                return
            if path == "/api/conversation/reset":
                self._send_json(self.server.conversation_reset())
                return
            if path == "/api/tasks/create":
                self._send_json(self.server.task_create(body))
                return
            if path in {"/api/tasks/update", "/api/tasks/edit"}:
                self._send_json(self.server.task_update(body))
                return
            if path == "/api/admin/modify-pipeline":
                self._send_json(self.server.modify_pipeline(
                    str(body.get("pipeline") or body.get("pipeline_id") or "public_mwp"),
                    add_stage=str(body.get("add_stage") or ""),
                    after=str(body.get("after") or ""),
                    before=str(body.get("before") or ""),
                    description=str(body.get("description") or ""),
                    team=str(body.get("team") or ""),
                    apply=bool(body.get("apply", False)),
                    create=bool(body.get("create", False)),
                ))
                return
            if path in {"/api/pipeline/run", "/api/pipelines/start"}:
                self._send_json(self.server.pipeline_run(str(body.get("pipeline") or body.get("pipeline_id") or "public_mwp"), str(body.get("request") or "GUI pipeline request"), allow_degraded=bool(body.get("allow_degraded", False))))
                return
            if path == "/api/pipeline/approve":
                self._send_json(self.server.pipeline_action("approve", str(body.get("run_id") or ""), body))
                return
            if path == "/api/pipeline/advance":
                self._send_json(self.server.pipeline_action("advance", str(body.get("run_id") or ""), body))
                return
            if path == "/api/model-evolution/run":
                self._send_json(self.server.model_evolution(str(body.get("request") or "GUI model evolution"), target_role=str(body.get("target_role") or "dev.work/dev"), apply=bool(body.get("apply", False))))
                return
            if path in {"/api/model-selection/plan", "/api/model-selection/apply"}:
                self._send_json(self.server.model_selection(
                    str(body.get("request") or body.get("message") or "GUI model selection"),
                    mode=str(body.get("mode") or "normal"),
                    scope=str(body.get("scope") or "active runtime"),
                    composite_top_n=int(body.get("composite_top_n") or body.get("n") or 0),
                    apply=bool(body.get("apply", False)) or path.endswith("/apply"),
                ))
                return
            if path == "/api/model-selection/continue":
                self._send_json(self.server.model_selection_continue(body))
                return
            if path == "/api/epoch/apply":
                self._send_json(self.server.epoch_apply(body))
                return
            if path == "/api/vault/reinventory":
                self._send_json(self.server.vault_reinventory())
                return
            if path == "/api/workflow/stop":
                self._send_json(self.server.workflow_stop(str(body.get("reason") or "operator_requested_stop")))
                return
            if path == "/api/runtime/device-policy":
                self._send_json(self.server.device_policy_set(str(body.get("policy") or body.get("mode") or "auto")))
                return
            if path == "/api/pipelines/draft":
                self._send_json(self.server.pipeline_draft(body))
                return
            if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                job_id = unquote(path.split("/")[-2])
                self._send_json(self.server.job_cancel(job_id))
                return
            if path == "/api/dev-team/run":
                self._send_json(self.server.dev_team_run(str(body.get("request") or "GUI dev-team task"), allow_degraded=bool(body.get("allow_degraded", False))))
                return
            if path == "/api/dev-team/write-file":
                self._send_json(self.server.dev_team_write_file(project=str(body.get("project") or ""), rel_path=str(body.get("path") or ""), content=str(body.get("content") or ""), apply=bool(body.get("apply", False))))
                return
            if path == "/api/dev-team/replace":
                self._send_json(self.server.dev_team_replace(project=str(body.get("project") or ""), rel_path=str(body.get("path") or ""), old=str(body.get("old") or ""), new=str(body.get("new") or ""), once=bool(body.get("once", True)), apply=bool(body.get("apply", False))))
                return
            if path == "/api/dev-team/set-version":
                self._send_json(self.server.dev_team_set_version(project=str(body.get("project") or ""), version=str(body.get("version") or ""), apply=bool(body.get("apply", False))))
                return
            if path == "/api/shutdown":
                self.server.record_system_event("shutdown", {"reason": body.get("reason") or "operator"})
                self._send_json({"ok": True, "message": "NoemaForge Admin GUI shutdown requested"})
                threading.Timer(0.25, self.server.shutdown).start()
                return
            self._send_json({"ok": False, "error": f"unknown API endpoint: {path}"}, status=404)
        except Exception as exc:  # pragma: no cover - server safety net
            self._send_json({"ok": False, "error": repr(exc)}, status=500)

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
        self.jobs_dir = self.data_root / "jobs"
        self.tasks_dir = self.data_root / "tasks"
        self.review_dir = self.data_root / "review"
        self.runtime_dir = self.data_root / "runtime"
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
        if locale:
            env["NOEMAFORGE_LANG"] = locale
        return env

    def _read_json(self, path: Path, default: Any) -> Any:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
        return default

    def _write_json(self, path: Path, obj: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json_dumps(obj), encoding="utf-8")

    def _append_jsonl(self, path: Path, obj: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")

    def health(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "version": RUNTIME_VERSION,
            "mode": "admin_gui",
            "inside_gui_supported": True,
            "root": str(self.root),
            "state": str(self.state),
            "api": [
                "/api/admin/message", "/api/conversation/current", "/api/conversation/history",
                "/api/tasks", "/api/inactivity/status", "/api/jobs", "/api/pipelines/catalog",
                "/api/persona/current", "/api/telemetry/status", "/api/runtime/status",
                "/api/runtime/device-policy", "/api/model-evolution/run", "/api/model-selection/plan",
                "/api/model-selection/continue", "/api/epoch/status", "/api/epoch/apply",
                "/api/vault/reinventory", "/api/usecases", "/api/locales", "/api/shutdown",
            ],
        }

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

    def save_message(self, role: str, text: str, *, persona: str = "Admin", locale: str = "", intent: str = "", artifacts: Optional[List[Dict[str, Any]]] = None, raw: Optional[Dict[str, Any]] = None, system_event: bool = False) -> Dict[str, Any]:
        conv = self._conversation()
        idx = len(conv.get("messages", [])) + 1
        msg = {
            "message_id": f"msg_{int(time.time())}_{idx}",
            "conversation_id": conv["conversation_id"],
            "ts": now_iso(),
            "role": role,
            "persona": persona,
            "locale": locale or conv.get("locale", "ru"),
            "intent": intent,
            "text": text,
            "artifacts": artifacts or [],
            "system_event": bool(system_event),
        }
        conv.setdefault("messages", []).append(msg)
        if artifacts:
            conv.setdefault("artifacts", []).extend(artifacts)
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
        return msg

    def record_system_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        self.save_message("system", f"System event: {event_type}", persona="System", intent=event_type, artifacts=payload.get("artifacts") or [], raw=payload, system_event=True)

    def conversation_current(self) -> Dict[str, Any]:
        conv = self._conversation()
        return {"ok": True, "version": RUNTIME_VERSION, "conversation": conv}

    def conversation_history(self) -> Dict[str, Any]:
        conv = self._conversation()
        return {"ok": True, "version": RUNTIME_VERSION, "conversation_id": conv.get("conversation_id"), "messages": conv.get("messages", []), "artifacts": conv.get("artifacts", []), "pending_intent": conv.get("pending_intent"), "pending_payload": conv.get("pending_payload", {})}

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
        data = self.tasks_data()
        tasks = data.get("tasks", [])
        categories = {}
        for t in tasks:
            categories[t.get("category", "uncategorized")] = categories.get(t.get("category", "uncategorized"), 0) + 1
        return {"ok": True, "version": RUNTIME_VERSION, "tasks": tasks, "summary": {"total": len(tasks), "by_category": categories, "pending": sum(1 for t in tasks if t.get("status") == "pending"), "blocked": sum(1 for t in tasks if t.get("status") == "blocked")}}

    def task_create(self, body: Dict[str, Any]) -> Dict[str, Any]:
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
        data = self.tasks_data()
        task_id = str(body.get("task_id") or body.get("id") or "")
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

    def jobs_file(self) -> Path:
        return self.jobs_dir / "jobs.json"

    def jobs_data(self) -> Dict[str, Any]:
        data = self._read_json(self.jobs_file(), {"jobs": []})
        if not isinstance(data, dict):
            data = {"jobs": []}
        data.setdefault("jobs", [])
        return data

    def _upsert_job(self, job: Dict[str, Any], *, idempotency_key: str = "") -> Dict[str, Any]:
        data = self.jobs_data()
        if idempotency_key:
            for existing in data.get("jobs", []):
                if existing.get("idempotency_key") == idempotency_key and existing.get("status") in {"queued", "running", "needs_privilege"}:
                    return existing
        data.setdefault("jobs", []).append(job)
        self._write_json(self.jobs_file(), data)
        self._write_json(self.jobs_dir / f"{job['job_id']}.json", job)
        return job

    def create_job(self, kind: str, *, status: str = "queued", progress: Optional[Dict[str, Any]] = None, command: str = "", artifacts: Optional[List[Dict[str, Any]]] = None, idempotency_key: str = "") -> Dict[str, Any]:
        job_id = "job_" + now_iso().replace(":", "").replace("-", "").replace("Z", "Z_") + safe_id(kind)
        job = {"job_id": job_id, "kind": kind, "status": status, "created_at": now_iso(), "updated_at": now_iso(), "progress": progress or {}, "command": command, "artifacts": artifacts or [], "idempotency_key": idempotency_key}
        return self._upsert_job(job, idempotency_key=idempotency_key)

    def jobs_list(self) -> Dict[str, Any]:
        data = self.jobs_data()
        return {"ok": True, "version": RUNTIME_VERSION, "jobs": data.get("jobs", [])}

    def job_get(self, job_id: str) -> Dict[str, Any]:
        job = self._read_json(self.jobs_dir / f"{safe_id(job_id)}.json", None)
        if not job:
            for j in self.jobs_data().get("jobs", []):
                if j.get("job_id") == job_id:
                    job = j
                    break
        return {"ok": bool(job), "version": RUNTIME_VERSION, "job": job or {}, "error": "job not found" if not job else ""}

    def job_cancel(self, job_id: str) -> Dict[str, Any]:
        data = self.jobs_data()
        target = None
        for j in data.get("jobs", []):
            if j.get("job_id") == job_id:
                j["status"] = "cancelled"
                j["updated_at"] = now_iso()
                target = j
        self._write_json(self.jobs_file(), data)
        if target:
            self._write_json(self.jobs_dir / f"{target['job_id']}.json", target)
        return {"ok": bool(target), "version": RUNTIME_VERSION, "job": target or {}, "reply": "Job cancelled" if target else "Job not found"}

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
        doc["conversation"] = self._conversation()
        doc["tasks"] = self.tasks_list().get("summary")
        doc["jobs"] = self.jobs_list().get("jobs", [])[-5:]
        return doc

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
        sockets = ["/run/noemaforge/llm/gateway.sock", "/run/noemaforge/llm/backends/main.sock", "/run/brainos/llm/gateway.sock"]
        sock_status = {s: Path(s).exists() for s in sockets}
        svc = run_json(["systemctl", "is-active", "noemaforge-llm-gateway.service"], timeout=10)
        main = run_json(["systemctl", "is-active", "noemaforge-llama@main.service"], timeout=10)
        main_manifest = self._read_json(Path("/var/lib/modelstore/models/main/noemaforge-model.json"), {}) or self._read_json(Path("/var/lib/modelstore/models/main/brainos-model.json"), {})
        return {"ok": True, "version": RUNTIME_VERSION, "sockets": sock_status, "gateway": svc, "main_backend": main, "main_manifest": main_manifest, "device_policy": self.device_policy().get("policy")}

    def device_policy(self) -> Dict[str, Any]:
        path = self.runtime_dir / "device-policy.json"
        policy = self._read_json(path, {"policy": "auto", "pending_apply": False, "applies_on": "next_persona_or_model_switch", "updated_at": now_iso()})
        return {"ok": True, "version": RUNTIME_VERSION, "policy": policy}

    def device_policy_set(self, policy: str) -> Dict[str, Any]:
        if policy not in {"auto", "cpu", "gpu", "cuda"}:
            return {"ok": False, "version": RUNTIME_VERSION, "error": "policy must be auto|cpu|gpu"}
        normalized = "gpu" if policy == "cuda" else policy
        doc = {"policy": normalized, "pending_apply": True, "applies_on": "next_persona_or_model_switch", "updated_at": now_iso(), "note": "Changing device policy does not migrate the currently running model; it applies on the next persona/model switch or backend restart."}
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
        staff = self._read_json(Path("/var/lib/noemaforge/bootstrap/firstboot-staffing-summary.json"), {})
        decision = self._read_json(Path("/var/lib/noemaforge/bootstrap/model-selection-decision.json"), {})
        hardware = {"memory": {"MemTotal": meminfo.get("MemTotal"), "MemAvailable": meminfo.get("MemAvailable"), "SwapTotal": meminfo.get("SwapTotal"), "SwapFree": meminfo.get("SwapFree")}, "nvidia_smi": nvidia, "sensors": sensors, "upower": upower}
        product = {"model_selection": {"staffing_state": staff.get("staffing_state"), "selected_model_count": staff.get("selected_model_count"), "missing_mandatory_core_roles": staff.get("missing_mandatory_core_roles"), "decision": decision}}
        return {"ok": True, "version": RUNTIME_VERSION, "hardware": hardware, "runtime": runtime, "product": product, "creative_metrics_policy": "creative media uses metadata/review-required metrics unless an explicit evaluator is configured"}

    # --- epoch/model-selection -------------------------------------------------------
    def model_selection_progress(self) -> Dict[str, Any]:
        inventory = self._read_json(Path("/var/lib/noemaforge/bootstrap/model-inventory.json"), {})
        health = self._read_json(Path("/var/lib/noemaforge/bootstrap/model-health-registry.json"), {})
        records = self._read_json(Path("/var/lib/noemaforge/bootstrap/model-run-records.json"), [])
        total = (inventory.get("summary") or {}).get("logical_models_total") or len(inventory.get("models", [])) or 0
        tested = len(records) if isinstance(records, list) else 0
        failed_models: List[str] = []
        if isinstance(health, dict):
            models = health.get("models") or {}
            if isinstance(models, dict):
                failed_models = [m for m, rec in models.items() if rec.get("exclude_from_selection") or rec.get("health_state", "").startswith("failed")]
        return {"total_models": total, "tested_models": tested, "failed_models": len(failed_models), "failed_model_ids": failed_models[:100], "remaining_models": max(0, int(total or 0) - int(tested or 0)), "records_path": "/var/lib/noemaforge/bootstrap/model-run-records.json", "health_registry": "/var/lib/noemaforge/bootstrap/model-health-registry.json"}

    def epoch_status(self) -> Dict[str, Any]:
        main_manifest = self._read_json(Path("/var/lib/modelstore/models/main/noemaforge-model.json"), {}) or self._read_json(Path("/var/lib/modelstore/models/main/brainos-model.json"), {})
        model_link = Path("/var/lib/modelstore/models/main/model.gguf")
        model_realpath = str(model_link.resolve()) if model_link.exists() else ""
        status = self._read_json(Path("/var/lib/noemaforge/bootstrap/firstboot-status.json"), {})
        staff = self._read_json(Path("/var/lib/noemaforge/bootstrap/firstboot-staffing-summary.json"), {})
        decision = self._read_json(Path("/var/lib/noemaforge/bootstrap/model-selection-decision.json"), {})
        candidate_plan = self._read_json(Path("/var/lib/noemaforge/bootstrap/candidate-selection-plan.json"), {})
        latest_msel = None
        for p in sorted(self.model_selection_state.glob("runs/msel_*"), reverse=True):
            if p.is_dir():
                latest_msel = p
                break
        latest_plan = self._read_json(latest_msel / "candidate-selection-plan.json", {}) if latest_msel else {}
        latest_decision = self._read_json(latest_msel / "model-selection-decision.json", {}) if latest_msel else {}
        return {"ok": True, "version": RUNTIME_VERSION, "current_epoch": {"manifest": main_manifest, "model_realpath": model_realpath}, "firstboot": {"status": status, "staffing": staff, "decision": decision, "candidate_plan": candidate_plan}, "latest_model_selection": {"run_dir": str(latest_msel) if latest_msel else "", "plan": latest_plan, "decision": latest_decision}, "progress": self.model_selection_progress(), "apply_available": bool(latest_plan or candidate_plan)}

    def model_selection(self, request: str, *, mode: str, scope: str, composite_top_n: int, apply: bool) -> Dict[str, Any]:
        cmd = [sys.executable, str(self.root / "src" / "model_selection_runtime.py"), "--root", str(self.root), "--state", str(self.model_selection_state), "plan", "--request", request, "--mode", mode, "--scope", scope, "--composite-top-n", str(composite_top_n), "--json"]
        if apply:
            cmd.append("--apply")
        result = run_json(cmd, env=self.env(), timeout=120)
        stdout = result.get("stdout")
        if result.get("ok") and isinstance(stdout, dict):
            artifacts = []
            artifact_map = stdout.get("artifacts") if isinstance(stdout.get("artifacts"), dict) else {}
            for key, path in artifact_map.items():
                artifacts.append({"type": "model_selection_artifact", "status": "created", "label": str(key).replace("_", "-"), "path": str(path), "open_command": "cat " + str(path)})
            reply = f"Режим отбора выбран: {stdout.get('mode', mode)}. Область: {stdout.get('scope', scope)}. План отбора модели создан; кандидаты, решение и rollback-plan прикреплены. Эпоха не применена без отдельного approve/apply."
            out = {"ok": True, "version": RUNTIME_VERSION, "reply": reply, "run_id": stdout.get("run_id"), "run_dir": stdout.get("run_dir"), "mode": stdout.get("mode", mode), "scope": stdout.get("scope", scope), "status": stdout.get("status"), "artifacts": artifacts, "raw": stdout, "api": {"inside_gui_supported": True, "endpoint": "/api/model-selection/plan", "cmd": cmd}}
            self.save_message("model", reply, persona="Optimizer", locale="ru", intent="model_selection", artifacts=artifacts, raw=out)
            return out
        out = {"ok": False, "version": RUNTIME_VERSION, "reply": "Model-selection plan failed.", "artifacts": [], "raw": result, "api": {"inside_gui_supported": True, "endpoint": "/api/model-selection/plan", "cmd": cmd}}
        self.save_message("model", out["reply"], persona="Optimizer", intent="model_selection", raw=out)
        return out

    def model_selection_continue(self, body: Dict[str, Any]) -> Dict[str, Any]:
        progress = self.model_selection_progress()
        mode = str(body.get("mode") or "full_composite")
        n = int(body.get("composite_top_n") or 4)
        idkey = f"model-selection-continue:{mode}:{n}"
        active = self.create_job("model_selection_continue", status="needs_privilege", progress=progress, command=(f"sudo noemaforge first-start --full_composite {n} --show-candidates --show-compositions --retry-failed-models --per-model-timeout 240 --total-timeout 7200" if mode == "full_composite" else f"sudo noemaforge first-start --{mode} --show-candidates --retry-failed-models --per-model-timeout 240 --total-timeout 7200"), idempotency_key=idkey)
        out = self.model_selection_state / "continue-selection-plan.json"
        doc = {"ok": True, "version": RUNTIME_VERSION, "created_at": now_iso(), "progress": progress, "job": active, "note": "Continuation plan created. A privileged terminal command or job runner is required for real continuation."}
        self._write_json(out, doc)
        active.setdefault("artifacts", []).append({"type": "model_selection_continue", "status": "created", "label": "continue-selection-plan.json", "path": str(out), "open_command": "cat " + str(out)})
        self._write_json(self.jobs_dir / f"{active['job_id']}.json", active)
        reply = f"Continuation plan ready: tested {progress.get('tested_models')} of {progress.get('total_models')} models; failed {progress.get('failed_models')}; remaining {progress.get('remaining_models')}."
        self.save_message("model", reply, persona="Optimizer", intent="model_selection_continue", artifacts=active.get("artifacts", []), raw=doc)
        return {"ok": True, "version": RUNTIME_VERSION, "reply": reply, "progress": progress, "job": active, "suggested_command": active.get("command"), "artifacts": active.get("artifacts", [])}

    def epoch_apply(self, body: Dict[str, Any]) -> Dict[str, Any]:
        status = self.epoch_status()
        plan = status.get("latest_model_selection", {}).get("plan") or status.get("firstboot", {}).get("candidate_plan") or {}
        mode = str(body.get("mode") or plan.get("mode") or "normal")
        scope = str(body.get("scope") or plan.get("scope") or "active runtime")
        composite_top_n = int(body.get("composite_top_n") or plan.get("composite_top_n") or 0)
        command = f"sudo noemaforge first-start --{mode}" if mode != "full_composite" else f"sudo noemaforge first-start --full_composite {composite_top_n}"
        job = self.create_job("epoch_apply", status="needs_privilege", progress=status.get("progress", {}), command=command, idempotency_key=f"epoch-apply:{mode}:{composite_top_n}:{scope}")
        out = self.model_selection_state / "epoch-apply-request.json"
        apply_doc = {"created_at": now_iso(), "mode": mode, "scope": scope, "composite_top_n": composite_top_n, "request": body.get("request") or "GUI epoch apply request", "suggested_command": command, "job": job, "status": status}
        self._write_json(out, apply_doc)
        artifacts = [{"type": "epoch_apply_request", "status": "created", "label": "epoch-apply-request.json", "path": str(out), "open_command": "cat " + str(out)}]
        reply = "Epoch transition request is ready. Review artifacts, then run the suggested sudo first-start apply command or approved job-runner action."
        self.save_message("system", reply, persona="Optimizer", intent="epoch_apply", artifacts=artifacts, raw=apply_doc)
        return {"ok": True, "version": RUNTIME_VERSION, "reply": reply, "job": job, "suggested_command": command, "artifacts": artifacts}

    # --- pipeline catalog ------------------------------------------------------------
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
            items.append({"id": pid, "description": desc, "group": group, "stages": p.get("stages", []) if isinstance(p, dict) else [], "team": p.get("team", "") if isinstance(p, dict) else ""})
        for p in media.get("pipelines", []) if isinstance(media, dict) else []:
            pid = p.get("id")
            if pid:
                items.append({"id": pid, "description": p.get("notes", ""), "group": "Media", "stages": [p.get("stage", "prepared")], "entrypoint": p.get("entrypoint", "")})
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
        return {"ok": True, "version": RUNTIME_VERSION, "pipeline_id": pipeline_id, "stages": stages, "mermaid": mermaid, "editable": "todo_draft_only"}

    def pipeline_stats(self, pipeline_id: str) -> Dict[str, Any]:
        runs_dir = self.state / "runs"
        runs = []
        if runs_dir.exists():
            for p in runs_dir.iterdir():
                if p.is_dir() and pipeline_id in p.name:
                    runs.append(str(p))
        return {"ok": True, "version": RUNTIME_VERSION, "pipeline_id": pipeline_id, "stats": {"runs_total": len(runs), "last_runs": runs[-10:], "runs_passed": None, "runs_failed": None, "avg_duration_sec": None, "note": "Full pipeline metrics will be accumulated by the job/pipeline event store."}}

    def pipeline_draft(self, body: Dict[str, Any]) -> Dict[str, Any]:
        draft_id = "draft_" + safe_id(str(body.get("id") or body.get("title") or now_iso()), "pipeline")
        out = self.data_root / "pipelines" / "drafts" / f"{draft_id}.json"
        draft = {"draft_id": draft_id, "created_at": now_iso(), "status": "draft_only", "body": body, "safety": "not active until Scary/Architecture/Admin approval"}
        self._write_json(out, draft)
        return {"ok": True, "version": RUNTIME_VERSION, "reply": "New pipeline draft created; it is not active until review/approval.", "draft": draft, "artifacts": [{"type": "pipeline_draft", "status": "created", "label": f"{draft_id}.json", "path": str(out), "open_command": "cat " + str(out)}]}

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
        if self._conversational(low):
            reply = self.try_llm_admin_reply(text, locale) or self.fallback_conversation_reply(text, locale)
            self.save_message("admin", reply, persona=conv.get("active_persona", "Admin"), locale=locale, intent="conversation")
            return {"ok": True, "version": RUNTIME_VERSION, "reply": reply, "mode": "conversation", "locale": locale, "artifacts": []}
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
        return any(k in low for k in ["добавь задачу", "измени задачу", "приоритет", "пометь задачу", "задач"])

    def _handle_task_intent(self, text: str, locale: str) -> Dict[str, Any]:
        low = text.lower()
        priority = 80 if any(k in low for k in ["высок", "high", "важн"]) else 50
        category = "dev_team" if "dev" in low or "код" in low else "general"
        if any(k in low for k in ["добав", "создай", "new"]):
            title = re.sub(r"^(добавь|создай) задачу[:：]?", "", text, flags=re.I).strip() or text
            return self.task_create({"title": title, "category": category, "priority": priority, "assignee": "Dev Team" if category == "dev_team" else "Admin"})
        return {"ok": True, "version": RUNTIME_VERSION, "reply": "Я могу добавлять, редактировать и приоритезировать задачи. Уточни task_id или сформулируй: 'добавь задачу: ... приоритет высокий'.", "tasks": self.tasks_list()}

    def _conversational(self, low: str) -> bool:
        control = ["оптимиз", "эволюц", "dev team", "доработ", "pipeline", "пайп", "модель", "подбор", "vault", "инвентар", "switch", "epoch", "задач"]
        if any(k in low for k in control):
            return False
        return True

    def try_llm_admin_reply(self, text: str, locale: str) -> str:
        if os.environ.get("NOEMAFORGE_GUI_DISABLE_LLM_CHAT") == "1":
            return ""
        if not (Path("/run/noemaforge/llm/gateway.sock").exists() or Path("/run/noemaforge/llm/backends/main.sock").exists()):
            return ""
        prompt = text if locale != "ru" else "Ответь по-русски как локальный Admin NoemaForge, коротко и полезно. Запрос: " + text
        cmd = [str(self.root / "bin" / "noemaforge"), "chat", "--role", "admin", "--once", prompt]
        r = run_json(cmd, env=self.env(locale), timeout=20)
        out = r.get("stdout")
        if isinstance(out, str) and out.strip() and "error" not in out.lower():
            return out.strip()[:4000]
        return ""

    def fallback_conversation_reply(self, text: str, locale: str) -> str:
        runtime = self.runtime_status()
        model = (runtime.get("main_manifest") or {}).get("model_id") or (runtime.get("main_manifest") or {}).get("name") or "main"
        if locale == "ru":
            return f"Я здесь. Сейчас работаю как локальный Admin NoemaForge в режиме GUI/control-plane. Текущая main-модель: {model}. Я могу вести чат, показывать метрики, управлять задачами, запускать пайплайны, готовить подбор моделей, Dev Team и эволюцию — без скрытого применения изменений."
        return f"I am here. I am running as the local NoemaForge Admin GUI/control-plane. Current main model: {model}. I can chat, show metrics, manage tasks, route pipelines, prepare model selection, Dev Team work and evolution without hidden apply steps."

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
        cmd = [sys.executable, str(self.root / "src" / "pipeline_runtime.py"), "--root", str(self.root), "--state", str(self.state), "run", pipeline, "--request", request]
        if allow_degraded:
            cmd.append("--allow-degraded")
        result = run_json(cmd, env=self.env(), timeout=180)
        self.save_message("system", f"Pipeline requested: {pipeline}", persona="Pipeline", intent="pipeline_run", raw=result)
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
        job = self.create_job("vault_reinventory", status="needs_privilege", progress=progress, command=command, idempotency_key="vault-reinventory")
        reply = "Vault re-inventory requires privileged execution. I created a job/plan with the exact command; run it in terminal or through an approved root job-runner."
        self.save_message("system", reply, persona="Vault", intent="vault_reinventory", raw=job)
        return {"ok": True, "version": RUNTIME_VERSION, "reply": reply, "job": job, "suggested_command": command}

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
