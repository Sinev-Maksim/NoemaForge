#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/model_scorecards.py
Zone: release/package
Version: 0.32.2
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
# File: src/model_scorecards.py
# Purpose: Provide the module 'model_scorecards'.
# Invoked by / imported from:
#   - src/brainctl.py
#   - src/firstboot_eval.py
#   - src/surgeon_auto.py
# Public API / entry functions:
#   - class UnixHTTPConnection
#   - load_eval_suite
#   - run_scorecard
#   - main
# Inputs:
#   - --epoch-dir
#   - --model
#   - --stream
#   - --role
#   - --cap
#   - --suite
#   - --gateway-sock
#   - --scorecards-dir
#   - --no-sel
#   - Environment: NOEMAFORGE_MODEL_SCORECARDS, NOEMAFORGE_LLM_GATEWAY_SOCKET, NOEMAFORGE_DATASETS_DIR
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""model_scorecards.py (v0.11.1)

Surgeon model evaluation harness.

This is intentionally pragmatic:

* The *law* (eval cases, thresholds) lives in the Contract Epoch.
* The *measurements* (scorecards) live in state (/var/lib/noemaforge/model_scorecards).
* Role selection can then prefer models that scored well.

Scorecards are not canaries.
They can be recomputed at runtime without switching epochs.

We keep the evaluation primitive, offline-first, and deterministic where possible.
"""


import datetime as dt
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


try:
    from seclog import append as sel_append
except Exception:  # pragma: no cover
    sel_append = None  # type: ignore


# Unix socket HTTP client (same pattern as toolproxy)
import http.client
import socket


class UnixHTTPConnection(http.client.HTTPConnection):
    # === NoemaForge Autodoc Function Header ===
    # Function: __init__(self, unix_socket_path: str, timeout: float = 30.0)
    # Purpose: Implement the routine '  init  '.
    # Inputs:
    #   - self
    #   - unix_socket_path: str
    #   - timeout: float = 30.0
    # Called by:
    #   - src/team_scorecards.py
    #   - src/toolproxy.py
    # Calls:
    #   - __init__, super
    # Returns / emits: unspecified Python value
    # === End NoemaForge Autodoc Function Header ===
    def __init__(self, unix_socket_path: str, timeout: float = 30.0):
        super().__init__("localhost", timeout=timeout)
        self.unix_socket_path = unix_socket_path

    # === NoemaForge Autodoc Function Header ===
    # Function: connect(self)
    # Purpose: Implement the routine 'connect'.
    # Inputs:
    #   - self
    # Called by:
    #   - src/casebase.py
    #   - src/dream_cycle.py
    #   - src/flow_metrics.py
    #   - src/incident_metrics.py
    #   - src/incidents.py
    #   - src/knowledge/gatekeeper.py
    #   - src/knowledge/retrieval.py
    #   - src/knowledge/store.py
    # Calls:
    #   - socket, settimeout, connect
    # Returns / emits: unspecified Python value
    # Side effects:
    #   - opens a database or socket connection
    # === End NoemaForge Autodoc Function Header ===
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.unix_socket_path)


DEFAULT_SCORECARDS_DIR = os.environ.get("NOEMAFORGE_MODEL_SCORECARDS", "/var/lib/noemaforge/model_scorecards")
DEFAULT_GATEWAY_SOCKET = os.environ.get("NOEMAFORGE_LLM_GATEWAY_SOCKET", "/run/noemaforge/llm/gateway.sock")
SCORECARD_DEVICE_ALIASES = {"cuda": "gpu", "nvidia": "gpu", "cpu": "cpu", "gpu": "gpu"}


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
    with open(path, "r", encoding="utf-8") as f:
        if yaml is None:
            raise RuntimeError("PyYAML is required to load model scorecard suites")
        return yaml.safe_load(f) or {}


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
#   - src/prestart.py
#   - src/roles/role_entry.py
#   - src/scary_sweep.py
#   - src/sr_cycle.py
# Calls:
#   - makedirs, replace, dirname, open, dump
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f, tmp
# === End NoemaForge Autodoc Function Header ===
def _save_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# === NoemaForge Autodoc Function Header ===
# Function: _scorecard_path(model_id: str, stream_id: str, role: str, cap: str, root: str = DEFAULT_SCORECARDS_DIR)
# Purpose: Implement the routine ' scorecard path'.
# Inputs:
#   - model_id: str
#   - stream_id: str
#   - role: str
#   - cap: str
#   - root: str = DEFAULT_SCORECARDS_DIR
# Called by:
#   - src/model_installer_plan.py
#   - src/model_router.py
#   - src/surgeon_auto.py
# Calls:
#   - replace, join
# Returns / emits: str
# Key locals:
#   - fname, rid, sid
# === End NoemaForge Autodoc Function Header ===
def normalize_scorecard_device(runtime_device: str = "") -> str:
    value = (runtime_device or "").strip().lower()
    return SCORECARD_DEVICE_ALIASES.get(value, "unspecified")


def scorecard_device_root(root: str = DEFAULT_SCORECARDS_DIR, runtime_device: str = "") -> str:
    device = normalize_scorecard_device(runtime_device)
    if device in {"cpu", "gpu"}:
        return os.path.join(root, device)
    return root


def _scorecard_path(model_id: str, stream_id: str, role: str, cap: str, root: str = DEFAULT_SCORECARDS_DIR, runtime_device: str = "") -> str:
    sid = (stream_id or "").replace("/", "_")
    rid = (role or "").replace("/", "_")
    fname = f"{sid}__{rid}__{cap}.json"
    return os.path.join(scorecard_device_root(root, runtime_device), model_id, fname)


# === NoemaForge Autodoc Function Header ===
# Function: _gateway_chat(sock: str, model: str, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 256, timeout_sec: float = 60.0)
# Purpose: Call local gateway /v1/chat/completions.
# Inputs:
#   - sock: str
#   - model: str
#   - messages: List[Dict[str, str]]
#   - temperature: float = 0.2
#   - max_tokens: int = 256
#   - timeout_sec: float = 60.0
# Called by:
#   - src/team_scorecards.py
# Calls:
#   - encode, time, exists, UnixHTTPConnection, request, getresponse, read, close, dumps, loads, decode
# Returns / emits: Tuple[bool, Dict[str, Any], str, float]
# Side effects:
#   - serializes structured data
# Key locals:
#   - body, conn, data, ms, resp, t0
# === End NoemaForge Autodoc Function Header ===
def _gateway_chat(
    *,
    sock: str,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 256,
    timeout_sec: float = 60.0,
) -> Tuple[bool, Dict[str, Any], str, float]:
    """Call local gateway /v1/chat/completions.

    Returns (ok, response_json, reason, elapsed_ms)
    """
    if not os.path.exists(sock):
        return False, {}, "gateway_socket_missing", 0.0

    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    t0 = time.time()
    try:
        conn = UnixHTTPConnection(sock, timeout=timeout_sec)
        conn.request("POST", "/v1/chat/completions", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        ms = (time.time() - t0) * 1000.0
        if resp.status >= 300:
            return False, {"status": resp.status, "body": data.decode("utf-8", "replace")}, "gateway_error", ms
        try:
            return True, json.loads(data.decode("utf-8")), "ok", ms
        except Exception:
            return True, {"raw": data.decode("utf-8", "replace")}, "ok_nonjson", ms
    except Exception as e:
        ms = (time.time() - t0) * 1000.0
        return False, {}, f"gateway_unreachable:{e!r}", ms


# === NoemaForge Autodoc Function Header ===
# Function: _extract_text(resp: Dict[str, Any])
# Purpose: Implement the routine ' extract text'.
# Inputs:
#   - resp: Dict[str, Any]
# Called by:
#   - src/team_scorecards.py
# Calls:
#   - str
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _extract_text(resp: Dict[str, Any]) -> str:
    try:
        return str(resp["choices"][0]["message"]["content"])
    except Exception:
        return ""


# === NoemaForge Autodoc Function Header ===
# Function: _looks_like_json(s: str)
# Purpose: Implement the routine ' looks like json'.
# Inputs:
#   - s: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, startswith, endswith
# Returns / emits: bool
# Key locals:
#   - s
# === End NoemaForge Autodoc Function Header ===
def _looks_like_json(s: str) -> bool:
    s = (s or "").strip()
    return (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]"))


# === NoemaForge Autodoc Function Header ===
# Function: _json_parse_ok(s: str)
# Purpose: Implement the routine ' json parse ok'.
# Inputs:
#   - s: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - loads
# Returns / emits: bool
# === End NoemaForge Autodoc Function Header ===
def _json_parse_ok(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except Exception:
        return False


# === NoemaForge Autodoc Function Header ===
# Function: _try_parse_json(s: str)
# Purpose: Parse JSON and return (ok, obj).
# Inputs:
#   - s: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - loads
# Returns / emits: tuple[bool, Any]
# === End NoemaForge Autodoc Function Header ===
def _try_parse_json(s: str) -> tuple[bool, Any]:
    """Parse JSON and return (ok, obj)."""
    try:
        return True, json.loads(s)
    except Exception:
        return False, None



# === Dataset JSONL merge helpers ===

# === NoemaForge Autodoc Function Header ===
# Function: _brain_root_from_src()
# Purpose: Best-effort locate NoemaForge root directory.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - realpath, join, dirname
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _brain_root_from_src() -> str:
    """Best-effort locate NoemaForge root directory.

    We assume this file is located at <root>/src/model_scorecards.py.
    """
    return os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))


# === NoemaForge Autodoc Function Header ===
# Function: _iter_jsonl_files(base_dir: str, include_files: list[str] | None = None)
# Purpose: Return absolute paths to JSONL files to load.
# Inputs:
#   - base_dir: str
#   - include_files: list[str] | None = None
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isdir, sorted, join, listdir, endswith, isfile, append, lower
# Returns / emits: list[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - f, files, fp
# === End NoemaForge Autodoc Function Header ===
def _iter_jsonl_files(base_dir: str, include_files: list[str] | None = None) -> list[str]:
    """Return absolute paths to JSONL files to load."""
    if not base_dir:
        return []
    if not os.path.isdir(base_dir):
        return []
    files: list[str] = []
    if include_files:
        for f in include_files:
            fp = os.path.join(base_dir, f)
            if os.path.isfile(fp) and fp.lower().endswith('.jsonl'):
                files.append(fp)
    else:
        for f in sorted(os.listdir(base_dir)):
            if f.lower().endswith('.jsonl'):
                files.append(os.path.join(base_dir, f))
    return files


# === NoemaForge Autodoc Function Header ===
# Function: _merge_case(doc: Dict[str, Any], suite: str, cap: str, stream_id: str, role: str, case: Dict[str, Any])
# Purpose: Implement the routine ' merge case'.
# Inputs:
#   - doc: Dict[str, Any]
#   - suite: str
#   - cap: str
#   - stream_id: str
#   - role: str
#   - case: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - setdefault, strip, set, append, isinstance, dict, str, get
# Returns / emits: None
# Side effects:
#   - appends to logs or files
# Key locals:
#   - arr, cap_cases, cases, cid, existing, key, srec, suites
# === End NoemaForge Autodoc Function Header ===
def _merge_case(doc: Dict[str, Any], *, suite: str, cap: str, stream_id: str, role: str, case: Dict[str, Any]) -> None:
    suites = doc.setdefault('suites', {})
    srec = suites.setdefault(suite, {})
    cases = srec.setdefault('cases', {})
    cap_cases = cases.setdefault(cap, {})
    if not isinstance(cap_cases, dict):
        # legacy format; keep it but don't crash
        return
    key = f"{(stream_id or '').strip()}__{(role or '').strip()}".strip('_')
    if not key:
        key = (role or 'default').strip() or 'default'
    arr = cap_cases.setdefault(key, [])
    if not isinstance(arr, list):
        return

    cid = str(case.get('id') or '').strip()
    if not cid:
        return
    existing = set(str(x.get('id')) for x in arr if isinstance(x, dict) and x.get('id'))
    if cid in existing:
        return
    arr.append(dict(case))


# === NoemaForge Autodoc Function Header ===
# Function: _merge_jsonl_datasets(doc: Dict[str, Any], epoch_dir: str)
# Purpose: Merge JSONL datasets into the eval suite doc.
# Inputs:
#   - doc: Dict[str, Any]
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, isinstance, _iter_jsonl_files, strip, join, lower, startswith, _infer_stream_id, isabs, _brain_root_from_src, str, basename
# Returns / emits: Dict[str, Any]
# Key locals:
#   - auto, b, base_dir, cap, case, dcfg, doc, f, files, fp, include_files, ln
# === End NoemaForge Autodoc Function Header ===
def _merge_jsonl_datasets(doc: Dict[str, Any], epoch_dir: str) -> Dict[str, Any]:
    """Merge JSONL datasets into the eval suite doc.

    Motivation: keep YAML small, put most cases into append-only JSONL datasets.

    JSONL line format (minimal):
        {"id": "...", "stream_id": "dev.work", "role": "dev", "messages": [...], "expect": {...},
         "suite": "smoke", "cap": "llm"}

    If stream_id is missing, we try to infer it from the filename prefix:
        dev_work_*.jsonl -> dev.work
        writing_story_*.jsonl -> writing.story
        system_guard_*.jsonl -> system.guard
    """
    if not isinstance(doc, dict):
        doc = {}
    dcfg = (doc.get('datasets') or {}) if isinstance(doc.get('datasets'), dict) else {}

    auto = dcfg.get('auto_load')
    if auto is False:
        return doc

    base_dir = str(dcfg.get('base_dir') or '').strip() or os.environ.get('NOEMAFORGE_DATASETS_DIR', '').strip()
    if base_dir:
        # relative paths are interpreted from NoemaForge root
        if not os.path.isabs(base_dir):
            base_dir = os.path.join(_brain_root_from_src(), base_dir)
    else:
        base_dir = os.path.join(_brain_root_from_src(), 'datasets', 'role_eval_cases')

    include_files = dcfg.get('include_files')
    if isinstance(include_files, list):
        include_files = [str(x) for x in include_files]
    else:
        include_files = None

    files = _iter_jsonl_files(base_dir, include_files)
    if not files:
        return doc

    # === NoemaForge Autodoc Function Header ===
    # Function: _infer_stream_id(fn: str)
    # Purpose: Implement the routine ' infer stream id'.
    # Inputs:
    #   - fn: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - lower, startswith, basename
    # Returns / emits: str
    # Key locals:
    #   - b
    # === End NoemaForge Autodoc Function Header ===
    def _infer_stream_id(fn: str) -> str:
        b = os.path.basename(fn).lower()
        if b.startswith('dev_work'):
            return 'dev.work'
        if b.startswith('writing_story'):
            return 'writing.story'
        if b.startswith('system_guard'):
            return 'system.guard'
        return ''

    for fp in files:
        stream_default = _infer_stream_id(fp)
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                for ln_no, ln in enumerate(f, start=1):
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        obj = json.loads(ln)
                    except Exception:
                        # Best-effort: skip bad lines
                        continue
                    if not isinstance(obj, dict):
                        continue
                    suite = str(obj.get('suite') or 'smoke').strip().lower() or 'smoke'
                    cap = str(obj.get('cap') or 'llm').strip().lower() or 'llm'
                    stream_id = str(obj.get('stream_id') or obj.get('stream') or stream_default).strip()
                    role = str(obj.get('role') or '').strip()
                    case = {
                        'id': obj.get('id') or f"{os.path.basename(fp)}:{ln_no}",
                        'messages': obj.get('messages') or [],
                        'expect': obj.get('expect') or {},
                    }
                    _merge_case(doc, suite=suite, cap=cap, stream_id=stream_id, role=role, case=case)
        except Exception:
            continue

    return doc



# === NoemaForge Autodoc Function Header ===
# Function: load_eval_suite(epoch_dir: str)
# Purpose: Load eval suite YAML and merge optional JSONL datasets.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, exists, _merge_jsonl_datasets, isinstance, _load_yaml
# Returns / emits: Dict[str, Any]
# Key locals:
#   - doc, loaded, p
# === End NoemaForge Autodoc Function Header ===
def load_eval_suite(epoch_dir: str) -> Dict[str, Any]:
    """Load eval suite YAML and merge optional JSONL datasets."""
    doc: Dict[str, Any] = {}
    p = os.path.join(epoch_dir, "model-eval-suite.yaml")
    if os.path.exists(p):
        try:
            loaded = _load_yaml(p)
            if isinstance(loaded, dict):
                doc = loaded
        except Exception:
            doc = {}

    # Merge JSONL datasets (keeps YAML from exploding).
    try:
        doc = _merge_jsonl_datasets(doc, epoch_dir)
    except Exception:
        pass

    return doc if isinstance(doc, dict) else {}


# === NoemaForge Autodoc Function Header ===
# Function: _select_cases(doc: Dict[str, Any], suite: str, cap: str, stream_id: str = '', role: str = '')
# Purpose: Implement the routine ' select cases'.
# Inputs:
#   - doc: Dict[str, Any]
#   - suite: str
#   - cap: str
#   - stream_id: str = ''
#   - role: str = ''
# Called by:
#   - src/team_scorecards.py
# Calls:
#   - isinstance, get, strip, append, dict
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - c, cap_cases, cap_cases_raw, key1, key2, out, srec, suites
# === End NoemaForge Autodoc Function Header ===
def _select_cases(doc: Dict[str, Any], suite: str, cap: str, *, stream_id: str = "", role: str = "") -> List[Dict[str, Any]]:
    suites = doc.get("suites") or {}
    srec = suites.get(suite) or {}
    cap_cases_raw = (srec.get("cases") or {}).get(cap) or []

    # Backward-compatible formats:
    # 1) cases[cap] is a list of case dicts (legacy)
    # 2) cases[cap] is a dict mapping role (or stream__role) -> list of cases
    buckets: List[Any] = []
    if isinstance(cap_cases_raw, dict):
        key_role = (role or "").strip()
        key_stream_role = f"{(stream_id or '').strip()}__{(role or '').strip()}".strip("_")
        # Merge rather than replace: default cases provide universal coverage, while role and
        # stream-specific cases deepen the evaluation surface for model selection.
        buckets.extend([
            cap_cases_raw.get("default") or [],
            cap_cases_raw.get(key_role) or [],
            cap_cases_raw.get(key_stream_role) or [],
        ])
    else:
        buckets.append(cap_cases_raw)

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for bucket in buckets:
        for c in bucket if isinstance(bucket, list) else []:
            if not isinstance(c, dict) or not c.get("id"):
                continue
            cid = str(c.get("id") or "")
            if cid in seen:
                continue
            seen.add(cid)
            out.append(dict(c))
    return out

# === Expectation checks (extended) ===

# === NoemaForge Autodoc Function Header ===
# Function: _json_path_get(obj, path: str)
# Purpose: Get a value from parsed JSON by a simple dot path.
# Inputs:
#   - obj
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, append, match, group, isinstance, str, get, int, len
# Returns / emits: Any
# Side effects:
#   - appends to logs or files
# Key locals:
#   - buf, ch, cur, i, idx_s, in_br, key, m, p, part, parts
# === End NoemaForge Autodoc Function Header ===
def _json_path_get(obj: Any, path: str) -> Any:
    """Get a value from parsed JSON by a simple dot path.

    Supports: a.b.c, a.b[0].c, $.root.path and bare '$'.
    """
    if path is None:
        return None
    p = str(path).strip()
    if not p or p == '$':
        return obj
    if p.startswith('$.'):
        p = p[2:]
    elif p.startswith('$'):
        p = p[1:]
    if not p:
        return obj

    cur = obj
    parts: list[str] = []
    buf = ''
    in_br = False
    for ch in p:
        if ch == '.' and not in_br:
            if buf:
                parts.append(buf)
                buf = ''
            continue
        if ch == '[':
            in_br = True
        if ch == ']':
            in_br = False
        buf += ch
    if buf:
        parts.append(buf)

    for part in parts:
        if cur is None:
            return None
        m = re.match(r"^([A-Za-z0-9_\-]+)(\[(\d+)\])?$", part)
        if not m:
            return None
        key = m.group(1)
        idx_s = m.group(3)
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            return None
        if idx_s is not None:
            try:
                i = int(idx_s)
            except Exception:
                return None
            if isinstance(cur, list) and 0 <= i < len(cur):
                cur = cur[i]
            else:
                return None
    return cur


# === NoemaForge Autodoc Function Header ===
# Function: _schema_errors(value, schema, path: str = '$')
# Purpose: Validate a very small JSON-schema subset.
# Inputs:
#   - value
#   - schema
#   - path: str = '$'
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, isinstance, enumerate, items, extend, _schema_errors, str, append
# Returns / emits: list[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - errs, item_schema, k, props, req, t
# === End NoemaForge Autodoc Function Header ===
def _schema_errors(value: Any, schema: Any, path: str = '$') -> list[str]:
    """Validate a very small JSON-schema subset.

    Supported:
      - type: object|array|string|number|integer|boolean
      - required: [..]
      - properties: {k: <schema>}
      - items: <schema>

    Returns list of errors.
    """
    if not isinstance(schema, dict):
        return []
    errs: list[str] = []
    t = schema.get('type')
    if t:
        if t == 'object' and not isinstance(value, dict):
            return [f"{path}: expected object"]
        if t == 'array' and not isinstance(value, list):
            return [f"{path}: expected array"]
        if t == 'string' and not isinstance(value, str):
            return [f"{path}: expected string"]
        if t == 'number' and not isinstance(value, (int, float)):
            return [f"{path}: expected number"]
        if t == 'integer' and not isinstance(value, int):
            return [f"{path}: expected integer"]
        if t == 'boolean' and not isinstance(value, bool):
            return [f"{path}: expected boolean"]

    if isinstance(value, dict):
        req = schema.get('required')
        if isinstance(req, list):
            for k in req:
                if str(k) not in value:
                    errs.append(f"{path}: missing required key '{k}'")
        props = schema.get('properties')
        if isinstance(props, dict):
            for k, subs in props.items():
                if k in value:
                    errs.extend(_schema_errors(value.get(k), subs, path=f"{path}.{k}"))

    if isinstance(value, list) and isinstance(schema.get('items'), dict):
        item_schema = schema.get('items')
        for i, it in enumerate(value[:100]):
            errs.extend(_schema_errors(it, item_schema, path=f"{path}[{i}]"))

    return errs


# === NoemaForge Autodoc Function Header ===
# Function: _check_expectations(expect: Dict[str, Any], raw_text: str, parsed_ok: bool, parsed_obj)
# Purpose: Apply extended expectation checks.
# Inputs:
#   - expect: Dict[str, Any]
#   - raw_text: str
#   - parsed_ok: bool
#   - parsed_obj
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, bool, get, isinstance, len, append, str, _schema_errors, _json_path_get, search, float, abs
# Returns / emits: tuple[bool, Dict[str, Any], list[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - actual, checks, det, equals, errs, exp, failures, hit, k, num_ok_all, numeric, ok
# === End NoemaForge Autodoc Function Header ===
def _check_expectations(*, expect: Dict[str, Any], raw_text: str, parsed_ok: bool, parsed_obj: Any) -> tuple[bool, Dict[str, Any], list[str]]:
    """Apply extended expectation checks.

    Returns: (passed, checks, failures)
    """
    checks: Dict[str, Any] = {}
    failures: list[str] = []
    txt = (raw_text or '').strip()

    # Exact match (string)
    if 'exact' in expect:
        exp = str(expect.get('exact') or '').strip()
        ok = (txt == exp)
        checks['exact'] = ok
        if not ok:
            failures.append('exact_mismatch')

    # Regex must-match / must-not-match on raw text
    for key, negate in [('regex', False), ('regex_not', True)]:
        pats = expect.get(key)
        if pats is None:
            continue
        if isinstance(pats, str):
            pats = [pats]
        if not isinstance(pats, list):
            continue
        ok_all = True
        for p in pats:
            p = str(p)
            try:
                hit = re.search(p, txt, flags=re.MULTILINE) is not None
            except Exception:
                hit = False
            if negate:
                if hit:
                    ok_all = False
                    failures.append(f"regex_forbidden:{p}")
            else:
                if not hit:
                    ok_all = False
                    failures.append(f"regex_missing:{p}")
        checks[key] = ok_all

    # JSON parsing requirement
    if bool(expect.get('json')):
        checks['json'] = bool(parsed_ok)
        if not parsed_ok:
            failures.append('json_parse_failed')

    # Root keys requirement
    req_keys = expect.get('keys')
    if req_keys is not None:
        if isinstance(req_keys, str):
            req_keys = [req_keys]
        if isinstance(req_keys, list) and req_keys:
            ok = bool(parsed_ok) and isinstance(parsed_obj, dict)
            if ok:
                for k in req_keys:
                    if str(k) not in parsed_obj:
                        ok = False
                        break
            checks['keys'] = ok
            if not ok:
                failures.append('missing_required_keys')

    # Schema (subset)
    schema = expect.get('schema')
    if schema is not None:
        ok = bool(parsed_ok)
        errs: list[str] = []
        if ok:
            errs = _schema_errors(parsed_obj, schema, path='$')
            ok = (len(errs) == 0)
        checks['schema'] = {'ok': ok, 'errors': errs[:20]}
        if not ok:
            failures.append('schema_failed')

    # Numeric checks
    numeric = expect.get('numeric')
    if numeric is not None:
        specs = numeric
        if isinstance(specs, dict):
            specs = [specs]
        if not isinstance(specs, list):
            specs = []
        num_ok_all = True
        det: list[dict] = []
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            path = str(spec.get('path') or '').strip()
            equals = spec.get('equals')
            tol = spec.get('tolerance')
            try:
                tol_f = float(tol) if tol is not None else 0.0
            except Exception:
                tol_f = 0.0
            actual = _json_path_get(parsed_obj, path) if parsed_ok else None
            ok = False
            try:
                if equals is not None and actual is not None and isinstance(actual, (int, float)):
                    ok = abs(float(actual) - float(equals)) <= tol_f
            except Exception:
                ok = False
            det.append({'path': path, 'equals': equals, 'tolerance': tol_f, 'actual': actual, 'ok': ok})
            if not ok:
                num_ok_all = False
                failures.append(f"numeric_mismatch:{path}")
        checks['numeric'] = {'ok': num_ok_all, 'details': det}

    passed = (len(failures) == 0)
    return passed, checks, failures



# === NoemaForge Autodoc Function Header ===
# Function: run_scorecard(epoch_dir: str, model_id: str, stream_id: str, role: str, cap: str = 'llm', suite: str = 'smoke', gateway_socket: str = DEFAULT_GATEWAY_SOCKET, scorecards_dir: str = DEFAULT_SCORECARDS_DIR, emit_sel: bool = True)
# Purpose: Run eval cases and write scorecard JSON.
# Inputs:
#   - epoch_dir: str
#   - model_id: str
#   - stream_id: str
#   - role: str
#   - cap: str = 'llm'
#   - suite: str = 'smoke'
#   - gateway_socket: str = DEFAULT_GATEWAY_SOCKET
#   - scorecards_dir: str = DEFAULT_SCORECARDS_DIR
#   - emit_sel: bool = True
# Called by:
#   - src/brainctl.py
#   - src/firstboot_eval.py
#   - src/surgeon_auto.py
# Calls:
#   - lower, load_eval_suite, _select_cases, max, _scorecard_path, _save_json, str, len, float, _nowz, strip, get
# Returns / emits: Dict[str, Any]
# Key locals:
#   - avg_ms, c, cap, card, cases, cid, doc, expect, expect_json, json_ok, json_rate, lat_ms
# === End NoemaForge Autodoc Function Header ===
def run_scorecard(
    *,
    epoch_dir: str,
    model_id: str,
    stream_id: str,
    role: str,
    cap: str = "llm",
    suite: str = "smoke",
    gateway_socket: str = DEFAULT_GATEWAY_SOCKET,
    scorecards_dir: str = DEFAULT_SCORECARDS_DIR,
    runtime_device: str = "",
    emit_sel: bool = True,
) -> Dict[str, Any]:
    """Run eval cases and write scorecard JSON.

    cap: "llm" (chat) or "embed" (reserved)
    suite: "smoke" or "full"
    """
    cap = (cap or "llm").strip().lower()
    suite = (suite or "smoke").strip().lower()
    runtime_device = normalize_scorecard_device(runtime_device)
    if cap not in ("llm", "embed"):
        cap = "llm"
    if suite not in ("smoke", "full"):
        suite = "smoke"

    doc = load_eval_suite(epoch_dir)
    cases = _select_cases(doc, suite, cap, stream_id=stream_id, role=role)

    # Minimal fallback case if suite is missing.
    if not cases:
        cases = [
            {
                "id": "default-json",
                "messages": [
                    {"role": "system", "content": "Return valid JSON only."},
                    {"role": "user", "content": "Return {\"ok\": true, \"role\": \"" + role + "\"}."},
                ],
                "expect": {"json": True},
            }
        ]

    results: List[Dict[str, Any]] = []
    ok_count = 0
    json_ok = 0
    lat_ms: List[float] = []

    for c in cases:
        cid = str(c.get("id") or "")
        msgs = c.get("messages") or []
        if not isinstance(msgs, list):
            msgs = []
        msgs2: List[Dict[str, str]] = []
        for m in msgs:
            if isinstance(m, dict) and m.get("role") and m.get("content") is not None:
                msgs2.append({"role": str(m.get("role")), "content": str(m.get("content"))})

        if cap == "llm":
            ok, resp, reason, ms = _gateway_chat(sock=gateway_socket, model=model_id, messages=msgs2)
            txt = _extract_text(resp) if ok else ""
            expect = (c.get("expect") or {}) if isinstance(c.get("expect"), dict) else {}
            expect_json = bool(expect.get("json"))
            parsed_ok = False
            obj = None
            if expect_json and _looks_like_json(txt):
                parsed_ok, obj = _try_parse_json(txt)

            exp_ok, checks, failures = _check_expectations(expect=expect, raw_text=txt, parsed_ok=parsed_ok, parsed_obj=obj)
            passed = bool(ok) and bool(exp_ok)

            if passed:
                ok_count += 1
            if parsed_ok:
                json_ok += 1
            if ms > 0:
                lat_ms.append(ms)

            results.append(
                {
                    "case_id": cid,
                    "ok": bool(ok),
                    "passed": passed,
                    "reason": reason,
                    "elapsed_ms": ms,
                    "json_ok": parsed_ok,
                    "checks": checks,
                    "failures": failures,
                    "raw_chars": len(txt),
                }
            )
        else:
            # Reserved for embedding endpoints; not implemented in MVP.
            results.append({"case_id": cid, "ok": False, "passed": False, "reason": "embed_not_implemented"})

    total = max(1, len(results))
    pass_rate = float(ok_count) / float(total)
    avg_ms = float(sum(lat_ms) / max(1, len(lat_ms))) if lat_ms else 0.0
    json_rate = float(json_ok) / float(total)

    # A pragmatic composite score (0..1-ish)
    quality = pass_rate
    if cap == "llm" and avg_ms > 0:
        # Penalize slow models very lightly; keeps selection stable.
        quality = max(0.0, pass_rate - min(0.25, avg_ms / 60_000.0))

    card = {
        "apiVersion": "noemaforge.modelscorecard/v1",
        "kind": "ModelScorecard",
        "created_at": _nowz(),
        "model_id": model_id,
        "stream_id": stream_id,
        "role": role,
        "capability": cap,
        "suite": suite,
        "runtime_device": runtime_device,
        "pass_rate": pass_rate,
        "json_parse_rate": json_rate,
        "avg_latency_ms": avg_ms,
        "quality_score": quality,
        "cases": results,
    }

    out_path = _scorecard_path(model_id, stream_id, role, cap, root=scorecards_dir, runtime_device=runtime_device)
    _save_json(out_path, card)

    if emit_sel and sel_append is not None:
        try:
            sel_append({
                "severity": "info" if pass_rate >= 0.8 else "high",
                "type": "model_scorecard_updated",
                "model_id": model_id,
                "stream_id": stream_id,
                "role": role,
                "capability": cap,
                "suite": suite,
                "runtime_device": runtime_device,
                "pass_rate": pass_rate,
                "avg_latency_ms": avg_ms,
                "path": out_path,
            })
        except Exception:
            pass

    return {"ok": True, "path": out_path, "scorecard": card}


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
#   - ArgumentParser, add_argument, parse_args, run_scorecard, print, dumps
# Returns / emits: int
# Side effects:
#   - serializes structured data
#   - spawns subprocesses or workers
# Key locals:
#   - ap, args, res
# === End NoemaForge Autodoc Function Header ===
def main(argv: List[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--epoch-dir", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--stream", required=True)
    ap.add_argument("--role", required=True)
    ap.add_argument("--cap", default="llm", choices=["llm", "embed"])
    ap.add_argument("--suite", default="smoke", choices=["smoke", "full"])
    ap.add_argument("--gateway-sock", default=DEFAULT_GATEWAY_SOCKET)
    ap.add_argument("--scorecards-dir", default=DEFAULT_SCORECARDS_DIR)
    ap.add_argument("--runtime-device", default="", choices=["", "unspecified", "auto", "cpu", "gpu", "cuda"], help="Record scorecard under a device-specific cpu/ or gpu/ namespace when known.")
    ap.add_argument("--no-sel", action="store_true")
    args = ap.parse_args(argv)

    res = run_scorecard(
        epoch_dir=args.epoch_dir,
        model_id=args.model,
        stream_id=args.stream,
        role=args.role,
        cap=args.cap,
        suite=args.suite,
        gateway_socket=args.gateway_sock,
        scorecards_dir=args.scorecards_dir,
        runtime_device=args.runtime_device,
        emit_sel=not args.no_sel,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(os.sys.argv[1:]))
