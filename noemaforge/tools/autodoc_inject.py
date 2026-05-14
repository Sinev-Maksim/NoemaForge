#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/autodoc_inject.py
Zone: release/package
Version: 0.31.13.alpha
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
# File: tools/autodoc_inject.py
# Purpose: Provide the module 'autodoc_inject'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - main
# Inputs:
#   - CLI arguments (argparse)
#   - Common path inputs: tools/windows/run_lab.cmd, tools/windows/noemaforge_check.ps1, tools/checker/noemaforge_check.py, src/brainctl.py, src/toolproxy.py, src/prestart.py
#   - Imports: __future__, ast, datetime, re, pathlib, typing
# Output formats / side effects:
#   - SQLite databases
#   - JSON files
#   - YAML files
#   - UTF-8 text files
#   - binary files
#   - copied filesystem artifacts
#   - CSV files
#   - Unix socket responses
#   - HTTP responses
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""Refresh NoemaForge code headers for Python modules and functions.

The generated comments are intentionally heuristic and designed for code review.
This injector is safe to re-run: existing NoemaForge autodoc blocks are removed
before new blocks are inserted.

Key improvements over the earlier injector:
- Uses AST-based imports and callsites so generated comments do not pollute
  later analysis.
- Adds explicit input/output summaries for files and functions.
- Regenerates docs/AUTODOC_INDEX.md for a consistent reviewer map.
"""


import ast
import datetime as dt
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple


ROOT_BEGIN = "# === NoemaForge Autodoc File Header ==="
ROOT_END = "# === End NoemaForge Autodoc File Header ==="
FUNC_BEGIN = "# === NoemaForge Autodoc Function Header ==="
FUNC_END = "# === End NoemaForge Autodoc Function Header ==="

SKIP_PARTS = {".git", "__pycache__", "reports", "noemaforge-lab", "data", ".mypy_cache", ".pytest_cache"}


# === NoemaForge Autodoc Function Header ===
# Function: _now_utc()
# Purpose: Implement the routine ' now utc'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strftime, now
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


# === NoemaForge Autodoc Function Header ===
# Function: _read_text(path: Path)
# Purpose: Implement the routine ' read text'.
# Inputs:
#   - path: Path
# Called by:
#   - src/hwscan.py
#   - src/lsm.py
#   - tools/checker/noemaforge_check.py
# Calls:
#   - read_text
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# === NoemaForge Autodoc Function Header ===
# Function: _write_text(path: Path, text: str)
# Purpose: Implement the routine ' write text'.
# Inputs:
#   - path: Path
#   - text: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - write_text
# Returns / emits: None
# Side effects:
#   - writes UTF-8 text
# === End NoemaForge Autodoc Function Header ===
def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


# === NoemaForge Autodoc Function Header ===
# Function: _iter_py_files(root: Path)
# Purpose: Implement the routine ' iter py files'.
# Inputs:
#   - root: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - rglob, sorted, relative_to, any, append
# Returns / emits: List[Path]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - files, path, rel
# === End NoemaForge Autodoc Function Header ===
def _iter_py_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root)
        if any(part in SKIP_PARTS for part in rel.parts):
            continue
        files.append(path)
    return sorted(files)


# === NoemaForge Autodoc Function Header ===
# Function: _iter_code_files(root: Path)
# Purpose: Implement the routine ' iter code files'.
# Inputs:
#   - root: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - rglob, sorted, relative_to, any, append, is_file, lower
# Returns / emits: List[Path]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - exts, files, path, rel
# === End NoemaForge Autodoc Function Header ===
def _iter_code_files(root: Path) -> List[Path]:
    exts = {".py", ".ps1", ".cmd", ".sh", ".go"}
    files: List[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in exts:
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_PARTS for part in rel.parts):
            continue
        files.append(path)
    return sorted(files)


# === NoemaForge Autodoc Function Header ===
# Function: _strip_autodoc_blocks(text: str)
# Purpose: Implement the routine ' strip autodoc blocks'.
# Inputs:
#   - text: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - splitlines, strip, append, join, endswith
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - line, lines, out, skip, stripped
# === End NoemaForge Autodoc Function Header ===
def _strip_autodoc_blocks(text: str) -> str:
    lines = text.splitlines()
    out: List[str] = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped == ROOT_BEGIN or stripped == FUNC_BEGIN:
            skip = True
            continue
        if stripped == ROOT_END or stripped == FUNC_END:
            skip = False
            continue
        if skip:
            continue
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


# === NoemaForge Autodoc Function Header ===
# Function: _strip_docstrings_for_regex(text: str)
# Purpose: Implement the routine ' strip docstrings for regex'.
# Inputs:
#   - text: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sub
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _strip_docstrings_for_regex(text: str) -> str:
    return re.sub(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', '""', text)


# === NoemaForge Autodoc Function Header ===
# Function: _clean_code_for_regex(text: str)
# Purpose: Implement the routine ' clean code for regex'.
# Inputs:
#   - text: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _strip_autodoc_blocks, _strip_docstrings_for_regex, splitlines, join, startswith, append, lstrip
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - line, out_lines, text
# === End NoemaForge Autodoc Function Header ===
def _clean_code_for_regex(text: str) -> str:
    text = _strip_autodoc_blocks(text)
    text = _strip_docstrings_for_regex(text)
    out_lines: List[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


# === NoemaForge Autodoc Function Header ===
# Function: _find_insert_index(lines: List[str])
# Purpose: Implement the routine ' find insert index'.
# Inputs:
#   - lines: List[str]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - startswith, match, len, strip
# Returns / emits: int
# Key locals:
#   - idx
# === End NoemaForge Autodoc Function Header ===
def _find_insert_index(lines: List[str]) -> int:
    idx = 0
    if idx < len(lines) and lines[idx].startswith("#!"):
        idx += 1
    if idx < len(lines) and re.match(r"^#\s*-\*-\s*coding\s*:\s*[^*]+-\*-", lines[idx]):
        idx += 1
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    return idx


# === NoemaForge Autodoc Function Header ===
# Function: _format_annotation(node: Optional[ast.AST])
# Purpose: Implement the routine ' format annotation'.
# Inputs:
#   - node: Optional[ast.AST]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - unparse
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _format_annotation(node: Optional[ast.AST]) -> str:
    if node is None:
        return "Any"
    try:
        return ast.unparse(node)
    except Exception:
        return "Any"


# === NoemaForge Autodoc Function Header ===
# Function: _format_params(args: ast.arguments)
# Purpose: Implement the routine ' format params'.
# Inputs:
#   - args: ast.arguments
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - list, zip, _format_annotation, append, getattr, add_arg, len, unparse
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - ann, base, combined, default_pad, defaults, params, posonly, regular
# === End NoemaForge Autodoc Function Header ===
def _format_params(args: ast.arguments) -> List[str]:
    params: List[str] = []

    # === NoemaForge Autodoc Function Header ===
    # Function: add_arg(a: ast.arg, default: Optional[ast.AST] = None)
    # Purpose: Implement the routine 'add arg'.
    # Inputs:
    #   - a: ast.arg
    #   - default: Optional[ast.AST] = None
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _format_annotation, append, unparse
    # Returns / emits: None
    # Side effects:
    #   - appends to logs or files
    # Key locals:
    #   - ann, base
    # === End NoemaForge Autodoc Function Header ===
    def add_arg(a: ast.arg, default: Optional[ast.AST] = None) -> None:
        ann = _format_annotation(a.annotation)
        base = f"{a.arg}: {ann}" if ann != "Any" else a.arg
        if default is not None:
            try:
                base += f" = {ast.unparse(default)}"
            except Exception:
                base += " = ..."
        params.append(base)

    posonly = list(getattr(args, "posonlyargs", []))
    regular = list(args.args)
    defaults = list(args.defaults)
    default_pad = [None] * (len(posonly) + len(regular) - len(defaults)) + defaults
    combined = posonly + regular
    for a, default in zip(combined, default_pad):
        add_arg(a, default)

    if args.vararg:
        ann = _format_annotation(args.vararg.annotation)
        params.append(f"*{args.vararg.arg}: {ann}" if ann != "Any" else f"*{args.vararg.arg}")
    for a, default in zip(args.kwonlyargs, args.kw_defaults):
        add_arg(a, default)
    if args.kwarg:
        ann = _format_annotation(args.kwarg.annotation)
        params.append(f"**{args.kwarg.arg}: {ann}" if ann != "Any" else f"**{args.kwarg.arg}")
    return params


# === NoemaForge Autodoc Function Header ===
# Function: _purpose_guess(path: Path)
# Purpose: Implement the routine ' purpose guess'.
# Inputs:
#   - path: Path
# Called by:
#   - tools/autodoc_inject_misc.py
# Calls:
#   - replace, str
# Returns / emits: str
# Key locals:
#   - curated, rel, stem
# === End NoemaForge Autodoc Function Header ===
def _purpose_guess(path: Path) -> str:
    rel = str(path).replace("\\", "/")
    stem = path.stem
    curated = {
        "noemaforge_core": "Boot the core runtime, coordinate projects/tasks, and enforce role-facing runtime rules.",
        "prestart": "Manage epoch-scoped changes, canary planning, validation, and apply/rollback preparation.",
        "toolproxy": "Serve as the only policy-gated runtime entry point for tools, LLM backends, and sensitive side effects.",
        "webgateway": "Fetch and stage external web content through policy gates and quarantine promotion.",
        "localgateway": "Broker local device access through typed connectors and safety controls.",
        "maintenance": "Run idle-cycle maintenance, scheduling, resource recovery, and background system housekeeping.",
        "taskqueue": "Persist and dispatch scheduled work with SQLite-backed queue state and audit metadata.",
        "brainui": "Expose a local UI for operator-visible snapshots, incidents, queues, and runtime state.",
        "pi_firewall": "Detect and scrub prompt-injection style content before promotion into trusted flows.",
        "brainctl": "Provide the main operator CLI for NoemaForge runtime, policy, gateway, and storage actions.",
    }
    if stem in curated:
        return curated[stem]
    if "/src/pipelines/" in rel:
        return f"Implement the deterministic pipeline '{stem}'."
    if "/src/knowledge/" in rel:
        return f"Implement the knowledge subsystem module '{stem}'."
    if "/tools/checker/" in rel:
        return f"Run offline integrity or attestation checks for '{stem}'."
    if "/tools/prep/" in rel:
        return f"Prepare or ingest external assets for '{stem}'."
    if "/tools/windows/" in rel:
        return f"Provide a Windows helper or entry script for '{stem}'."
    if "/tools/migrate/" in rel:
        return f"Run one-time migration logic for '{stem}'."
    if "/bootstrap/" in rel:
        return f"Bootstrap NoemaForge components for '{stem}'."
    return f"Provide the module '{stem}'."


# === NoemaForge Autodoc Function Header ===
# Function: _extract_env_vars(text: str)
# Purpose: Implement the routine ' extract env vars'.
# Inputs:
#   - text: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _clean_code_for_regex, set, extend, findall, add, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - clean, found, item, out, pat, patterns, seen
# === End NoemaForge Autodoc Function Header ===
def _extract_env_vars(text: str) -> List[str]:
    patterns = [
        r"os\.environ(?:\.get)?\(\s*['\"]([A-Za-z0-9_]+)['\"]",
        r"os\.getenv\(\s*['\"]([A-Za-z0-9_]+)['\"]",
        r"environ\.get\(\s*['\"]([A-Za-z0-9_]+)['\"]",
    ]
    found: List[str] = []
    clean = _clean_code_for_regex(text)
    for pat in patterns:
        found.extend(re.findall(pat, clean))
    out: List[str] = []
    seen: Set[str] = set()
    for item in found:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out[:12]


# === NoemaForge Autodoc Function Header ===
# Function: _extract_cli_inputs(text: str)
# Purpose: Implement the routine ' extract cli inputs'.
# Inputs:
#   - text: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _clean_code_for_regex, findall, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - args, clean, item, out
# === End NoemaForge Autodoc Function Header ===
def _extract_cli_inputs(text: str) -> List[str]:
    clean = _clean_code_for_regex(text)
    args = re.findall(r'add_argument\(\s*["\']([^"\']+)["\']', clean)
    out: List[str] = []
    for item in args:
        if item not in out:
            out.append(item)
    if "argparse.ArgumentParser" in clean or "ArgumentParser(" in clean:
        if not out:
            out.append("CLI arguments (argparse)")
    elif "click." in clean:
        out.append("CLI arguments (click)")
    return out[:16]


# === NoemaForge Autodoc Function Header ===
# Function: _extract_path_literals(text: str)
# Purpose: Implement the routine ' extract path literals'.
# Inputs:
#   - text: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _clean_code_for_regex, findall, startswith, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - candidates, clean, item, out
# === End NoemaForge Autodoc Function Header ===
def _extract_path_literals(text: str) -> List[str]:
    clean = _clean_code_for_regex(text)
    candidates = re.findall(r'["\']((?:/var|/run|/opt|/srv|/workspace|[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+)[A-Za-z0-9_./-]*)["\']', clean)
    out: List[str] = []
    for item in candidates:
        if item.startswith("http://") or item.startswith("https://"):
            continue
        if " " in item or "\t" in item:
            continue
        if item not in out:
            out.append(item)
    return out[:8]


# === NoemaForge Autodoc Function Header ===
# Function: _extract_outputs_hint(text: str)
# Purpose: Implement the routine ' extract outputs hint'.
# Inputs:
#   - text: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _clean_code_for_regex, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - clean, hints, mapping
# === End NoemaForge Autodoc Function Header ===
def _extract_outputs_hint(text: str) -> List[str]:
    clean = _clean_code_for_regex(text)
    hints: List[str] = []
    mapping = [
        ("sqlite3.connect", "SQLite databases"),
        ("json.dump", "JSON files"),
        ("yaml.safe_dump", "YAML files"),
        ("write_text(", "UTF-8 text files"),
        ("write_bytes(", "binary files"),
        ("shutil.copy2", "copied filesystem artifacts"),
        ("csv.writer", "CSV files"),
        ("socketserver", "Unix socket responses"),
        ("http.server", "HTTP responses"),
        ("ServeMux", "HTTP responses"),
    ]
    for needle, label in mapping:
        if needle in clean and label not in hints:
            hints.append(label)
    for ext, label in [(".json", "JSON files"), (".yaml", "YAML files"), (".yml", "YAML files"), (".sqlite", "SQLite databases"), (".md", "Markdown files")]:
        if ext in clean and label not in hints:
            hints.append(label)
    return hints[:10]


# === NoemaForge Autodoc Function Header ===
# Function: _public_api(tree: ast.AST)
# Purpose: Implement the routine ' public api'.
# Inputs:
#   - tree: ast.AST
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isinstance, append, startswith
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - items, node
# === End NoemaForge Autodoc Function Header ===
def _public_api(tree: ast.AST) -> List[str]:
    items: List[str] = []
    if not isinstance(tree, ast.Module):
        return items
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            items.append(f"class {node.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            items.append(node.name)
    return items[:12]


# === NoemaForge Autodoc Function Header ===
# Function: _collect_imports(tree: ast.AST)
# Purpose: Implement the routine ' collect imports'.
# Inputs:
#   - tree: ast.AST
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - walk, set, isinstance, add, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - alias, imports, item, node, out, seen
# === End NoemaForge Autodoc Function Header ===
def _collect_imports(tree: ast.AST) -> List[str]:
    imports: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    out: List[str] = []
    seen: Set[str] = set()
    for item in imports:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out[:16]


# === NoemaForge Autodoc Function Header ===
# Function: _module_name(root: Path, path: Path)
# Purpose: Implement the routine ' module name'.
# Inputs:
#   - root: Path
#   - path: Path
# Called by:
#   - tools/checker/noemaforge_check.py
# Calls:
#   - relative_to, list, join
# Returns / emits: str
# Key locals:
#   - parts, rel
# === End NoemaForge Autodoc Function Header ===
def _module_name(root: Path, path: Path) -> str:
    rel = path.relative_to(root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        return ".".join(parts[:-1])
    return ".".join(parts)[:-3]


# === NoemaForge Autodoc Function Header ===
# Function: _build_import_index(py_files: Sequence[Path], root: Path)
# Purpose: Implement the routine ' build import index'.
# Inputs:
#   - py_files: Sequence[Path]
#   - root: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - items, _module_name, replace, add, _strip_autodoc_blocks, set, split, walk, _read_text, parse, isinstance, str
# Returns / emits: Dict[str, Set[str]]
# Key locals:
#   - alias, base, current_mod, current_parts, imported, imported_modules, index, module, module_to_file, node, path, rel
# === End NoemaForge Autodoc Function Header ===
def _build_import_index(py_files: Sequence[Path], root: Path) -> Dict[str, Set[str]]:
    module_to_file = {_module_name(root, p): str(p.relative_to(root)).replace("\\", "/") for p in py_files}
    simple_to_files: Dict[str, Set[str]] = {}
    for mod, rel in module_to_file.items():
        simple_to_files.setdefault(mod.split(".")[-1], set()).add(rel)

    index: Dict[str, Set[str]] = {}
    for path in py_files:
        rel = str(path.relative_to(root)).replace("\\", "/")
        text = _strip_autodoc_blocks(_read_text(path))
        try:
            tree = ast.parse(text)
        except Exception:
            continue
        imported_modules: Set[str] = set()
        current_mod = _module_name(root, path)
        current_parts = current_mod.split(".")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    base = current_parts[:-1]
                    up = max(0, node.level - 1)
                    base = base[: len(base) - up] if up <= len(base) else []
                    if module:
                        imported_modules.add(".".join(base + [module]))
                    elif base:
                        imported_modules.add(".".join(base))
                elif module:
                    imported_modules.add(module)
        for imported in imported_modules:
            if imported in module_to_file:
                targets = [module_to_file[imported]]
            else:
                targets = sorted(simple_to_files.get(imported.split(".")[-1], set()))
            for target in targets:
                if target != rel:
                    index.setdefault(target, set()).add(rel)
    return index


# === NoemaForge Autodoc Function Header ===
# Function: _build_callsite_index(py_files: Sequence[Path], root: Path)
# Purpose: Implement the routine ' build callsite index'.
# Inputs:
#   - py_files: Sequence[Path]
#   - root: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - replace, _strip_autodoc_blocks, walk, _read_text, parse, isinstance, str, relative_to, add, setdefault, set
# Returns / emits: Dict[str, Set[str]]
# Key locals:
#   - func, idx, name, node, path, rel, text, tree
# === End NoemaForge Autodoc Function Header ===
def _build_callsite_index(py_files: Sequence[Path], root: Path) -> Dict[str, Set[str]]:
    idx: Dict[str, Set[str]] = {}
    for path in py_files:
        rel = str(path.relative_to(root)).replace("\\", "/")
        text = _strip_autodoc_blocks(_read_text(path))
        try:
            tree = ast.parse(text)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                else:
                    name = None
                if name:
                    idx.setdefault(name, set()).add(rel)
    return idx


# === NoemaForge Autodoc Function Header ===
# Function: _purpose_from_docstring(name: str, doc: str)
# Purpose: Implement the routine ' purpose from docstring'.
# Inputs:
#   - name: str
#   - doc: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - splitlines, strip, replace
# Returns / emits: str
# Key locals:
#   - first
# === End NoemaForge Autodoc Function Header ===
def _purpose_from_docstring(name: str, doc: str) -> str:
    first = (doc or "").strip().splitlines()
    if first:
        return first[0].strip()
    return f"Implement the routine '{name.replace('_', ' ')}'."


# === NoemaForge Autodoc Function Header ===
# Function: _collect_locals(fn: ast.AST)
# Purpose: Implement the routine ' collect locals'.
# Inputs:
#   - fn: ast.AST
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set, visit, sorted, generic_visit, isinstance, Visitor, add
# Returns / emits: List[str]
# Key locals:
#   - item, names, target
# === End NoemaForge Autodoc Function Header ===
def _collect_locals(fn: ast.AST) -> List[str]:
    names: Set[str] = set()

    class Visitor(ast.NodeVisitor):
        # === NoemaForge Autodoc Function Header ===
        # Function: visit_Assign(self, node: ast.Assign)
        # Purpose: Implement the routine 'visit Assign'.
        # Inputs:
        #   - self
        #   - node: ast.Assign
        # Called by:
        #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
        # Calls:
        #   - generic_visit, isinstance, add
        # Returns / emits: None
        # Key locals:
        #   - target
        # === End NoemaForge Autodoc Function Header ===
        def visit_Assign(self, node: ast.Assign) -> None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
            self.generic_visit(node)

        # === NoemaForge Autodoc Function Header ===
        # Function: visit_AnnAssign(self, node: ast.AnnAssign)
        # Purpose: Implement the routine 'visit AnnAssign'.
        # Inputs:
        #   - self
        #   - node: ast.AnnAssign
        # Called by:
        #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
        # Calls:
        #   - isinstance, generic_visit, add
        # Returns / emits: None
        # === End NoemaForge Autodoc Function Header ===
        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
            self.generic_visit(node)

        # === NoemaForge Autodoc Function Header ===
        # Function: visit_For(self, node: ast.For)
        # Purpose: Implement the routine 'visit For'.
        # Inputs:
        #   - self
        #   - node: ast.For
        # Called by:
        #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
        # Calls:
        #   - isinstance, generic_visit, add
        # Returns / emits: None
        # === End NoemaForge Autodoc Function Header ===
        def visit_For(self, node: ast.For) -> None:
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
            self.generic_visit(node)

        # === NoemaForge Autodoc Function Header ===
        # Function: visit_With(self, node: ast.With)
        # Purpose: Implement the routine 'visit With'.
        # Inputs:
        #   - self
        #   - node: ast.With
        # Called by:
        #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
        # Calls:
        #   - generic_visit, isinstance, add
        # Returns / emits: None
        # Key locals:
        #   - item
        # === End NoemaForge Autodoc Function Header ===
        def visit_With(self, node: ast.With) -> None:
            for item in node.items:
                if isinstance(item.optional_vars, ast.Name):
                    names.add(item.optional_vars.id)
            self.generic_visit(node)

    Visitor().visit(fn)
    return sorted(names)[:12]


# === NoemaForge Autodoc Function Header ===
# Function: _collect_calls(fn: ast.AST)
# Purpose: Implement the routine ' collect calls'.
# Inputs:
#   - fn: ast.AST
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - walk, set, isinstance, add, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - calls, func, item, node, out, seen
# === End NoemaForge Autodoc Function Header ===
def _collect_calls(fn: ast.AST) -> List[str]:
    calls: List[str] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                calls.append(func.id)
            elif isinstance(func, ast.Attribute):
                calls.append(func.attr)
    out: List[str] = []
    seen: Set[str] = set()
    for item in calls:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out[:12]


# === NoemaForge Autodoc Function Header ===
# Function: _return_summary(fn: ast.AST)
# Purpose: Implement the routine ' return summary'.
# Inputs:
#   - fn: ast.AST
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - walk, set, join, isinstance, _format_annotation, add, append, type
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - item, node, out, returns, seen, value
# === End NoemaForge Autodoc Function Header ===
def _return_summary(fn: ast.AST) -> str:
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.returns is not None:
        return _format_annotation(fn.returns)
    returns: List[str] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Return):
            value = node.value
            if value is None:
                returns.append("None")
            elif isinstance(value, ast.Dict):
                returns.append("dict")
            elif isinstance(value, ast.List):
                returns.append("list")
            elif isinstance(value, ast.Tuple):
                returns.append("tuple")
            elif isinstance(value, ast.Constant):
                returns.append(type(value.value).__name__)
            elif isinstance(value, ast.Name):
                returns.append(f"value from '{value.id}'")
            elif isinstance(value, ast.Call):
                if isinstance(value.func, ast.Name):
                    returns.append(f"result of {value.func.id}()")
                elif isinstance(value.func, ast.Attribute):
                    returns.append(f"result of .{value.func.attr}()")
    if not returns:
        return "unspecified Python value"
    out: List[str] = []
    seen: Set[str] = set()
    for item in returns:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return ", ".join(out[:4])


# === NoemaForge Autodoc Function Header ===
# Function: _side_effects_summary(fn: ast.AST)
# Purpose: Implement the routine ' side effects summary'.
# Inputs:
#   - fn: ast.AST
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, _collect_calls, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - joined, side, table
# === End NoemaForge Autodoc Function Header ===
def _side_effects_summary(fn: ast.AST) -> List[str]:
    joined = " ".join(_collect_calls(fn))
    side: List[str] = []
    table = [
        ("open", "reads or writes files"),
        ("write_text", "writes UTF-8 text"),
        ("write_bytes", "writes binary data"),
        ("dump", "serializes structured data"),
        ("connect", "opens a database or socket connection"),
        ("execute", "executes SQL or shell-like commands"),
        ("makedirs", "creates directories"),
        ("copy2", "copies filesystem artifacts"),
        ("run", "spawns subprocesses or workers"),
        ("append", "appends to logs or files"),
        ("send", "sends a response or network payload"),
    ]
    for needle, label in table:
        if needle in joined and label not in side:
            side.append(label)
    return side[:6]


# === NoemaForge Autodoc Function Header ===
# Function: _remove_existing_header(text: str, begin: str, end: str)
# Purpose: Implement the routine ' remove existing header'.
# Inputs:
#   - text: str
#   - begin: str
#   - end: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - splitlines, strip, append, join
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - line, lines, out, skip, stripped
# === End NoemaForge Autodoc Function Header ===
def _remove_existing_header(text: str, begin: str, end: str) -> str:
    lines = text.splitlines()
    out: List[str] = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped == begin:
            skip = True
            continue
        if stripped == end:
            skip = False
            continue
        if skip:
            continue
        out.append(line)
    return "\n".join(out) + "\n"


# === NoemaForge Autodoc Function Header ===
# Function: _insert_file_header(path: Path, root: Path, import_index: Dict[str, Set[str]])
# Purpose: Implement the routine ' insert file header'.
# Inputs:
#   - path: Path
#   - root: Path
#   - import_index: Dict[str, Set[str]]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - replace, _strip_autodoc_blocks, parse, _collect_imports, _purpose_guess, _extract_env_vars, _extract_cli_inputs, _extract_outputs_hint, _public_api, _extract_path_literals, append, _remove_existing_header
# Returns / emits: None
# Side effects:
#   - appends to logs or files
# Key locals:
#   - caller, callers, clean_text, cli_inputs, envs, file_lines, imports, inputs, ins, item, lines, new_lines
# === End NoemaForge Autodoc Function Header ===
def _insert_file_header(path: Path, root: Path, import_index: Dict[str, Set[str]]) -> None:
    rel = str(path.relative_to(root)).replace("\\", "/")
    clean_text = _strip_autodoc_blocks(_read_text(path))
    tree = ast.parse(clean_text)
    callers = sorted(import_index.get(rel, set()))[:10]
    imports = _collect_imports(tree)
    purpose = _purpose_guess(path)
    envs = _extract_env_vars(clean_text)
    cli_inputs = _extract_cli_inputs(clean_text)
    outputs = _extract_outputs_hint(clean_text)
    public_api = _public_api(tree)
    paths = _extract_path_literals(clean_text)

    lines: List[str] = []
    lines.append(ROOT_BEGIN)
    lines.append(f"# File: {rel}")
    lines.append(f"# Purpose: {purpose}")
    lines.append("# Invoked by / imported from:")
    if callers:
        for caller in callers:
            lines.append(f"#   - {caller}")
    else:
        lines.append("#   - No inbound Python import detected; treat as library leaf or direct entrypoint.")
    if public_api:
        lines.append("# Public API / entry functions:")
        for item in public_api:
            lines.append(f"#   - {item}")
    lines.append("# Inputs:")
    inputs: List[str] = []
    if cli_inputs:
        inputs.extend(cli_inputs)
    if envs:
        inputs.append("Environment: " + ", ".join(envs))
    if paths:
        inputs.append("Common path inputs: " + ", ".join(paths))
    if imports:
        inputs.append("Imports: " + ", ".join(imports[:8]))
    if inputs:
        for item in inputs[:10]:
            lines.append(f"#   - {item}")
    else:
        lines.append("#   - Imported Python calls only; no explicit CLI or environment inputs detected.")
    lines.append("# Output formats / side effects:")
    if outputs:
        for item in outputs:
            lines.append(f"#   - {item}")
    else:
        lines.append("#   - Returns Python values and/or performs in-memory orchestration.")
    lines.append(f"# AutoDoc: refreshed {_now_utc()} (heuristic, review before trusting for policy work)")
    lines.append(ROOT_END)
    lines.append("")

    text = _remove_existing_header(_read_text(path), ROOT_BEGIN, ROOT_END)
    file_lines = text.splitlines()
    ins = _find_insert_index(file_lines)
    new_lines = file_lines[:ins] + lines + file_lines[ins:]
    _write_text(path, "\n".join(new_lines) + "\n")


# === NoemaForge Autodoc Function Header ===
# Function: _insert_function_headers(path: Path, root: Path, callsite_index: Dict[str, Set[str]])
# Purpose: Implement the routine ' insert function headers'.
# Inputs:
#   - path: Path
#   - root: Path
#   - callsite_index: Dict[str, Set[str]]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - replace, _remove_existing_header, parse, splitlines, walk, sort, _write_text, _read_text, isinstance, max, getattr, _format_params
# Returns / emits: int
# Side effects:
#   - writes UTF-8 text
# Key locals:
#   - block, called_by, calls, dec_lines, effects, fns, idx, indent, inserted, item, lines, locals_
# === End NoemaForge Autodoc Function Header ===
def _insert_function_headers(path: Path, root: Path, callsite_index: Dict[str, Set[str]]) -> int:
    rel = str(path.relative_to(root)).replace("\\", "/")
    original = _remove_existing_header(_read_text(path), FUNC_BEGIN, FUNC_END)
    tree = ast.parse(original)
    lines = original.splitlines()

    fns: List[Tuple[int, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            dec_lines = [getattr(dec, "lineno", node.lineno) for dec in node.decorator_list] or [node.lineno]
            fns.append((min(dec_lines), node))
    fns.sort(key=lambda item: item[0], reverse=True)

    inserted = 0
    for lineno, node in fns:
        idx = max(0, lineno - 1)
        indent = re.match(r"^(\s*)", lines[idx]).group(1) if idx < len(lines) else ""
        name = getattr(node, "name", "<fn>")
        params = _format_params(node.args)
        called_by = sorted((callsite_index.get(name, set()) - {rel}))[:8]
        calls = _collect_calls(node)
        locals_ = _collect_locals(node)
        returns = _return_summary(node)
        effects = _side_effects_summary(node)
        purpose = _purpose_from_docstring(name, ast.get_docstring(node) or "")

        block: List[str] = []
        block.append(indent + FUNC_BEGIN)
        block.append(indent + f"# Function: {name}({', '.join(params)})")
        block.append(indent + f"# Purpose: {purpose}")
        block.append(indent + "# Inputs:")
        if params:
            for param in params:
                block.append(indent + f"#   - {param}")
        else:
            block.append(indent + "#   - No explicit parameters.")
        block.append(indent + "# Called by:")
        if called_by:
            for item in called_by:
                block.append(indent + f"#   - {item}")
        else:
            block.append(indent + "#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.")
        if calls:
            block.append(indent + "# Calls:")
            block.append(indent + "#   - " + ", ".join(calls))
        block.append(indent + f"# Returns / emits: {returns}")
        if effects:
            block.append(indent + "# Side effects:")
            for item in effects:
                block.append(indent + f"#   - {item}")
        if locals_:
            block.append(indent + "# Key locals:")
            block.append(indent + "#   - " + ", ".join(locals_))
        block.append(indent + FUNC_END)
        lines[idx:idx] = block
        inserted += 1

    _write_text(path, "\n".join(lines) + "\n")
    return inserted


# === NoemaForge Autodoc Function Header ===
# Function: _generate_autodoc_index(root: Path, py_files: Sequence[Path], code_files: Sequence[Path], import_index: Dict[str, Set[str]])
# Purpose: Implement the routine ' generate autodoc index'.
# Inputs:
#   - root: Path
#   - py_files: Sequence[Path]
#   - code_files: Sequence[Path]
#   - import_index: Dict[str, Set[str]]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - append, mkdir, _write_text, exists, replace, _purpose_guess, sorted, get, lower, join, str, set
# Returns / emits: None
# Side effects:
#   - writes UTF-8 text
#   - appends to logs or files
# Key locals:
#   - caller_note, callers, lines, out, path, purpose, rel
# === End NoemaForge Autodoc Function Header ===
def _generate_autodoc_index(root: Path, py_files: Sequence[Path], code_files: Sequence[Path], import_index: Dict[str, Set[str]]) -> None:
    out = root / "docs" / "AUTODOC_INDEX.md"
    lines: List[str] = []
    lines.append("# Autodoc index")
    lines.append("")
    lines.append("This file is autogenerated to help reviewers navigate the repo.")
    lines.append("The per-file and per-function headers are heuristic and should not be treated as security proofs.")
    lines.append("")
    lines.append("## Key entrypoints")
    lines.append("")
    for rel in [
        "tools/windows/run_lab.cmd",
        "tools/windows/noemaforge_check.ps1",
        "tools/checker/noemaforge_check.py",
        "src/brainctl.py",
        "src/toolproxy.py",
        "src/prestart.py",
    ]:
        if (root / rel).exists():
            lines.append(f"- `{rel}`")
    lines.append("")
    lines.append("## Python modules")
    lines.append("")
    for path in py_files:
        rel = str(path.relative_to(root)).replace("\\", "/")
        purpose = _purpose_guess(path)
        callers = sorted(import_index.get(rel, set()))
        caller_note = callers[0] if callers else "entrypoint or library leaf"
        lines.append(f"- `{rel}`  - {purpose} First inbound reference: {caller_note}.")
    lines.append("")
    lines.append("## Non-Python code files")
    lines.append("")
    for path in code_files:
        if path.suffix.lower() == ".py":
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        lines.append(f"- `{rel}`")
    out.parent.mkdir(parents=True, exist_ok=True)
    _write_text(out, "\n".join(lines) + "\n")


# === NoemaForge Autodoc Function Header ===
# Function: main()
# Purpose: Implement the routine 'main'.
# Inputs:
#   - No explicit parameters.
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
#   - _iter_py_files, _iter_code_files, _build_import_index, _build_callsite_index, _generate_autodoc_index, print, resolve, _insert_file_header, _insert_function_headers, Path
# Returns / emits: None
# Key locals:
#   - callsite_index, code_files, file_hdr, func_hdr, import_index, path, py_files, root
# === End NoemaForge Autodoc Function Header ===
def main() -> None:
    root = Path(__file__).resolve().parent.parent
    py_files = _iter_py_files(root)
    code_files = _iter_code_files(root)
    import_index = _build_import_index(py_files, root)
    callsite_index = _build_callsite_index(py_files, root)

    file_hdr = 0
    func_hdr = 0
    for path in py_files:
        try:
            _insert_file_header(path, root, import_index)
            file_hdr += 1
        except Exception:
            continue
    for path in py_files:
        try:
            func_hdr += _insert_function_headers(path, root, callsite_index)
        except Exception:
            continue

    _generate_autodoc_index(root, py_files, code_files, import_index)
    print(f"Autodoc(py): file headers refreshed: {file_hdr}")
    print(f"Autodoc(py): function headers refreshed: {func_hdr}")


if __name__ == "__main__":
    main()
