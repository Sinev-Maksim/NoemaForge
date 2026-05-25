#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/pipeline_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-14
Modified: 2026-05-25
Purpose: Manage NoemaForge pipeline catalog, runs, gates, artifacts and state.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

Existing module notes:
NoemaForge switchable pipeline runtime.

NoemaForge-native, conservative process-centric scaffold for administrator-launched
pipelines. It targets switchable LLMs, not simultaneous multi-model teams.
Stage-to-stage handoff is done with markdown context packets:
`task_<task_id>_project_<project_id>_<stage>_context.md`.

0.32.2 includes pipeline member cells: each participant can be standalone or a sequential multi-model cell with proposal/consensus/unique artifacts.

0.30.0 MVP/MWP scope:
- durable local SQLite run/event/artifact registry;
- explicit lifecycle commands: run, approve, advance, pause, resume, fail, cancel;
- artifact registration and listing;
- safe worktree planning/creation for evolution work;
- dashboard state for a tiny static GUI;
- doctor/next helpers for non-engineer operators;
- 0.30.05 pattern catalog / persona catalog validation hooks.
- 0.30.09 readiness, run-repair, stage gates and template import helpers.
- 0.30.21 P1 typed event/state core, LLM leases, schema validation and metrics exporters.
- 0.32.2 carries forward self-improvement testbench/wiki-patch integration hooks.
- 0.32.2 includes member-cell pipeline subcommands and code analyzer/visualizer handoff artifacts.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import os
import re
import hashlib
import fnmatch
import tarfile
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import production_ai_contracts

DEFAULT_ROOT = Path(os.environ.get("NOEMAFORGE_ROOT", "/opt/noemaforge"))
DEFAULT_STATE = Path(os.environ.get("NOEMAFORGE_PIPELINE_STATE", "/var/lib/noemaforge/pipelines"))
DEFAULT_PERSONA_STATE = Path(os.environ.get("NOEMAFORGE_PERSONA_STATE", "/var/lib/noemaforge/personas"))
SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")
from noemaforge_version import RUNTIME_VERSION
FINISHED_STATUSES = {"done", "completed", "cancelled", "failed", "archived"}
PAUSED_STATUSES = {"paused", "waiting_for_admin"}
ACTIVE_STATUSES = {"ready_for_admin_approval", "approved", "in_progress", "testing", "review", "optimization"}
EVOLUTION_WORKTREE_BRANCH_PREFIX = "noemaforge/evolution/"
WORKTREE_REF_RE = re.compile(r"^[A-Za-z0-9._/@+-]{1,180}$")
TOOLPROXY_POLICY_REF = "tool-policy:tool-policy-main:0.32.2"
TOOLPROXY_CAPABILITY_SCHEMA_REF = "contracts/capability_token.schema.json"
TOOLPROXY_BASE_ACTIONS = [
    "llm.chat",
    "llm.embed",
    "fs.read",
    "vstore.query",
    "task.get",
    "task.output",
    "plan.status",
    "roadmap.list",
]
TOOLPROXY_MUTATING_ACTIONS = {"fs.write", "task.create", "task.update", "vstore.upsert", "roadmap.record", "worktree.enter"}
TOOLPROXY_SANDBOXED_ACTIONS = {"exec.run"}
TOOLPROXY_BLOCKED_BY_STAGE_DEFAULT = [
    "db.write",
    "team_memory.import",
    "worktree.promote",
    "localgw.discover",
    "voice.capture_live",
]
TOOLPROXY_WRITE_STAGE_TERMS = {
    "development",
    "drafting",
    "docs_update",
    "changelog",
    "graph_patch",
    "relation_mapping",
    "entity_extraction",
    "integration_edit",
}
TOOLPROXY_EXEC_STAGE_TERMS = {
    "testing",
    "test",
    "smoke",
    "validation",
    "optimization",
    "fact_check",
    "inventory",
}
TOOLPROXY_REVIEW_STAGE_TERMS = {
    "review",
    "admin_review",
    "merge_plan",
    "publish_plan",
    "archive_plan",
    "export_plan",
}

DEFAULT_PIPELINES: Dict[str, Dict[str, Any]] = {
    "public_mwp": {
        "description": "Public minimum workable path: status, safe start, first chat, first pipeline, support bundle.",
        "project_id": "noemaforge_public_mwp",
        "stages": ["orient", "status_check", "safe_runtime", "first_chat", "first_pipeline", "support_bundle", "review"],
        "team": "public_onboarding_team",
        "permission_mode": "guided_readmostly",
        "llm_policy": {"mode": "switchable", "max_active_llms": 1},
        "deliverables": ["status_note", "safe_runtime_check", "first_chat_note", "first_pipeline_note", "support_bundle_plan"],
    },
    "evolution": {
        "description": "Architecture-aware development/evolution pipeline.",
        "project_id": "noemaforge",
        "stages": ["intake", "architecture_clarification", "development", "unit_testing", "integration_testing", "optimization", "review", "merge_plan"],
        "team": "development_evolution_team",
        "permission_mode": "ask_before_write",
        "llm_policy": {"mode": "switchable", "max_active_llms": 1},
        "deliverables": ["architecture_note", "patch_or_plan", "test_report", "optimization_note", "merge_plan"],
    },
    "book": {
        "description": "Research-to-book pipeline with editor/reviewer handoffs.",
        "project_id": "noemaforge_book",
        "stages": ["intake", "research", "outline", "drafting", "editor_review", "fact_check", "integration_edit", "export_plan"],
        "team": "book_team",
        "permission_mode": "plan_only",
        "llm_policy": {"mode": "switchable", "max_active_llms": 1},
        "deliverables": ["source_notes", "outline", "draft", "editor_notes", "fact_check", "export_plan"],
    },
    "knowledge_graph": {
        "description": "Knowledge graph creation/update pipeline.",
        "project_id": "noemaforge_kg",
        "stages": ["intake", "source_inventory", "entity_extraction", "relation_mapping", "provenance_review", "graph_patch", "validation", "publish_plan"],
        "team": "knowledge_graph_team",
        "permission_mode": "ask_before_write",
        "llm_policy": {"mode": "switchable", "max_active_llms": 1},
        "deliverables": ["source_inventory", "entities", "relations", "provenance", "graph_patch", "validation_report"],
    },
    "release_prep": {
        "description": "Release merge, checks, notes and archive preparation.",
        "project_id": "noemaforge_release",
        "stages": ["intake", "inventory", "merge_analysis", "smoke_tests", "docs_update", "changelog", "archive_plan", "admin_review"],
        "team": "release_team",
        "permission_mode": "ask_before_write",
        "llm_policy": {"mode": "switchable", "max_active_llms": 1},
        "deliverables": ["inventory", "merge_summary", "smoke_report", "release_notes", "archive_plan"],
    },
}

DEFAULT_TEAMS: Dict[str, Dict[str, Any]] = {
    "public_onboarding_team": {
        "coordinator": "operator_guide",
        "roles": ["status_checker", "safe_runtime_helper", "chat_guide", "support_archivist"],
        "handoff": "single active LLM; guided read-mostly MVP/MWP onboarding path",
    },
    "development_evolution_team": {
        "coordinator": "administrator",
        "roles": ["architect", "developer", "tester", "integration_tester", "optimizer", "reviewer", "archivist"],
        "handoff": "single active LLM; each role receives the previous context packet and writes a new artifact",
    },
    "book_team": {
        "coordinator": "editor_in_chief",
        "roles": ["researcher", "outline_architect", "writer", "editor", "fact_checker", "archivist"],
        "handoff": "single active LLM; source notes and chapter drafts move through markdown packets",
    },
    "knowledge_graph_team": {
        "coordinator": "knowledge_architect",
        "roles": ["source_curator", "entity_mapper", "relation_mapper", "provenance_reviewer", "graph_validator"],
        "handoff": "single active LLM; graph patches must include provenance before publish_plan",
    },
    "release_team": {
        "coordinator": "release_manager",
        "roles": ["inventory_checker", "merge_analyst", "smoke_tester", "docs_writer", "reviewer"],
        "handoff": "single active LLM; every release stage produces an auditable artifact",
    },
}


def nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_id(value: str) -> str:
    value = SAFE_ID_RE.sub("_", (value or "").strip()).strip("_")
    return value or "task"


def build_toolproxy_stage_binding(pipeline_id: str, stage: str, permission_mode: str = "plan_only") -> Dict[str, Any]:
    """Build the ToolProxy action contract that a pipeline stage may request."""
    stage_id = safe_id(stage)
    stage_key = stage_id.lower()
    allowed = set(TOOLPROXY_BASE_ACTIONS)
    mutating_allowed: List[str] = []

    if any(term in stage_key for term in TOOLPROXY_WRITE_STAGE_TERMS) and permission_mode != "guided_readmostly":
        mutating_allowed.extend(["fs.write", "task.create", "task.update", "vstore.upsert"])
    if any(term in stage_key for term in TOOLPROXY_EXEC_STAGE_TERMS):
        allowed.add("exec.run")
    if any(term in stage_key for term in TOOLPROXY_REVIEW_STAGE_TERMS):
        mutating_allowed.extend(["task.update", "roadmap.record"])
    if str(pipeline_id) == "evolution" and stage_key in {"development", "review", "merge_plan"}:
        mutating_allowed.append("worktree.enter")

    allowed.update(mutating_allowed)
    allowed_actions = sorted(allowed)
    mutating = sorted(action for action in allowed_actions if action in TOOLPROXY_MUTATING_ACTIONS)
    sandboxed = sorted(action for action in allowed_actions if action in TOOLPROXY_SANDBOXED_ACTIONS)
    approval_required = bool(mutating or permission_mode == "ask_before_write")
    return {
        "apiVersion": "noemaforge.pipeline.toolproxy-stage-binding/v1",
        "policy_ref": TOOLPROXY_POLICY_REF,
        "capability_schema_ref": TOOLPROXY_CAPABILITY_SCHEMA_REF,
        "pipeline_id": str(pipeline_id),
        "stage": stage_id,
        "scope": f"pipeline:{safe_id(str(pipeline_id))}:stage:{stage_id}",
        "capability_token_required": True,
        "approval_required": approval_required,
        "sandbox_required": bool(sandboxed),
        "network_allowed": False,
        "allowed_actions": allowed_actions,
        "mutating_actions": mutating,
        "sandboxed_actions": sandboxed,
        "blocked_actions": list(TOOLPROXY_BLOCKED_BY_STAGE_DEFAULT),
        "issue_hint": f"noemaforge toolproxy token issue --scope pipeline:{safe_id(str(pipeline_id))}:stage:{stage_id}",
    }


def build_toolproxy_stage_bindings(pipeline: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    pipeline_id = str(pipeline.get("id") or "unknown")
    permission_mode = str(pipeline.get("permission_mode") or "plan_only")
    return {
        str(stage): build_toolproxy_stage_binding(pipeline_id, str(stage), permission_mode)
        for stage in list(pipeline.get("stages") or [])
    }


def path_is_under(child: Path, parent: Path) -> bool:
    child_resolved = child.resolve()
    parent_resolved = parent.resolve()
    try:
        child_resolved.relative_to(parent_resolved)
        return True
    except ValueError:
        return False


def validate_worktree_ref(value: str, *, field: str) -> str:
    ref = str(value or "").strip()
    if not ref:
        raise SystemExit(f"missing_{field}")
    if (
        not WORKTREE_REF_RE.match(ref)
        or ".." in ref
        or ref.startswith("/")
        or ref.endswith("/")
        or ref.endswith(".lock")
        or "@{" in ref
    ):
        raise SystemExit(f"unsafe_{field}: {ref}")
    return ref


def safe_evolution_worktree_branch(run: Dict[str, Any], requested: str = "") -> str:
    task_id = safe_id(str(run.get("task_id") or "task")).replace("_", "-")
    if requested:
        branch = validate_worktree_ref(requested, field="branch")
        if not branch.startswith(EVOLUTION_WORKTREE_BRANCH_PREFIX):
            raise SystemExit(f"unsafe_branch_namespace: expected {EVOLUTION_WORKTREE_BRANCH_PREFIX}")
        return branch
    return f"{EVOLUTION_WORKTREE_BRANCH_PREFIX}{task_id}"


def build_evolution_worktree_plan(
    run: Dict[str, Any],
    *,
    repo: str,
    branch: str = "",
    base: str = "HEAD",
    path: str = "",
    cwd: Optional[Path] = None,
) -> Dict[str, Any]:
    if str(run.get("pipeline_id") or "") != "evolution":
        raise SystemExit("worktree_requires_evolution_pipeline")
    repo_path = Path(repo or str(cwd or Path.cwd())).resolve()
    if not ((repo_path / ".git").is_dir() or (repo_path / ".git").is_file()):
        raise SystemExit(f"not a git worktree/repo: {repo_path}")
    base_ref = validate_worktree_ref(base or "HEAD", field="base_ref")
    branch_name = safe_evolution_worktree_branch(run, branch)
    run_dir = Path(str(run["run_dir"])).resolve()
    dest_root = run_dir / "worktrees"
    if path:
        requested = Path(path)
        dest = requested.resolve() if requested.is_absolute() else (dest_root / requested).resolve()
    else:
        dest = (dest_root / branch_name.replace("/", "-")).resolve()
    if not path_is_under(dest, dest_root):
        raise SystemExit(f"worktree_path_outside_run_dir: {dest}")
    cmd = ["git", "-C", str(repo_path), "worktree", "add", "-B", branch_name, str(dest), base_ref]
    return {
        "ok": True,
        "run_id": run["run_id"],
        "repo": str(repo_path),
        "branch": branch_name,
        "path": str(dest),
        "base": base_ref,
        "command": cmd,
        "applied": False,
        "safety": {
            "pipeline_id": run.get("pipeline_id"),
            "branch_namespace": EVOLUTION_WORKTREE_BRANCH_PREFIX,
            "destination_root": str(dest_root.resolve()),
            "destination_under_run_dir": True,
            "plan_default": True,
            "apply_requires_flag": True,
            "subprocess_uses_argv": True,
        },
    }


def read_text_if_exists(path: Path, limit: int = 24000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception:
        return ""


def load_json_or_default(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    try:
        loaded = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        pass
    return default


def json_dumps(data: Any, *, pretty: bool = True) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2 if pretty else None, sort_keys=False)


def atomic_write_text(path: Path, text: str) -> None:
    """Write text atomically enough for local operator state files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def parse_jsonish_text(text: str) -> Any:
    """Best-effort JSON parser used by template import without external deps."""
    text = text.strip()
    if not text:
        return {}
    return json.loads(text)


def db_connect(state: Path) -> sqlite3.Connection:
    state.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(state / "pipeline_registry.sqlite")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", ("schema_runtime_version", RUNTIME_VERSION))
    conn.execute("CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, pipeline_id TEXT NOT NULL, task_id TEXT NOT NULL, project_id TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, current_stage TEXT NOT NULL, run_dir TEXT NOT NULL, request TEXT NOT NULL, manifest TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, ts TEXT NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS artifacts (artifact_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, stage TEXT NOT NULL, artifact_type TEXT NOT NULL, path TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}')")
    conn.execute("CREATE TABLE IF NOT EXISTS stage_states (run_id TEXT NOT NULL, stage TEXT NOT NULL, state TEXT NOT NULL, updated_at TEXT NOT NULL, details TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(run_id, stage))")
    conn.execute("CREATE TABLE IF NOT EXISTS task_contexts (context_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, stage TEXT NOT NULL, md_path TEXT NOT NULL, json_path TEXT NOT NULL, json_sha256 TEXT NOT NULL, created_at TEXT NOT NULL, envelope TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS approvals (approval_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL, approved_by TEXT NOT NULL, created_at TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}')")
    conn.execute("CREATE TABLE IF NOT EXISTS llm_leases (lease_id TEXT PRIMARY KEY, owner TEXT NOT NULL, task_id TEXT NOT NULL, priority INTEGER NOT NULL, state TEXT NOT NULL, acquired_at TEXT NOT NULL, expires_at TEXT NOT NULL, updated_at TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}')")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_events_run_id ON events(run_id, id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_artifacts_run_id ON artifacts(run_id, stage)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_stage_states_run_id ON stage_states(run_id, stage)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_task_contexts_run_id ON task_contexts(run_id, stage)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_llm_leases_state ON llm_leases(state, priority)")
    conn.commit()
    return conn


def emit(conn: sqlite3.Connection, run_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    conn.execute("INSERT INTO events(run_id,ts,event_type,payload) VALUES(?,?,?,?)", (run_id, nowz(), event_type, json_dumps(payload)))
    conn.commit()


def _parse_ts(value: str) -> Optional[dt.datetime]:
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _seconds_from_now(seconds: int) -> str:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=int(seconds))).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _active_unexpired_lease(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    now = dt.datetime.now(dt.timezone.utc)
    rows = conn.execute("SELECT lease_id,owner,task_id,priority,state,acquired_at,expires_at,updated_at,metadata FROM llm_leases WHERE state='active' ORDER BY priority DESC, acquired_at ASC").fetchall()
    for row in rows:
        rec = dict(zip(["lease_id", "owner", "task_id", "priority", "state", "acquired_at", "expires_at", "updated_at", "metadata"], row))
        expires = _parse_ts(str(rec.get("expires_at") or ""))
        if expires and expires < now:
            conn.execute("UPDATE llm_leases SET state='expired', updated_at=? WHERE lease_id=?", (nowz(), rec["lease_id"]))
            conn.commit()
            continue
        try:
            rec["metadata"] = json.loads(str(rec.get("metadata") or "{}"))
        except Exception:
            rec["metadata"] = {}
        return rec
    return None


def upsert_stage_states(conn: sqlite3.Connection, run_id: str, stages: List[str], current_stage: str, status: str) -> None:
    ts = nowz()
    seen_current = False
    for stage in stages:
        if stage == current_stage:
            state = status
            seen_current = True
        elif not seen_current:
            state = "done_or_prior"
        else:
            state = "pending"
        conn.execute(
            "INSERT OR REPLACE INTO stage_states(run_id,stage,state,updated_at,details) VALUES(?,?,?,?,?)",
            (run_id, stage, state, ts, json_dumps({"runtime_version": RUNTIME_VERSION}, pretty=False)),
        )
    conn.commit()


def register_task_contexts(conn: sqlite3.Connection, run_id: str, packet_paths: List[str]) -> None:
    ts = nowz()
    for packet in packet_paths:
        md_path = Path(packet)
        json_path = md_path.with_suffix(".json")
        if not json_path.exists():
            continue
        raw = json_path.read_text(encoding="utf-8", errors="replace")
        digest = hashlib.sha256(json_path.read_bytes()).hexdigest()
        try:
            envelope = json.loads(raw)
        except Exception:
            envelope = {"parse_error": True, "raw_prefix": raw[:2000]}
        stage = str(envelope.get("stage") or md_path.stem)
        context_id = safe_id(f"ctx_{run_id}_{stage}_{digest[:12]}")
        conn.execute(
            "INSERT OR REPLACE INTO task_contexts(context_id,run_id,stage,md_path,json_path,json_sha256,created_at,envelope) VALUES(?,?,?,?,?,?,?,?)",
            (context_id, run_id, stage, str(md_path), str(json_path), digest, ts, json_dumps(envelope, pretty=False)),
        )
    conn.commit()


def load_pipeline_catalog(root: Path) -> Dict[str, Dict[str, Any]]:
    """Load packaged pipelines plus an optional reviewed local catalog.

    `pipelines.local.json` is intentionally separate from the shipped catalog so
    imported n8n/Temporal/Airflow/GitHub Actions drafts can be reviewed and
    enabled without mutating the distribution file.
    """
    base = dict(load_json_or_default(root / "configs" / "pipelines.json", DEFAULT_PIPELINES))
    local_path = root / "configs" / "pipelines.local.json"
    if local_path.exists():
        local = load_json_or_default(local_path, {})
        for key, value in local.items():
            if isinstance(value, dict):
                base[key] = value
    return base


def load_team_catalog(root: Path) -> Dict[str, Dict[str, Any]]:
    return load_json_or_default(root / "configs" / "pipeline-teams.json", DEFAULT_TEAMS)


def load_pattern_catalog(root: Path) -> Dict[str, Any]:
    return load_json_or_default(root / "configs" / "pipeline-pattern-catalog.json", {"version": RUNTIME_VERSION, "patterns": []})


def load_persona_catalog(root: Path) -> Dict[str, Any]:
    return load_json_or_default(root / "configs" / "persona-catalog.json", {"version": RUNTIME_VERSION, "personas": {}})


def load_low_hanging_catalog(root: Path) -> Dict[str, Any]:
    return load_json_or_default(root / "configs" / "low-hanging-fruits.json", {"version": RUNTIME_VERSION, "collections": []})


def load_selftest_catalog(root: Path) -> Dict[str, Any]:
    return load_json_or_default(root / "configs" / "selftest-case-catalog.json", {"version": RUNTIME_VERSION, "cases": [], "suites": {}})


def load_selftest_policy(root: Path) -> Dict[str, Any]:
    return load_json_or_default(root / "configs" / "selftest-telemetry-policy.json", {"version": RUNTIME_VERSION, "thresholds": {}})


def load_persona_state(state: Path = DEFAULT_PERSONA_STATE) -> Dict[str, Any]:
    return load_json_or_default(state / "persona_state.json", {"active": None, "generations": {}, "events": []})


def active_llm_sockets() -> List[str]:
    backend_dir = Path("/run/noemaforge/llm/backends")
    try:
        return sorted(str(p) for p in backend_dir.glob("*.sock") if p.exists())
    except Exception:
        return []


def active_llm_count() -> int:
    # Do not cap this. Doctor/readiness must be able to detect invariant drift.
    return len(active_llm_sockets())


def runtime_snapshot() -> Dict[str, Any]:
    sockets = active_llm_sockets()
    return {
        "mode": "switchable",
        "active_llms": len(sockets),
        "max_active_llms": 1,
        "ok": len(sockets) <= 1,
        "backend_sockets": sockets,
    }




def firstboot_staffing_summary_path() -> Path:
    return Path(os.environ.get("NOEMAFORGE_FIRSTBOOT_STAFFING_SUMMARY", "/var/lib/noemaforge/bootstrap/firstboot-staffing-summary.json"))


def degraded_readonly_state() -> Dict[str, Any]:
    """Return whether mutating pipeline operations must be blocked.

    Degraded firstboot is useful as a readable baseline, but it should not
    silently run mutating workflows. Operators can override deliberately with
    --allow-degraded or NOEMAFORGE_ALLOW_DEGRADED_MUTATION=1.
    """
    path = firstboot_staffing_summary_path()
    override = os.environ.get("NOEMAFORGE_ALLOW_DEGRADED_MUTATION", "").lower() in {"1", "true", "yes"}
    summary: Dict[str, Any] = {}
    state = "unknown"
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(loaded, dict):
                summary = loaded
                state = str(loaded.get("staffing_state") or loaded.get("state") or "unknown")
        except Exception:
            state = "malformed"
    active = state in {"degraded_selected", "unstaffed", "malformed"} and not override
    return {
        "active": active,
        "state": state,
        "override": override,
        "path": str(path),
        "summary": summary,
        "mode": "degraded_readonly" if active else "normal",
    }


def guard_degraded_mutation(operation: str, allow: bool = False) -> None:
    st = degraded_readonly_state()
    if allow or st.get("override") or not st.get("active"):
        return
    print(json_dumps({
        "ok": False,
        "blocked": True,
        "operation": operation,
        "reason": "degraded_readonly",
        "staffing_state": st.get("state"),
        "staffing_summary": st.get("path"),
        "override": "rerun with --allow-degraded or set NOEMAFORGE_ALLOW_DEGRADED_MUTATION=1 after explicit admin approval",
    }))
    raise SystemExit(3)

def _row_to_run(row: sqlite3.Row | tuple[Any, ...]) -> Dict[str, Any]:
    keys = ["run_id", "pipeline_id", "task_id", "project_id", "status", "created_at", "updated_at", "current_stage", "run_dir"]
    return dict(zip(keys, row))


def _event_rows(conn: sqlite3.Connection, run_id: str, limit: int = 12) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT id,ts,event_type,payload FROM events WHERE run_id=? ORDER BY id DESC LIMIT ?", (run_id, limit)).fetchall()
    out: List[Dict[str, Any]] = []
    for eid, ts, event_type, payload in reversed(rows):
        try:
            body = json.loads(payload)
        except Exception:
            body = {"raw": payload}
        out.append({"id": eid, "ts": ts, "event_type": event_type, "payload": body})
    return out


def _artifact_rows(conn: sqlite3.Connection, run_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT artifact_id,stage,artifact_type,path,status,created_at,updated_at,metadata FROM artifacts WHERE run_id=? ORDER BY created_at, artifact_id", (run_id,)).fetchall()
    out: List[Dict[str, Any]] = []
    for artifact_id, stage, artifact_type, path, status, created_at, updated_at, metadata in rows:
        try:
            meta = json.loads(metadata or "{}")
        except Exception:
            meta = {}
        out.append({"artifact_id": artifact_id, "stage": stage, "artifact_type": artifact_type, "path": path, "status": status, "created_at": created_at, "updated_at": updated_at, "metadata": meta})
    return out




def _all_artifact_rows(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT artifact_id,run_id,stage,artifact_type,path,status,created_at,updated_at,metadata FROM artifacts ORDER BY created_at, artifact_id").fetchall()
    out: List[Dict[str, Any]] = []
    for artifact_id, run_id, stage, artifact_type, path, status, created_at, updated_at, metadata in rows:
        try:
            meta = json.loads(metadata or "{}")
        except Exception:
            meta = {}
        out.append({
            "artifact_id": artifact_id,
            "run_id": run_id,
            "stage": stage,
            "artifact_type": artifact_type,
            "path": path,
            "status": status,
            "created_at": created_at,
            "updated_at": updated_at,
            "metadata": meta,
        })
    return out

def get_run(conn: sqlite3.Connection, run_id: str) -> Dict[str, Any]:
    row = conn.execute("SELECT run_id,pipeline_id,task_id,project_id,status,created_at,updated_at,current_stage,run_dir,request,manifest FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not row:
        raise SystemExit(f"run not found: {run_id}")
    keys = ["run_id", "pipeline_id", "task_id", "project_id", "status", "created_at", "updated_at", "current_stage", "run_dir", "request", "manifest"]
    data = dict(zip(keys, row))
    try:
        data["manifest"] = json.loads(str(data["manifest"]))
    except Exception:
        data["manifest"] = {}
    return data


def update_run(conn: sqlite3.Connection, run: Dict[str, Any], status: str, stage: Optional[str] = None, note: str = "", event_type: str = "pipeline_stage_updated") -> Dict[str, Any]:
    ts = nowz()
    stage = stage or str(run.get("current_stage") or "intake")
    manifest = dict(run.get("manifest") or {})
    manifest["status"] = status
    manifest["current_stage"] = stage
    manifest["updated_at"] = ts
    if note:
        manifest.setdefault("notes", []).append({"ts": ts, "stage": stage, "status": status, "note": note})
    run_dir = Path(str(run["run_dir"]))
    run_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(run_dir / "manifest.json", json_dumps(manifest))
    with (run_dir / "decisions.md").open("a", encoding="utf-8") as f:
        f.write(f"\n## {ts} — {stage}\n\n- Status: `{status}`\n- Note: {note or 'stage state updated by operator'}\n")
    conn.execute("UPDATE runs SET status=?, current_stage=?, updated_at=?, manifest=? WHERE run_id=?", (status, stage, ts, json_dumps(manifest, pretty=False), run["run_id"]))
    conn.commit()
    stages = list(((manifest.get("pipeline") or {}).get("stages") or []))
    upsert_stage_states(conn, str(run["run_id"]), stages, stage, status)
    if event_type == "pipeline_approved" or status == "approved":
        approval_id = safe_id(f"appr_{run['run_id']}_{stage}_{ts}")
        conn.execute(
            "INSERT OR REPLACE INTO approvals(approval_id,run_id,stage,status,approved_by,created_at,metadata) VALUES(?,?,?,?,?,?,?)",
            (approval_id, str(run["run_id"]), stage, status, os.environ.get("USER", "operator"), ts, json_dumps({"note": note, "event_type": event_type}, pretty=False)),
        )
        conn.commit()
    emit(conn, str(run["run_id"]), event_type, {"stage": stage, "status": status, "note": note})
    run["status"] = status
    run["current_stage"] = stage
    run["updated_at"] = ts
    run["manifest"] = manifest
    return run


def next_stage_for(manifest: Dict[str, Any], current_stage: str) -> Optional[str]:
    stages = list(((manifest.get("pipeline") or {}).get("stages")) or [])
    if current_stage not in stages:
        return stages[0] if stages else None
    idx = stages.index(current_stage)
    if idx + 1 < len(stages):
        return stages[idx + 1]
    return None


def context_root(root: Path) -> str:
    candidates = [
        root.parent / "context.md",
        root / ".." / "context.md",
        root / "context.md",
        Path.cwd() / "context.md",
    ]
    for candidate in candidates:
        text = read_text_if_exists(candidate)
        if text:
            return text
    return "# Project context snapshot\n\nNo context.md found at package root.\n"


def write_stage_packet(run_dir: Path, pipeline: Dict[str, Any], team: Dict[str, Any], task_id: str, project_id: str, stage: str, request: str, previous: Optional[str]) -> Path:
    fname = f"task_{safe_id(task_id)}_project_{safe_id(project_id)}_{safe_id(stage)}_context.md"
    path = run_dir / "context_packets" / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    roles = list(team.get("roles", []))
    role_hint = team.get("coordinator", "coordinator") if stage in ("intake", "review", "admin_review", "merge_plan", "publish_plan", "export_plan") else ", ".join(roles)
    deliverables = "\n".join(f"- `{item}`" for item in pipeline.get("deliverables", [])) or "- stage output artifact"
    toolproxy_binding = build_toolproxy_stage_binding(
        str(pipeline.get("id", "unknown")),
        stage,
        str(pipeline.get("permission_mode", "plan_only")),
    )
    toolproxy_allowed = ", ".join(f"`{item}`" for item in toolproxy_binding["allowed_actions"])
    toolproxy_blocked = ", ".join(f"`{item}`" for item in toolproxy_binding["blocked_actions"])
    content = f"""# NoemaForge Pipeline Context Packet

- task_id: `{task_id}`
- project_id: `{project_id}`
- pipeline_id: `{pipeline.get('id', 'unknown')}`
- stage: `{stage}`
- created_at: `{nowz()}`
- llm_mode: `switchable`
- max_active_llms: `1`
- permission_mode: `{pipeline.get('permission_mode', 'plan_only')}`
- suggested_role_or_team: `{role_hint}`
- toolproxy_policy_ref: `{toolproxy_binding['policy_ref']}`
- toolproxy_stage_scope: `{toolproxy_binding['scope']}`
- toolproxy_capability_token_required: `true`

## Operator request

{request.strip() or 'No free-text request supplied.'}

## Stage objective

Complete the `{stage}` stage and produce an auditable artifact. Do not assume another LLM is running. If another role/model must continue, write the handoff as markdown in this packet or in the stage output artifact.

## Lifecycle contract

Every task must pass through:

1. architecture clarification;
2. development or content production;
3. testing / fact checking;
4. integration testing / consistency review;
5. optimization attempt: speed, memory, operation count, complexity, UX;
6. final review and merge/publish plan.

## Expected deliverables

{deliverables}

## ToolProxy stage binding

This stage may request only its declared ToolProxy actions. Capability tokens must be issued for `{toolproxy_binding['scope']}` and tied to the current run/stage before sensitive tool calls are attempted.

- allowed_actions: {toolproxy_allowed}
- blocked_actions: {toolproxy_blocked}
- approval_required: `{str(toolproxy_binding['approval_required']).lower()}`
- sandbox_required: `{str(toolproxy_binding['sandbox_required']).lower()}`
- network_allowed: `false`

## Previous stage summary

{previous or 'This is the first packet or no previous summary exists yet.'}

## Required output

Write the next artifact into `outputs/` and register it with:

```bash
noemaforge pipeline artifact add <run_id> --stage {stage} --type <type> --path <path> --status draft
```

Then update `decisions.md` with:

- decision;
- reason;
- risk;
- next handoff note.
"""
    atomic_write_text(path, content)
    sidecar = path.with_suffix(".json")
    envelope = {
        "apiVersion": "noemaforge.pipeline.context/v1",
        "version": RUNTIME_VERSION,
        "task_id": task_id,
        "project_id": project_id,
        "pipeline_id": pipeline.get("id", "unknown"),
        "stage": stage,
        "created_at": nowz(),
        "llm_policy": {"mode": "switchable", "max_active_llms": 1},
        "permission_mode": pipeline.get("permission_mode", "plan_only"),
        "suggested_role_or_team": role_hint,
        "toolproxy_stage_binding": toolproxy_binding,
        "request": request.strip(),
        "previous_stage_summary": previous or "",
        "output_contract": {"artifact_dir": "outputs", "register_command": f"noemaforge pipeline artifact add <run_id> --stage {stage} --type <type> --path <path> --status draft"},
        "markdown_packet": str(path),
        "markdown_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }
    atomic_write_text(sidecar, json_dumps(envelope) + "\n")
    atomic_write_text(sidecar.with_suffix(sidecar.suffix + ".sha256"), hashlib.sha256(sidecar.read_bytes()).hexdigest() + "  " + sidecar.name + "\n")
    return path


def write_run_files(root: Path, run_dir: Path, pipeline: Dict[str, Any], team: Dict[str, Any], task_id: str, project_id: str, request: str) -> Tuple[List[str], str]:
    for d in ["context_packets", "outputs", "logs", "reviews", "graph_patches", "tests", "worktrees", "forensics"]:
        (run_dir / d).mkdir(parents=True, exist_ok=True)
    context_md = context_root(root)
    atomic_write_text(run_dir / "project_context_snapshot.md", context_md)
    atomic_write_text(run_dir / "toolproxy_stage_bindings.json", json_dumps(build_toolproxy_stage_bindings(pipeline)) + "\n")
    previous = None
    packet_paths: List[str] = []
    for stage in pipeline.get("stages", []):
        packet = write_stage_packet(run_dir, pipeline, team, task_id, project_id, stage, request, previous)
        packet_paths.append(str(packet))
        output_stub = run_dir / "outputs" / f"{safe_id(stage)}.md"
        if not output_stub.exists():
            atomic_write_text(output_stub, f"# {stage}\n\nStatus: pending\n\nDecision:\n\nRisk:\n\nNext handoff:\n")
        previous = f"Previous handoff packet prepared: `{packet.name}`."
    atomic_write_text(
        run_dir / "decisions.md",
        f"# Decisions for {run_dir.name}\n\n- Created: {nowz()}\n- Runtime invariant: one active LLM by default.\n",
    )
    atomic_write_text(
        run_dir / "README.md",
        f"# {run_dir.name}\n\nPipeline `{pipeline.get('id')}` prepared. Start from `context_packets/`.\n\n"
        "Useful commands:\n\n"
        f"```bash\nnoemaforge pipeline show {run_dir.name}\nnoemaforge pipeline next {run_dir.name}\nnoemaforge pipeline approve {run_dir.name}\nnoemaforge pipeline gate {run_dir.name}\n```\n",
    )
    return packet_paths, context_md


def register_artifact(conn: sqlite3.Connection, run_id: str, stage: str, artifact_type: str, path: Path, status: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    ts = nowz()
    artifact_id = safe_id(metadata.get("artifact_id") or f"art_{run_id}_{stage}_{artifact_type}_{path.stem}")[:180]
    rec = {
        "artifact_id": artifact_id,
        "run_id": run_id,
        "stage": stage,
        "artifact_type": artifact_type,
        "path": str(path),
        "status": status,
        "created_at": ts,
        "updated_at": ts,
        "metadata": metadata,
    }
    conn.execute(
        "INSERT OR REPLACE INTO artifacts(artifact_id,run_id,stage,artifact_type,path,status,created_at,updated_at,metadata) VALUES(?,?,?,?,?,?,?,?,?)",
        (artifact_id, run_id, stage, artifact_type, str(path), status, ts, ts, json_dumps(metadata, pretty=False)),
    )
    conn.commit()
    emit(conn, run_id, "artifact_registered", {k: v for k, v in rec.items() if k != "metadata"} | {"metadata": metadata})
    return rec


def create_run(args: argparse.Namespace) -> None:
    guard_degraded_mutation("pipeline run", getattr(args, "allow_degraded", False))
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    pipelines = load_pipeline_catalog(root)
    teams = load_team_catalog(root)
    pipeline_id = args.pipeline
    if pipeline_id not in pipelines:
        raise SystemExit(f"unknown pipeline: {pipeline_id}; available: {', '.join(sorted(pipelines))}")
    pipeline = dict(pipelines[pipeline_id])
    pipeline["id"] = pipeline_id
    team = teams.get(pipeline.get("team", ""), {"coordinator": "administrator", "roles": []})
    task_id = safe_id(args.task_id or f"{pipeline_id}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}")
    project_id = safe_id(args.project or pipeline.get("project_id", "noemaforge"))
    trace_id = str(getattr(args, "trace_id", "") or os.environ.get("NOEMAFORGE_TRACE_ID") or production_ai_contracts.new_trace_id("pipeline"))
    run_id = safe_id(args.run_id or f"run_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{pipeline_id}_{task_id}")
    run_dir = state / "runs" / run_id
    if run_dir.exists() and not args.allow_existing:
        raise SystemExit(f"run directory already exists: {run_dir}; pass --allow-existing or choose --run-id")
    request = args.request or ""
    packet_paths, _ = write_run_files(root, run_dir, pipeline, team, task_id, project_id, request)
    manifest = {
        "run_id": run_id,
        "trace_id": trace_id,
        "pipeline_id": pipeline_id,
        "task_id": task_id,
        "project_id": project_id,
        "created_at": nowz(),
        "updated_at": nowz(),
        "status": "planned" if args.dry_run else "ready_for_admin_approval",
        "current_stage": pipeline.get("stages", ["intake"])[0],
        "llm_policy": {"mode": "switchable", "max_active_llms": 1},
        "pipeline": pipeline,
        "team": team,
        "context_packet_pattern": "task_<task_id>_project_<project_id>_<stage>_context.md",
        "context_packets": packet_paths,
        "toolproxy_stage_bindings": build_toolproxy_stage_bindings(pipeline),
    }
    atomic_write_text(run_dir / "manifest.json", json_dumps(manifest))
    conn = db_connect(state)
    ts = nowz()
    conn.execute("INSERT OR REPLACE INTO runs VALUES(?,?,?,?,?,?,?,?,?,?,?)", (run_id, pipeline_id, task_id, project_id, manifest["status"], ts, ts, manifest["current_stage"], str(run_dir), request, json_dumps(manifest, pretty=False)))
    conn.commit()
    upsert_stage_states(conn, run_id, list(pipeline.get("stages", [])), str(manifest["current_stage"]), str(manifest["status"]))
    register_task_contexts(conn, run_id, packet_paths)
    emit(conn, run_id, "pipeline_created", {"trace_id": trace_id, "run_dir": str(run_dir), "dry_run": bool(args.dry_run), "packet_count": len(packet_paths), "typed_contexts": len(packet_paths)})
    conn.close()
    print(json_dumps({"ok": True, "trace_id": trace_id, "run_id": run_id, "run_dir": str(run_dir), "status": manifest["status"], "next": f"noemaforge pipeline approve {run_id}"}))


def catalog(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    pipelines = load_pipeline_catalog(root)
    if args.json:
        print(json_dumps(pipelines))
        return
    for pid, spec in sorted(pipelines.items()):
        stages = ",".join(spec.get("stages", []))
        print(f"{pid}\t{spec.get('description', '')}\tstages={stages}")


def list_runs(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    rows = conn.execute("SELECT run_id,pipeline_id,status,current_stage,updated_at FROM runs ORDER BY updated_at DESC LIMIT ?", (args.limit,)).fetchall()
    if args.json:
        print(json_dumps([dict(zip(["run_id", "pipeline_id", "status", "current_stage", "updated_at"], row)) for row in rows]))
        return
    if not rows:
        print("no pipeline runs yet")
        return
    for row in rows:
        print("\t".join(map(str, row)))


def show_run(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    data = get_run(conn, args.run_id)
    data["events"] = _event_rows(conn, args.run_id, limit=args.events)
    data["artifacts"] = _artifact_rows(conn, args.run_id)
    print(json_dumps(data))


def toolproxy_policy_cmd(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    run = get_run(conn, args.run_id)
    stage = args.stage or str(run.get("current_stage") or "")
    assert_stage(run, str(stage))
    manifest = run.get("manifest") or {}
    bindings = manifest.get("toolproxy_stage_bindings") if isinstance(manifest.get("toolproxy_stage_bindings"), dict) else {}
    binding = bindings.get(str(stage))
    if not isinstance(binding, dict):
        pipeline = manifest.get("pipeline") if isinstance(manifest.get("pipeline"), dict) else {}
        binding = build_toolproxy_stage_binding(str(run.get("pipeline_id") or pipeline.get("id") or "unknown"), str(stage), str(pipeline.get("permission_mode") or "plan_only"))
    print(json_dumps({"ok": True, "run_id": args.run_id, "stage": stage, "toolproxy_stage_binding": binding}))


def snapshot(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    out = Path(args.out or state / f"pipeline_snapshot_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    conn = db_connect(state)
    runs = [dict(zip(["run_id", "pipeline_id", "task_id", "project_id", "status", "created_at", "updated_at", "current_stage", "run_dir"], row)) for row in conn.execute("SELECT run_id,pipeline_id,task_id,project_id,status,created_at,updated_at,current_stage,run_dir FROM runs").fetchall()]
    events = [dict(zip(["run_id", "ts", "event_type", "payload"], row)) for row in conn.execute("SELECT run_id,ts,event_type,payload FROM events").fetchall()]
    artifacts = _all_artifact_rows(conn)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json_dumps({"created_at": nowz(), "runs": runs, "events": events, "artifacts": artifacts}), encoding="utf-8")
    print(str(out))


def assert_stage(run: Dict[str, Any], stage: str) -> None:
    stages = list(((run.get("manifest") or {}).get("pipeline") or {}).get("stages") or [])
    if stage not in stages:
        raise SystemExit(f"unknown stage for this run: {stage}; available: {', '.join(stages)}")


def advance_run(args: argparse.Namespace) -> None:
    guard_degraded_mutation("pipeline advance", getattr(args, "allow_degraded", False))
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    run = get_run(conn, args.run_id)
    stage = args.stage or run["current_stage"]
    if args.next:
        stage = next_stage_for(run["manifest"], str(run["current_stage"])) or str(run["current_stage"])
    assert_stage(run, str(stage))
    status = args.status or "in_progress"
    run = update_run(conn, run, status=status, stage=str(stage), note=args.note or "", event_type="pipeline_stage_updated")
    print(json_dumps({"ok": True, "run_id": args.run_id, "stage": run["current_stage"], "status": run["status"], "next_stage": next_stage_for(run["manifest"], str(run["current_stage"]))}))


def approve_run(args: argparse.Namespace) -> None:
    guard_degraded_mutation("pipeline approve", getattr(args, "allow_degraded", False))
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    run = get_run(conn, args.run_id)
    stage = args.stage or run["current_stage"]
    assert_stage(run, str(stage))
    note = args.note or "admin approved this stage/run for controlled execution"
    update_run(conn, run, status=args.status, stage=str(stage), note=note, event_type="pipeline_approved")
    print(json_dumps({"ok": True, "run_id": args.run_id, "status": args.status, "stage": stage, "next": f"noemaforge pipeline next {args.run_id}"}))


def pause_run(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    run = get_run(conn, args.run_id)
    stage = args.stage or run["current_stage"]
    assert_stage(run, str(stage))
    update_run(conn, run, status="paused", stage=str(stage), note=args.note or "paused by operator", event_type="pipeline_paused")
    print(json_dumps({"ok": True, "run_id": args.run_id, "status": "paused", "stage": stage}))


def resume_run(args: argparse.Namespace) -> None:
    guard_degraded_mutation("pipeline resume", getattr(args, "allow_degraded", False))
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    run = get_run(conn, args.run_id)
    stage = args.stage or run["current_stage"]
    assert_stage(run, str(stage))
    update_run(conn, run, status=args.status, stage=str(stage), note=args.note or "resumed by operator", event_type="pipeline_resumed")
    print(json_dumps({"ok": True, "run_id": args.run_id, "status": args.status, "stage": stage}))


def fail_or_cancel_run(args: argparse.Namespace, status: str, event_type: str) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    run = get_run(conn, args.run_id)
    stage = args.stage or run["current_stage"]
    assert_stage(run, str(stage))
    update_run(conn, run, status=status, stage=str(stage), note=args.reason or args.note or status, event_type=event_type)
    print(json_dumps({"ok": True, "run_id": args.run_id, "status": status, "stage": stage}))


def next_run(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    run = get_run(conn, args.run_id)
    manifest = run["manifest"]
    stage = str(run["current_stage"])
    next_stage = next_stage_for(manifest, stage)
    packet_name = f"task_{safe_id(str(run['task_id']))}_project_{safe_id(str(run['project_id']))}_{safe_id(stage)}_context.md"
    packet_path = str(Path(str(run["run_dir"])) / "context_packets" / packet_name)
    suggestions = []
    if run["status"] == "ready_for_admin_approval":
        suggestions.append(f"noemaforge pipeline approve {run['run_id']}")
    elif run["status"] in PAUSED_STATUSES:
        suggestions.append(f"noemaforge pipeline resume {run['run_id']}")
    elif next_stage:
        suggestions.append(f"noemaforge pipeline advance {run['run_id']} --next --status in_progress")
    else:
        suggestions.append(f"noemaforge pipeline advance {run['run_id']} --status completed --note 'pipeline complete' ")
    doc = {
        "ok": True,
        "run_id": run["run_id"],
        "status": run["status"],
        "current_stage": stage,
        "context_packet": packet_path,
        "next_stage": next_stage,
        "suggested_commands": suggestions,
        "artifact_command": f"noemaforge pipeline artifact add {run['run_id']} --stage {stage} --type note --path <path>",
    }
    print(json_dumps(doc))


def artifact_cmd(args: argparse.Namespace) -> None:
    if getattr(args, "artifact_action", "") == "add":
        guard_degraded_mutation("pipeline artifact add", getattr(args, "allow_degraded", False))
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    if args.artifact_action == "list":
        if args.run_id:
            get_run(conn, args.run_id)
            rows = _artifact_rows(conn, args.run_id)
        else:
            raw = conn.execute("SELECT artifact_id,run_id,stage,artifact_type,path,status,created_at,updated_at,metadata FROM artifacts ORDER BY updated_at DESC LIMIT ?", (args.limit,)).fetchall()
            rows = []
            for artifact_id, run_id, stage, artifact_type, path, status, created_at, updated_at, metadata in raw:
                rows.append({"artifact_id": artifact_id, "run_id": run_id, "stage": stage, "artifact_type": artifact_type, "path": path, "status": status, "created_at": created_at, "updated_at": updated_at, "metadata": json.loads(metadata or "{}")})
        print(json_dumps(rows))
        return
    if args.artifact_action == "add":
        run = get_run(conn, args.run_id)
        stage = args.stage or run["current_stage"]
        assert_stage(run, str(stage))
        path = Path(args.path)
        if not path.is_absolute():
            path = Path(str(run["run_dir"])) / path
        metadata: Dict[str, Any] = {}
        for item in args.meta or []:
            if "=" not in item:
                raise SystemExit(f"metadata must be key=value, got: {item}")
            k, v = item.split("=", 1)
            metadata[k] = v
        metadata.setdefault("exists", path.exists())
        metadata.setdefault("size_bytes", path.stat().st_size if path.exists() else 0)
        rec = register_artifact(conn, args.run_id, str(stage), args.type, path, args.status, metadata)
        print(json_dumps({"ok": True, "artifact": rec}))
        return
    raise SystemExit(f"unknown artifact action: {args.artifact_action}")


def worktree_cmd(args: argparse.Namespace) -> None:
    if getattr(args, "apply", False):
        guard_degraded_mutation("pipeline worktree create --apply", getattr(args, "allow_degraded", False))
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    run = get_run(conn, args.run_id)
    plan = build_evolution_worktree_plan(
        run,
        repo=args.repo or os.getcwd(),
        branch=args.branch or "",
        base=args.base,
        path=args.path or "",
        cwd=Path.cwd(),
    )
    if args.apply:
        if not shutil.which("git"):
            raise SystemExit("git not found")
        dest = Path(str(plan["path"]))
        cmd = list(plan["command"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(cmd, text=True, capture_output=True)
        plan["applied"] = completed.returncode == 0
        plan["stdout"] = completed.stdout
        plan["stderr"] = completed.stderr
        if completed.returncode != 0:
            print(json_dumps(plan))
            raise SystemExit(completed.returncode)
        register_artifact(conn, args.run_id, str(run["current_stage"]), "worktree", dest, "created", {"branch": plan["branch"], "repo": plan["repo"], "destination_root": plan["safety"]["destination_root"]})
        emit(conn, args.run_id, "worktree_created", {"repo": plan["repo"], "branch": plan["branch"], "path": str(dest), "destination_root": plan["safety"]["destination_root"]})
    else:
        emit(conn, args.run_id, "worktree_plan", {"repo": plan["repo"], "branch": plan["branch"], "path": plan["path"], "base": plan["base"], "destination_root": plan["safety"]["destination_root"]})
    print(json_dumps(plan))



def summary_run(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    run = get_run(conn, args.run_id)
    artifacts = _artifact_rows(conn, args.run_id)
    events = _event_rows(conn, args.run_id, limit=args.events)
    stages = list(((run.get("manifest") or {}).get("pipeline") or {}).get("stages") or [])
    current = str(run.get("current_stage") or "")
    idx = stages.index(current) + 1 if current in stages else 0
    doc = {
        "run_id": run["run_id"],
        "pipeline_id": run["pipeline_id"],
        "status": run["status"],
        "current_stage": current,
        "progress": {"stage_index": idx, "stage_count": len(stages)},
        "artifact_count": len(artifacts),
        "latest_events": events,
        "next_stage": next_stage_for(run["manifest"], current),
        "run_dir": run["run_dir"],
    }
    if args.json:
        print(json_dumps(doc))
        return
    print(f"{doc['pipeline_id']} / {doc['run_id']}")
    print(f"status: {doc['status']}  stage: {doc['current_stage']} ({idx}/{len(stages)})  artifacts: {len(artifacts)}")
    print(f"run_dir: {doc['run_dir']}")
    print(f"next: noemaforge pipeline next {doc['run_id']}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def export_run(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    run = get_run(conn, args.run_id)
    run_dir = Path(str(run["run_dir"]))
    if not run_dir.exists():
        raise SystemExit(f"run directory missing: {run_dir}")
    out = Path(args.out or state / "exports" / f"{args.run_id}.tar.gz")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:gz") as tar:
        tar.add(run_dir, arcname=run_dir.name)
    digest = sha256_file(out)
    checksum_path = out.with_suffix(out.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {out.name}\n", encoding="utf-8")
    emit(conn, args.run_id, "pipeline_exported", {"path": str(out), "sha256": digest, "checksum": str(checksum_path)})
    print(json_dumps({"ok": True, "run_id": args.run_id, "path": str(out), "sha256": digest, "checksum": str(checksum_path)}))

def patterns_cmd(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    catalog = load_pattern_catalog(root)
    patterns = list(catalog.get("patterns") or [])
    if args.family:
        patterns = [p for p in patterns if str(p.get("family") or "") == args.family]
    if args.use_case:
        needle = str(args.use_case).casefold()
        patterns = [p for p in patterns if needle in " ".join(map(str, p.get("noemaforge_use_cases") or [])).casefold() or needle in str(p.get("name") or "").casefold()]
    limit = max(1, int(args.limit or 80))
    view = patterns[:limit]
    doc = {
        "ok": True,
        "version": catalog.get("version", RUNTIME_VERSION),
        "total": len(catalog.get("patterns") or []),
        "returned": len(view),
        "family": args.family,
        "use_case": args.use_case,
        "patterns": view,
        "families": sorted({str(p.get("family")) for p in (catalog.get("patterns") or []) if p.get("family")}),
    }
    if args.json:
        print(json_dumps(doc))
        return
    print(f"pattern catalog: total={doc['total']} returned={doc['returned']}")
    for item in view:
        uses = ",".join(item.get("noemaforge_use_cases") or [])
        print(f"{item.get('id')}	{item.get('family')}	{item.get('name')}	{uses}")


def dashboard_state(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    rows = conn.execute("SELECT run_id,pipeline_id,task_id,project_id,status,created_at,updated_at,current_stage,run_dir FROM runs ORDER BY updated_at DESC").fetchall()
    runs = [_row_to_run(row) for row in rows]
    current = runs[0] if runs else {"pipeline_id": "evolution", "status": "catalog", "current_stage": "intake", "run_id": ""}
    wip = sum(1 for r in runs if str(r.get("status") or "").lower() not in FINISHED_STATUSES)
    pipelines = load_pipeline_catalog(root)
    patterns = load_pattern_catalog(root).get("patterns") or []
    personas = (load_persona_catalog(root).get("personas") or {})
    low_hanging = load_low_hanging_catalog(root).get("collections") or []
    persona_state = load_persona_state(Path(args.persona_state) if getattr(args, "persona_state", None) else DEFAULT_PERSONA_STATE)
    active_persona = persona_state.get("active") or {}
    active_role = active_persona.get("role_key") or "system.guard/surgeon"
    persona_doc = None
    if active_role in personas:
        persona_doc = {"role_key": active_role, **personas[active_role], **{k: v for k, v in active_persona.items() if v is not None}}
    current_run_id = str(current.get("run_id") or "")
    artifacts = _artifact_rows(conn, current_run_id) if current_run_id else []
    events = _event_rows(conn, current_run_id, limit=8) if current_run_id else []
    doc = {
        "generated_at": nowz(),
        "runtime": runtime_snapshot(),
        "persona": persona_doc,
        "current": {
            "run_id": current.get("run_id", ""),
            "pipeline_id": current.get("pipeline_id", "evolution"),
            "status": current.get("status", "catalog"),
            "current_stage": current.get("current_stage", "intake"),
        },
        "metrics": {
            "flow.wip": wip,
            "flow.backlog": max(0, len(runs) - wip),
            "flow.runs_total": len(runs),
            "pipeline.catalog_count": len(pipelines),
            "pipeline.pattern_count": len(patterns),
            "persona.count": len(personas),
            "low_hanging.collection_count": len(low_hanging),
            "artifact.count": len(artifacts),
            "llm.error_rate": 0.0,
            "llm.latency_ms.p95": None,
            "llm.policy_denies": 0,
            "sec.incidents.open": 0,
            "system.readiness_score": 100 if runtime_snapshot().get("ok") and not degraded_readonly_state().get("active") else 60,
            "system.degraded_readonly": bool(degraded_readonly_state().get("active")),
        },
        "pipelines": {pid: {"description": spec.get("description", ""), "stages": spec.get("stages", [])} for pid, spec in pipelines.items()},
        "artifacts": artifacts[:12],
        "events": events,
        "runs": runs[:20],
        "next_actions": [
            "noemaforge status --json",
            "noemaforge trixie-preflight --json --skip-modelstore",
            "noemaforge persona activate Бехтерев --reason operator_console",
            "noemaforge pipeline patterns --family n8n --limit 12",
            (f"noemaforge pipeline next {current.get('run_id')}" if current.get("run_id") else "noemaforge pipeline run public_mwp --request 'first local run'"),
        ],
    }
    out = Path(args.out) if args.out else None
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json_dumps(doc), encoding="utf-8")
        print(str(out))
    else:
        print(json_dumps(doc))


def _pipeline_stage_contract(stage: str) -> Dict[str, Any]:
    low = stage.lower()
    if any(k in low for k in ["test", "validation", "smoke", "fact_check"]):
        return {"requires": ["test_evidence", "result", "risk"], "artifact_types": ["test_report", "validation_report", "fact_check"]}
    if any(k in low for k in ["optimization", "performance", "budget"]):
        return {"requires": ["baseline", "change", "measurement"], "artifact_types": ["optimization_note", "perf_report"]}
    if any(k in low for k in ["review", "approval", "merge", "publish"]):
        return {"requires": ["decision", "risk", "next_handoff"], "artifact_types": ["review", "decision", "publish_plan"]}
    if any(k in low for k in ["research", "source", "inventory", "entity", "relation", "graph"]):
        return {"requires": ["sources", "provenance", "uncertainty"], "artifact_types": ["research_note", "graph_patch", "source_inventory"]}
    return {"requires": ["decision", "risk", "next_handoff"], "artifact_types": ["note", "stage_output"]}


def stage_output_quality(path: Path) -> Dict[str, Any]:
    text = read_text_if_exists(path, limit=16000)
    exists = path.exists()
    stripped = text.strip()
    placeholders = ["Status: pending", "Decision:\n\nRisk:", "Next handoff:\n"]
    has_placeholder = any(p in text for p in placeholders)
    has_decision = "decision" in text.casefold()
    has_risk = "risk" in text.casefold()
    has_handoff = "handoff" in text.casefold() or "next" in text.casefold()
    score = 0
    score += 20 if exists else 0
    score += 20 if bool(stripped) else 0
    score += 20 if has_decision else 0
    score += 20 if has_risk else 0
    score += 20 if has_handoff else 0
    if has_placeholder and len(stripped) < 260:
        score = min(score, 40)
    return {
        "path": str(path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
        "non_empty": bool(stripped),
        "looks_placeholder": has_placeholder and len(stripped) < 260,
        "has_decision": has_decision,
        "has_risk": has_risk,
        "has_handoff": has_handoff,
        "quality_score": score,
        "pending": has_placeholder and len(stripped) < 260,
    }


def repair_one_run(root: Path, conn: sqlite3.Connection, run: Dict[str, Any], dry_run: bool = True) -> Dict[str, Any]:
    manifest = dict(run.get("manifest") or {})
    pipelines = load_pipeline_catalog(root)
    pipeline = manifest.get("pipeline") or pipelines.get(run.get("pipeline_id"), {})
    if pipeline and "id" not in pipeline:
        pipeline = {**pipeline, "id": run.get("pipeline_id")}
    teams = load_team_catalog(root)
    team = manifest.get("team") or teams.get(pipeline.get("team", ""), {"coordinator": "administrator", "roles": []})
    run_dir = Path(str(run["run_dir"]))
    actions: List[Dict[str, Any]] = []
    def act(kind: str, path: Path, text: str = "") -> None:
        rec = {"action": kind, "path": str(path), "applied": False}
        if not dry_run:
            if kind == "mkdir":
                path.mkdir(parents=True, exist_ok=True)
            elif kind == "write" and text:
                atomic_write_text(path, text)
            rec["applied"] = True
        actions.append(rec)
    for name in ["context_packets", "outputs", "logs", "reviews", "graph_patches", "tests", "worktrees", "forensics"]:
        path = run_dir / name
        if not path.exists():
            act("mkdir", path)
    stages = list(pipeline.get("stages") or [])
    packet_paths: List[str] = []
    previous = None
    for stage in stages:
        packet = run_dir / "context_packets" / f"task_{safe_id(str(run['task_id']))}_project_{safe_id(str(run['project_id']))}_{safe_id(stage)}_context.md"
        if not packet.exists():
            text = write_stage_packet.__globals__["write_stage_packet"]
            # Avoid writing in dry-run by recreating the content in a temp-free path only when applying.
            if dry_run:
                actions.append({"action": "write", "path": str(packet), "applied": False})
            else:
                write_stage_packet(run_dir, pipeline, team, str(run["task_id"]), str(run["project_id"]), stage, str(run.get("request") or ""), previous)
                actions.append({"action": "write", "path": str(packet), "applied": True})
        packet_paths.append(str(packet))
        output = run_dir / "outputs" / f"{safe_id(stage)}.md"
        if not output.exists():
            act("write", output, f"# {stage}\n\nStatus: pending\n\nDecision:\n\nRisk:\n\nNext handoff:\n")
        previous = f"Previous handoff packet prepared: `{packet.name}`."
    if not (run_dir / "decisions.md").exists():
        act("write", run_dir / "decisions.md", f"# Decisions for {run_dir.name}\n\n- Repaired: {nowz()}\n- Runtime invariant: one active LLM by default.\n")
    if not (run_dir / "manifest.json").exists() and manifest:
        act("write", run_dir / "manifest.json", json_dumps(manifest))
    if not dry_run and packet_paths:
        manifest["context_packets"] = packet_paths
        manifest["updated_at"] = nowz()
        conn.execute("UPDATE runs SET manifest=?,updated_at=? WHERE run_id=?", (json_dumps(manifest, pretty=False), manifest["updated_at"], run["run_id"]))
        conn.commit()
        emit(conn, str(run["run_id"]), "pipeline_repaired", {"action_count": len(actions)})
    return {"run_id": run["run_id"], "run_dir": str(run_dir), "dry_run": dry_run, "actions": actions}


def repair_run_cmd(args: argparse.Namespace) -> None:
    if not getattr(args, "dry_run", False):
        guard_degraded_mutation("pipeline repair", getattr(args, "allow_degraded", False))
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    targets: List[Dict[str, Any]] = []
    if args.all:
        rows = conn.execute("SELECT run_id FROM runs ORDER BY updated_at DESC LIMIT ?", (args.limit,)).fetchall()
        targets = [get_run(conn, row[0]) for row in rows]
    else:
        targets = [get_run(conn, args.run_id)]
    results = [repair_one_run(root, conn, run, dry_run=args.dry_run) for run in targets]
    print(json_dumps({"ok": True, "dry_run": args.dry_run, "run_count": len(results), "results": results}))


def gate_run_cmd(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    run = get_run(conn, args.run_id)
    run_dir = Path(str(run["run_dir"]))
    manifest = run.get("manifest") or {}
    stages = list(((manifest.get("pipeline") or {}).get("stages") or []))
    current = args.stage or str(run.get("current_stage") or (stages[0] if stages else ""))
    assert_stage(run, current)
    artifacts = _artifact_rows(conn, args.run_id)
    by_stage: Dict[str, List[Dict[str, Any]]] = {}
    for art in artifacts:
        by_stage.setdefault(str(art.get("stage")), []).append(art)
    checks = []
    for stage in stages:
        output = run_dir / "outputs" / f"{safe_id(stage)}.md"
        quality = stage_output_quality(output)
        packet = run_dir / "context_packets" / f"task_{safe_id(str(run['task_id']))}_project_{safe_id(str(run['project_id']))}_{safe_id(stage)}_context.md"
        stage_ok = packet.exists() and quality["exists"] and (not quality["looks_placeholder"] or stage != current)
        checks.append({
            "stage": stage,
            "current": stage == current,
            "packet_exists": packet.exists(),
            "output": quality,
            "artifact_count": len(by_stage.get(stage, [])),
            "contract": _pipeline_stage_contract(stage),
            "ok": stage_ok,
        })
    current_check = next((c for c in checks if c["stage"] == current), None)
    warnings = []
    if current_check and current_check["output"]["looks_placeholder"]:
        warnings.append(f"current stage {current} output still looks like a placeholder")
    if current_check and current_check["artifact_count"] == 0:
        warnings.append(f"current stage {current} has no registered artifact yet")
    ok = all(c["packet_exists"] for c in checks) and all(c["output"]["exists"] for c in checks)
    ready = bool(current_check and not current_check["output"]["looks_placeholder"] and current_check["artifact_count"] > 0)
    doc = {"ok": ok and (ready or not args.strict), "run_id": args.run_id, "stage": current, "ready_to_advance": ready, "warnings": warnings, "checks": checks}
    print(json_dumps(doc))
    if args.strict and not doc["ok"]:
        raise SystemExit(1)


def readiness_cmd(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    problems: List[str] = []
    warnings: List[str] = []
    runtime = runtime_snapshot()
    if not runtime["ok"]:
        problems.append(f"runtime invariant violated: active_llms={runtime['active_llms']} > 1")
    pipelines = load_pipeline_catalog(root)
    teams = load_team_catalog(root)
    patterns = load_pattern_catalog(root).get("patterns") or []
    personas = load_persona_catalog(root).get("personas") or {}
    if not pipelines:
        problems.append("pipeline catalog missing")
    if not teams:
        problems.append("team catalog missing")
    if len(patterns) < 100:
        warnings.append("pattern catalog is unexpectedly small")
    if len(personas) < 2:
        warnings.append("persona catalog is unexpectedly small")
    rows = conn.execute("SELECT run_id,status,current_stage,updated_at,run_dir FROM runs ORDER BY updated_at DESC LIMIT 8").fetchall()
    wip = 0
    stale = []
    for run_id, status, stage, updated_at, run_dir in rows:
        if str(status).lower() not in FINISHED_STATUSES:
            wip += 1
        if not Path(run_dir).exists():
            stale.append(run_id)
    if stale:
        warnings.append(f"runs with missing run_dir: {', '.join(stale[:5])}")
    score = 100
    score -= 30 if problems else 0
    score -= min(20, len(warnings) * 5)
    score -= 10 if wip > 8 else 0
    doc = {
        "ok": not problems,
        "version": RUNTIME_VERSION,
        "readiness_score": max(0, score),
        "problems": problems,
        "warnings": warnings,
        "runtime": runtime,
        "catalogs": {"pipelines": len(pipelines), "teams": len(teams), "patterns": len(patterns), "personas": len(personas)},
        "state": {"path": str(state), "latest_runs": len(rows), "wip": wip},
        "next": "noemaforge pipeline doctor" if not problems else "noemaforge pipeline validate",
    }
    print(json_dumps(doc))
    if problems:
        raise SystemExit(1)


def _guess_template_family(path: Path, raw: str, data: Any) -> str:
    name = path.name.lower()
    if "n8n" in name or (isinstance(data, dict) and "nodes" in data and "connections" in data):
        return "n8n"
    if "github" in name or ".github" in str(path) or "on:" in raw[:800] or "jobs:" in raw[:800]:
        return "github_actions"
    if "airflow" in name or "dag" in raw[:1200].lower():
        return "airflow"
    if "temporal" in name or "workflow" in raw[:1200].lower():
        return "temporal"
    return "generic"


def template_import_cmd(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"template source not found: {source}")
    raw = source.read_text(encoding="utf-8", errors="replace")
    data: Any = {}
    try:
        data = parse_jsonish_text(raw)
    except Exception:
        data = {}
    family = args.family or _guess_template_family(source, raw, data)
    base = safe_id(args.pipeline_id or source.stem)
    nodes: List[str] = []
    if isinstance(data, dict):
        if isinstance(data.get("nodes"), list):
            nodes = [safe_id(str(n.get("name") or n.get("type") or f"node_{i}")) for i, n in enumerate(data.get("nodes") or [], 1)]
        elif isinstance(data.get("jobs"), dict):
            nodes = [safe_id(k) for k in data["jobs"].keys()]
        elif isinstance(data.get("steps"), list):
            nodes = [safe_id(str(x.get("name") or x.get("id") or f"step_{i}")) for i, x in enumerate(data["steps"], 1)]
    if not nodes:
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("-") and len(nodes) < 12:
                nodes.append(safe_id(stripped.strip("- :")[:40]))
        if not nodes:
            nodes = ["intake", "execute", "review"]
    stages = ["intake"] + [n for n in nodes[:10] if n and n != "intake"] + ["admin_review"]
    # de-duplicate preserving order
    seen: set[str] = set(); stages = [x for x in stages if not (x in seen or seen.add(x))]
    pipeline_spec = {
        "description": f"Imported {family} template from {source.name}; review before enabling.",
        "project_id": f"noemaforge_imported_{base}",
        "stages": stages,
        "team": "automation_patterns_team",
        "permission_mode": "plan_only",
        "llm_policy": {"mode": "switchable", "max_active_llms": 1},
        "deliverables": ["template_inventory", "mapping_notes", "operator_review"],
        "source_template": {"path": str(source), "family": family, "imported_at": nowz()},
    }
    doc = {"ok": True, "pipeline_id": base, "family": family, "stage_count": len(stages), "pipeline": pipeline_spec}
    if args.out:
        out = Path(args.out)
        atomic_write_text(out, json_dumps({base: pipeline_spec}))
        doc["out"] = str(out)
    print(json_dumps(doc))


def validate(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    pipelines = load_pipeline_catalog(root)
    teams = load_team_catalog(root)
    pattern_catalog = load_pattern_catalog(root)
    persona_catalog = load_persona_catalog(root)
    low_hanging = load_low_hanging_catalog(root)
    selftests = load_selftest_catalog(root)
    problems: List[str] = []
    warnings: List[str] = []
    for pid, spec in pipelines.items():
        stages = spec.get("stages")
        if not stages or not isinstance(stages, list):
            problems.append(f"pipeline {pid}: no stages")
        elif len(set(stages)) != len(stages):
            problems.append(f"pipeline {pid}: duplicate stages")
        team_id = spec.get("team")
        if team_id and team_id not in teams:
            problems.append(f"pipeline {pid}: unknown team {team_id}")
        pol = spec.get("llm_policy") or {}
        if pol.get("mode") != "switchable" or int(pol.get("max_active_llms") or 0) != 1:
            problems.append(f"pipeline {pid}: llm_policy must be switchable/max_active_llms=1")
        if "development" in (stages or []) and "architecture_clarification" not in (stages or []) and pid == "evolution":
            problems.append("evolution pipeline must include architecture_clarification before development")
    patterns = pattern_catalog.get("patterns") or []
    if not patterns:
        problems.append("pattern catalog is empty or missing")
    for item in patterns:
        if not item.get("id") or not item.get("family"):
            problems.append("pattern catalog: pattern with missing id/family")
        mapping = item.get("noemaforge_mapping", {})
        invariant = mapping.get("invariant", mapping)
        if invariant.get("max_active_llms") != 1:
            problems.append(f"pattern {item.get('id')}: invariant max_active_llms must be 1")
    personas = persona_catalog.get("personas") or {}
    if not personas:
        problems.append("persona catalog is empty or missing")
    seen_codenames: set[str] = set()
    for role, spec in personas.items():
        codename = str(spec.get("codename") or "").strip()
        if not codename:
            problems.append(f"persona {role}: missing codename")
        if codename in seen_codenames:
            problems.append(f"persona catalog: duplicate codename {codename}")
        seen_codenames.add(codename)
        if (spec.get("safety") or {}).get("max_active_llms") != 1:
            problems.append(f"persona {role}: max_active_llms must be 1")
        portrait = spec.get("portrait")
        if not portrait or not (root / portrait).exists():
            problems.append(f"persona {role}: missing portrait {portrait}")
    if personas.get("system.guard/surgeon", {}).get("codename") != "Бехтерев":
        problems.append("surgeon persona codename must be Бехтерев")
    if personas.get("system.guard/scary", {}).get("codename") != "Гармр":
        problems.append("Scary persona codename must be Гармр")
    collections = low_hanging.get("collections") or []
    if len(collections) < 2:
        warnings.append("expected at least two low-hanging-fruit collections")
    for collection in collections:
        pipeline_id = collection.get("pipeline")
        if pipeline_id and pipeline_id not in pipelines:
            problems.append(f"low-hanging collection {collection.get('id')}: missing pipeline {pipeline_id}")
        for item in collection.get("items") or []:
            if not isinstance(item, dict) or not item.get("id") or not item.get("action"):
                problems.append(f"low-hanging collection {collection.get('id')}: malformed item")
    team_member_policy = load_json_or_default(root / "configs" / "team-member-policy.json", {})
    member_cells = team_member_policy.get("member_cells") or {}
    if int((team_member_policy.get("invariant") or {}).get("max_active_llms") or 0) != 1:
        problems.append("team-member-policy: max_active_llms must be 1")
    for required_member in ["developer", "qa", "code_analyser_visualiser"]:
        if required_member not in member_cells:
            problems.append(f"team-member-policy: missing {required_member}")
    selftest_cases = selftests.get("cases") or []
    selftest_ids = {str(c.get("id")) for c in selftest_cases if isinstance(c, dict)}
    if len(selftest_ids) != len(selftest_cases):
        problems.append("selftest catalog: duplicate or malformed case ids")
    for suite, ids in (selftests.get("suites") or {}).items():
        for cid in ids:
            if cid not in selftest_ids:
                problems.append(f"selftest suite {suite}: missing case {cid}")
    db_connect(state)
    result = {
        "ok": not problems,
        "pipeline_count": len(pipelines),
        "team_count": len(teams),
        "pattern_count": len(patterns),
        "persona_count": len(personas),
        "low_hanging_collection_count": len(collections),
        "selftest_case_count": len(selftest_cases),
        "member_cell_count": len(member_cells),
        "state": str(state),
        "warnings": warnings,
        "problems": problems,
    }
    print(json_dumps(result))
    if problems:
        raise SystemExit(1)


def doctor(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    pipelines = load_pipeline_catalog(root)
    teams = load_team_catalog(root)
    conn = db_connect(state)
    problems: List[str] = []
    warnings: List[str] = []
    target_run_id = getattr(args, "run_id", None)

    if active_llm_count() > 1:
        problems.append("more than one active LLM backend socket visible")
    for pid, spec in pipelines.items():
        if spec.get("team") not in teams:
            problems.append(f"pipeline {pid} references missing team {spec.get('team')}")
        if (spec.get("llm_policy") or {}).get("max_active_llms") != 1:
            problems.append(f"pipeline {pid} violates switchable LLM invariant")

    run_summary: Optional[Dict[str, Any]] = None
    latest = None
    if target_run_id:
        run = get_run(conn, target_run_id)
        manifest = run.get("manifest") or {}
        run_dir = Path(str(run["run_dir"]))
        stages = list(((manifest.get("pipeline") or {}).get("stages") or []))
        for stage in stages:
            packet_matches = list(run_dir.glob(f"context_packets/*_{safe_id(stage)}_context.md"))
            output_path = run_dir / "outputs" / f"{safe_id(stage)}.md"
            if not packet_matches:
                warnings.append(f"run {target_run_id}: missing context packet for stage {stage}")
            if not output_path.exists():
                warnings.append(f"run {target_run_id}: missing output stub for stage {stage}")
        if run["status"] == "ready_for_admin_approval":
            warnings.append(f"run {target_run_id} is waiting for: noemaforge pipeline approve {target_run_id}")
        run_summary = {
            "run_id": target_run_id,
            "pipeline_id": run.get("pipeline_id"),
            "status": run.get("status"),
            "current_stage": run.get("current_stage"),
            "run_dir": str(run_dir),
            "stage_count": len(stages),
        }
        latest = (target_run_id, run.get("status"), run.get("current_stage"), str(run_dir))
    else:
        latest = conn.execute("SELECT run_id,status,current_stage,run_dir FROM runs ORDER BY updated_at DESC LIMIT 1").fetchone()
        if latest:
            run_id, status, stage, run_dir = latest
            if not list(Path(run_dir).glob(f"context_packets/*_{safe_id(stage)}_context.md")):
                warnings.append(f"latest run {run_id} has no context packet for stage {stage}")
            if status == "ready_for_admin_approval":
                warnings.append(f"latest run {run_id} is waiting for: noemaforge pipeline approve {run_id}")

    if problems:
        next_action = "noemaforge pipeline validate"
    elif latest:
        next_action = f"noemaforge pipeline next {latest[0]}"
    else:
        next_action = "noemaforge pipeline run public_mwp --request '<first local run>'"

    result = {
        "ok": not problems,
        "warnings": warnings,
        "problems": problems,
        "run": run_summary,
        "next_safe_action": next_action,
        "runtime": runtime_snapshot(),
        "catalogs": {
            "pipelines": len(pipelines),
            "teams": len(teams),
            "patterns": len(load_pattern_catalog(root).get("patterns") or []),
            "personas": len((load_persona_catalog(root).get("personas") or {})),
            "low_hanging_collections": len(load_low_hanging_catalog(root).get("collections") or []),
        },
    }
    print(json_dumps(result))
    if problems:
        raise SystemExit(1)




def _stage_paths(run: Dict[str, Any], stage: str) -> Dict[str, Path]:
    run_dir = Path(str(run["run_dir"]))
    packets = list(run_dir.glob(f"context_packets/*_{safe_id(stage)}_context.md"))
    return {
        "run_dir": run_dir,
        "packet": packets[0] if packets else run_dir / "context_packets" / f"missing_{safe_id(stage)}_context.md",
        "output": run_dir / "outputs" / f"{safe_id(stage)}.md",
    }


def validate_stage_artifacts(run: Dict[str, Any], artifacts: List[Dict[str, Any]], stage: str) -> Dict[str, Any]:
    """Validate one pipeline stage using only local run artifacts and sidecars."""
    paths = _stage_paths(run, stage)
    packet_text = read_text_if_exists(paths["packet"], limit=50000)
    output_quality = stage_output_quality(paths["output"])
    contract = _pipeline_stage_contract(stage)
    stage_artifacts = [art for art in artifacts if str(art.get("stage") or "") == stage]
    contract_artifacts = [
        art
        for art in stage_artifacts
        if str(art.get("artifact_type") or "") in set(contract.get("artifact_types") or [])
    ]
    sidecar = paths["packet"].with_suffix(".json")
    checksum = sidecar.with_suffix(sidecar.suffix + ".sha256")
    sidecar_ok = False
    sidecar_problem = ""
    sidecar_envelope: Dict[str, Any] = {}
    if sidecar.exists():
        try:
            sidecar_envelope = json.loads(sidecar.read_text(encoding="utf-8", errors="replace"))
            required = ["apiVersion", "task_id", "project_id", "pipeline_id", "stage", "llm_policy", "output_contract"]
            missing = [key for key in required if key not in sidecar_envelope]
            if missing:
                sidecar_problem = f"typed sidecar missing fields: {missing}"
            elif sidecar_envelope.get("stage") != stage:
                sidecar_problem = f"typed sidecar stage mismatch: {sidecar_envelope.get('stage')} != {stage}"
            else:
                sidecar_ok = True
        except Exception as exc:
            sidecar_problem = f"typed sidecar parse error: {exc}"
    else:
        sidecar_problem = "missing typed context sidecar"
    checksum_ok = False
    if sidecar.exists() and checksum.exists():
        expected = checksum.read_text(encoding="utf-8", errors="replace").split()[0]
        actual = hashlib.sha256(sidecar.read_bytes()).hexdigest()
        checksum_ok = expected == actual
        if not checksum_ok:
            sidecar_ok = False
            sidecar_problem = "typed sidecar checksum mismatch"
    elif sidecar.exists():
        sidecar_problem = sidecar_problem or "missing typed sidecar checksum"
    binding = sidecar_envelope.get("toolproxy_stage_binding") if isinstance(sidecar_envelope.get("toolproxy_stage_binding"), dict) else {}
    manifest_bindings = (run.get("manifest") or {}).get("toolproxy_stage_bindings")
    manifest_binding = manifest_bindings.get(stage) if isinstance(manifest_bindings, dict) and isinstance(manifest_bindings.get(stage), dict) else {}
    smoke_cases = [
        {"id": "context_packet_present", "ok": paths["packet"].exists(), "detail": str(paths["packet"])},
        {"id": "typed_sidecar_valid", "ok": sidecar_ok, "detail": sidecar_problem or str(sidecar)},
        {"id": "typed_sidecar_checksum", "ok": checksum_ok, "detail": str(checksum)},
        {"id": "output_non_placeholder", "ok": output_quality["exists"] and not output_quality["looks_placeholder"], "detail": str(paths["output"])},
        {"id": "contract_artifact_registered", "ok": bool(contract_artifacts), "detail": f"{len(contract_artifacts)} matching artifacts"},
        {"id": "toolproxy_binding_present", "ok": bool(binding) and bool(manifest_binding), "detail": str(binding.get("scope") or "")},
        {"id": "no_live_host_required", "ok": True, "detail": "offline filesystem and SQLite checks only"},
        {"id": "no_llm_autostart", "ok": True, "detail": "validator does not call model or ToolProxy sockets"},
    ]
    problems = [case["id"] for case in smoke_cases if not case["ok"] and case["id"] not in {"output_non_placeholder", "contract_artifact_registered"}]
    warnings = [case["id"] for case in smoke_cases if not case["ok"] and case["id"] in {"output_non_placeholder", "contract_artifact_registered"}]
    ready = output_quality["exists"] and not output_quality["looks_placeholder"] and bool(contract_artifacts)
    return {
        "stage": stage,
        "packet": str(paths["packet"]),
        "packet_exists": paths["packet"].exists(),
        "packet_bytes": len(packet_text.encode("utf-8")),
        "typed_context_sidecar": str(sidecar),
        "typed_context_sidecar_exists": sidecar.exists(),
        "typed_context_sidecar_ok": sidecar_ok,
        "typed_context_sidecar_checksum_ok": checksum_ok,
        "typed_context_sidecar_problem": sidecar_problem,
        "output": output_quality,
        "stage_contract": contract,
        "artifact_count": len(stage_artifacts),
        "contract_artifact_count": len(contract_artifacts),
        "toolproxy_stage_binding": binding,
        "manifest_toolproxy_stage_binding": manifest_binding,
        "smoke_cases": smoke_cases,
        "ready_to_advance": ready,
        "warnings": warnings,
        "problems": problems,
        "ok": not problems,
    }


def stage_validate_cmd(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    run = get_run(conn, args.run_id)
    manifest = run.get("manifest") or {}
    stages = list(((manifest.get("pipeline") or {}).get("stages") or []))
    selected = [args.stage] if args.stage else stages
    for stage in selected:
        assert_stage(run, str(stage))
    artifacts = _artifact_rows(conn, args.run_id)
    reports = [validate_stage_artifacts(run, artifacts, str(stage)) for stage in selected]
    strict_ready_failures = [report["stage"] for report in reports if not report["ready_to_advance"]]
    problems = [f"{report['stage']}:{item}" for report in reports for item in report.get("problems", [])]
    warnings = [f"{report['stage']}:{item}" for report in reports for item in report.get("warnings", [])]
    result = {
        "ok": not problems and (not args.strict or not strict_ready_failures),
        "run_id": args.run_id,
        "stage_count": len(reports),
        "strict_ready_failures": strict_ready_failures,
        "warnings": warnings,
        "problems": problems,
        "stages": reports,
        "offline_only": True,
        "no_llm_autostart": True,
    }
    conn.close()
    print(json_dumps(result))
    if not result["ok"]:
        raise SystemExit(1)


def stage_smoke_cmd(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    with tempfile.TemporaryDirectory(prefix="noemaforge_stage_smoke_") as raw:
        state = Path(raw) / "state"
        run_id = safe_id(args.run_id or "run_stage_validator_smoke")
        pipeline = args.pipeline or "public_mwp"
        create_args = argparse.Namespace(
            root=str(root),
            state=str(state),
            pipeline=pipeline,
            task_id="stage_validator_smoke",
            project="noemaforge",
            request="offline stage validator smoke",
            dry_run=False,
            run_id=run_id,
            trace_id="trace:pipeline:stage-validator-smoke",
            allow_existing=False,
            allow_degraded=False,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            create_run(create_args)
        conn = db_connect(state)
        run = get_run(conn, run_id)
        stage = args.stage or str(run.get("current_stage") or "orient")
        assert_stage(run, stage)
        unready = validate_stage_artifacts(run, _artifact_rows(conn, run_id), stage)
        output = Path(str(run["run_dir"])) / "outputs" / f"{safe_id(stage)}.md"
        atomic_write_text(output, f"# {stage}\n\nDecision: smoke pass.\n\nRisk: low.\n\nNext handoff: continue.\n\nEvidence: offline stage validator smoke.\n")
        register_artifact(conn, run_id, stage, (_pipeline_stage_contract(stage)["artifact_types"][0]), output, "draft", {"smoke": True})
        ready = validate_stage_artifacts(run, _artifact_rows(conn, run_id), stage)
        result = {
            "ok": bool((not unready["ready_to_advance"]) and ready["ready_to_advance"] and ready["ok"]),
            "pipeline_id": pipeline,
            "stage": stage,
            "state_dir": str(state),
            "smoke_cases": [
                {"id": "unready_stage_is_not_advanceable", "ok": not unready["ready_to_advance"]},
                {"id": "ready_stage_is_advanceable", "ok": ready["ready_to_advance"]},
                {"id": "typed_sidecar_smoke_valid", "ok": ready["typed_context_sidecar_ok"]},
                {"id": "contract_artifact_smoke_registered", "ok": ready["contract_artifact_count"] == 1},
                {"id": "offline_only", "ok": True},
            ],
            "unready": unready,
            "ready": ready,
        }
        conn.close()
        print(json_dumps(result))
        if not result["ok"]:
            raise SystemExit(1)


def context_lint_cmd(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    run = get_run(conn, args.run_id)
    manifest = run.get("manifest") or {}
    stages = list(((manifest.get("pipeline") or {}).get("stages") or []))
    required_packet_markers = ["## Operator request", "## Stage objective", "## Lifecycle contract", "## Required output"]
    required_output_markers = ["Decision:", "Risk:", "Next handoff:"]
    stage_reports: List[Dict[str, Any]] = []
    problems: List[str] = []
    warnings: List[str] = []
    for stage in stages:
        paths = _stage_paths(run, stage)
        packet_text = read_text_if_exists(paths["packet"], limit=50000)
        output_text = read_text_if_exists(paths["output"], limit=50000)
        packet_missing = [m for m in required_packet_markers if m not in packet_text]
        output_missing = [m for m in required_output_markers if m not in output_text]
        sidecar = paths["packet"].with_suffix(".json")
        sidecar_checksum = sidecar.with_suffix(sidecar.suffix + ".sha256")
        sidecar_ok = False
        sidecar_problem = ""
        if sidecar.exists():
            try:
                envelope = json.loads(sidecar.read_text(encoding="utf-8", errors="replace"))
                sidecar_ok = all(envelope.get(k) for k in ["apiVersion", "task_id", "project_id", "pipeline_id", "stage", "llm_policy", "output_contract"])
                if envelope.get("stage") != stage:
                    sidecar_problem = f"sidecar stage mismatch: {envelope.get('stage')} != {stage}"
            except Exception as exc:
                sidecar_problem = f"sidecar parse error: {exc}"
        else:
            sidecar_problem = "missing typed context sidecar"
        if sidecar_checksum.exists() and sidecar.exists():
            expected = sidecar_checksum.read_text(encoding="utf-8", errors="replace").split()[0]
            actual = hashlib.sha256(sidecar.read_bytes()).hexdigest()
            if expected != actual:
                sidecar_problem = "typed sidecar checksum mismatch"
                sidecar_ok = False
        if not paths["packet"].exists():
            problems.append(f"{stage}: missing context packet")
        elif packet_missing:
            warnings.append(f"{stage}: packet missing markers {packet_missing}")
        if sidecar_problem:
            (problems if args.strict else warnings).append(f"{stage}: {sidecar_problem}")
        if not paths["output"].exists():
            problems.append(f"{stage}: missing output stub")
        elif output_missing:
            warnings.append(f"{stage}: output missing markers {output_missing}")
        stage_reports.append({
            "stage": stage,
            "packet": str(paths["packet"]),
            "packet_exists": paths["packet"].exists(),
            "packet_bytes": len(packet_text.encode("utf-8")),
            "packet_missing_markers": packet_missing,
            "typed_context_sidecar": str(sidecar),
            "typed_context_sidecar_exists": sidecar.exists(),
            "typed_context_sidecar_ok": sidecar_ok and not sidecar_problem,
            "typed_context_sidecar_problem": sidecar_problem,
            "output": str(paths["output"]),
            "output_exists": paths["output"].exists(),
            "output_quality": stage_output_quality(paths["output"]),
            "output_missing_markers": output_missing,
        })
    result = {
        "ok": not problems,
        "run_id": args.run_id,
        "stage_count": len(stages),
        "warnings": warnings,
        "problems": problems,
        "stages": stage_reports,
    }
    print(json_dumps(result))
    if problems and args.strict:
        raise SystemExit(1)


def compact_run_cmd(args: argparse.Namespace) -> None:
    if getattr(args, "register", False):
        guard_degraded_mutation("pipeline compact --register", getattr(args, "allow_degraded", False))
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    run = get_run(conn, args.run_id)
    artifacts = _artifact_rows(conn, args.run_id)
    events = _event_rows(conn, args.run_id, limit=20)
    manifest = run.get("manifest") or {}
    run_dir = Path(str(run["run_dir"]))
    stages = list(((manifest.get("pipeline") or {}).get("stages") or []))
    lines = [
        "# NoemaForge Compact Run Context",
        "",
        f"- run_id: `{args.run_id}`",
        f"- pipeline_id: `{run.get('pipeline_id')}`",
        f"- status: `{run.get('status')}`",
        f"- current_stage: `{run.get('current_stage')}`",
        f"- generated_at: `{nowz()}`",
        "- invariant: `switchable LLM / max_active_llms=1`",
        "",
        "## Operator request",
        "",
        str(run.get("request") or ""),
        "",
        "## Stage map",
        "",
    ]
    current = str(run.get("current_stage") or "")
    for stage in stages:
        marker = "→" if stage == current else " "
        quality = stage_output_quality(run_dir / "outputs" / f"{safe_id(stage)}.md")
        lines.append(f"- {marker} `{stage}` quality={quality.get('quality_score', 0)} pending={quality.get('pending')}")
    lines += ["", "## Registered artifacts", ""]
    if artifacts:
        for art in artifacts[:80]:
            lines.append(f"- `{art['stage']}` `{art['artifact_type']}` `{art['status']}` — {art['path']}")
    else:
        lines.append("- none registered yet")
    lines += ["", "## Recent events", ""]
    for ev in events[-12:]:
        lines.append(f"- `{ev['ts']}` `{ev['event_type']}`")
    lines += ["", "## Next safe command", "", f"```bash\nnoemaforge pipeline next {args.run_id}\n```", ""]
    out = Path(args.out) if args.out else run_dir / "context_compact.md"
    atomic_write_text(out, "\n".join(lines))
    if args.register:
        register_artifact(conn, args.run_id, str(run.get("current_stage") or "summary"), "compact_context", out, "ready", {"source": "pipeline compact", "version": RUNTIME_VERSION})
    print(json_dumps({"ok": True, "run_id": args.run_id, "out": str(out), "registered": bool(args.register)}))


def queue_cmd(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    statuses = ACTIVE_STATUSES | PAUSED_STATUSES
    rows = conn.execute(
        "SELECT run_id,pipeline_id,task_id,project_id,status,created_at,updated_at,current_stage,run_dir FROM runs ORDER BY updated_at DESC LIMIT ?",
        (int(args.limit),),
    ).fetchall()
    items: List[Dict[str, Any]] = []
    for row in rows:
        rec = _row_to_run(row)
        if args.active and rec["status"] not in statuses:
            continue
        rec["next_command"] = f"noemaforge pipeline next {rec['run_id']}"
        rec["compact_command"] = f"noemaforge pipeline compact {rec['run_id']} --register"
        items.append(rec)
    if args.json:
        print(json_dumps({"ok": True, "count": len(items), "items": items}))
        return
    for rec in items:
        print(f"{rec['run_id']}\t{rec['pipeline_id']}\t{rec['status']}\t{rec['current_stage']}\t{rec['next_command']}")


def metrics_cmd(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    rows = conn.execute("SELECT status FROM runs").fetchall()
    status_counts: Dict[str, int] = {}
    for (status,) in rows:
        status_counts[status] = status_counts.get(status, 0) + 1
    wip = sum(v for k, v in status_counts.items() if k in ACTIVE_STATUSES or k in PAUSED_STATUSES)
    readiness = 100
    runtime = runtime_snapshot()
    degraded = degraded_readonly_state()
    active_lease = _active_unexpired_lease(conn)
    if not runtime.get("ok"):
        readiness -= 40
    if degraded.get("active"):
        readiness -= 15
    if status_counts.get("failed"):
        readiness -= min(25, status_counts["failed"] * 5)
    if wip > 5:
        readiness -= min(20, (wip - 5) * 2)
    readiness = max(0, readiness)
    metrics = {
        "ok": runtime.get("ok", False) and readiness >= 60,
        "version": RUNTIME_VERSION,
        "readiness_score": readiness,
        "flow.wip": wip,
        "flow.runs_total": len(rows),
        "flow.status_counts": status_counts,
        "pipeline.catalog_count": len(load_pipeline_catalog(root)),
        "pipeline.pattern_count": len(load_pattern_catalog(root).get("patterns") or []),
        "persona.count": len(load_persona_catalog(root).get("personas") or {}),
        "runtime": runtime,
        "degraded_readonly": degraded,
        "llm_lease": active_lease,
    }
    fmt = getattr(args, "format", "json") or "json"
    if fmt == "prometheus":
        lines = [
            "# HELP noemaforge_pipeline_runs_total Total known NoemaForge pipeline runs.",
            "# TYPE noemaforge_pipeline_runs_total gauge",
            f"noemaforge_pipeline_runs_total {len(rows)}",
            "# HELP noemaforge_pipeline_active Active or paused NoemaForge pipeline runs.",
            "# TYPE noemaforge_pipeline_active gauge",
            f"noemaforge_pipeline_active {wip}",
            "# HELP noemaforge_pipeline_readiness_score NoemaForge pipeline readiness score from 0 to 100.",
            "# TYPE noemaforge_pipeline_readiness_score gauge",
            f"noemaforge_pipeline_readiness_score {readiness}",
            "# HELP noemaforge_llm_active_count Visible active LLM backend sockets.",
            "# TYPE noemaforge_llm_active_count gauge",
            f"noemaforge_llm_active_count {int(runtime.get('active_llms') or 0)}",
            "# HELP noemaforge_llm_lease_active Whether an active LLM lease exists.",
            "# TYPE noemaforge_llm_lease_active gauge",
            f"noemaforge_llm_lease_active {1 if active_lease else 0}",
            "# HELP noemaforge_degraded_mode Whether NoemaForge is in degraded-readonly mode.",
            "# TYPE noemaforge_degraded_mode gauge",
            f"noemaforge_degraded_mode {1 if degraded.get('active') else 0}",
            "# HELP noemaforge_persona_count Persona catalog size.",
            "# TYPE noemaforge_persona_count gauge",
            f"noemaforge_persona_count {len(load_persona_catalog(root).get('personas') or {})}",
        ]
        for status, count in sorted(status_counts.items()):
            safe_status = re.sub(r"[^a-zA-Z0-9_]", "_", status)
            lines.append(f'noemaforge_pipeline_status_count{{status="{safe_status}"}} {count}')
        print("\n".join(lines) + "\n")
        return
    print(json_dumps(metrics))


def template_append_cmd(args: argparse.Namespace) -> None:
    guard_degraded_mutation("pipeline template-append", getattr(args, "allow_degraded", False))
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    draft_path = Path(args.draft).expanduser().resolve()
    if not draft_path.exists():
        raise SystemExit(f"draft not found: {draft_path}")
    raw = json.loads(draft_path.read_text(encoding="utf-8", errors="replace"))
    if "pipeline" in raw and "pipeline_id" in raw:
        additions = {safe_id(raw["pipeline_id"]): raw["pipeline"]}
    elif isinstance(raw, dict):
        additions = {safe_id(k): v for k, v in raw.items() if isinstance(v, dict)}
    else:
        raise SystemExit("draft must be an object or a template-import result")
    if not additions:
        print(json_dumps({"ok": False, "problems": ["draft contains no pipeline templates"]}))
        raise SystemExit(1)
    if not args.approve:
        print(json_dumps({"ok": False, "ready_to_append": True, "requires": "--approve", "pipelines": sorted(additions)}))
        raise SystemExit(1)
    existing = load_pipeline_catalog(root)
    problems: List[str] = []
    for pid, spec in additions.items():
        if pid in existing and not args.replace:
            problems.append(f"pipeline already exists: {pid}")
        if not spec.get("stages"):
            problems.append(f"{pid}: missing stages")
        pol = spec.get("llm_policy") or {}
        if pol.get("mode") != "switchable" or int(pol.get("max_active_llms") or 0) != 1:
            problems.append(f"{pid}: must use switchable/max_active_llms=1")
        spec.setdefault("review", {})
        spec["review"].update({"approved_at": nowz(), "approved_by": args.approved_by or "operator", "source_draft": str(draft_path)})
    if problems:
        print(json_dumps({"ok": False, "problems": problems}))
        raise SystemExit(1)
    out = Path(args.out).resolve() if args.out else root / "configs" / "pipelines.local.json"
    merged: Dict[str, Any] = {}
    if out.exists():
        merged = load_json_or_default(out, {})
    merged.update(additions)
    atomic_write_text(out, json_dumps(merged) + "\n")
    print(json_dumps({"ok": True, "out": str(out), "added": sorted(additions), "count": len(merged)}))



def member_cmd(args: argparse.Namespace) -> None:
    """Delegate NoemaForge-native member-cell execution from inside pipeline CLI."""
    script = Path(__file__).with_name("team_member_runtime.py")
    base = [sys.executable, str(script)]
    # Preserve root/state in a form team_member_runtime accepts.
    if getattr(args, "root", None):
        base.extend(["--root", str(args.root)])
    if getattr(args, "member_state", None):
        base.extend(["--state", str(args.member_state)])
    if getattr(args, "state", None):
        base.extend(["--pipeline-state", str(args.state)])
    action = args.member_action
    if action == "team":
        cmd = ["team", "--member", args.member, "--producer", args.producer, "--count", str(args.count)]
        for m in args.model or []:
            cmd.extend(["--model", m])
        if args.json:
            cmd.append("--json")
    elif action == "run":
        cmd = ["run", "--pipeline-run-id", args.run_id, "--stage", args.stage, "--member", args.member, "--project", args.project, "--producer", args.producer, "--count", str(args.count), "--mode", args.mode, "--request", args.request]
        if args.run_id_member:
            cmd.extend(["--run-id", args.run_id_member])
        for m in args.model or []:
            cmd.extend(["--model", m])
        if args.write_diagrams:
            cmd.append("--write-diagrams")
        if args.strict:
            cmd.append("--strict")
        if args.json:
            cmd.append("--json")
    elif action == "analyze-code":
        cmd = ["analyze-code", "--project", args.project]
        if args.out:
            cmd.extend(["--out", args.out])
    elif action == "validate":
        cmd = ["validate"]
    elif action == "list":
        cmd = ["list", "--limit", str(args.limit)]
    elif action == "show":
        cmd = ["show", args.run_id_member]
    else:
        raise SystemExit(f"unknown member action: {action}")
    raise SystemExit(subprocess.run(base + cmd).returncode)

def policy_cmd(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    result = {
        "ok": True,
        "version": RUNTIME_VERSION,
        "runtime_invariant": {"mode": "switchable", "max_active_llms": 1, "heavy_llm_autostart": "conditional_safe_start_only"},
        "boot_modes": {"manual": "no autostart", "gui": "safe-start after display-manager/GUI", "wogui": "safe-start under multi-user target instead of GUI"},
        "degraded_readonly": degraded_readonly_state(),
        "default_state": str(state),
        "operator_rules": [
            "GUI/NVIDIA first; LLM starts manually only unless explicitly changed by admin.",
            "Imported workflow templates stay drafts until reviewed with pipeline template-append --approve.",
            "Every pipeline stage must pass through markdown context handoff packets.",
            "Evolution/development work should use worktree isolation before merge.",
        ],
        "catalogs": {
            "pipelines": len(load_pipeline_catalog(root)),
            "teams": len(load_team_catalog(root)),
            "patterns": len(load_pattern_catalog(root).get("patterns") or []),
        },
    }
    print(json_dumps(result))

def schema_validate_cmd(args: argparse.Namespace) -> None:
    """P1 config/context schema validation without third-party dependencies."""
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    problems: List[str] = []
    warnings: List[str] = []
    checked: Dict[str, int] = {}

    pipelines = load_pipeline_catalog(root)
    checked["pipelines"] = len(pipelines)
    for pid, spec in pipelines.items():
        if not isinstance(spec, dict):
            problems.append(f"pipeline {pid}: spec must be object")
            continue
        for key in ["description", "stages", "team", "permission_mode", "llm_policy"]:
            if key not in spec:
                problems.append(f"pipeline {pid}: missing {key}")
        if not isinstance(spec.get("stages"), list) or not all(isinstance(x, str) and x for x in spec.get("stages", [])):
            problems.append(f"pipeline {pid}: stages must be non-empty string list")
        pol = spec.get("llm_policy") or {}
        if pol.get("mode") != "switchable" or int(pol.get("max_active_llms") or 0) != 1:
            problems.append(f"pipeline {pid}: llm_policy must be switchable/max_active_llms=1")

    teams = load_team_catalog(root)
    checked["teams"] = len(teams)
    for tid, spec in teams.items():
        if not isinstance(spec.get("roles", []), list):
            problems.append(f"team {tid}: roles must be list")
        if not spec.get("coordinator"):
            warnings.append(f"team {tid}: missing coordinator")

    patterns = load_pattern_catalog(root).get("patterns") or []
    checked["patterns"] = len(patterns)
    for item in patterns:
        if not isinstance(item, dict) or not item.get("id") or not item.get("family"):
            problems.append("pattern catalog: malformed entry")
            continue
        mapping = item.get("noemaforge_mapping", {})
        invariant = mapping.get("invariant", mapping)
        if invariant.get("max_active_llms") != 1:
            problems.append(f"pattern {item.get('id')}: max_active_llms must be 1")

    personas = load_persona_catalog(root).get("personas") or {}
    checked["personas"] = len(personas)
    seen: set[str] = set()
    for role, spec in personas.items():
        codename = str(spec.get("codename") or "")
        if not codename:
            problems.append(f"persona {role}: missing codename")
        if codename in seen:
            problems.append(f"persona catalog: duplicate codename {codename}")
        seen.add(codename)
        portrait = spec.get("portrait")
        if portrait and not (root / portrait).exists():
            problems.append(f"persona {role}: portrait missing {portrait}")

    low = load_low_hanging_catalog(root).get("collections") or []
    checked["low_hanging_collections"] = len(low)
    for collection in low:
        if not collection.get("id") or not collection.get("pipeline"):
            problems.append("low-hanging collection: missing id/pipeline")

    selftests = load_selftest_catalog(root)
    cases = selftests.get("cases") or []
    checked["selftest_cases"] = len(cases)
    if not cases:
        problems.append("selftest case catalog is empty or missing")
    seen_cases: set[str] = set()
    for case in cases:
        cid = str(case.get("id") or "")
        if not cid:
            problems.append("selftest catalog: case missing id")
        if cid in seen_cases:
            problems.append(f"selftest catalog: duplicate case id {cid}")
        seen_cases.add(cid)
        if not isinstance(case.get("command"), list) or not case.get("command"):
            problems.append(f"selftest case {cid}: command must be non-empty list")
    for suite, ids in (selftests.get("suites") or {}).items():
        for cid in ids:
            if cid not in seen_cases:
                problems.append(f"selftest suite {suite}: unknown case {cid}")
    policy = load_selftest_policy(root)
    checked["selftest_policy_thresholds"] = len(policy.get("thresholds") or {})

    if getattr(args, "run_id", None):
        conn = db_connect(state)
        run = get_run(conn, args.run_id)
        run_dir = Path(str(run["run_dir"]))
        sidecars = sorted(run_dir.glob("context_packets/*.json"))
        checked["typed_context_sidecars"] = len(sidecars)
        if not sidecars:
            problems.append(f"run {args.run_id}: no typed context sidecars")
        for sidecar in sidecars:
            try:
                env = json.loads(sidecar.read_text(encoding="utf-8", errors="replace"))
            except Exception as exc:
                problems.append(f"{sidecar}: invalid json: {exc}")
                continue
            required = ["apiVersion", "task_id", "project_id", "pipeline_id", "stage", "llm_policy", "output_contract", "markdown_sha256"]
            missing = [k for k in required if k not in env]
            if missing:
                problems.append(f"{sidecar.name}: missing {missing}")
            checksum = sidecar.with_suffix(sidecar.suffix + ".sha256")
            if not checksum.exists():
                problems.append(f"{sidecar.name}: missing checksum file")
            else:
                expected = checksum.read_text(encoding="utf-8", errors="replace").split()[0]
                actual = hashlib.sha256(sidecar.read_bytes()).hexdigest()
                if expected != actual:
                    problems.append(f"{sidecar.name}: checksum mismatch")

    result = {"ok": not problems, "version": RUNTIME_VERSION, "checked": checked, "warnings": warnings, "problems": problems}
    print(json_dumps(result))
    if problems:
        raise SystemExit(1)


def event_log_cmd(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    if getattr(args, "run_id", None):
        rows = conn.execute("SELECT id,run_id,ts,event_type,payload FROM events WHERE run_id=? ORDER BY id DESC LIMIT ?", (args.run_id, int(args.limit))).fetchall()
    else:
        rows = conn.execute("SELECT id,run_id,ts,event_type,payload FROM events ORDER BY id DESC LIMIT ?", (int(args.limit),)).fetchall()
    items: List[Dict[str, Any]] = []
    for row in rows:
        rec = dict(zip(["id", "run_id", "ts", "event_type", "payload"], row))
        try:
            rec["payload"] = json.loads(str(rec.get("payload") or "{}"))
        except Exception:
            pass
        items.append(rec)
    if args.json:
        print(json_dumps({"ok": True, "count": len(items), "items": items}))
        return
    for rec in items:
        print(f"{rec['id']}\t{rec['ts']}\t{rec['run_id']}\t{rec['event_type']}")


def lease_cmd(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    action = args.lease_action
    if action == "status":
        active = _active_unexpired_lease(conn)
        rows = conn.execute("SELECT lease_id,owner,task_id,priority,state,acquired_at,expires_at,updated_at,metadata FROM llm_leases ORDER BY updated_at DESC LIMIT ?", (int(args.limit),)).fetchall()
        items = []
        for row in rows:
            rec = dict(zip(["lease_id", "owner", "task_id", "priority", "state", "acquired_at", "expires_at", "updated_at", "metadata"], row))
            try:
                rec["metadata"] = json.loads(str(rec.get("metadata") or "{}"))
            except Exception:
                rec["metadata"] = {}
            items.append(rec)
        print(json_dumps({"ok": True, "active": active, "items": items, "runtime": runtime_snapshot()}))
        return
    if action == "acquire":
        owner = safe_id(args.owner or "operator")
        task_id = safe_id(args.task_id or owner)
        priority = int(args.priority)
        active = _active_unexpired_lease(conn)
        if active and not args.preempt:
            print(json_dumps({"ok": False, "error": "lease_busy", "active": active, "hint": "use --preempt for reviewed urgent takeover"}))
            raise SystemExit(1)
        if active and args.preempt:
            conn.execute("UPDATE llm_leases SET state='preempted', updated_at=? WHERE lease_id=?", (nowz(), active["lease_id"]))
            emit(conn, "_runtime", "llm_lease_preempted", {"lease_id": active["lease_id"], "by": owner})
        lease_id = safe_id(args.lease_id or f"lease_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{owner}")
        acquired = nowz()
        expires = _seconds_from_now(int(args.ttl_seconds))
        metadata = {"reason": args.reason or "", "mode": "switchable", "max_active_llms": 1}
        conn.execute(
            "INSERT OR REPLACE INTO llm_leases(lease_id,owner,task_id,priority,state,acquired_at,expires_at,updated_at,metadata) VALUES(?,?,?,?,?,?,?,?,?)",
            (lease_id, owner, task_id, priority, "active", acquired, expires, acquired, json_dumps(metadata, pretty=False)),
        )
        conn.commit()
        emit(conn, "_runtime", "llm_lease_acquired", {"lease_id": lease_id, "owner": owner, "task_id": task_id, "priority": priority, "expires_at": expires})
        print(json_dumps({"ok": True, "lease_id": lease_id, "owner": owner, "task_id": task_id, "priority": priority, "expires_at": expires}))
        return
    if action == "release":
        conn.execute("UPDATE llm_leases SET state='released', updated_at=? WHERE lease_id=?", (nowz(), args.lease_id))
        conn.commit()
        emit(conn, "_runtime", "llm_lease_released", {"lease_id": args.lease_id})
        print(json_dumps({"ok": True, "lease_id": args.lease_id, "state": "released"}))
        return
    if action == "preempt":
        target = args.lease_id
        if not target:
            active = _active_unexpired_lease(conn)
            if not active:
                print(json_dumps({"ok": True, "changed": False, "reason": "no_active_lease"}))
                return
            target = active["lease_id"]
        conn.execute("UPDATE llm_leases SET state='preempted', updated_at=? WHERE lease_id=?", (nowz(), target))
        conn.commit()
        emit(conn, "_runtime", "llm_lease_preempted", {"lease_id": target, "reason": args.reason or "operator preemption"})
        print(json_dumps({"ok": True, "lease_id": target, "state": "preempted"}))
        return
    raise SystemExit(f"unknown lease action: {action}")


def executor_step_cmd(args: argparse.Namespace) -> None:
    """Tiny NoemaForge-native DAG/event stepper: inspect current stage and optionally advance."""
    if args.apply:
        guard_degraded_mutation("pipeline executor-step --apply", getattr(args, "allow_degraded", False))
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = db_connect(state)
    run = get_run(conn, args.run_id)
    stage = args.stage or str(run.get("current_stage"))
    assert_stage(run, stage)
    paths = _stage_paths(run, stage)
    contract = _pipeline_stage_contract(stage)
    quality = stage_output_quality(paths["output"])
    artifacts = [a for a in _artifact_rows(conn, args.run_id) if a.get("stage") == stage]
    contract_artifacts = [a for a in artifacts if str(a.get("artifact_type") or "") in set(contract.get("artifact_types") or [])]
    ready = bool(paths["packet"].exists() and paths["output"].exists() and not quality.get("looks_placeholder") and contract_artifacts)
    next_stage = next_stage_for(run.get("manifest") or {}, stage)
    action = "wait"
    new_status = run.get("status")
    if ready:
        action = "complete" if not next_stage else "advance"
        new_status = "completed" if not next_stage else "in_progress"
    result = {
        "ok": True,
        "run_id": args.run_id,
        "stage": stage,
        "ready": ready,
        "action": action,
        "apply": bool(args.apply),
        "next_stage": next_stage,
        "worker_contract_version": "noemaforge.pipeline.executor-stage-worker/v1",
        "stage_contract": contract,
        "quality": quality,
        "artifact_count": len(artifacts),
        "contract_artifact_count": len(contract_artifacts),
        "warnings": [] if ready else ["stage is not ready: needs non-placeholder output and at least one contract-matching registered artifact"],
    }
    if args.apply and ready:
        target_stage = next_stage or stage
        run = update_run(conn, run, status=str(new_status), stage=str(target_stage), note=f"executor-step {action} from {stage}", event_type="pipeline_executor_step")
        result["status"] = run.get("status")
        result["current_stage"] = run.get("current_stage")
    elif args.apply and not ready:
        emit(conn, args.run_id, "pipeline_executor_wait", {"stage": stage, "reason": "gate_not_ready"})
    print(json_dumps(result))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noemaforge pipeline")
    parser.add_argument("--root")
    parser.add_argument("--state")
    sub = parser.add_subparsers(dest="cmd", required=True)

    cat = sub.add_parser("catalog")
    cat.add_argument("--json", action="store_true")
    cat.set_defaults(func=catalog)

    run = sub.add_parser("run")
    run.add_argument("pipeline")
    run.add_argument("--task-id")
    run.add_argument("--project")
    run.add_argument("--request", default="")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--run-id")
    run.add_argument("--trace-id", default="")
    run.add_argument("--allow-existing", action="store_true")
    run.add_argument("--allow-degraded", action="store_true", help="explicit admin override for degraded_readonly firstboot state")
    run.set_defaults(func=create_run)

    listp = sub.add_parser("list")
    listp.add_argument("--limit", type=int, default=20)
    listp.add_argument("--json", action="store_true")
    listp.set_defaults(func=list_runs)

    show = sub.add_parser("show")
    show.add_argument("run_id")
    show.add_argument("--events", type=int, default=12)
    show.set_defaults(func=show_run)

    tp = sub.add_parser("toolproxy-policy")
    tp.add_argument("run_id")
    tp.add_argument("--stage")
    tp.set_defaults(func=toolproxy_policy_cmd)

    nextp = sub.add_parser("next")
    nextp.add_argument("run_id")
    nextp.set_defaults(func=next_run)

    snap = sub.add_parser("snapshot")
    snap.add_argument("--out")
    snap.set_defaults(func=snapshot)

    adv = sub.add_parser("advance")
    adv.add_argument("run_id")
    adv.add_argument("--stage")
    adv.add_argument("--next", action="store_true")
    adv.add_argument("--status", default="in_progress")
    adv.add_argument("--note", default="")
    adv.add_argument("--allow-degraded", action="store_true")
    adv.set_defaults(func=advance_run)

    approve = sub.add_parser("approve")
    approve.add_argument("run_id")
    approve.add_argument("--stage")
    approve.add_argument("--status", default="approved")
    approve.add_argument("--note", default="")
    approve.add_argument("--allow-degraded", action="store_true")
    approve.set_defaults(func=approve_run)

    pause = sub.add_parser("pause")
    pause.add_argument("run_id")
    pause.add_argument("--stage")
    pause.add_argument("--note", default="")
    pause.set_defaults(func=pause_run)

    resume = sub.add_parser("resume")
    resume.add_argument("run_id")
    resume.add_argument("--stage")
    resume.add_argument("--status", default="in_progress")
    resume.add_argument("--note", default="")
    resume.add_argument("--allow-degraded", action="store_true")
    resume.set_defaults(func=resume_run)

    fail = sub.add_parser("fail")
    fail.add_argument("run_id")
    fail.add_argument("--stage")
    fail.add_argument("--reason", default="")
    fail.add_argument("--note", default="")
    fail.set_defaults(func=lambda a: fail_or_cancel_run(a, "failed", "pipeline_failed"))

    cancel = sub.add_parser("cancel")
    cancel.add_argument("run_id")
    cancel.add_argument("--stage")
    cancel.add_argument("--reason", default="")
    cancel.add_argument("--note", default="")
    cancel.set_defaults(func=lambda a: fail_or_cancel_run(a, "cancelled", "pipeline_cancelled"))

    art = sub.add_parser("artifact")
    artsub = art.add_subparsers(dest="artifact_action", required=True)
    artadd = artsub.add_parser("add")
    artadd.add_argument("run_id")
    artadd.add_argument("--stage")
    artadd.add_argument("--type", default="note")
    artadd.add_argument("--path", required=True)
    artadd.add_argument("--status", default="draft")
    artadd.add_argument("--meta", action="append")
    artadd.add_argument("--allow-degraded", action="store_true")
    artadd.set_defaults(func=artifact_cmd)
    artlist = artsub.add_parser("list")
    artlist.add_argument("run_id", nargs="?")
    artlist.add_argument("--limit", type=int, default=50)
    artlist.set_defaults(func=artifact_cmd)

    wt = sub.add_parser("worktree")
    wtsub = wt.add_subparsers(dest="worktree_action", required=True)
    wtcreate = wtsub.add_parser("create")
    wtcreate.add_argument("run_id")
    wtcreate.add_argument("--repo")
    wtcreate.add_argument("--branch")
    wtcreate.add_argument("--base", default="HEAD")
    wtcreate.add_argument("--path")
    wtcreate.add_argument("--apply", action="store_true")
    wtcreate.add_argument("--allow-degraded", action="store_true")
    wtcreate.set_defaults(func=worktree_cmd)

    summ = sub.add_parser("summary")
    summ.add_argument("run_id")
    summ.add_argument("--events", type=int, default=6)
    summ.add_argument("--json", action="store_true")
    summ.set_defaults(func=summary_run)

    # Compatibility alias from early 0.30 scaffolding.
    np = sub.add_parser("next-packet")
    np.add_argument("run_id")
    np.set_defaults(func=next_run)

    exp = sub.add_parser("export")
    exp.add_argument("run_id")
    exp.add_argument("--out")
    exp.set_defaults(func=export_run)

    dash = sub.add_parser("dashboard-state")
    dash.add_argument("--out")
    dash.add_argument("--persona-state", default=os.environ.get("NOEMAFORGE_PERSONA_STATE", str(DEFAULT_PERSONA_STATE)))
    dash.set_defaults(func=dashboard_state)

    pat = sub.add_parser("patterns")
    pat.add_argument("--json", action="store_true")
    pat.add_argument("--family")
    pat.add_argument("--use-case")
    pat.add_argument("--limit", type=int, default=80)
    pat.set_defaults(func=patterns_cmd)

    val = sub.add_parser("validate")
    val.set_defaults(func=validate)

    doc = sub.add_parser("doctor")
    doc.add_argument("run_id", nargs="?")
    doc.set_defaults(func=doctor)

    ready = sub.add_parser("readiness")
    ready.add_argument("--json", action="store_true")  # kept for CLI symmetry; output is JSON either way
    ready.set_defaults(func=readiness_cmd)

    repair = sub.add_parser("repair")
    repair.add_argument("run_id", nargs="?")
    repair.add_argument("--all", action="store_true")
    repair.add_argument("--limit", type=int, default=50)
    repair.add_argument("--dry-run", action="store_true", default=False)
    repair.add_argument("--allow-degraded", action="store_true")
    repair.set_defaults(func=repair_run_cmd)

    gate = sub.add_parser("gate")
    gate.add_argument("run_id")
    gate.add_argument("--stage")
    gate.add_argument("--strict", action="store_true")
    gate.add_argument("--json", action="store_true")  # output is JSON; flag retained for docs symmetry
    gate.set_defaults(func=gate_run_cmd)

    imp = sub.add_parser("template-import")
    imp.add_argument("source")
    imp.add_argument("--family")
    imp.add_argument("--pipeline-id")
    imp.add_argument("--out")
    imp.set_defaults(func=template_import_cmd)

    tapp = sub.add_parser("template-append")
    tapp.add_argument("draft")
    tapp.add_argument("--approve", action="store_true")
    tapp.add_argument("--approved-by")
    tapp.add_argument("--replace", action="store_true")
    tapp.add_argument("--out")
    tapp.add_argument("--allow-degraded", action="store_true")
    tapp.set_defaults(func=template_append_cmd)

    lint = sub.add_parser("context-lint")
    lint.add_argument("run_id")
    lint.add_argument("--strict", action="store_true")
    lint.set_defaults(func=context_lint_cmd)

    stageval = sub.add_parser("stage-validate")
    stageval.add_argument("run_id")
    stageval.add_argument("--stage")
    stageval.add_argument("--strict", action="store_true")
    stageval.set_defaults(func=stage_validate_cmd)

    smoke = sub.add_parser("stage-smoke")
    smoke.add_argument("--pipeline", default="public_mwp")
    smoke.add_argument("--stage")
    smoke.add_argument("--run-id")
    smoke.set_defaults(func=stage_smoke_cmd)

    comp = sub.add_parser("compact")
    comp.add_argument("run_id")
    comp.add_argument("--out")
    comp.add_argument("--register", action="store_true")
    comp.add_argument("--allow-degraded", action="store_true")
    comp.set_defaults(func=compact_run_cmd)

    q = sub.add_parser("queue")
    q.add_argument("--limit", type=int, default=40)
    q.add_argument("--active", action="store_true")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=queue_cmd)

    metr = sub.add_parser("metrics")
    metr.add_argument("--format", choices=["json", "prometheus"], default="json")
    metr.set_defaults(func=metrics_cmd)

    sch = sub.add_parser("schema-validate")
    sch.add_argument("--run-id")
    sch.set_defaults(func=schema_validate_cmd)

    ev = sub.add_parser("event-log")
    ev.add_argument("--run-id")
    ev.add_argument("--limit", type=int, default=50)
    ev.add_argument("--json", action="store_true")
    ev.set_defaults(func=event_log_cmd)

    lease = sub.add_parser("lease")
    leasesub = lease.add_subparsers(dest="lease_action", required=True)
    lstat = leasesub.add_parser("status")
    lstat.add_argument("--limit", type=int, default=20)
    lstat.set_defaults(func=lease_cmd)
    lacq = leasesub.add_parser("acquire")
    lacq.add_argument("--owner", required=True)
    lacq.add_argument("--task-id")
    lacq.add_argument("--priority", type=int, default=50)
    lacq.add_argument("--ttl-seconds", type=int, default=600)
    lacq.add_argument("--lease-id")
    lacq.add_argument("--reason")
    lacq.add_argument("--preempt", action="store_true")
    lacq.set_defaults(func=lease_cmd)
    lrel = leasesub.add_parser("release")
    lrel.add_argument("lease_id")
    lrel.set_defaults(func=lease_cmd)
    lpre = leasesub.add_parser("preempt")
    lpre.add_argument("lease_id", nargs="?")
    lpre.add_argument("--reason")
    lpre.set_defaults(func=lease_cmd)

    estep = sub.add_parser("executor-step")
    estep.add_argument("run_id")
    estep.add_argument("--stage")
    estep.add_argument("--apply", action="store_true")
    estep.add_argument("--allow-degraded", action="store_true")
    estep.set_defaults(func=executor_step_cmd)

    member = sub.add_parser("member")
    member.add_argument("member_action", choices=["team", "run", "analyze-code", "validate", "list", "show"])
    member.add_argument("run_id", nargs="?", help="pipeline run id for member run, or member run id for show")
    member.add_argument("--stage", default="development")
    member.add_argument("--member", default="qa")
    member.add_argument("--project", default=os.getcwd())
    member.add_argument("--producer", default="qwen25-coder-14b")
    member.add_argument("--model", action="append")
    member.add_argument("--count", type=int, default=2)
    member.add_argument("--mode", choices=["sequential", "parallel_requested_serialized"], default="sequential")
    member.add_argument("--request", default="Pipeline member execution")
    member.add_argument("--run-id-member")
    member.add_argument("--member-state")
    member.add_argument("--out")
    member.add_argument("--limit", type=int, default=20)
    member.add_argument("--write-diagrams", action="store_true")
    member.add_argument("--strict", action="store_true")
    member.add_argument("--json", action="store_true")
    member.set_defaults(func=member_cmd)

    pol = sub.add_parser("policy")
    pol.set_defaults(func=policy_cmd)
    return parser


def normalize_global_argv(argv: Optional[List[str]]) -> List[str]:
    """Allow --root/--state before or after the subcommand.

    argparse global options normally have to appear before the subcommand.
    Operators naturally type `noemaforge pipeline validate --state ...`, so the
    MVP runtime accepts both forms and normalizes them before parsing.
    """
    items = list(sys.argv[1:] if argv is None else argv)
    global_opts: List[str] = []
    rest: List[str] = []
    i = 0
    while i < len(items):
        item = items[i]
        if item in {"--root", "--state"} and i + 1 < len(items):
            global_opts.extend([item, items[i + 1]])
            i += 2
            continue
        rest.append(item)
        i += 1
    return global_opts + rest


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_global_argv(argv))
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


