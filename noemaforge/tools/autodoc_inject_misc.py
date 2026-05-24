#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/autodoc_inject_misc.py
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
# File: tools/autodoc_inject_misc.py
# Purpose: Provide the module 'autodoc_inject_misc'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - main
# Inputs:
#   - Imports: __future__, datetime, re, pathlib, typing
# Output formats / side effects:
#   - UTF-8 text files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""Refresh NoemaForge headers for non-Python code files.

Supported file types:
- PowerShell (.ps1): file headers + function headers
- Shell (.sh): file headers + function headers
- Batch (.cmd): file headers
- Go (.go): file headers + function headers
"""


import datetime as dt
import re
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple

MARKER = "NoemaForge Autodoc File Header"
FUNC_MARKER = "NoemaForge Autodoc Function Header"
SKIP_PARTS = {".git", "__pycache__", "reports", "noemaforge-lab", "data", ".mypy_cache", ".pytest_cache"}


# === NoemaForge Autodoc Function Header ===
# Function: _now()
# Purpose: Implement the routine ' now'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/bootdoctor.py
#   - src/flow_metrics.py
#   - src/localgw_ratelimit.py
#   - src/resource_recovery.py
#   - src/storage_broker.py
# Calls:
#   - strftime, now
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


# === NoemaForge Autodoc Function Header ===
# Function: _write(path: Path, text: str)
# Purpose: Implement the routine ' write'.
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
def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


# === NoemaForge Autodoc Function Header ===
# Function: _iter_files(root: Path)
# Purpose: Implement the routine ' iter files'.
# Inputs:
#   - root: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - rglob, sorted, any, append, is_file, lower, relative_to
# Returns / emits: List[Path]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - exts, files, path
# === End NoemaForge Autodoc Function Header ===
def _iter_files(root: Path) -> List[Path]:
    exts = {".ps1", ".cmd", ".sh", ".go"}
    files: List[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in exts:
            continue
        if any(part in SKIP_PARTS for part in path.relative_to(root).parts):
            continue
        files.append(path)
    return sorted(files)


# === NoemaForge Autodoc Function Header ===
# Function: _purpose_guess(rel: str)
# Purpose: Implement the routine ' purpose guess'.
# Inputs:
#   - rel: str
# Called by:
#   - tools/autodoc_inject.py
# Calls:
#   - replace, endswith, Path
# Returns / emits: str
# Key locals:
#   - name, norm
# === End NoemaForge Autodoc Function Header ===
def _purpose_guess(rel: str) -> str:
    norm = rel.replace("\\", "/")
    name = Path(rel).stem
    if "/tools/windows/" in norm:
        return f"Provide the Windows helper script '{name}'."
    if "/bootstrap/" in norm:
        return f"Provide the bootstrap helper '{name}'."
    if norm.endswith(".go"):
        return f"Provide the Go service or helper '{name}'."
    return f"Provide the script '{name}'."


# === NoemaForge Autodoc Function Header ===
# Function: _strip_block(text: str, begin: str, end: str)
# Purpose: Implement the routine ' strip block'.
# Inputs:
#   - text: str
#   - begin: str
#   - end: str
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
def _strip_block(text: str, begin: str, end: str) -> str:
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
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


# === NoemaForge Autodoc Function Header ===
# Function: _inject_ps1_file_header(path: Path, rel: str)
# Purpose: Implement the routine ' inject ps1 file header'.
# Inputs:
#   - path: Path
#   - rel: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - read_text, sub, _purpose_guess, _write, _now, lstrip
# Returns / emits: None
# Key locals:
#   - header, inputs, outputs, purpose, text
# === End NoemaForge Autodoc Function Header ===
def _inject_ps1_file_header(path: Path, rel: str) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(?s)^<#[\r\n]+=== NoemaForge Autodoc File Header ===.*?#>\s*", "", text)
    purpose = _purpose_guess(rel)
    inputs = "Parameters and environment variables declared in the script."
    outputs = "Console output, spawned processes, and filesystem changes as implemented below."
    header = (
        "<#\n"
        "=== NoemaForge Autodoc File Header ===\n"
        f"File: {rel}\n"
        f"Purpose: {purpose}\n"
        "Invoked by: Windows operator scripts, dot-sourcing, or direct PowerShell execution.\n"
        f"Inputs: {inputs}\n"
        f"Outputs: {outputs}\n"
        f"AutoDoc: refreshed {_now()} (heuristic)\n"
        "#>\n\n"
    )
    _write(path, header + text.lstrip("\n"))


# === NoemaForge Autodoc Function Header ===
# Function: _inject_cmd_file_header(path: Path, rel: str)
# Purpose: Implement the routine ' inject cmd file header'.
# Inputs:
#   - path: Path
#   - rel: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - read_text, _purpose_guess, _write, splitlines, join, _now, startswith
# Returns / emits: None
# Key locals:
#   - header, lines, purpose, text
# === End NoemaForge Autodoc Function Header ===
def _inject_cmd_file_header(path: Path, rel: str) -> None:
    text = path.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if "NoemaForge Autodoc File Header" not in line and "End NoemaForge Autodoc File Header" not in line and not line.startswith("@REM File:") and not line.startswith("@REM Purpose:") and not line.startswith("@REM Invoked by:") and not line.startswith("@REM Inputs:") and not line.startswith("@REM Outputs:") and not line.startswith("@REM AutoDoc:")]
    purpose = _purpose_guess(rel)
    header = [
        "@REM === NoemaForge Autodoc File Header ===",
        f"@REM File: {rel}",
        f"@REM Purpose: {purpose}",
        "@REM Invoked by: Windows operators or wrapper scripts.",
        "@REM Inputs: Command-line arguments and environment variables read below.",
        "@REM Outputs: Console output and spawned helper processes.",
        f"@REM AutoDoc: refreshed {_now()} (heuristic)",
        "@REM === End NoemaForge Autodoc File Header ===",
        "",
    ]
    _write(path, "\n".join(header + lines) + "\n")


# === NoemaForge Autodoc Function Header ===
# Function: _inject_sh_file_header(path: Path, rel: str)
# Purpose: Implement the routine ' inject sh file header'.
# Inputs:
#   - path: Path
#   - rel: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - read_text, _strip_block, splitlines, _purpose_guess, _write, startswith, join, _now
# Returns / emits: None
# Key locals:
#   - header, idx, lines, new_lines, purpose, text
# === End NoemaForge Autodoc Function Header ===
def _inject_sh_file_header(path: Path, rel: str) -> None:
    text = path.read_text(encoding="utf-8")
    text = _strip_block(text, "# === NoemaForge Autodoc File Header ===", "# === End NoemaForge Autodoc File Header ===")
    lines = text.splitlines()
    idx = 1 if lines and lines[0].startswith("#!") else 0
    purpose = _purpose_guess(rel)
    header = [
        "# === NoemaForge Autodoc File Header ===",
        f"# File: {rel}",
        f"# Purpose: {purpose}",
        "# Invoked by: shell operators or wrapper scripts.",
        "# Inputs: Positional arguments, environment variables, and files read below.",
        "# Outputs: Console output and filesystem side effects.",
        f"# AutoDoc: refreshed {_now()} (heuristic)",
        "# === End NoemaForge Autodoc File Header ===",
        "",
    ]
    new_lines = lines[:idx] + header + lines[idx:]
    _write(path, "\n".join(new_lines) + "\n")


# === NoemaForge Autodoc Function Header ===
# Function: _inject_go_file_header(path: Path, rel: str)
# Purpose: Implement the routine ' inject go file header'.
# Inputs:
#   - path: Path
#   - rel: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - read_text, _strip_block, splitlines, _purpose_guess, _write, join, _now
# Returns / emits: None
# Key locals:
#   - header, idx, lines, new_lines, purpose, text
# === End NoemaForge Autodoc Function Header ===
def _inject_go_file_header(path: Path, rel: str) -> None:
    text = path.read_text(encoding="utf-8")
    text = _strip_block(text, "// === NoemaForge Autodoc File Header ===", "// === End NoemaForge Autodoc File Header ===")
    lines = text.splitlines()
    idx = 0
    purpose = _purpose_guess(rel)
    header = [
        "// === NoemaForge Autodoc File Header ===",
        f"// File: {rel}",
        f"// Purpose: {purpose}",
        "// Invoked by: systemd/services, operator builds, or direct process startup.",
        "// Inputs: environment variables, HTTP requests, and local Unix sockets as implemented below.",
        "// Outputs: HTTP responses, log lines, and local socket side effects.",
        f"// AutoDoc: refreshed {_now()} (heuristic)",
        "// === End NoemaForge Autodoc File Header ===",
        "",
    ]
    new_lines = lines[:idx] + header + lines[idx:]
    _write(path, "\n".join(new_lines) + "\n")


# === NoemaForge Autodoc Function Header ===
# Function: _parse_ps1_params(lines: Sequence[str], start_idx: int)
# Purpose: Implement the routine ' parse ps1 params'.
# Inputs:
#   - lines: Sequence[str]
#   - start_idx: int
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - finditer, join, search, group, append, min, len
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - m, match, name, out, signature, window
# === End NoemaForge Autodoc Function Header ===
def _parse_ps1_params(lines: Sequence[str], start_idx: int) -> List[str]:
    out: List[str] = []
    signature = lines[start_idx]
    for match in re.finditer(r"\$([A-Za-z_][A-Za-z0-9_]*)", signature):
        name = "$" + match.group(1)
        if name not in out:
            out.append(name)
    window = "\n".join(lines[start_idx : min(len(lines), start_idx + 12)])
    m = re.search(r"param\s*\(([\s\S]*?)\)", window, re.I)
    if m:
        for match in re.finditer(r"\$([A-Za-z_][A-Za-z0-9_]*)", m.group(1)):
            name = "$" + match.group(1)
            if name not in out:
                out.append(name)
    return out[:8]


# === NoemaForge Autodoc Function Header ===
# Function: _refresh_ps1_function_headers(path: Path)
# Purpose: Implement the routine ' refresh ps1 function headers'.
# Inputs:
#   - path: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - read_text, splitlines, _write, len, match, append, strip, group, _parse_ps1_params, extend, join
# Returns / emits: int
# Side effects:
#   - appends to logs or files
# Key locals:
#   - block, i, indent, inserted, line, lines, m, name, out, params, text
# === End NoemaForge Autodoc Function Header ===
def _refresh_ps1_function_headers(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out: List[str] = []
    i = 0
    inserted = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "# === NoemaForge Autodoc Function Header ===":
            while i < len(lines) and lines[i].strip() != "# === End NoemaForge Autodoc Function Header ===":
                i += 1
            i += 1
            continue
        m = re.match(r"^(\s*)function\s+([A-Za-z0-9_-]+)", line, re.I)
        if m:
            indent = m.group(1)
            name = m.group(2)
            params = _parse_ps1_params(lines, i)
            block = [
                indent + "# === NoemaForge Autodoc Function Header ===",
                indent + f"# Function: {name}",
                indent + f"# Purpose: Provide the PowerShell routine '{name}'.",
                indent + "# Inputs:",
            ]
            if params:
                block.extend(indent + f"#   - {p}" for p in params)
            else:
                block.append(indent + "#   - See the param() block or in-body variable handling below.")
            block.extend([
                indent + "# Called by:",
                indent + "#   - Wrapper scripts, direct PowerShell execution, or dot-sourced callers.",
                indent + "# Outputs: Console output and side effects implemented in the body below.",
                indent + "# === End NoemaForge Autodoc Function Header ===",
            ])
            out.extend(block)
            inserted += 1
        out.append(line)
        i += 1
    _write(path, "\n".join(out) + "\n")
    return inserted


# === NoemaForge Autodoc Function Header ===
# Function: _refresh_sh_function_headers(path: Path)
# Purpose: Implement the routine ' refresh sh function headers'.
# Inputs:
#   - path: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - read_text, splitlines, _write, len, match, append, strip, group, extend, join
# Returns / emits: int
# Side effects:
#   - appends to logs or files
# Key locals:
#   - block, i, indent, inserted, line, lines, m, name, out, text
# === End NoemaForge Autodoc Function Header ===
def _refresh_sh_function_headers(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out: List[str] = []
    i = 0
    inserted = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "# === NoemaForge Autodoc Function Header ===":
            while i < len(lines) and lines[i].strip() != "# === End NoemaForge Autodoc Function Header ===":
                i += 1
            i += 1
            continue
        m = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{", line)
        if m:
            indent = m.group(1)
            name = m.group(2)
            block = [
                indent + "# === NoemaForge Autodoc Function Header ===",
                indent + f"# Function: {name}()",
                indent + f"# Purpose: Provide the shell routine '{name}'.",
                indent + "# Inputs:",
                indent + "#   - Positional shell arguments and environment variables read in the body below.",
                indent + "# Called by:",
                indent + "#   - The current shell script or sourced callers.",
                indent + "# Outputs: Console output and filesystem/process side effects implemented in the body below.",
                indent + "# === End NoemaForge Autodoc Function Header ===",
            ]
            out.extend(block)
            inserted += 1
        out.append(line)
        i += 1
    _write(path, "\n".join(out) + "\n")
    return inserted


# === NoemaForge Autodoc Function Header ===
# Function: _go_signatures(text: str)
# Purpose: Implement the routine ' go signatures'.
# Inputs:
#   - text: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - enumerate, splitlines, match, strip, append, group
# Returns / emits: List[Tuple[int, str, str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - m, out, params, ret, sig
# === End NoemaForge Autodoc Function Header ===
def _go_signatures(text: str) -> List[Tuple[int, str, str]]:
    out: List[Tuple[int, str, str]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        m = re.match(r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)\s*(.*)$", line)
        if m:
            params = m.group(2).strip()
            ret = m.group(3).strip().rstrip("{").strip()
            sig = params if not ret else f"{params} -> {ret}"
            out.append((idx, m.group(1), sig))
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _go_call_index(files: Sequence[Path], root: Path)
# Purpose: Implement the routine ' go call index'.
# Inputs:
#   - files: Sequence[Path]
#   - root: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - replace, _strip_block, join, finditer, read_text, add, str, splitlines, relative_to, startswith, setdefault, group
# Returns / emits: Dict[str, Set[str]]
# Key locals:
#   - clean, clean_lines, idx, match, path, rel, text
# === End NoemaForge Autodoc Function Header ===
def _go_call_index(files: Sequence[Path], root: Path) -> Dict[str, Set[str]]:
    idx: Dict[str, Set[str]] = {}
    for path in files:
        rel = str(path.relative_to(root)).replace("\\", "/")
        text = _strip_block(path.read_text(encoding="utf-8"), "// === NoemaForge Autodoc Function Header ===", "// === End NoemaForge Autodoc Function Header ===")
        # Remove line comments for simpler scanning.
        clean_lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("//")]
        clean = "\n".join(clean_lines)
        for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", clean):
            idx.setdefault(match.group(1), set()).add(rel)
    return idx


# === NoemaForge Autodoc Function Header ===
# Function: _refresh_go_function_headers(path: Path, call_index: Dict[str, Set[str]], root: Path)
# Purpose: Implement the routine ' refresh go function headers'.
# Inputs:
#   - path: Path
#   - call_index: Dict[str, Set[str]]
#   - root: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - replace, _strip_block, splitlines, _go_signatures, reversed, _write, read_text, max, extend, str, sorted, append
# Returns / emits: int
# Side effects:
#   - appends to logs or files
# Key locals:
#   - block, callers, idx, inserted, lines, rel, sigs, text
# === End NoemaForge Autodoc Function Header ===
def _refresh_go_function_headers(path: Path, call_index: Dict[str, Set[str]], root: Path) -> int:
    rel = str(path.relative_to(root)).replace("\\", "/")
    text = _strip_block(path.read_text(encoding="utf-8"), "// === NoemaForge Autodoc Function Header ===", "// === End NoemaForge Autodoc Function Header ===")
    lines = text.splitlines()
    sigs = _go_signatures(text)
    inserted = 0
    for lineno, name, params in reversed(sigs):
        idx = max(0, lineno - 1)
        callers = sorted(call_index.get(name, set()) - {rel})[:6]
        block = [
            "// === NoemaForge Autodoc Function Header ===",
            f"// Function: {name}({params})",
            f"// Purpose: Provide the Go routine '{name}'.",
            "// Inputs:",
            f"//   - {params if params else 'No explicit parameters.'}",
            "// Called by:",
        ]
        if callers:
            block.extend(f"//   - {item}" for item in callers)
        else:
            block.append("//   - No external Go callsite detected; may be process entry, HTTP callback, or local helper.")
        block.extend([
            "// Outputs: Return values, HTTP responses, log lines, or socket side effects implemented in the body below.",
            "// === End NoemaForge Autodoc Function Header ===",
        ])
        lines[idx:idx] = block
        inserted += 1
    _write(path, "\n".join(lines) + "\n")
    return inserted


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
#   - _iter_files, _go_call_index, print, replace, resolve, lower, _inject_ps1_file_header, _refresh_ps1_function_headers, str, _inject_cmd_file_header, Path, relative_to
# Returns / emits: None
# Key locals:
#   - file_count, files, func_count, go_files, go_index, path, rel, root
# === End NoemaForge Autodoc Function Header ===
def main() -> None:
    root = Path(__file__).resolve().parent.parent
    files = _iter_files(root)
    go_files = [p for p in files if p.suffix.lower() == ".go"]
    go_index = _go_call_index(go_files, root)

    file_count = 0
    func_count = 0
    for path in files:
        rel = str(path.relative_to(root)).replace("\\", "/")
        if path.suffix.lower() == ".ps1":
            _inject_ps1_file_header(path, rel)
            func_count += _refresh_ps1_function_headers(path)
        elif path.suffix.lower() == ".cmd":
            _inject_cmd_file_header(path, rel)
        elif path.suffix.lower() == ".sh":
            _inject_sh_file_header(path, rel)
            func_count += _refresh_sh_function_headers(path)
        elif path.suffix.lower() == ".go":
            _inject_go_file_header(path, rel)
            func_count += _refresh_go_function_headers(path, go_index, root)
        file_count += 1

    print(f"Autodoc(misc): file headers refreshed: {file_count}")
    print(f"Autodoc(misc): function headers refreshed: {func_count}")


if __name__ == "__main__":
    main()
