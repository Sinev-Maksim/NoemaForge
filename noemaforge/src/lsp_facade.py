#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/lsp_facade.py
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
# File: src/lsp_facade.py
# Purpose: Provide offline-first source diagnostics, symbol extraction, and reference lookup behind ToolProxy without requiring an external LSP bundle.
# Invoked by / imported from:
#   - src/toolproxy.py
#   - tests/test_lsp_facade.py
# Public API / entry functions:
#   - diagnostics
#   - symbols
#   - references
#   - prepare_tool_action
# Inputs:
#   - paths / root_paths / symbol / query style arguments passed through ToolProxy.
#   - Common path inputs: /workspace, /opt/noemaforge/src, /opt/noemaforge/configs, /opt/noemaforge/docs
# Output formats / side effects:
#   - JSON-like Python dictionaries that can be serialized by ToolProxy or tests.
# AutoDoc: refreshed 2026-04-10 (manual, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""lsp_facade.py (v0.26.4)

Offline-first LSP-like helpers for the seed tree.

This module intentionally does not spawn language servers and does not open any
network connections. It provides enough deterministic functionality to make
`lsp.*` actions operational immediately after rollout gating is lifted:

- `lsp.diagnostics`: syntax / parse diagnostics for Python, JSON, YAML, and text.
- `lsp.symbols`: lightweight symbol extraction for Python source files.
- `lsp.references`: project-wide textual reference lookup with word-boundary mode.

The facade keeps the same ToolProxy-only execution posture as the rest of the
system. A future attested bundle may replace or augment this implementation, but
no additional code is required to make the current actions functional.
"""


import ast
import json
import os
import re
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

import yaml

DEFAULT_ROOTS = [
    "/workspace",
    "/opt/noemaforge/src",
    "/opt/noemaforge/configs",
    "/opt/noemaforge/docs",
]
DEFAULT_EXTENSIONS = [".py", ".json", ".yaml", ".yml", ".md", ".txt", ".sh", ".ps1"]
_MAX_FILE_BYTES = 512 * 1024


# === NoemaForge Autodoc Function Header ===
# Function: _safe_int(value: Any, default: int)
# Purpose: Coerce arbitrary values to a bounded integer.
# Inputs:
#   - value: Any
#   - default: int
# Called by:
#   - diagnostics
#   - symbols
#   - references
# Returns / emits: int
# === End NoemaForge Autodoc Function Header ===
def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


# === NoemaForge Autodoc Function Header ===
# Function: _as_list(value: Any)
# Purpose: Normalize a scalar or list-like input into a list of non-empty strings.
# Inputs:
#   - value: Any
# Called by:
#   - _candidate_files
#   - diagnostics
#   - symbols
#   - references
# Returns / emits: List[str]
# === End NoemaForge Autodoc Function Header ===
def _as_list(value: Any) -> List[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    if str(value or "").strip():
        return [str(value).strip()]
    return []


# === NoemaForge Autodoc Function Header ===
# Function: _read_text(path: str, max_bytes: int = _MAX_FILE_BYTES)
# Purpose: Read a text file conservatively and return decoded text.
# Inputs:
#   - path: str
#   - max_bytes: int = _MAX_FILE_BYTES
# Called by:
#   - diagnostics
#   - symbols
#   - references
# Returns / emits: Tuple[bool, str, str]
# Side effects:
#   - reads files
# === End NoemaForge Autodoc Function Header ===
def _read_text(path: str, max_bytes: int = _MAX_FILE_BYTES) -> Tuple[bool, str, str]:
    try:
        if os.path.getsize(path) > int(max_bytes):
            return False, "", "file_too_large"
        with open(path, "rb") as f:
            data = f.read(int(max_bytes) + 1)
        if len(data) > int(max_bytes):
            return False, "", "file_too_large"
        text = data.decode("utf-8", errors="replace")
        return True, text, "ok"
    except Exception as e:
        return False, "", f"read_failed:{e!r}"


# === NoemaForge Autodoc Function Header ===
# Function: _candidate_files(paths: Optional[Sequence[str]] = None, root_paths: Optional[Sequence[str]] = None, extensions: Optional[Sequence[str]] = None)
# Purpose: Yield candidate source files under explicit paths or root directories.
# Inputs:
#   - paths: Optional[Sequence[str]] = None
#   - root_paths: Optional[Sequence[str]] = None
#   - extensions: Optional[Sequence[str]] = None
# Called by:
#   - diagnostics
#   - symbols
#   - references
# Returns / emits: Iterator[str]
# Side effects:
#   - reads filesystem metadata
# === End NoemaForge Autodoc Function Header ===
def _candidate_files(
    paths: Optional[Sequence[str]] = None,
    root_paths: Optional[Sequence[str]] = None,
    extensions: Optional[Sequence[str]] = None,
) -> Iterator[str]:
    seen: set[str] = set()
    exts = {str(x).lower() for x in (extensions or DEFAULT_EXTENSIONS)}

    for raw in list(paths or []):
        p = os.path.abspath(str(raw))
        if not os.path.exists(p):
            continue
        if os.path.isfile(p):
            if exts and os.path.splitext(p)[1].lower() not in exts:
                continue
            if p not in seen:
                seen.add(p)
                yield p
            continue
        for dirpath, _dirnames, filenames in os.walk(p):
            for name in filenames:
                fp = os.path.abspath(os.path.join(dirpath, name))
                if exts and os.path.splitext(fp)[1].lower() not in exts:
                    continue
                if fp not in seen:
                    seen.add(fp)
                    yield fp

    for raw in list(root_paths or []):
        p = os.path.abspath(str(raw))
        if not os.path.isdir(p):
            continue
        for dirpath, dirnames, filenames in os.walk(p):
            dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv", "node_modules"}]
            for name in filenames:
                fp = os.path.abspath(os.path.join(dirpath, name))
                if exts and os.path.splitext(fp)[1].lower() not in exts:
                    continue
                if fp not in seen:
                    seen.add(fp)
                    yield fp


# === NoemaForge Autodoc Function Header ===
# Function: _py_symbols(path: str, text: str)
# Purpose: Extract Python classes, functions, and imports from a file.
# Inputs:
#   - path: str
#   - text: str
# Called by:
#   - symbols
# Returns / emits: Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]
# === End NoemaForge Autodoc Function Header ===
def _py_symbols(path: str, text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    found: List[Dict[str, Any]] = []
    diagnostics: List[Dict[str, Any]] = []
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as e:
        diagnostics.append(
            {
                "path": path,
                "severity": "error",
                "code": "python.syntax",
                "message": str(e.msg or "invalid syntax"),
                "line": int(getattr(e, "lineno", 0) or 0),
                "column": int(getattr(e, "offset", 0) or 0),
            }
        )
        return found, diagnostics

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append(
                {
                    "path": path,
                    "name": str(node.name),
                    "kind": "function",
                    "line": int(getattr(node, "lineno", 0) or 0),
                    "column": int(getattr(node, "col_offset", 0) or 0),
                }
            )
        elif isinstance(node, ast.ClassDef):
            found.append(
                {
                    "path": path,
                    "name": str(node.name),
                    "kind": "class",
                    "line": int(getattr(node, "lineno", 0) or 0),
                    "column": int(getattr(node, "col_offset", 0) or 0),
                }
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found.append(
                    {
                        "path": path,
                        "name": str(alias.name),
                        "kind": "import",
                        "line": int(getattr(node, "lineno", 0) or 0),
                        "column": int(getattr(node, "col_offset", 0) or 0),
                    }
                )
        elif isinstance(node, ast.ImportFrom):
            mod = str(node.module or "")
            for alias in node.names:
                found.append(
                    {
                        "path": path,
                        "name": f"{mod}.{alias.name}" if mod else str(alias.name),
                        "kind": "import",
                        "line": int(getattr(node, "lineno", 0) or 0),
                        "column": int(getattr(node, "col_offset", 0) or 0),
                    }
                )
    return found, diagnostics


# === NoemaForge Autodoc Function Header ===
# Function: diagnostics(paths: Optional[Sequence[str]] = None, root_paths: Optional[Sequence[str]] = None, max_results: int = 200)
# Purpose: Generate lightweight parse diagnostics for candidate files.
# Inputs:
#   - paths: Optional[Sequence[str]] = None
#   - root_paths: Optional[Sequence[str]] = None
#   - max_results: int = 200
# Called by:
#   - prepare_tool_action
#   - tests/test_lsp_facade.py
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def diagnostics(
    paths: Optional[Sequence[str]] = None,
    root_paths: Optional[Sequence[str]] = None,
    max_results: int = 200,
) -> Dict[str, Any]:
    diags: List[Dict[str, Any]] = []
    scanned = 0
    max_results = max(1, _safe_int(max_results, 200))
    for path in _candidate_files(paths=paths, root_paths=root_paths or DEFAULT_ROOTS):
        scanned += 1
        ok, text, reason = _read_text(path)
        if not ok:
            diags.append({"path": path, "severity": "warning", "code": reason, "message": reason, "line": 0, "column": 0})
            if len(diags) >= max_results:
                break
            continue

        ext = os.path.splitext(path)[1].lower()
        if ext == ".py":
            _symbols, errs = _py_symbols(path, text)
            diags.extend(errs)
        elif ext == ".json":
            try:
                json.loads(text)
            except Exception as e:
                diags.append({"path": path, "severity": "error", "code": "json.parse", "message": str(e), "line": 0, "column": 0})
        elif ext in {".yaml", ".yml"}:
            try:
                yaml.safe_load(text)
            except Exception as e:
                diags.append({"path": path, "severity": "error", "code": "yaml.parse", "message": str(e), "line": 0, "column": 0})

        if len(diags) >= max_results:
            diags = diags[:max_results]
            break

    return {
        "ok": True,
        "kind": "lsp.diagnostics",
        "scanned_files": scanned,
        "count": len(diags),
        "diagnostics": diags,
    }


# === NoemaForge Autodoc Function Header ===
# Function: symbols(paths: Optional[Sequence[str]] = None, root_paths: Optional[Sequence[str]] = None, query: str = '', kinds: Optional[Sequence[str]] = None, max_results: int = 200)
# Purpose: Extract lightweight source symbols from Python files.
# Inputs:
#   - paths: Optional[Sequence[str]] = None
#   - root_paths: Optional[Sequence[str]] = None
#   - query: str = ''
#   - kinds: Optional[Sequence[str]] = None
#   - max_results: int = 200
# Called by:
#   - prepare_tool_action
#   - tests/test_lsp_facade.py
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def symbols(
    paths: Optional[Sequence[str]] = None,
    root_paths: Optional[Sequence[str]] = None,
    query: str = "",
    kinds: Optional[Sequence[str]] = None,
    max_results: int = 200,
) -> Dict[str, Any]:
    found: List[Dict[str, Any]] = []
    scanned = 0
    allow_kinds = {str(x).strip().lower() for x in (kinds or ["function", "class", "import"])}
    q = str(query or "").strip().lower()
    max_results = max(1, _safe_int(max_results, 200))

    for path in _candidate_files(paths=paths, root_paths=root_paths or DEFAULT_ROOTS, extensions=[".py"]):
        scanned += 1
        ok, text, _reason = _read_text(path)
        if not ok:
            continue
        syms, _diags = _py_symbols(path, text)
        for sym in syms:
            if str(sym.get("kind") or "").lower() not in allow_kinds:
                continue
            if q and q not in str(sym.get("name") or "").lower():
                continue
            found.append(sym)
            if len(found) >= max_results:
                return {"ok": True, "kind": "lsp.symbols", "scanned_files": scanned, "count": len(found), "symbols": found}

    return {"ok": True, "kind": "lsp.symbols", "scanned_files": scanned, "count": len(found), "symbols": found}


# === NoemaForge Autodoc Function Header ===
# Function: references(symbol: str, paths: Optional[Sequence[str]] = None, root_paths: Optional[Sequence[str]] = None, max_results: int = 200, word_boundary: bool = True)
# Purpose: Find textual references to a symbol across candidate files.
# Inputs:
#   - symbol: str
#   - paths: Optional[Sequence[str]] = None
#   - root_paths: Optional[Sequence[str]] = None
#   - max_results: int = 200
#   - word_boundary: bool = True
# Called by:
#   - prepare_tool_action
#   - tests/test_lsp_facade.py
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def references(
    symbol: str,
    paths: Optional[Sequence[str]] = None,
    root_paths: Optional[Sequence[str]] = None,
    max_results: int = 200,
    word_boundary: bool = True,
) -> Dict[str, Any]:
    sym = str(symbol or "").strip()
    if not sym:
        raise ValueError("missing_symbol")

    if word_boundary:
        rx = re.compile(rf"\b{re.escape(sym)}\b")
    else:
        rx = re.compile(re.escape(sym))

    matches: List[Dict[str, Any]] = []
    scanned = 0
    max_results = max(1, _safe_int(max_results, 200))

    for path in _candidate_files(paths=paths, root_paths=root_paths or DEFAULT_ROOTS):
        scanned += 1
        ok, text, _reason = _read_text(path)
        if not ok:
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            if rx.search(line):
                matches.append(
                    {
                        "path": path,
                        "line": idx,
                        "match": sym,
                        "preview": line.strip()[:240],
                    }
                )
                if len(matches) >= max_results:
                    return {"ok": True, "kind": "lsp.references", "scanned_files": scanned, "count": len(matches), "references": matches}

    return {"ok": True, "kind": "lsp.references", "scanned_files": scanned, "count": len(matches), "references": matches}


# === NoemaForge Autodoc Function Header ===
# Function: prepare_tool_action(action: str, args: Dict[str, Any])
# Purpose: Provide a ToolProxy-facing entrypoint for offline LSP-like actions.
# Inputs:
#   - action: str
#   - args: Dict[str, Any]
# Called by:
#   - src/toolproxy.py
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# === End NoemaForge Autodoc Function Header ===
def prepare_tool_action(action: str, args: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
    action = str(action or "").strip()
    args = args if isinstance(args, dict) else {}
    paths = _as_list(args.get("paths") or args.get("path"))
    root_paths = _as_list(args.get("root_paths") or args.get("roots")) or list(DEFAULT_ROOTS)
    max_results = _safe_int(args.get("max_results") or args.get("limit"), 200)
    try:
        if action == "lsp.diagnostics":
            return True, diagnostics(paths=paths, root_paths=root_paths, max_results=max_results), "ok"
        if action == "lsp.symbols":
            return True, symbols(paths=paths, root_paths=root_paths, query=str(args.get("query") or args.get("symbol") or ""), kinds=_as_list(args.get("kinds")), max_results=max_results), "ok"
        if action == "lsp.references":
            return True, references(symbol=str(args.get("symbol") or args.get("query") or ""), paths=paths, root_paths=root_paths, max_results=max_results, word_boundary=bool(args.get("word_boundary", True))), "ok"
        return False, {}, "unsupported_action"
    except Exception as e:
        return False, {"error": repr(e)}, "lsp_facade_failed"
