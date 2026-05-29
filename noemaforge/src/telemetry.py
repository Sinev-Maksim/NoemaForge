#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/telemetry.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Collect or report NoemaForge telemetry and metric snapshots.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations


# === NoemaForge Autodoc File Header ===
# File: src/telemetry.py
# Purpose: Provide the module 'telemetry'.
# Invoked by / imported from:
#   - src/metrics_snapshot.py
#   - src/toolproxy.py
# Public API / entry functions:
#   - load_policy
#   - record_llm_call
#   - record_tool_call
# Inputs:
#   - Common path inputs: /opt/noemaforge/configs/observability-policy.yaml, /var/lib/noemaforge/telemetry
#   - Imports: __future__, datetime, hashlib, json, os, random, typing, yaml
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""telemetry.py (v0.20.4)

Offline-first observability for NoemaForge.

This module records *metadata* about:
  - LLM calls (chat/embed)
  - (optional) tool calls

Design goals
------------
1) No network.
2) Safe by default: avoid storing raw prompts/responses.
3) Robust: best-effort append; never break ToolProxy.
4) Epoch-scoped policy (observability-policy.yaml).
"""


import datetime as dt
import hashlib
import json
import os
import random
from typing import Any, Dict, Optional, Tuple


try:  # pragma: no cover
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

try:  # pragma: no cover
    from epoch import current_epoch_dir
except Exception:  # pragma: no cover
    current_epoch_dir = None  # type: ignore


DEFAULT_POLICY_PATH = "/opt/noemaforge/configs/observability-policy.yaml"


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
# Function: _sha256_text(s: str)
# Purpose: Implement the routine ' sha256 text'.
# Inputs:
#   - s: str
# Called by:
#   - src/pipelines/photos_diary.py
#   - src/team_memory_sync.py
# Calls:
#   - hexdigest, sha256, encode
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _sha256_text(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8", errors="ignore")).hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _load_yaml(path: str)
# Purpose: Implement the routine ' load yaml'.
# Inputs:
#   - path: str
# Called by:
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/canary_runner.py
#   - src/daily_scheduler.py
#   - src/fixture_bundle.py
#   - src/flow_metrics.py
#   - src/incidents.py
#   - src/knowledge/policy.py
# Calls:
#   - open, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_yaml(path: str) -> Dict[str, Any]:
    if yaml is None:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _policy_path()
# Purpose: Implement the routine ' policy path'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/fixture_bundle.py
#   - src/incidents.py
#   - src/llm_backends_manager.py
# Calls:
#   - current_epoch_dir, join, exists
# Returns / emits: str
# Key locals:
#   - cand, e
# === End NoemaForge Autodoc Function Header ===
def _policy_path() -> str:
    try:
        if current_epoch_dir is not None:
            e = current_epoch_dir()
            if e:
                cand = os.path.join(e, "observability-policy.yaml")
                if os.path.exists(cand):
                    return cand
    except Exception:
        pass
    return DEFAULT_POLICY_PATH


# === NoemaForge Autodoc Function Header ===
# Function: load_policy()
# Purpose: Implement the routine 'load policy'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/audit_remediation.py
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/daily_scheduler.py
#   - src/lsm.py
#   - src/maintenance.py
#   - src/resource_policy.py
#   - src/role_runner.py
# Calls:
#   - setdefault, _load_yaml, isinstance, get, _policy_path
# Returns / emits: Dict[str, Any]
# Key locals:
#   - pol, st
# === End NoemaForge Autodoc Function Header ===
def load_policy() -> Dict[str, Any]:
    pol = _load_yaml(_policy_path()) or {}
    if not isinstance(pol, dict):
        pol = {}
    pol.setdefault("enabled", True)
    pol.setdefault("storage", {})
    pol.setdefault("collection", {})
    pol.setdefault("metrics", {})
    # Safe defaults
    st = pol.get("storage") or {}
    st.setdefault("base_dir", "/var/lib/noemaforge/telemetry")
    st.setdefault("files", {})
    (st.get("files") or {}).setdefault("llm_calls", "llm_calls.jsonl")
    (st.get("files") or {}).setdefault("tool_calls", "tool_calls.jsonl")
    (st.get("files") or {}).setdefault("snapshots", "snapshots")
    (st.get("files") or {}).setdefault("exports", "exports")
    st.setdefault("rotation", {"max_file_mb": 256, "retention_days": 30})
    pol["storage"] = st
    return pol


# === NoemaForge Autodoc Function Header ===
# Function: _storage_paths(pol: Dict[str, Any])
# Purpose: Implement the routine ' storage paths'.
# Inputs:
#   - pol: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, get, join
# Returns / emits: Dict[str, str]
# Key locals:
#   - base, files, st
# === End NoemaForge Autodoc Function Header ===
def _storage_paths(pol: Dict[str, Any]) -> Dict[str, str]:
    st = pol.get("storage") or {}
    base = str(st.get("base_dir") or "/var/lib/noemaforge/telemetry")
    files = st.get("files") or {}
    return {
        "base": base,
        "llm_calls": os.path.join(base, str(files.get("llm_calls") or "llm_calls.jsonl")),
        "tool_calls": os.path.join(base, str(files.get("tool_calls") or "tool_calls.jsonl")),
        "snapshots": os.path.join(base, str(files.get("snapshots") or "snapshots")),
        "exports": os.path.join(base, str(files.get("exports") or "exports")),
    }


# === NoemaForge Autodoc Function Header ===
# Function: _should_sample(sample_rate: float)
# Purpose: Implement the routine ' should sample'.
# Inputs:
#   - sample_rate: float
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - float, random
# Returns / emits: bool
# Key locals:
#   - r
# === End NoemaForge Autodoc Function Header ===
def _should_sample(sample_rate: float) -> bool:
    try:
        r = float(sample_rate)
    except Exception:
        r = 1.0
    if r >= 1.0:
        return True
    if r <= 0.0:
        return False
    return random.random() <= r


# === NoemaForge Autodoc Function Header ===
# Function: _ensure_parent(path: str)
# Purpose: Implement the routine ' ensure parent'.
# Inputs:
#   - path: str
# Called by:
#   - src/dream_cycle.py
#   - src/roadmap.py
#   - src/session_memory_extractor.py
#   - src/task_tools.py
#   - src/taskqueue.py
#   - tools/prep/scan_tabs.py
#   - tools/prep/scan_tg.py
# Calls:
#   - makedirs, dirname
# Returns / emits: None
# Side effects:
#   - creates directories
# === End NoemaForge Autodoc Function Header ===
def _ensure_parent(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)


# === NoemaForge Autodoc Function Header ===
# Function: _rotate_if_needed(path: str, pol: Dict[str, Any])
# Purpose: Implement the routine ' rotate if needed'.
# Inputs:
#   - path: str
#   - pol: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - int, get, float, exists, strftime, replace, getsize, utcnow
# Returns / emits: None
# Key locals:
#   - max_bytes, max_mb, new, rot, ts
# === End NoemaForge Autodoc Function Header ===
def _rotate_if_needed(path: str, pol: Dict[str, Any]) -> None:
    rot = (pol.get("storage") or {}).get("rotation") or {}
    try:
        max_mb = float(rot.get("max_file_mb") or 256)
    except Exception:
        max_mb = 256.0
    max_bytes = int(max_mb * 1024 * 1024)
    try:
        if os.path.exists(path) and os.path.getsize(path) > max_bytes:
            ts = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            new = f"{path}.{ts}.rot"
            os.replace(path, new)
    except Exception:
        pass


# === NoemaForge Autodoc Function Header ===
# Function: _append_jsonl(path: str, obj: Dict[str, Any], pol: Dict[str, Any])
# Purpose: Implement the routine ' append jsonl'.
# Inputs:
#   - path: str
#   - obj: Dict[str, Any]
#   - pol: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _ensure_parent, _rotate_if_needed, dumps, open, write
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
# Key locals:
#   - f, line
# === End NoemaForge Autodoc Function Header ===
def _append_jsonl(path: str, obj: Dict[str, Any], pol: Dict[str, Any]) -> None:
    _ensure_parent(path)
    _rotate_if_needed(path, pol)
    line = json.dumps(obj, ensure_ascii=False)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line)
        f.write("\n")


# === NoemaForge Autodoc Function Header ===
# Function: _estimate_tokens_from_chars(n_chars: int)
# Purpose: Implement the routine ' estimate tokens from chars'.
# Inputs:
#   - n_chars: int
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - max, int
# Returns / emits: int
# === End NoemaForge Autodoc Function Header ===
def _estimate_tokens_from_chars(n_chars: int) -> int:
    # Very rough heuristic; good enough for trend monitoring when usage is absent.
    if n_chars <= 0:
        return 0
    return max(1, int(n_chars / 4))


# === NoemaForge Autodoc Function Header ===
# Function: _extract_chat_text_and_shape(payload: Dict[str, Any])
# Purpose: Implement the routine ' extract chat text and shape'.
# Inputs:
#   - payload: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, join, isinstance, append, len, str
# Returns / emits: Tuple[str, Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - c, m, meta, msgs, parts, roles, txt
# === End NoemaForge Autodoc Function Header ===
def _extract_chat_text_and_shape(payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    msgs = payload.get("messages")
    if not isinstance(msgs, list):
        return "", {"messages": 0}
    parts = []
    roles = []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        roles.append(str(m.get("role") or ""))
        c = m.get("content")
        if isinstance(c, str):
            parts.append(c)
    txt = "\n".join(parts)
    meta = {"messages": len(msgs), "roles": roles[:32]}
    return txt, meta


# === NoemaForge Autodoc Function Header ===
# Function: _extract_embed_text(payload: Dict[str, Any])
# Purpose: Implement the routine ' extract embed text'.
# Inputs:
#   - payload: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, isinstance, join
# Returns / emits: str
# Key locals:
#   - inp, parts
# === End NoemaForge Autodoc Function Header ===
def _extract_embed_text(payload: Dict[str, Any]) -> str:
    inp = payload.get("input")
    if isinstance(inp, str):
        return inp
    if isinstance(inp, list):
        # embeddings API: list[str]
        parts = [x for x in inp if isinstance(x, str)]
        return "\n".join(parts)
    return ""


# === NoemaForge Autodoc Function Header ===
# Function: _extract_response_text(result)
# Purpose: Implement the routine ' extract response text'.
# Inputs:
#   - result
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isinstance, get
# Returns / emits: str
# Key locals:
#   - c, choices, msg
# === End NoemaForge Autodoc Function Header ===
def _extract_response_text(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    # OpenAI-ish format.
    try:
        choices = result.get("choices")
        if isinstance(choices, list) and choices:
            msg = (choices[0] or {}).get("message")
            if isinstance(msg, dict):
                c = msg.get("content")
                if isinstance(c, str):
                    return c
    except Exception:
        pass
    return ""


# === NoemaForge Autodoc Function Header ===
# Function: _extract_usage(result)
# Purpose: Implement the routine ' extract usage'.
# Inputs:
#   - result
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, isinstance, int
# Returns / emits: Dict[str, Any]
# Key locals:
#   - k, out, u
# === End NoemaForge Autodoc Function Header ===
def _extract_usage(result: Any) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    u = result.get("usage")
    if not isinstance(u, dict):
        return {}
    out: Dict[str, Any] = {}
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        try:
            if k in u:
                out[k] = int(u.get(k) or 0)
        except Exception:
            continue
    return out


# === NoemaForge Autodoc Function Header ===
# Function: record_llm_call(actor: Dict[str, Any], trace_id: str, action: str, request_payload: Dict[str, Any], ok: bool, result, reason: str, elapsed_ms: Optional[int] = None)
# Purpose: Record one LLM call (chat/embed) metadata.
# Inputs:
#   - actor: Dict[str, Any]
#   - trace_id: str
#   - action: str
#   - request_payload: Dict[str, Any]
#   - ok: bool
#   - result
#   - reason: str
#   - elapsed_ms: Optional[int] = None
# Called by:
#   - src/toolproxy.py
# Calls:
#   - load_policy, _storage_paths, str, bool, _extract_response_text, _extract_usage, len, _estimate_tokens_from_chars, _append_jsonl, get, _should_sample, isinstance
# Returns / emits: None
# Side effects:
#   - appends to logs or files
# Key locals:
#   - coll, cpol, est_in, est_out, model, obj, path, paths, pol, project_id, prompt_len, prompt_txt
# === End NoemaForge Autodoc Function Header ===
def record_llm_call(
    *,
    actor: Dict[str, Any],
    trace_id: str,
    action: str,
    request_payload: Dict[str, Any],
    ok: bool,
    result: Any,
    reason: str,
    elapsed_ms: Optional[int] = None,
) -> None:
    """Record one LLM call (chat/embed) metadata.

    Best-effort: never raise.
    """

    try:
        pol = load_policy()
        if not bool(pol.get("enabled", True)):
            return
        coll = pol.get("collection") or {}

        if action == "llm.chat":
            cpol = coll.get("llm_calls") or {}
        else:
            cpol = coll.get("llm_calls") or {}

        if not bool(cpol.get("enabled", True)):
            return
        if not _should_sample(float(cpol.get("sample_rate") or 1.0)):
            return

        paths = _storage_paths(pol)
        path = paths["llm_calls"]

        model = str(request_payload.get("model") or "")
        stream_id = str(actor.get("stream_id") or "")
        role = str(actor.get("role") or "")
        project_id = str(actor.get("project_id") or "")
        run_id = str(actor.get("run_id") or "")

        red = (cpol.get("redact") or {}) if isinstance(cpol.get("redact"), dict) else {}
        store_prompt_text = bool(red.get("store_prompt_text", False))
        store_prompt_hash = bool(red.get("store_prompt_hash", True))
        store_prompt_len = bool(red.get("store_prompt_len", True))
        store_shape = bool(red.get("store_messages_shape", True))
        store_resp_text = bool(red.get("store_response_text", False))
        store_resp_len = bool(red.get("store_response_len", True))

        prompt_txt = ""
        shape: Dict[str, Any] = {}
        if action == "llm.chat":
            prompt_txt, shape = _extract_chat_text_and_shape(request_payload)
        elif action == "llm.embed":
            prompt_txt = _extract_embed_text(request_payload)
        resp_txt = _extract_response_text(result)
        usage = _extract_usage(result)

        prompt_len = len(prompt_txt)
        resp_len = len(resp_txt)

        # Fill missing token counts with estimates (kept separate).
        est_in = _estimate_tokens_from_chars(prompt_len)
        est_out = _estimate_tokens_from_chars(resp_len)

        obj: Dict[str, Any] = {
            "schema_version": "v1",
            "kind": "LLMCall",
            "ts": _nowz(),
            "trace_id": trace_id,
            "action": action,
            "ok": bool(ok),
            "reason": str(reason or ""),
            "elapsed_ms": int(elapsed_ms or 0),
            "actor": {
                "stream_id": stream_id,
                "role": role,
                "project_id": project_id,
                "run_id": run_id,
            },
            "model": model,
            "usage": {
                **usage,
                "estimated_prompt_tokens": est_in,
                "estimated_completion_tokens": est_out,
            },
        }

        if store_shape and shape:
            obj["prompt_shape"] = shape
        if store_prompt_len:
            obj["prompt_len"] = prompt_len
        if store_resp_len:
            obj["response_len"] = resp_len
        if store_prompt_hash:
            obj["prompt_sha256"] = _sha256_text(prompt_txt)
        if store_prompt_text:
            obj["prompt_text"] = prompt_txt[:8000]
        if store_resp_text:
            obj["response_text"] = resp_txt[:8000]

        _append_jsonl(path, obj, pol)
    except Exception:
        return


# === NoemaForge Autodoc Function Header ===
# Function: record_tool_call(actor: Dict[str, Any], trace_id: str, action: str, args: Dict[str, Any], ok: bool, decision: str, reason: str, elapsed_ms: Optional[int] = None)
# Purpose: Optional tool-call telemetry (metadata only).
# Inputs:
#   - actor: Dict[str, Any]
#   - trace_id: str
#   - action: str
#   - args: Dict[str, Any]
#   - ok: bool
#   - decision: str
#   - reason: str
#   - elapsed_ms: Optional[int] = None
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - load_policy, _storage_paths, bool, _append_jsonl, get, _should_sample, isinstance, _nowz, str, int, _sha256_text, float
# Returns / emits: None
# Side effects:
#   - appends to logs or files
# Key locals:
#   - coll, obj, path, paths, pol, red, store_args, store_args_hash, tpol
# === End NoemaForge Autodoc Function Header ===
def record_tool_call(
    *,
    actor: Dict[str, Any],
    trace_id: str,
    action: str,
    args: Dict[str, Any],
    ok: bool,
    decision: str,
    reason: str,
    elapsed_ms: Optional[int] = None,
) -> None:
    """Optional tool-call telemetry (metadata only)."""
    try:
        pol = load_policy()
        if not bool(pol.get("enabled", True)):
            return
        coll = pol.get("collection") or {}
        tpol = coll.get("tool_calls") or {}
        if not bool(tpol.get("enabled", False)):
            return
        if not _should_sample(float(tpol.get("sample_rate") or 0.25)):
            return
        paths = _storage_paths(pol)
        path = paths["tool_calls"]

        red = (tpol.get("redact") or {}) if isinstance(tpol.get("redact"), dict) else {}
        store_args = bool(red.get("store_args", False))
        store_args_hash = bool(red.get("store_args_hash", True))

        obj: Dict[str, Any] = {
            "schema_version": "v1",
            "kind": "ToolCall",
            "ts": _nowz(),
            "trace_id": trace_id,
            "action": action,
            "ok": bool(ok),
            "decision": str(decision or ""),
            "reason": str(reason or ""),
            "elapsed_ms": int(elapsed_ms or 0),
            "actor": {
                "stream_id": str(actor.get("stream_id") or ""),
                "role": str(actor.get("role") or ""),
                "project_id": str(actor.get("project_id") or ""),
                "run_id": str(actor.get("run_id") or ""),
            },
        }
        if store_args_hash:
            obj["args_sha256"] = _sha256_text(json.dumps(args, ensure_ascii=False, sort_keys=True))
        if store_args:
            obj["args"] = args
        _append_jsonl(path, obj, pol)
    except Exception:
        return
