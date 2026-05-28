#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/roles/role_entry.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations


# === NoemaForge Autodoc File Header ===
# File: src/roles/role_entry.py
# Purpose: Provide the module 'role_entry'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - main
# Inputs:
#   - --role
#   - --context
#   - --out
#   - --run-id
#   - --trace-id
#   - Environment: NOEMAFORGE_TOOLPROXY_SOCKET, NOEMAFORGE_CAP_TOKEN, NOEMAFORGE_PROJECT_ID
#   - Common path inputs: /run/noemaforge/toolproxy.sock, n/a
#   - Imports: __future__, argparse, datetime, json, os, socket, sys, uuid
# Output formats / side effects:
#   - JSON files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""role_entry.py (MVP)

This file is executed by RoleRunner (podman or host).

Input:
- context JSON (created by noemaforge_core)
Output:
- role_result JSON (pure data)

Roles are *pure compute* in v0.9:
- they do not write directly to project files
- they may call ToolProxy for approved actions (e.g., llm.chat)

This is deliberate: it keeps the OS "spinal cord" deterministic.
"""


import argparse
import datetime as dt
import json
import os
import socket
import sys
import uuid
from typing import Any, Dict, List, Optional, Tuple


# === NoemaForge Autodoc Function Header ===
# Function: _nowz()
# Purpose: Implement the routine ' nowz'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/bundles.py
#   - src/caps.py
#   - src/casebase.py
#   - src/coordinator_fanout.py
#   - src/dream_cycle.py
#   - src/fixture_bundle.py
# Calls:
#   - isoformat, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"


# === NoemaForge Autodoc Function Header ===
# Function: _load_json(path: str)
# Purpose: Implement the routine ' load json'.
# Inputs:
#   - path: str
# Called by:
#   - src/noemaforge_core.py
#   - src/fixture_bundle.py
#   - src/glove_agent.py
#   - src/model_installer_plan.py
#   - src/model_registry.py
#   - src/model_router.py
#   - src/scary_sweep.py
#   - src/team_installer_plan.py
# Calls:
#   - open, load
# Returns / emits: Any
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# === NoemaForge Autodoc Function Header ===
# Function: _save_json(path: str, obj)
# Purpose: Implement the routine ' save json'.
# Inputs:
#   - path: str
#   - obj
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/fixture_bundle.py
#   - src/model_registry.py
#   - src/model_scorecards.py
#   - src/prestart.py
#   - src/scary_sweep.py
#   - src/sr_cycle.py
# Calls:
#   - open, dump
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _save_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# === NoemaForge Autodoc Function Header ===
# Function: _toolproxy_call(sock_path: str, req: Dict[str, Any], timeout_sec: float = 30.0)
# Purpose: Implement the routine ' toolproxy call'.
# Inputs:
#   - sock_path: str
#   - req: Dict[str, Any]
#   - timeout_sec: float = 30.0
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - socket, settimeout, connect, encode, sendall, shutdown, close, recv, loads, dumps, decode
# Returns / emits: Dict[str, Any]
# Side effects:
#   - serializes structured data
#   - opens a database or socket connection
#   - sends a response or network payload
# Key locals:
#   - chunk, data, out, s
# === End NoemaForge Autodoc Function Header ===
def _toolproxy_call(sock_path: str, req: Dict[str, Any], timeout_sec: float = 30.0) -> Dict[str, Any]:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout_sec)
    s.connect(sock_path)
    data = json.dumps(req, ensure_ascii=False).encode("utf-8")
    s.sendall(data)
    s.shutdown(socket.SHUT_WR)
    out = b""
    while True:
        chunk = s.recv(4096)
        if not chunk:
            break
        out += chunk
    s.close()
    try:
        return json.loads(out.decode("utf-8"))
    except Exception:
        return {"ok": False, "error": "bad_toolproxy_response", "raw": out.decode("utf-8", "replace")}


# === NoemaForge Autodoc Function Header ===
# Function: _has_role(roster_roles: List[str], role_id: str)
# Purpose: Implement the routine ' has role'.
# Inputs:
#   - roster_roles: List[str]
#   - role_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set
# Returns / emits: bool
# === End NoemaForge Autodoc Function Header ===
def _has_role(roster_roles: List[str], role_id: str) -> bool:
    return role_id in set(roster_roles or [])


# === NoemaForge Autodoc Function Header ===
# Function: _prio_idx(p: Optional[str])
# Purpose: Implement the routine ' prio idx'.
# Inputs:
#   - p: Optional[str]
# Called by:
#   - src/noemaforge_core.py
# Calls:
#   - get, str, enumerate
# Returns / emits: int
# Key locals:
#   - m, order
# === End NoemaForge Autodoc Function Header ===
def _prio_idx(p: Optional[str]) -> int:
    order = ["critical", "urgent", "daily_sla", "high", "normal", "background"]
    m = {v: i for i, v in enumerate(order)}
    return m.get(str(p or "normal"), m["normal"])


# === NoemaForge Autodoc Function Header ===
# Function: _choose_specialist(roster_roles: List[str], task_title: str)
# Purpose: Implement the routine ' choose specialist'.
# Inputs:
#   - roster_roles: List[str]
#   - task_title: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, any, has, _has_role
# Returns / emits: str
# Key locals:
#   - r, s
# === End NoemaForge Autodoc Function Header ===
def _choose_specialist(roster_roles: List[str], task_title: str) -> str:
    s = (task_title or "").lower()

    # === NoemaForge Autodoc Function Header ===
    # Function: has(r: str)
    # Purpose: Implement the routine 'has'.
    # Inputs:
    #   - r: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _has_role
    # Returns / emits: bool
    # === End NoemaForge Autodoc Function Header ===
    def has(r: str) -> bool:
        return _has_role(roster_roles, r)

    if any(k in s for k in ["архит", "контракт", "schema", "дизайн", "solution"]):
        if has("solution_architect"):
            return "solution_architect"
        if has("architect"):
            return "architect"
    if any(k in s for k in ["sql", "бд", "db", "таблиц", "миграц", "postgres", "mysql", "индекс", "index"]):
        if has("sql_dev"):
            return "sql_dev"
    if has("python_dev"):
        return "python_dev"

    # fallback: first non-pm
    for r in roster_roles:
        if r != "pm":
            return r
    return "pm"




# === NoemaForge Autodoc Function Header ===
# Function: _offline_specialist_content(role: str, task_id: str, objective: str, ctx: Dict[str, Any])
# Purpose: Build a deterministic offline work packet when llm.chat is unavailable.
# Inputs:
#   - role: str
#   - task_id: str
#   - objective: str
#   - ctx: Dict[str, Any]
# Called by:
#   - _specialist_logic
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _offline_specialist_content(role: str, task_id: str, objective: str, ctx: Dict[str, Any]) -> str:
    stream_id = str(ctx.get("stream_id") or "")
    project_id = str(ctx.get("project_id") or "")
    assumptions = [
        "Work stays offline-first unless a policy-gated tool explicitly allows otherwise.",
        "ToolProxy remains the only tool execution path.",
        "Outputs must stay reviewable and easy to verify.",
    ]
    role_hints = {
        "solution_architect": [
            "List the interfaces and contracts before proposing components.",
            "Call out rollback and migration boundaries.",
        ],
        "architect": [
            "Prioritize architecture boundaries and contract changes.",
            "Surface operational and failure-mode risks.",
        ],
        "sql_dev": [
            "Specify schema changes, indexes, and migration/rollback steps.",
            "Include validation queries.",
        ],
        "python_dev": [
            "Describe the code path to change and the tests to add.",
            "Prefer small patches with deterministic behavior.",
        ],
        "dev": [
            "Describe the implementation plan, affected files, and tests.",
            "Keep the change minimal and reversible.",
        ],
        "qa": [
            "Translate the task into smoke, regression, and edge-case checks.",
        ],
    }
    steps = role_hints.get(role, [
        "Clarify the desired outcome and affected contracts.",
        "Propose the smallest safe change that meets the objective.",
    ])
    deliverables = [
        "A concrete implementation or review plan.",
        "A verification checklist tied to the requested change.",
        "A short rollback note if the task changes behavior or data.",
    ]
    lines = [
        f"# {role} offline work packet\n\n",
        f"Task: {task_id or 'UNSPECIFIED'}\n\n",
        "## Objective\n",
        (objective.strip() or "No explicit objective was provided.") + "\n\n",
        "## Working assumptions\n",
    ]
    for item in assumptions:
        lines.append(f"- {item}\n")
    if stream_id or project_id:
        lines.append("\n## Context\n")
        if stream_id:
            lines.append(f"- Stream: `{stream_id}`\n")
        if project_id:
            lines.append(f"- Project: `{project_id}`\n")
    lines.append("\n## Proposed steps\n")
    for idx, step in enumerate(steps, start=1):
        lines.append(f"{idx}. {step}\n")
    lines.append("\n## Expected deliverables\n")
    for item in deliverables:
        lines.append(f"- {item}\n")
    lines.append("\n## Verification\n")
    lines.append("- Confirm the result matches the stated objective.\n")
    lines.append("- Add or update tests/checklists for the touched behavior.\n")
    lines.append("- Record any contract or rollback note required for review.\n")
    return "".join(lines)

# === NoemaForge Autodoc Function Header ===
# Function: _pm_logic(ctx: Dict[str, Any], run_id: str, trace_id: str)
# Purpose: Implement the routine ' pm logic'.
# Inputs:
#   - ctx: Dict[str, Any]
#   - run_id: str
#   - trace_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - list, get, sort, str, _choose_specialist, startswith, _has_role, _nowz, _prio_idx
# Returns / emits: Dict[str, Any]
# Key locals:
#   - backlog, baton, from_role, items, nxt, roster_roles, task_id, title, to_role
# === End NoemaForge Autodoc Function Header ===
def _pm_logic(ctx: Dict[str, Any], run_id: str, trace_id: str) -> Dict[str, Any]:
    roster_roles = list(ctx.get("roster_roles") or [])
    backlog = ctx.get("backlog") or {"items": []}
    baton = ctx.get("baton")

    # If baton exists, decide how to react.
    if baton:
        from_role = str(baton.get("from_role") or "")
        task_id = str(baton.get("task_id") or "")
        # If QA already checked, close task.
        if from_role == "qa" and task_id.startswith("T-"):
            return {
                "status": "OK",
                "run_id": run_id,
                "role": "pm",
                "trace_id": trace_id,
                "freeze_summary": f"PM received QA result for {task_id} at {_nowz()}",
                "pm": {"proposed_action": "CLOSE_TASK", "task_id": task_id, "notes": "QA completed"},
            }

        # Specialist delivered => request QA if available, else close.
        if from_role and from_role not in ("pm", "system") and task_id.startswith("T-"):
            if _has_role(roster_roles, "qa"):
                return {
                    "status": "OK",
                    "run_id": run_id,
                    "role": "pm",
                    "trace_id": trace_id,
                    "freeze_summary": f"PM received specialist result for {task_id} and requests QA at {_nowz()}",
                    "pm": {"proposed_action": "REQUEST_QA", "task_id": task_id, "notes": f"from {from_role}"},
                }
            return {
                "status": "OK",
                "run_id": run_id,
                "role": "pm",
                "trace_id": trace_id,
                "freeze_summary": f"PM received specialist result for {task_id} and closes (no QA) at {_nowz()}",
                "pm": {"proposed_action": "CLOSE_TASK", "task_id": task_id, "notes": "no QA"},
            }

    # Otherwise: assign next todo.
    items = [it for it in (backlog.get("items") or []) if it.get("status") == "todo"]
    if not items:
        return {
            "status": "OK",
            "run_id": run_id,
            "role": "pm",
            "trace_id": trace_id,
            "freeze_summary": f"PM idle at {_nowz()} (no todo)",
            "pm": {"proposed_action": "IDLE", "notes": "no todo"},
        }

    items.sort(key=lambda it: (_prio_idx(it.get("priority_class")), it.get("created_at") or ""))
    nxt = items[0]
    task_id = str(nxt.get("id") or "")
    title = str(nxt.get("title") or "")
    to_role = _choose_specialist(roster_roles, title)

    return {
        "status": "OK",
        "run_id": run_id,
        "role": "pm",
        "trace_id": trace_id,
        "freeze_summary": f"PM assigns {task_id} -> {to_role} at {_nowz()}\nTitle: {title}",
        "pm": {"proposed_action": "ASSIGN", "task_id": task_id, "to_role": to_role, "notes": title},
    }


# === NoemaForge Autodoc Function Header ===
# Function: _specialist_logic(ctx: Dict[str, Any], role: str, run_id: str, trace_id: str)
# Purpose: Implement the routine ' specialist logic'.
# Inputs:
#   - ctx: Dict[str, Any]
#   - role: str
#   - run_id: str
#   - trace_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, get, exists, _toolproxy_call, _nowz, dumps
# Returns / emits: Dict[str, Any]
# Side effects:
#   - serializes structured data
# Key locals:
#   - baton, cap, content, objective, out_path, prompt, req, resp, task_id, tool_sock, used_llm
# === End NoemaForge Autodoc Function Header ===
def _specialist_logic(ctx: Dict[str, Any], role: str, run_id: str, trace_id: str) -> Dict[str, Any]:
    baton = ctx.get("baton") or {}
    task_id = str(baton.get("task_id") or "")
    objective = str(baton.get("objective") or "")

    # Try to use LLM via ToolProxy
    tool_sock = os.environ.get("NOEMAFORGE_TOOLPROXY_SOCKET", "/run/noemaforge/toolproxy.sock")
    cap = os.environ.get("NOEMAFORGE_CAP_TOKEN", "")

    prompt = (
        "Ты — помощник разработчика. Сгенерируй практичный результат для задачи. "
        "Сначала кратко перечисли шаги, затем дай код/SQL/структуру. "
        "Всегда добавляй раздел 'Проверка' с командами или чеклистом.\n\n"
        f"Роль: {role}\n"
        f"Stream: {str(ctx.get('stream_id') or '')}\n"
        f"Task: {task_id}\n"
        f"Objective: {objective}\n"
    )

    content = ""
    used_llm = False
    if cap and os.path.exists(tool_sock):
        req = {
            "token": cap,
            "action": "llm.chat",
            "args": {
                "messages": [
                    {"role": "system", "content": "You are a careful engineering assistant."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 800,
            },
            "meta": {
                "run_id": run_id,
                "role": role,
                "project_id": str(ctx.get("project_id") or ""),
                "trace_id": trace_id,
                "stream_id": str(ctx.get("stream_id") or ""),
            },
        }
        resp = _toolproxy_call(tool_sock, req)
        if resp.get("ok") and resp.get("result"):
            used_llm = True
            try:
                content = resp["result"]["choices"][0]["message"]["content"]
            except Exception:
                content = json.dumps(resp["result"], ensure_ascii=False, indent=2)

    if not content:
        content = _offline_specialist_content(role=role, task_id=task_id, objective=objective, ctx=ctx)

    out_path = f"outputs/{task_id}/{role}.md" if task_id else f"outputs/UNKNOWN/{role}.md"

    return {
        "status": "OK",
        "run_id": run_id,
        "role": role,
        "trace_id": trace_id,
        "freeze_summary": f"{role} finished {task_id} at {_nowz()} (llm={used_llm})",
        "outputs": [{"path": out_path, "content": content}],
    }


# === NoemaForge Autodoc Function Header ===
# Function: _qa_logic(ctx: Dict[str, Any], run_id: str, trace_id: str)
# Purpose: Implement the routine ' qa logic'.
# Inputs:
#   - ctx: Dict[str, Any]
#   - run_id: str
#   - trace_id: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, get, append, _nowz, count, join
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - baton, o, ok, produced, reasons, report, task_id, txt
# === End NoemaForge Autodoc Function Header ===
def _qa_logic(ctx: Dict[str, Any], run_id: str, trace_id: str) -> Dict[str, Any]:
    baton = ctx.get("baton") or {}
    task_id = str(baton.get("task_id") or "")
    produced = ctx.get("produced_outputs") or []

    ok = False
    reasons: List[str] = []

    if not produced:
        reasons.append("no_outputs")
    else:
        # Basic checks: at least one output has >= 5 lines
        for o in produced:
            txt = str(o.get("content") or "")
            if txt.count("\n") >= 5:
                ok = True
                break
        if not ok:
            reasons.append("outputs_too_short")

    report = (
        f"# QA report\n\n"
        f"Task: {task_id}\n\n"
        f"OK: {ok}\n\n"
        f"Reasons: {', '.join(reasons) if reasons else 'n/a'}\n\n"
        f"Time: {_nowz()}\n"
    )

    return {
        "status": "OK",
        "run_id": run_id,
        "role": "qa",
        "trace_id": trace_id,
        "freeze_summary": f"QA checked {task_id} at {_nowz()} -> {'OK' if ok else 'FAIL'}",
        "qa": {"task_id": task_id, "ok": ok, "report": report},
    }


# === NoemaForge Autodoc Function Header ===
# Function: main(argv: List[str])
# Purpose: Implement the routine 'main'.
# Inputs:
#   - argv: List[str]
# Called by:
#   - bootstrap/microvm/noemaforge-microvm-run.py
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/brainui.py
#   - src/canary_runner.py
#   - src/doctor.py
#   - src/dream_cycle.py
# Calls:
#   - ArgumentParser, add_argument, parse_args, setdefault, _save_json, _load_json, get, encode, hexdigest, _pm_logic, _nowz, str
# Returns / emits: int
# Key locals:
#   - _ctx_sha, _payload, ap, args, ctx, res, role, run_id, trace_id
# === End NoemaForge Autodoc Function Header ===
def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True)
    ap.add_argument("--context", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--trace-id", required=True)
    args = ap.parse_args(argv)

    ctx = _load_json(args.context) or {}
    ctx.setdefault("project_id", os.environ.get("NOEMAFORGE_PROJECT_ID", ""))

    role = args.role
    run_id = args.run_id
    trace_id = args.trace_id

    try:
        if role == "pm":
            res = _pm_logic(ctx, run_id, trace_id)
        elif role == "qa":
            res = _qa_logic(ctx, run_id, trace_id)
        else:
            res = _specialist_logic(ctx, role, run_id, trace_id)
    except Exception as e:
        res = {
            "status": "ERROR",
            "run_id": run_id,
            "role": role,
            "trace_id": trace_id,
            "freeze_summary": f"role crashed: {e!r}",
        }


    # Minimal checkpoint for freeze/thaw (control-plane only).
    try:
        import hashlib as _hashlib
        import json as _json
        _payload = _json.dumps(ctx, ensure_ascii=False, sort_keys=True).encode("utf-8")
        _ctx_sha = _hashlib.sha256(_payload).hexdigest()
    except Exception:
        _ctx_sha = None

    res.setdefault(
        "checkpoint",
        {
            "role": role,
            "run_id": run_id,
            "trace_id": trace_id,
            "created_at": _nowz(),
            "context_sha256": _ctx_sha,
            "freeze_summary": str(res.get("freeze_summary") or ""),
        },
    )

    _save_json(args.out, res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
