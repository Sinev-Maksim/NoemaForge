#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/mcp_router.py
Zone: release/package
Version: 0.31.13.alpha-patched1
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
# File: src/mcp_router.py
# Purpose: Provide offline-first MCP-like adapter listing, validation, and execution helpers for ToolProxy.
# Invoked by / imported from:
#   - src/toolproxy.py
#   - tests/test_mcp_router.py
# Public API / entry functions:
#   - load_adapter_catalog
#   - list_adapters
#   - resolve_adapter
#   - build_call_envelope
#   - runtime_action
#   - prepare_tool_action
# Inputs:
#   - Common path inputs: /opt/noemaforge/configs/mcp-adapters.yaml, /opt/noemaforge/docs, /opt/noemaforge/src, /opt/noemaforge/configs, seed_data/mcp/issues.sample.json
# Output formats / side effects:
#   - JSON-like Python dictionaries that can be serialized by ToolProxy or tests.
# AutoDoc: refreshed 2026-04-10 (manual, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""mcp_router.py (v0.26.4)

Offline-first MCP-like adapter runtime.

This module keeps the MCP surface usable without requiring a separate bundle. It
supports two execution modes:

- `local`: execute a deterministic built-in adapter implementation.
- `bundle`: build a plugin envelope for a future attested bundle runtime.

The current seed catalog ships with local read-only adapters so that `mcp.*`
actions become functional immediately after rollout gating is lifted. No network
access occurs here and ToolProxy remains the only runtime entrypoint.
"""


import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # type: ignore


DEFAULT_CATALOG_PATH = "/opt/noemaforge/configs/mcp-adapters.yaml"
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
_DEFAULT_SEARCH_EXTS = {".md", ".txt", ".rst", ".py", ".json", ".yaml", ".yml", ".sh", ".ps1"}


def _parse_scalar(value: str) -> Any:
    text = str(value or "").strip()
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    return text


def _load_simple_catalog_yaml(text: str) -> Dict[str, Any]:
    doc: Dict[str, Any] = {}
    adapters: List[Dict[str, Any]] = []
    in_adapters = False
    current: Optional[Dict[str, Any]] = None
    current_list_key = ""

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()

        if not in_adapters:
            if ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key == "adapters" and not value:
                in_adapters = True
                doc["adapters"] = adapters
            else:
                doc[key] = _parse_scalar(value)
            continue

        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if ":" in item:
                current = {}
                adapters.append(current)
                key, value = item.split(":", 1)
                current[key.strip()] = _parse_scalar(value)
                current_list_key = ""
            elif current is not None and current_list_key:
                current.setdefault(current_list_key, []).append(_parse_scalar(item))
            continue

        if current is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value:
                current[key] = _parse_scalar(value)
                current_list_key = ""
            else:
                current[key] = []
                current_list_key = key

    doc["adapters"] = adapters
    return doc


# === NoemaForge Autodoc Function Header ===
# Function: _load_yaml(path: str)
# Purpose: Load a YAML mapping from disk.
# Inputs:
#   - path: str
# Called by:
#   - load_adapter_catalog
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads files
# === End NoemaForge Autodoc Function Header ===
def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        if yaml is None:
            obj = _load_simple_catalog_yaml(f.read())
        else:
            obj = yaml.safe_load(f) or {}
    return obj if isinstance(obj, dict) else {}


# === NoemaForge Autodoc Function Header ===
# Function: _config_dir(path: str)
# Purpose: Return the directory containing a config file.
# Inputs:
#   - path: str
# Called by:
#   - load_adapter_catalog
#   - _resolve_paths
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _config_dir(path: str) -> str:
    return os.path.dirname(os.path.abspath(path or DEFAULT_CATALOG_PATH))


# === NoemaForge Autodoc Function Header ===
# Function: _resolve_paths(base_dir: str, raw: Any)
# Purpose: Resolve scalar or list-like path values relative to a base directory.
# Inputs:
#   - base_dir: str
#   - raw: Any
# Called by:
#   - load_adapter_catalog
# Returns / emits: List[str]
# === End NoemaForge Autodoc Function Header ===
def _resolve_paths(base_dir: str, raw: Any) -> List[str]:
    vals: List[str] = []
    if isinstance(raw, (list, tuple, set)):
        seq = raw
    else:
        seq = [raw]
    for item in seq:
        txt = str(item or "").strip()
        if not txt:
            continue
        vals.append(txt if os.path.isabs(txt) else os.path.abspath(os.path.join(base_dir, txt)))
    return vals


# === NoemaForge Autodoc Function Header ===
# Function: _safe_int(value: Any, default: int)
# Purpose: Coerce arbitrary values to an integer.
# Inputs:
#   - value: Any
#   - default: int
# Called by:
#   - _docs_search
#   - _issue_tracker
# Returns / emits: int
# === End NoemaForge Autodoc Function Header ===
def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


# === NoemaForge Autodoc Function Header ===
# Function: _read_text(path: str, max_bytes: int = 524288)
# Purpose: Read a text file conservatively.
# Inputs:
#   - path: str
#   - max_bytes: int = 524288
# Called by:
#   - _docs_search
# Returns / emits: Tuple[bool, str, str]
# Side effects:
#   - reads files
# === End NoemaForge Autodoc Function Header ===
def _read_text(path: str, max_bytes: int = 524288) -> Tuple[bool, str, str]:
    try:
        if os.path.getsize(path) > int(max_bytes):
            return False, "", "file_too_large"
        with open(path, "rb") as f:
            data = f.read(int(max_bytes) + 1)
        if len(data) > int(max_bytes):
            return False, "", "file_too_large"
        return True, data.decode("utf-8", errors="replace"), "ok"
    except Exception as e:
        return False, "", f"read_failed:{e!r}"


# === NoemaForge Autodoc Function Header ===
# Function: load_adapter_catalog(config_path: str = DEFAULT_CATALOG_PATH)
# Purpose: Load and normalize the MCP adapter catalog.
# Inputs:
#   - config_path: str = DEFAULT_CATALOG_PATH
# Called by:
#   - list_adapters
#   - resolve_adapter
#   - runtime_action
#   - prepare_tool_action
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads files
# === End NoemaForge Autodoc Function Header ===
def load_adapter_catalog(config_path: str = DEFAULT_CATALOG_PATH) -> Dict[str, Any]:
    if not str(config_path or "").strip():
        config_path = DEFAULT_CATALOG_PATH
    path = os.path.abspath(config_path)
    if not os.path.exists(path):
        return {
            "ok": False,
            "reason": "catalog_missing",
            "path": path,
            "enabled_by_default": False,
            "adapters": [],
        }

    base_dir = _config_dir(path)
    doc = _load_yaml(path)
    adapters = doc.get("adapters") if isinstance(doc.get("adapters"), list) else []
    out: List[Dict[str, Any]] = []
    for rec in adapters:
        if not isinstance(rec, dict):
            continue
        adapter_id = str(rec.get("id") or "").strip()
        if not adapter_id or not _SAFE_ID_RE.match(adapter_id):
            continue
        execution_mode = str(rec.get("mode") or rec.get("execution_mode") or "local").strip().lower()
        if execution_mode not in {"local", "bundle"}:
            execution_mode = "local"
        out.append(
            {
                "id": adapter_id,
                "title": str(rec.get("title") or adapter_id),
                "bundle_id": str(rec.get("bundle_id") or "mcp.bundle"),
                "allowlist_profile": str(rec.get("allowlist_profile") or "default"),
                "enabled": bool(rec.get("enabled", bool(doc.get("enabled_by_default", False)))),
                "mode": execution_mode,
                "local_handler": str(rec.get("local_handler") or "").strip(),
                "search_roots": _resolve_paths(base_dir, rec.get("search_roots") or rec.get("roots") or []),
                "search_extensions": [str(x).strip().lower() for x in (rec.get("search_extensions") or []) if str(x).strip()],
                "issues_path": (_resolve_paths(base_dir, rec.get("issues_path") or rec.get("issues_json_path") or "") or [""])[0],
                "tool_allowlist": [str(x).strip() for x in (rec.get("tool_allowlist") or []) if str(x).strip()],
            }
        )
    return {
        "ok": True,
        "path": path,
        "apiVersion": str(doc.get("apiVersion") or "noemaforge.mcp_adapters/v1"),
        "kind": str(doc.get("kind") or "MCPAdapterCatalog"),
        "enabled_by_default": bool(doc.get("enabled_by_default", False)),
        "adapters": out,
    }


# === NoemaForge Autodoc Function Header ===
# Function: list_adapters(config_path: str = DEFAULT_CATALOG_PATH, include_disabled: bool = True)
# Purpose: Return catalog adapters in a ToolProxy/UI-friendly structure.
# Inputs:
#   - config_path: str = DEFAULT_CATALOG_PATH
#   - include_disabled: bool = True
# Called by:
#   - prepare_tool_action
#   - runtime_action
#   - tests/test_mcp_router.py
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def list_adapters(config_path: str = DEFAULT_CATALOG_PATH, include_disabled: bool = True) -> Dict[str, Any]:
    cat = load_adapter_catalog(config_path=config_path)
    if not cat.get("ok"):
        return cat
    adapters = list(cat.get("adapters") or [])
    if not include_disabled:
        adapters = [a for a in adapters if a.get("enabled")]
    return {
        "ok": True,
        "source": cat.get("path"),
        "enabled_by_default": bool(cat.get("enabled_by_default")),
        "adapters": adapters,
        "count": len(adapters),
    }


# === NoemaForge Autodoc Function Header ===
# Function: resolve_adapter(adapter_id: str, config_path: str = DEFAULT_CATALOG_PATH)
# Purpose: Resolve a single adapter record by ID.
# Inputs:
#   - adapter_id: str
#   - config_path: str = DEFAULT_CATALOG_PATH
# Called by:
#   - build_call_envelope
#   - runtime_action
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# === End NoemaForge Autodoc Function Header ===
def resolve_adapter(adapter_id: str, config_path: str = DEFAULT_CATALOG_PATH) -> Tuple[bool, Dict[str, Any], str]:
    adapter_id = str(adapter_id or "").strip()
    if not adapter_id or not _SAFE_ID_RE.match(adapter_id):
        return False, {}, "adapter_id_invalid"
    cat = load_adapter_catalog(config_path=config_path)
    if not cat.get("ok"):
        return False, {}, str(cat.get("reason") or "catalog_missing")
    for rec in cat.get("adapters") or []:
        if isinstance(rec, dict) and str(rec.get("id") or "") == adapter_id:
            return True, dict(rec), "ok"
    return False, {}, "adapter_not_found"


# === NoemaForge Autodoc Function Header ===
# Function: build_call_envelope(adapter_id: str, tool_name: str, args: Dict[str, Any], config_path: str = DEFAULT_CATALOG_PATH, allow_disabled: bool = False)
# Purpose: Build a structured bundle-consumable envelope for a bundle-backed adapter call.
# Inputs:
#   - adapter_id: str
#   - tool_name: str
#   - args: Dict[str, Any]
#   - config_path: str = DEFAULT_CATALOG_PATH
#   - allow_disabled: bool = False
# Called by:
#   - prepare_tool_action
#   - runtime_action
#   - tests/test_mcp_router.py
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# === End NoemaForge Autodoc Function Header ===
def build_call_envelope(
    adapter_id: str,
    tool_name: str,
    args: Dict[str, Any],
    config_path: str = DEFAULT_CATALOG_PATH,
    allow_disabled: bool = False,
) -> Tuple[bool, Dict[str, Any], str]:
    ok, rec, reason = resolve_adapter(adapter_id=adapter_id, config_path=config_path)
    if not ok:
        return False, {}, reason
    tool_name = str(tool_name or "").strip()
    if not tool_name or not _SAFE_ID_RE.match(tool_name):
        return False, {}, "tool_name_invalid"
    payload = args if isinstance(args, dict) else {}
    if not bool(rec.get("enabled")) and not allow_disabled:
        return False, {"adapter": rec, "tool_name": tool_name}, "adapter_disabled"
    env = {
        "apiVersion": "noemaforge.mcp/v1",
        "kind": "MCPCallEnvelope",
        "adapter_id": str(rec.get("id")),
        "tool_name": tool_name,
        "bundle_id": str(rec.get("bundle_id") or "mcp.bundle"),
        "allowlist_profile": str(rec.get("allowlist_profile") or "default"),
        "input": dict(payload),
    }
    return True, env, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: _docs_search(adapter: Dict[str, Any], tool_name: str, payload: Dict[str, Any])
# Purpose: Execute a read-only local documentation search adapter.
# Inputs:
#   - adapter: Dict[str, Any]
#   - tool_name: str
#   - payload: Dict[str, Any]
# Called by:
#   - _execute_local_adapter
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Side effects:
#   - reads files
# === End NoemaForge Autodoc Function Header ===
def _docs_search(adapter: Dict[str, Any], tool_name: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
    if tool_name not in {"search", "query", "find"}:
        return False, {}, "tool_not_supported"
    query = str(payload.get("query") or payload.get("q") or "").strip()
    if not query:
        return False, {}, "missing_query"

    roots = [str(x) for x in (payload.get("search_roots") or []) if str(x).strip()] or [str(x) for x in (adapter.get("search_roots") or []) if str(x).strip()]
    if not roots:
        return False, {}, "search_roots_missing"
    extensions = {str(x).strip().lower() for x in (payload.get("extensions") or adapter.get("search_extensions") or []) if str(x).strip()}
    if not extensions:
        extensions = set(_DEFAULT_SEARCH_EXTS)

    terms = [t.lower() for t in re.findall(r"[A-Za-z0-9_.:-]+", query) if t.strip()]
    if not terms:
        return False, {}, "query_terms_missing"
    max_results = max(1, min(_safe_int(payload.get("max_results") or payload.get("limit"), 10), 100))

    results: List[Dict[str, Any]] = []
    scanned = 0
    for root in roots:
        rp = os.path.abspath(root)
        if not os.path.isdir(rp):
            continue
        for dirpath, dirnames, filenames in os.walk(rp):
            dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", ".venv", "venv"}]
            for name in filenames:
                path = os.path.abspath(os.path.join(dirpath, name))
                if os.path.splitext(path)[1].lower() not in extensions:
                    continue
                scanned += 1
                ok, text, _reason = _read_text(path)
                if not ok:
                    continue
                ltext = text.lower()
                score = sum(ltext.count(term) for term in terms)
                if score <= 0:
                    continue
                line_no = 0
                preview = ""
                for idx, line in enumerate(text.splitlines(), start=1):
                    if all(term in line.lower() for term in terms) or any(term in line.lower() for term in terms):
                        line_no = idx
                        preview = line.strip()[:240]
                        break
                results.append({"path": path, "line": line_no, "score": score, "preview": preview})
    results.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("path") or ""), int(item.get("line") or 0)))
    results = results[:max_results]
    return True, {
        "ok": True,
        "adapter_id": str(adapter.get("id") or "docs.search"),
        "tool_name": tool_name,
        "query": query,
        "scanned_files": scanned,
        "count": len(results),
        "results": results,
    }, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: _load_issues_json(path: str)
# Purpose: Load a list of issue records from JSON.
# Inputs:
#   - path: str
# Called by:
#   - _issue_tracker
# Returns / emits: Tuple[bool, List[Dict[str, Any]], str]
# Side effects:
#   - reads files
# === End NoemaForge Autodoc Function Header ===
def _load_issues_json(path: str) -> Tuple[bool, List[Dict[str, Any]], str]:
    if not path:
        return False, [], "issues_path_missing"
    if not os.path.exists(path):
        return False, [], "issues_path_missing"
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except Exception as e:
        return False, [], f"issues_load_failed:{e!r}"
    if not isinstance(obj, list):
        return False, [], "issues_payload_must_be_list"
    out: List[Dict[str, Any]] = []
    for rec in obj:
        if isinstance(rec, dict):
            out.append(dict(rec))
    return True, out, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: _issue_tracker(adapter: Dict[str, Any], tool_name: str, payload: Dict[str, Any])
# Purpose: Execute a read-only local issue tracker adapter.
# Inputs:
#   - adapter: Dict[str, Any]
#   - tool_name: str
#   - payload: Dict[str, Any]
# Called by:
#   - _execute_local_adapter
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Side effects:
#   - reads files
# === End NoemaForge Autodoc Function Header ===
def _issue_tracker(adapter: Dict[str, Any], tool_name: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
    issues_path = str(payload.get("issues_path") or adapter.get("issues_path") or "").strip()
    ok, issues, reason = _load_issues_json(issues_path)
    if not ok:
        return False, {}, reason

    max_results = max(1, min(_safe_int(payload.get("max_results") or payload.get("limit"), 20), 100))
    tool_name = str(tool_name or "").strip().lower()
    if tool_name == "get":
        issue_id = str(payload.get("issue_id") or payload.get("id") or "").strip()
        if not issue_id:
            return False, {}, "missing_issue_id"
        for rec in issues:
            if str(rec.get("id") or "").strip() == issue_id:
                return True, {"ok": True, "adapter_id": str(adapter.get("id") or "issue.tracker"), "tool_name": tool_name, "issue": rec}, "ok"
        return False, {}, "issue_not_found"

    query = str(payload.get("query") or payload.get("q") or "").strip().lower()
    state = str(payload.get("state") or "").strip().lower()
    tags = {str(x).strip().lower() for x in (payload.get("tags") or []) if str(x).strip()}
    filtered: List[Dict[str, Any]] = []
    for rec in issues:
        if state and str(rec.get("state") or "").strip().lower() != state:
            continue
        rec_tags = {str(x).strip().lower() for x in (rec.get("tags") or []) if str(x).strip()}
        if tags and not tags.issubset(rec_tags):
            continue
        hay = " ".join([
            str(rec.get("id") or ""),
            str(rec.get("title") or ""),
            str(rec.get("body") or ""),
            " ".join(sorted(rec_tags)),
            str(rec.get("state") or ""),
        ]).lower()
        if query and query not in hay:
            continue
        filtered.append(rec)

    filtered.sort(key=lambda rec: (str(rec.get("state") or ""), str(rec.get("id") or "")))
    if tool_name in {"list", "search", "query"}:
        return True, {
            "ok": True,
            "adapter_id": str(adapter.get("id") or "issue.tracker"),
            "tool_name": tool_name,
            "issues_path": issues_path,
            "count": min(len(filtered), max_results),
            "issues": filtered[:max_results],
        }, "ok"
    return False, {}, "tool_not_supported"


# === NoemaForge Autodoc Function Header ===
# Function: _execute_local_adapter(adapter: Dict[str, Any], tool_name: str, payload: Dict[str, Any])
# Purpose: Dispatch a local adapter implementation.
# Inputs:
#   - adapter: Dict[str, Any]
#   - tool_name: str
#   - payload: Dict[str, Any]
# Called by:
#   - runtime_action
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# === End NoemaForge Autodoc Function Header ===
def _execute_local_adapter(adapter: Dict[str, Any], tool_name: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
    handler = str(adapter.get("local_handler") or "").strip().lower()
    if handler == "docs_search":
        return _docs_search(adapter, tool_name, payload)
    if handler == "issue_tracker":
        return _issue_tracker(adapter, tool_name, payload)
    return False, {}, "local_handler_missing"


# === NoemaForge Autodoc Function Header ===
# Function: runtime_action(action: str, args: Dict[str, Any], config_path: str = DEFAULT_CATALOG_PATH)
# Purpose: Provide a ToolProxy-facing runtime entrypoint that returns either a local result or plugin args.
# Inputs:
#   - action: str
#   - args: Dict[str, Any]
#   - config_path: str = DEFAULT_CATALOG_PATH
# Called by:
#   - src/toolproxy.py
#   - tests/test_mcp_router.py
# Returns / emits: Tuple[str, Dict[str, Any], str]
# === End NoemaForge Autodoc Function Header ===
def runtime_action(action: str, args: Dict[str, Any], config_path: str = DEFAULT_CATALOG_PATH) -> Tuple[str, Dict[str, Any], str]:
    action = str(action or "").strip()
    args = args if isinstance(args, dict) else {}
    if action == "mcp.adapters.list":
        res = list_adapters(config_path=config_path, include_disabled=bool(args.get("include_disabled", True)))
        return ("local_result" if res.get("ok") else "error"), res, str(res.get("reason") or "ok")

    if action != "mcp.call":
        return "error", {}, "unsupported_action"

    adapter_id = str(args.get("adapter_id") or "").strip()
    tool_name = str(args.get("tool_name") or args.get("tool") or "").strip()
    payload = args.get("input") if isinstance(args.get("input"), dict) else args.get("args") if isinstance(args.get("args"), dict) else {}
    allow_disabled = bool(args.get("allow_disabled", False))

    ok, rec, reason = resolve_adapter(adapter_id=adapter_id, config_path=config_path)
    if not ok:
        return "error", {}, reason
    if not bool(rec.get("enabled")) and not allow_disabled:
        return "error", {"adapter": rec, "tool_name": tool_name}, "adapter_disabled"

    if str(rec.get("mode") or "local") == "local":
        ok2, result, local_reason = _execute_local_adapter(rec, tool_name, payload if isinstance(payload, dict) else {})
        return ("local_result" if ok2 else "error"), result, local_reason

    ok2, env, env_reason = build_call_envelope(
        adapter_id=adapter_id,
        tool_name=tool_name,
        args=payload if isinstance(payload, dict) else {},
        config_path=config_path,
        allow_disabled=allow_disabled,
    )
    if not ok2:
        return "error", env, env_reason
    norm = dict(args)
    norm["input"] = env
    return "plugin_args", norm, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: prepare_tool_action(action: str, args: Dict[str, Any], config_path: str = DEFAULT_CATALOG_PATH)
# Purpose: Backward-compatible preflight entrypoint for ToolProxy and tests.
# Inputs:
#   - action: str
#   - args: Dict[str, Any]
#   - config_path: str = DEFAULT_CATALOG_PATH
# Called by:
#   - tests/test_mcp_router.py
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# === End NoemaForge Autodoc Function Header ===
def prepare_tool_action(action: str, args: Dict[str, Any], config_path: str = DEFAULT_CATALOG_PATH) -> Tuple[bool, Dict[str, Any], str]:
    mode, payload, reason = runtime_action(action=action, args=args, config_path=config_path)
    if mode in {"local_result", "plugin_args"}:
        return True, payload, reason
    return False, payload, reason
