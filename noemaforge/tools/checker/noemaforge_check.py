#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tools/checker/noemaforge_check.py
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
# File: tools/checker/noemaforge_check.py
# Purpose: Run offline integrity or attestation checks for 'noemaforge_check'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - class Step
#   - class Reporter
#   - check_structure
#   - check_sha256
#   - check_forbidden
#   - check_json
#   - check_yaml
#   - check_compile
#   - check_epoch_files
#   - check_deps
#   - check_unicode
#   - check_roles_prompts
# Inputs:
#   - --root
#   - --out
#   - --deep
#   - Common path inputs: checksums/SHA256SUMS, src/noemaforge-llm-gateway, src/noemaforge-llm-gateway.exe, /var/lib/noemaforge/.sys, noemaforge.checker/v1
#   - Imports: __future__, argparse, ast, base64, hashlib, json, os, re
# Output formats / side effects:
#   - JSON files
#   - YAML files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""noemaforge_check.py (seed checker)

Goal
----
An offline checker that:
  - continues after failures
  - emits a structured JSON report
  - is safe to run on Windows / Linux

It does NOT modify the seed tree.

Usage
-----
  python tools/checker/noemaforge_check.py --root <seed/noemaforge> --out <report.json>

Exit codes
----------
  0 = no FAIL
  1 = WARN only
  2 = FAIL present
"""


import argparse
import ast
import base64
import hashlib
import json
import os
import re
import sys
import traceback
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Set, Tuple


# NOTE: This checker validates the *seed* (code/config/contracts). In practice
# users often run it inside a working directory that also contains runtime
# artifacts (reports/, data/, lab outputs, etc). Runtime artifacts must not
# break seed validation.
EXCLUDE_DIR_NAMES: Set[str] = {
    ".git",
    ".hg",
    ".svn",
    "reports",
    "cd",
    "noemaforge-lab",
    "data",
    "node_modules",
    "venv",
    ".venv",
    ".pytest_cache",
}


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
#   - strftime, now
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    import datetime as dt

    # Use timezone-aware UTC to avoid deprecation warnings in newer Python.
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# === NoemaForge Autodoc Function Header ===
# Function: _sha256_file(path: str)
# Purpose: Implement the routine ' sha256 file'.
# Inputs:
#   - path: str
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/casebase.py
#   - src/doctor.py
#   - src/glove_agent.py
#   - src/localgw_uplink_agent.py
#   - src/model_registry.py
#   - src/pipelines/finance_budget.py
# Calls:
#   - sha256, hexdigest, open, iter, update, read
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - chunk, f, h
# === End NoemaForge Autodoc Function Header ===
def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _read_text(path: str)
# Purpose: Implement the routine ' read text'.
# Inputs:
#   - path: str
# Called by:
#   - src/hwscan.py
#   - src/lsm.py
#   - tools/autodoc_inject.py
# Calls:
#   - decode, open, read
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - b, enc, f
# === End NoemaForge Autodoc Function Header ===
def _read_text(path: str) -> str:
    with open(path, "rb") as f:
        b = f.read()
    # Prefer utf-8-sig: it strips UTF-8 BOM (common on Windows).
    # BOM presence is still detected in the odd-chars scan.
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return b.decode(enc)
        except Exception:
            pass
    return b.decode("utf-8", errors="replace")


# === NoemaForge Autodoc Function Header ===
# Function: _list_files(root: str, exclude_dir_names: Optional[Set[str]] = None)
# Purpose: Implement the routine ' list files'.
# Inputs:
#   - root: str
#   - exclude_dir_names: Optional[Set[str]] = None
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - walk, append, join
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - ex, fn, out
# === End NoemaForge Autodoc Function Header ===
def _list_files(root: str, *, exclude_dir_names: Optional[Set[str]] = None) -> List[str]:
    out: List[str] = []
    ex = exclude_dir_names if exclude_dir_names is not None else EXCLUDE_DIR_NAMES
    for dp, dns, fns in os.walk(root):
        # Prune known runtime / VCS / cache directories to avoid false failures.
        dns[:] = [d for d in dns if d not in ex]
        for fn in fns:
            out.append(os.path.join(dp, fn))
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _rel(root: str, path: str)
# Purpose: Implement the routine ' rel'.
# Inputs:
#   - root: str
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - replace, relpath
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _rel(root: str, path: str) -> str:
    try:
        return os.path.relpath(path, root).replace("\\", "/")
    except Exception:
        return path.replace("\\", "/")


@dataclass
class Step:
    id: str
    title: str
    status: str = "PASS"  # PASS/WARN/FAIL/SKIP
    message: str = ""
    data: Dict[str, Any] = None  # type: ignore

    # === NoemaForge Autodoc Function Header ===
    # Function: __post_init__(self)
    # Purpose: Implement the routine '  post init  '.
    # Inputs:
    #   - self
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Returns / emits: None
    # === End NoemaForge Autodoc Function Header ===
    def __post_init__(self) -> None:
        if self.data is None:
            self.data = {}


class Reporter:
    # === NoemaForge Autodoc Function Header ===
    # Function: __init__(self)
    # Purpose: Implement the routine '  init  '.
    # Inputs:
    #   - self
    # Called by:
    #   - src/model_scorecards.py
    #   - src/team_scorecards.py
    #   - src/toolproxy.py
    # Returns / emits: None
    # === End NoemaForge Autodoc Function Header ===
    def __init__(self) -> None:
        self.steps: List[Step] = []
        self.fail = 0
        self.warn = 0

    # === NoemaForge Autodoc Function Header ===
    # Function: add(self, s: Step)
    # Purpose: Implement the routine 'add'.
    # Inputs:
    #   - self
    #   - s: Step
    # Called by:
    #   - src/bootdoctor.py
    #   - src/brainctl.py
    #   - src/noemaforge_core.py
    #   - src/flow_catalog.py
    #   - src/glove_agent.py
    #   - src/incidents.py
    #   - src/installer_plan.py
    #   - src/localgateway.py
    # Calls:
    #   - append
    # Returns / emits: None
    # Side effects:
    #   - appends to logs or files
    # === End NoemaForge Autodoc Function Header ===
    def add(self, s: Step) -> None:
        self.steps.append(s)
        if s.status == "FAIL":
            self.fail += 1
        if s.status == "WARN":
            self.warn += 1

    # === NoemaForge Autodoc Function Header ===
    # Function: run(self, id: str, title: str, fn)
    # Purpose: Implement the routine 'run'.
    # Inputs:
    #   - self
    #   - id: str
    #   - title: str
    #   - fn
    # Called by:
    #   - src/bootdoctor.py
    #   - src/brainctl.py
    #   - src/firstboot_eval.py
    #   - src/hwscan.py
    #   - src/knowledge_maintainer.py
    #   - src/lan_discovery.py
    #   - src/localgateway.py
    #   - src/localgw_connectors/ipp.py
    # Calls:
    #   - Step, add, fn, isinstance, format_exc
    # Returns / emits: None
    # Key locals:
    #   - r, s
    # === End NoemaForge Autodoc Function Header ===
    def run(self, id: str, title: str, fn) -> None:
        s = Step(id=id, title=title)
        try:
            r = fn(s)
            if isinstance(r, Step):
                s = r
        except Exception as e:
            s.status = "FAIL"
            s.message = f"Exception: {e!r}"
            s.data = {"trace": traceback.format_exc()}
        self.add(s)

    # === NoemaForge Autodoc Function Header ===
    # Function: exit_code(self)
    # Purpose: Implement the routine 'exit code'.
    # Inputs:
    #   - self
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Returns / emits: int
    # === End NoemaForge Autodoc Function Header ===
    def exit_code(self) -> int:
        if self.fail > 0:
            return 2
        if self.warn > 0:
            return 1
        return 0


# === NoemaForge Autodoc Function Header ===
# Function: _try_import(mod: str)
# Purpose: Implement the routine ' try import'.
# Inputs:
#   - mod: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - __import__
# Returns / emits: Tuple[bool, str]
# === End NoemaForge Autodoc Function Header ===
def _try_import(mod: str) -> Tuple[bool, str]:
    try:
        __import__(mod)
        return True, "ok"
    except Exception as e:
        return False, f"{e.__class__.__name__}:{e}"


# === NoemaForge Autodoc Function Header ===
# Function: check_structure(brain: str)
# Purpose: Implement the routine 'check structure'.
# Inputs:
#   - brain: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - Step, exists, join
# Returns / emits: Step
# Key locals:
#   - missing, req, s
# === End NoemaForge Autodoc Function Header ===
def check_structure(brain: str) -> Step:
    s = Step("00", "Basic structure")
    req = [
        "manifest.yaml",
        "checksums/SHA256SUMS",
        "configs",
        "src",
        "contracts",
    ]
    missing = [p for p in req if not os.path.exists(os.path.join(brain, p))]
    if missing:
        s.status = "FAIL"
        s.message = "Missing required paths"
        s.data = {"missing": missing}
        return s
    s.message = "OK"
    return s


# === NoemaForge Autodoc Function Header ===
# Function: check_sha256(brain: str)
# Purpose: Implement the routine 'check sha256'.
# Inputs:
#   - brain: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - Step, join, exists, open, strip, split, lower, startswith, len, append, _sha256_file
# Returns / emits: Step
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - act, exp, f, fail, line, mismatch, missing, ok, parts, path, rel, s
# === End NoemaForge Autodoc Function Header ===
def check_sha256(brain: str) -> Step:
    s = Step("10", "SHA256SUMS integrity")
    sum_path = os.path.join(brain, "checksums", "SHA256SUMS")
    if not os.path.exists(sum_path):
        s.status = "FAIL"
        s.message = "SHA256SUMS not found"
        return s
    ok = 0
    fail = 0
    missing: List[str] = []
    mismatch: List[Dict[str, Any]] = []
    with open(sum_path, "r", encoding="utf-8") as f:
        for line in f:
            t = line.strip()
            if not t:
                continue
            parts = re.split(r"\s+", t, maxsplit=1)
            if len(parts) < 2:
                continue
            exp = parts[0].lower()
            rel = parts[1].strip()
            if rel.startswith("./"):
                rel = rel[2:]
            path = os.path.join(brain, rel)
            if not os.path.exists(path):
                missing.append(rel)
                fail += 1
                continue
            act = _sha256_file(path).lower()
            if act == exp:
                ok += 1
            else:
                mismatch.append({"file": rel, "expected": exp, "actual": act})
                fail += 1
    if fail > 0:
        s.status = "FAIL"
    s.message = f"OK={ok} FAIL={fail}"
    s.data = {"ok": ok, "fail": fail, "missing": missing, "mismatch": mismatch}
    return s


# === NoemaForge Autodoc Function Header ===
# Function: check_forbidden(brain: str)
# Purpose: Implement the routine 'check forbidden'.
# Inputs:
#   - brain: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - Step, walk, join, exists, append, len, endswith, sorted, _rel
# Returns / emits: Step
# Side effects:
#   - appends to logs or files
# Key locals:
#   - dn, fn, forbidden, p, s, x
# === End NoemaForge Autodoc Function Header ===
def check_forbidden(brain: str) -> Step:
    s = Step("11", "Forbidden artifacts")
    forbidden: List[str] = []
    for dp, dns, fns in os.walk(brain):
        for dn in dns:
            if dn == "__pycache__":
                forbidden.append(os.path.join(dp, dn))
        for fn in fns:
            if fn.endswith(".pyc") or fn in (".DS_Store", "Thumbs.db"):
                forbidden.append(os.path.join(dp, fn))
    for x in ["src/noemaforge-llm-gateway", "src/noemaforge-llm-gateway.exe"]:
        p = os.path.join(brain, x)
        if os.path.exists(p):
            forbidden.append(p)
    if forbidden:
        s.status = "FAIL"
        s.message = "Forbidden artifacts present"
        s.data = {"paths": sorted(_rel(brain, p) for p in forbidden)[:200], "count": len(forbidden)}
        return s
    s.message = "Clean"
    return s


# === NoemaForge Autodoc Function Header ===
# Function: check_json(brain: str)
# Purpose: Implement the routine 'check json'.
# Inputs:
#   - brain: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - Step, _list_files, endswith, len, lower, loads, _read_text, append, _rel, repr
# Returns / emits: Step
# Side effects:
#   - appends to logs or files
# Key locals:
#   - bad, p, s, total
# === End NoemaForge Autodoc Function Header ===
def check_json(brain: str) -> Step:
    s = Step("12", "JSON parse")
    bad: List[Dict[str, Any]] = []
    total = 0
    for p in _list_files(brain):
        if p.lower().endswith(".json"):
            total += 1
            try:
                json.loads(_read_text(p))
            except Exception as e:
                bad.append({"file": _rel(brain, p), "error": repr(e)})
    if bad:
        s.status = "FAIL"
        s.message = "JSON parse errors"
        s.data = {"total": total, "bad": bad[:50], "bad_count": len(bad)}
        return s
    s.message = f"OK ({total} files)"
    return s


# === NoemaForge Autodoc Function Header ===
# Function: check_yaml(brain: str)
# Purpose: Implement the routine 'check yaml'.
# Inputs:
#   - brain: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - Step, _try_import, join, _list_files, isdir, endswith, len, lower, safe_load, _read_text, append, _rel
# Returns / emits: Step
# Side effects:
#   - appends to logs or files
# Key locals:
#   - bad, base, p, s, total
# === End NoemaForge Autodoc Function Header ===
def check_yaml(brain: str) -> Step:
    s = Step("13", "YAML parse (configs + contracts)")
    ok_yaml, why = _try_import("yaml")
    if not ok_yaml:
        s.status = "WARN"
        s.message = "PyYAML not available; skipping YAML parse"
        s.data = {"import": why}
        return s
    import yaml  # type: ignore

    bad: List[Dict[str, Any]] = []
    total = 0
    for base in [os.path.join(brain, "configs"), os.path.join(brain, "contracts")]:
        if not os.path.isdir(base):
            continue
        for p in _list_files(base):
            if p.lower().endswith((".yaml", ".yml")):
                total += 1
                try:
                    yaml.safe_load(_read_text(p))
                except Exception as e:
                    bad.append({"file": _rel(brain, p), "error": repr(e)})
    if bad:
        s.status = "FAIL"
        s.message = "YAML parse errors"
        s.data = {"total": total, "bad": bad[:50], "bad_count": len(bad)}
        return s
    s.message = f"OK ({total} files)"
    return s


# === NoemaForge Autodoc Function Header ===
# Function: check_compile(brain: str)
# Purpose: Implement the routine 'check compile'.
# Inputs:
#   - brain: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - Step, join, _list_files, isdir, len, endswith, replace, _read_text, compile, append, lower, _rel
# Returns / emits: Step
# Side effects:
#   - appends to logs or files
# Key locals:
#   - bad, pth, root, roots, s, src, total
# === End NoemaForge Autodoc Function Header ===
def check_compile(brain: str) -> Step:
    s = Step("14", "Python syntax compile (src + tools)")

    roots = [os.path.join(brain, "src"), os.path.join(brain, "tools")]
    bad: List[Dict[str, Any]] = []
    total = 0

    for root in roots:
        if not os.path.isdir(root):
            continue
        for pth in _list_files(root):
            if not pth.lower().endswith(".py"):
                continue
            # Never touch cache dirs if someone ran other tools before.
            if "__pycache__" in pth.replace("\\", "/"):
                continue
            total += 1
            try:
                src = _read_text(pth)
                compile(src, pth, "exec")
            except Exception as e:
                bad.append({"file": _rel(brain, pth), "error": repr(e)})

    if bad:
        s.status = "FAIL"
        s.message = "Python syntax errors"
        s.data = {"total": total, "bad_count": len(bad), "bad": bad[:50]}
        return s

    if total == 0:
        s.status = "WARN"
        s.message = "No Python files found"
        return s

    s.message = f"OK ({total} files)"
    return s


# === NoemaForge Autodoc Function Header ===
# Function: check_epoch_files(brain: str)
# Purpose: Implement the routine 'check epoch files'.
# Inputs:
#   - brain: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - Step, join, _read_text, search, group, sorted, exists, findall, set, append, len
# Returns / emits: Step
# Side effects:
#   - appends to logs or files
# Key locals:
#   - blob, cfg, m, missing, n, names, prestart, s, txt
# === End NoemaForge Autodoc Function Header ===
def check_epoch_files(brain: str) -> Step:
    s = Step("15", "Epoch contract files referenced by prestart")
    prestart = os.path.join(brain, "src", "prestart.py")
    cfg = os.path.join(brain, "configs")
    if not os.path.exists(prestart):
        s.status = "FAIL"
        s.message = "prestart.py missing"
        return s
    txt = _read_text(prestart)
    # naive parse of EPOCH_FILES list
    m = re.search(r"EPOCH_FILES\s*=\s*\[(.*?)\]\s*\n", txt, flags=re.S)
    if not m:
        s.status = "WARN"
        s.message = "Could not parse EPOCH_FILES; skipping"
        return s
    blob = m.group(1)
    names = re.findall(r"\"([^\"]+\.ya?ml)\"", blob) + re.findall(r"'([^']+\.ya?ml)'", blob)
    names = sorted(set(names))
    missing: List[str] = []
    for n in names:
        if not os.path.exists(os.path.join(cfg, n)):
            missing.append(n)
    if missing:
        s.status = "FAIL"
        s.message = "Missing epoch config files"
        s.data = {"missing": missing, "epoch_files_count": len(names)}
        return s
    s.message = f"OK ({len(names)} epoch files)"
    return s


# === NoemaForge Autodoc Function Header ===
# Function: check_deps()
# Purpose: Implement the routine 'check deps'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - Step, _try_import, items, join
# Returns / emits: Step
# Key locals:
#   - deps, missing, s
# === End NoemaForge Autodoc Function Header ===
def check_deps() -> Step:
    s = Step("16", "Python dependencies (import probes)")
    deps = {
        "yaml": _try_import("yaml"),
        "cryptography": _try_import("cryptography"),
        "jsonschema": _try_import("jsonschema"),
    }
    missing = [k for k, (ok, _) in deps.items() if not ok]
    s.data = {k: {"ok": ok, "why": why} for k, (ok, why) in deps.items()}
    if missing:
        s.status = "WARN"
        s.message = f"Missing modules: {', '.join(missing)}"
        return s
    s.message = "All present"
    return s


# === NoemaForge Autodoc Function Header ===
# Function: check_unicode(brain: str)
# Purpose: Implement the routine 'check unicode'.
# Inputs:
#   - brain: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - Step, _list_files, lower, read, decode, any, len, append, open, splitext, _rel, repr
# Returns / emits: Step
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - b, exts, hits, p, s, t
# === End NoemaForge Autodoc Function Header ===
def check_unicode(brain: str) -> Step:
    s = Step("17", "Odd characters scan (warn-only)")
    exts = {".py", ".ps1", ".sh", ".yaml", ".yml", ".md", ".json"}
    hits: List[Dict[str, Any]] = []
    for p in _list_files(brain):
        if os.path.splitext(p)[1].lower() not in exts:
            continue
        try:
            b = open(p, "rb").read()
            if b[:3] == b"\xEF\xBB\xBF":
                hits.append({"file": _rel(brain, p), "kind": "UTF8_BOM"})
            if b"\x00" in b:
                hits.append({"file": _rel(brain, p), "kind": "NUL"})
            t = b.decode("utf-8", errors="ignore")
            if any(ch in t for ch in ["\u200b", "\u200c", "\u200d", "\ufeff"]):
                hits.append({"file": _rel(brain, p), "kind": "ZERO_WIDTH"})
        except Exception as e:
            hits.append({"file": _rel(brain, p), "kind": "READ_ERROR", "error": repr(e)})
    if hits:
        s.status = "WARN"
        s.message = f"Found {len(hits)} potential issues"
        s.data = {"hits": hits[:80], "count": len(hits)}
        return s
    s.message = "Clean"
    return s


# === NoemaForge Autodoc Function Header ===
# Function: check_roles_prompts(brain: str)
# Purpose: Implement the routine 'check roles prompts'.
# Inputs:
#   - brain: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - Step, _try_import, join, _load_yaml, compile, items, set, isinstance, sorted, append, str, startswith
# Returns / emits: Step
# Side effects:
#   - appends to logs or files
# Key locals:
#   - aff, aff_txt, b, banned_substrings, cfg_dir, f, fc, flows, i, issues, m, missing
# === End NoemaForge Autodoc Function Header ===
def check_roles_prompts(brain: str) -> Step:
    s = Step("18", "Roles/prompts cross-file consistency")
    ok_yaml, why = _try_import("yaml")
    if not ok_yaml:
        s.status = "WARN"
        s.message = "PyYAML not available; skipping roles/prompts checks"
        s.data = {"import": why}
        return s

    import yaml  # type: ignore

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
    #   - safe_load, _read_text, repr
    # Returns / emits: any
    # === End NoemaForge Autodoc Function Header ===
    def _load_yaml(path: str) -> any:
        try:
            return yaml.safe_load(_read_text(path))
        except Exception as e:
            return {"__parse_error__": repr(e)}

    cfg_dir = os.path.join(brain, "configs")
    paths = {
        "role_affirmations": os.path.join(cfg_dir, "role-affirmations.yaml"),
        "promptkit": os.path.join(cfg_dir, "promptkit.yaml"),
        "flow_catalog": os.path.join(cfg_dir, "flow-catalog.yaml"),
        "role_roadmaps": os.path.join(cfg_dir, "role-roadmaps.yaml"),
        "team_model_policy": os.path.join(cfg_dir, "team-model-policy.yaml"),
    }

    missing = [k for k, v in paths.items() if not os.path.exists(v)]
    if missing:
        s.status = "FAIL"
        s.message = "Missing config files for roles/prompts checks"
        s.data = {"missing": missing, "paths": {k: _rel(brain, v) for k, v in paths.items()}}
        return s

    aff = _load_yaml(paths["role_affirmations"])
    pk = _load_yaml(paths["promptkit"])
    fc = _load_yaml(paths["flow_catalog"])
    rm = _load_yaml(paths["role_roadmaps"])
    tm = _load_yaml(paths["team_model_policy"])

    parse_errors = {}
    for k, obj in [("role_affirmations", aff), ("promptkit", pk), ("flow_catalog", fc), ("role_roadmaps", rm), ("team_model_policy", tm)]:
        if isinstance(obj, dict) and "__parse_error__" in obj:
            parse_errors[k] = obj["__parse_error__"]
    if parse_errors:
        s.status = "FAIL"
        s.message = "YAML parse errors in roles/prompts related configs"
        s.data = {"parse_errors": parse_errors}
        return s

    issues = {"fail": [], "warn": []}

    # --- role-affirmations basic sanity
    roles_map = ((aff or {}).get("roles") or {}) if isinstance(aff, dict) else {}
    if not isinstance(roles_map, dict):
        issues["fail"].append({"where": "role-affirmations.yaml", "msg": "roles must be a mapping"})
        roles_map = {}

    safe_re = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
    banned_substrings = [
        "tokens_dir",
        "/var/lib/noemaforge/.sys",
        "cap_tokens",
        "SHA256SUMS",
        "toolproxy.sock",
    ]

    for rid, rdoc in roles_map.items():
        if not isinstance(rid, str) or not safe_re.match(rid):
            issues["fail"].append({"where": "role-affirmations.yaml", "role": str(rid), "msg": "unsafe role id"})
            continue
        if not isinstance(rdoc, dict):
            issues["fail"].append({"where": "role-affirmations.yaml", "role": rid, "msg": "role entry must be mapping"})
            continue
        aff_txt = str(rdoc.get("affirmation") or "")
        if aff_txt.strip().startswith("|"):
            issues["warn"].append({"where": "role-affirmations.yaml", "role": rid, "msg": "affirmation starts with literal '|' (possible quoting bug)"})
        for b in banned_substrings:
            if b in aff_txt:
                issues["warn"].append({"where": "role-affirmations.yaml", "role": rid, "msg": f"affirmation contains suspicious token: {b}"})
                break
        rules = rdoc.get("rules")
        if rules is not None and not (isinstance(rules, list) and all(isinstance(x, (str, int, float)) for x in rules)):
            issues["warn"].append({"where": "role-affirmations.yaml", "role": rid, "msg": "rules should be a list of strings"})

    # --- flow-catalog roles completeness
    used_roles = set()
    if isinstance(fc, dict):
        flows = fc.get("flows") or []
        if isinstance(flows, list):
            for f in flows:
                if not isinstance(f, dict):
                    continue
                team = f.get("team") or {}
                if isinstance(team, dict):
                    for m in (team.get("members") or []):
                        if isinstance(m, dict) and m.get("role"):
                            used_roles.add(str(m.get("role")))
                    v = team.get("verifier")
                    if isinstance(v, dict) and v.get("role"):
                        used_roles.add(str(v.get("role")))

    for rid in sorted(used_roles):
        if rid in roles_map:
            continue
        # specialization inheritance: allow parent role to exist
        ok = False
        if "." in rid:
            parts = rid.split(".")
            for i in range(len(parts) - 1, 0, -1):
                if ".".join(parts[:i]) in roles_map:
                    ok = True
                    break
        if not ok:
            issues["fail"].append({"where": "flow-catalog.yaml", "role": rid, "msg": "role used in flow is missing in role-affirmations.yaml"})

    # --- promptkit role coverage (warn-only)
    if isinstance(pk, dict):
        pk_roles = pk.get("roles") or {}
        if isinstance(pk_roles, dict):
            for rid in sorted(pk_roles.keys()):
                if rid not in roles_map and rid not in ("default",):
                    issues["warn"].append({"where": "promptkit.yaml", "role": rid, "msg": "role has promptkit template but no affirmation (will fallback to default)"})

    # --- role-roadmaps coverage (warn-only)
    if isinstance(rm, dict):
        rm_roles = (rm.get("roles") or {}) if isinstance(rm.get("roles"), dict) else {}
        for rid in sorted(used_roles):
            if rid in rm_roles:
                continue
            ok = False
            if "." in rid:
                parts = rid.split(".")
                for i in range(len(parts) - 1, 0, -1):
                    if ".".join(parts[:i]) in rm_roles:
                        ok = True
                        break
            if not ok:
                issues["warn"].append({"where": "role-roadmaps.yaml", "role": rid, "msg": "flow role has no roadmap entry (optional but recommended)"})

    if issues["fail"]:
        s.status = "FAIL"
    elif issues["warn"]:
        s.status = "WARN"
    else:
        s.status = "PASS"

    s.message = f"FAIL={len(issues['fail'])} WARN={len(issues['warn'])}"
    s.data = issues
    return s


# === NoemaForge Autodoc Function Header ===
# Function: check_config_contract_pairs(brain: str)
# Purpose: Implement the routine 'check config contract pairs'.
# Inputs:
#   - brain: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - Step, _try_import, join, listdir, sorted, sub, _norm, get, replace, endswith, append, _read_text
# Returns / emits: Step
# Side effects:
#   - appends to logs or files
# Key locals:
#   - cfg_dir, cfg_path, ctr_dir, data, fail, fn, norm, ok, raw, s, sch_path, schema
# === End NoemaForge Autodoc Function Header ===
def check_config_contract_pairs(brain: str) -> Step:
    s = Step("19", "Config/schema contract validation")
    ok_yaml, why_yaml = _try_import("yaml")
    ok_js, why_js = _try_import("jsonschema")
    if not ok_yaml or not ok_js:
        s.status = "WARN"
        s.message = "Schema validation skipped because PyYAML or jsonschema is unavailable"
        s.data = {"yaml": why_yaml, "jsonschema": why_js}
        return s

    import yaml  # type: ignore
    import jsonschema  # type: ignore

    # === NoemaForge Autodoc Function Header ===
    # Function: _norm(name: str)
    # Purpose: Implement the routine ' norm'.
    # Inputs:
    #   - name: str
    # Called by:
    #   - src/pipelines/finance_budget.py
    # Calls:
    #   - sub, replace
    # Returns / emits: str
    # === End NoemaForge Autodoc Function Header ===
    def _norm(name: str) -> str:
        return re.sub(r"[-.]", "_", name.replace(".schema", ""))

    cfg_dir = os.path.join(brain, "configs")
    ctr_dir = os.path.join(brain, "contracts")
    schema_by_norm: Dict[str, str] = {}
    for fn in os.listdir(ctr_dir):
        if not fn.endswith(".schema.json"):
            continue
        schema_by_norm[_norm(os.path.splitext(os.path.splitext(fn)[0])[0])] = os.path.join(ctr_dir, fn)

    fail: List[Dict[str, Any]] = []
    warn: List[Dict[str, Any]] = []
    ok = 0
    for fn in sorted(os.listdir(cfg_dir)):
        if not fn.endswith((".yaml", ".yml", ".json")):
            continue
        cfg_path = os.path.join(cfg_dir, fn)
        norm = _norm(os.path.splitext(fn)[0])
        sch_path = schema_by_norm.get(norm)
        if not sch_path:
            warn.append({"config": fn, "reason": "missing_matching_schema"})
            continue
        try:
            raw = _read_text(cfg_path)
            data = json.loads(raw) if fn.endswith(".json") else yaml.safe_load(raw)
            schema = json.loads(_read_text(sch_path))
            jsonschema.Draft202012Validator(schema).validate(data)
            ok += 1
        except Exception as e:
            fail.append({"config": fn, "schema": _rel(brain, sch_path), "error": str(e)})

    if fail:
        s.status = "FAIL"
    elif warn:
        s.status = "WARN"
    else:
        s.status = "PASS"
    s.message = f"OK={ok} WARN={len(warn)} FAIL={len(fail)}"
    s.data = {"ok": ok, "warn": warn, "fail": fail}
    return s


# === NoemaForge Autodoc Function Header ===
# Function: check_orphan_python_modules(brain: str)
# Purpose: Implement the routine 'check orphan python modules'.
# Inputs:
#   - brain: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - Step, join, walk, splitlines, _rel, _module_name, add, set, _strip_autodoc, split, basename, get
# Returns / emits: Step
# Key locals:
#   - alias, base, findings, fn, imp, imported, inbound, line, lines, mod, mod_parts, module
# === End NoemaForge Autodoc Function Header ===
def check_orphan_python_modules(brain: str) -> Step:
    s = Step("20", "Dormant Python module scan")

    # === NoemaForge Autodoc Function Header ===
    # Function: _strip_autodoc(text: str)
    # Purpose: Implement the routine ' strip autodoc'.
    # Inputs:
    #   - text: str
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - splitlines, join, strip, append
    # Returns / emits: str
    # Side effects:
    #   - appends to logs or files
    # Key locals:
    #   - line, lines, out, skip, stripped
    # === End NoemaForge Autodoc Function Header ===
    def _strip_autodoc(text: str) -> str:
        lines = text.splitlines()
        out: List[str] = []
        skip = False
        for line in lines:
            stripped = line.strip()
            if stripped in {"# === NoemaForge Autodoc File Header ===", "# === NoemaForge Autodoc Function Header ==="}:
                skip = True
                continue
            if stripped in {"# === End NoemaForge Autodoc File Header ===", "# === End NoemaForge Autodoc Function Header ==="}:
                skip = False
                continue
            if skip:
                continue
            out.append(line)
        return "\n".join(out)

    # === NoemaForge Autodoc Function Header ===
    # Function: _module_name(rel_parts: List[str])
    # Purpose: Implement the routine ' module name'.
    # Inputs:
    #   - rel_parts: List[str]
    # Called by:
    #   - tools/autodoc_inject.py
    # Calls:
    #   - join
    # Returns / emits: str
    # === End NoemaForge Autodoc Function Header ===
    def _module_name(rel_parts: List[str]) -> str:
        if rel_parts[-1] == "__init__.py":
            return ".".join(rel_parts[:-1])
        return ".".join(rel_parts)[:-3]

    src_root = os.path.join(brain, "src")
    py_files: List[str] = []
    for base, dirs, files in os.walk(src_root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIR_NAMES and d != "__pycache__"]
        for fn in files:
            if fn.endswith(".py"):
                py_files.append(os.path.join(base, fn))

    module_to_file: Dict[str, str] = {}
    simple_to_files: Dict[str, Set[str]] = {}
    for path in py_files:
        rel = _rel(brain, path)
        mod = _module_name(rel.split("/"))
        module_to_file[mod] = rel
        simple_to_files.setdefault(mod.split(".")[-1], set()).add(rel)

    inbound: Dict[str, Set[str]] = {rel: set() for rel in module_to_file.values()}
    for path in py_files:
        rel = _rel(brain, path)
        txt = _strip_autodoc(_read_text(path))
        try:
            tree = ast.parse(txt)
        except Exception:
            continue
        mod = _module_name(rel.split("/"))
        mod_parts = mod.split(".")
        imported: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    base = mod_parts[:-1]
                    up = max(0, node.level - 1)
                    base = base[: len(base) - up] if up <= len(base) else []
                    if module:
                        imported.add(".".join(base + [module]))
                    elif base:
                        imported.add(".".join(base))
                elif module:
                    imported.add(module)
        for imp in imported:
            if imp in module_to_file:
                targets = [module_to_file[imp]]
            else:
                targets = list(simple_to_files.get(imp.split(".")[-1], set()))
            for target in targets:
                if target != rel:
                    inbound.setdefault(target, set()).add(rel)

    repo_texts: List[Tuple[str, str]] = []
    for base, dirs, files in os.walk(brain):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIR_NAMES and d != "__pycache__"]
        for fn in files:
            if fn == "AUTODOC_INDEX.md" or fn == "SHA256SUMS":
                continue
            path = os.path.join(base, fn)
            if not fn.endswith((".py", ".yaml", ".yml", ".json", ".md", ".txt", ".ps1", ".cmd", ".sh", ".go")):
                continue
            try:
                repo_texts.append((_rel(brain, path), _strip_autodoc(_read_text(path))))
            except Exception:
                continue

    findings: List[Dict[str, Any]] = []
    for path in py_files:
        rel = _rel(brain, path)
        fn = os.path.basename(path)
        if fn == "__init__.py":
            continue
        txt = _strip_autodoc(_read_text(path))
        if 'if __name__ == "__main__"' in txt or "if __name__ == '__main__'" in txt:
            continue
        if inbound.get(rel):
            continue
        stem = os.path.splitext(fn)[0]
        referenced = False
        for other_rel, other_txt in repo_texts:
            if other_rel == rel:
                continue
            if stem in other_txt or rel in other_txt:
                referenced = True
                break
        if not referenced:
            findings.append({"module": rel, "reason": "no inbound imports and no external textual references"})

    if findings:
        s.status = "FAIL"
        s.message = f"Dormant modules detected: {len(findings)}"
    else:
        s.status = "PASS"
        s.message = "No high-confidence dormant Python modules detected"
    s.data = {"findings": findings}
    return s


# === NoemaForge Autodoc Function Header ===
# Function: check_autodoc_coverage(brain: str)
# Purpose: Implement the routine 'check autodoc coverage'.
# Inputs:
#   - brain: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - Step, walk, lower, join, _read_text, append, len, _rel, splitext
# Returns / emits: Step
# Side effects:
#   - appends to logs or files
# Key locals:
#   - ext, exts, fn, missing, path, s, total, txt
# === End NoemaForge Autodoc Function Header ===
def check_autodoc_coverage(brain: str) -> Step:
    s = Step("21", "Autodoc coverage for code files")
    exts = {".py", ".ps1", ".cmd", ".sh", ".go"}
    missing: List[str] = []
    total = 0
    for base, dirs, files in os.walk(brain):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIR_NAMES and d != "__pycache__"]
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in exts:
                continue
            path = os.path.join(base, fn)
            total += 1
            try:
                txt = _read_text(path)
            except Exception:
                continue
            if "NoemaForge Autodoc File Header" not in txt:
                missing.append(_rel(brain, path))
    if missing:
        s.status = "WARN"
        s.message = f"Missing file headers in {len(missing)} code files"
    else:
        s.status = "PASS"
        s.message = f"All {total} code files contain file headers"
    s.data = {"total": total, "missing": missing[:200]}
    return s


# === NoemaForge Autodoc Function Header ===
# Function: check_tool_activation_alignment(brain: str)
# Purpose: Validate that ToolPolicy allowlists do not silently depend on disabled registry entries unless rollout gating is explicit.
# Inputs:
#   - brain: str
# Called by:
#   - main
# Returns / emits: Step
# === End NoemaForge Autodoc Function Header ===
def check_tool_activation_alignment(brain: str) -> Step:
    s = Step("22", "Tool activation alignment")
    ok_yaml, _ = _try_import("yaml")
    if not ok_yaml:
        s.status = "WARN"
        s.message = "Skipped because PyYAML is unavailable"
        return s
    import yaml  # type: ignore

    reg_path = os.path.join(brain, 'configs', 'tool-registry.yaml')
    pol_path = os.path.join(brain, 'configs', 'tool-policy.yaml')
    if not (os.path.exists(reg_path) and os.path.exists(pol_path)):
        s.status = "WARN"
        s.message = "Registry or policy file is missing"
        return s
    registry_doc = yaml.safe_load(_read_text(reg_path)) or {}
    policy_doc = yaml.safe_load(_read_text(pol_path)) or {}
    registry = {str(t.get('id')): t for t in (registry_doc.get('tools') or []) if isinstance(t, dict) and t.get('id')}

    allowlisted: Dict[str, List[Dict[str, str]]] = {}
    for stream_id, stream_rec in (policy_doc.get('streams') or {}).items():
        if not isinstance(stream_rec, dict):
            continue
        for role_id, role_rec in ((stream_rec.get('roles') or {}).items()):
            if not isinstance(role_rec, dict):
                continue
            for action in role_rec.get('allow') or []:
                allowlisted.setdefault(str(action), []).append({'stream_id': str(stream_id), 'role': str(role_id)})

    fail: List[Dict[str, Any]] = []
    gated: List[str] = []
    for action, refs in sorted(allowlisted.items()):
        rec = registry.get(action)
        if not rec:
            fail.append({'action': action, 'reason': 'missing_from_registry', 'refs': refs})
            continue
        if bool(rec.get('enabled')):
            continue
        activation_mode = str(rec.get('activation_mode') or '').strip().lower()
        if activation_mode in {'rollout_gated', 'bundle_ready'}:
            gated.append(action)
            continue
        fail.append({'action': action, 'reason': 'allowlisted_but_disabled', 'refs': refs})

    if fail:
        s.status = 'FAIL'
        s.message = f'Tool activation mismatches detected: {len(fail)}'
    else:
        s.status = 'PASS'
        if gated:
            s.message = f'Policy/registry aligned; {len(gated)} actions are explicitly rollout-gated'
        else:
            s.message = 'Policy/registry aligned'
    s.data = {'fail': fail, 'gated': gated}
    return s


# === NoemaForge Autodoc Function Header ===
# Function: check_runtime_placeholder_markers(brain: str)
# Purpose: Detect high-confidence runtime placeholder markers in source, config, bootstrap, and runtime tools.
# Inputs:
#   - brain: str
# Called by:
#   - main
# Returns / emits: Step
# === End NoemaForge Autodoc Function Header ===
def check_runtime_placeholder_markers(brain: str) -> Step:
    s = Step("23", "Runtime placeholder markers")
    patterns = [
        (re.compile(r'if False else'), 'dead_branch_placeholder'),
        (re.compile(r'\(LLM unavailable -> placeholder\)'), 'role_placeholder_output'),
        (re.compile(r'\(stub\)'), 'stub_marker'),
        (re.compile(r'intentionally ships as a stub'), 'stub_docstring'),
        (re.compile(r'placeholder, expand'), 'config_placeholder_text'),
    ]
    scope_roots = [
        os.path.join(brain, 'src'),
        os.path.join(brain, 'configs'),
        os.path.join(brain, 'bootstrap'),
        os.path.join(brain, 'tools'),
    ]
    findings: List[Dict[str, Any]] = []
    for scope in scope_roots:
        if not os.path.exists(scope):
            continue
        for path in _list_files(scope):
            rel = _rel(brain, path)
            if rel.startswith('tools/sim/') or rel.startswith('tools/checker/') or rel.startswith('tests/'):
                continue
            text = _read_text(path)
            for rx, tag in patterns:
                for m in rx.finditer(text):
                    findings.append({'path': rel, 'tag': tag, 'offset': m.start()})
                    break
    if findings:
        s.status = 'FAIL'
        s.message = f'Runtime placeholder markers detected: {len(findings)}'
    else:
        s.status = 'PASS'
        s.message = 'No high-confidence runtime placeholder markers detected'
    s.data = {'findings': findings}
    return s


# === NoemaForge Autodoc Function Header ===
# Function: check_verifier_catalog_runtime(brain: str)
# Purpose: Validate that required stream verifiers exist in the catalog and that their declared types are supported by the runtime.
# Inputs:
#   - brain: str
# Called by:
#   - main
# Returns / emits: Step
# === End NoemaForge Autodoc Function Header ===
def check_verifier_catalog_runtime(brain: str) -> Step:
    s = Step("24", "Verifier catalog/runtime coverage")
    ok_yaml, _ = _try_import('yaml')
    if not ok_yaml:
        s.status = 'WARN'
        s.message = 'Skipped because PyYAML is unavailable'
        return s
    import yaml  # type: ignore

    src_dir = os.path.join(brain, 'src')
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    try:
        import verifiers as verifier_runtime  # type: ignore
    except Exception as e:
        s.status = 'FAIL'
        s.message = 'Unable to import verifier runtime'
        s.data = {'error': str(e)}
        return s

    ver_path = os.path.join(brain, 'configs', 'verifiers.yaml')
    streams_path = os.path.join(brain, 'configs', 'streams.yaml')
    if not (os.path.exists(ver_path) and os.path.exists(streams_path)):
        s.status = 'WARN'
        s.message = 'Verifier or stream config is missing'
        return s

    vdoc = yaml.safe_load(_read_text(ver_path)) or {}
    sdoc = yaml.safe_load(_read_text(streams_path)) or {}
    catalog = vdoc.get('verifiers') or {}
    required_ids: Set[str] = set()
    for _sid, rec in (sdoc.get('streams') or {}).items():
        if not isinstance(rec, dict):
            continue
        for vid in rec.get('required_verifiers') or []:
            required_ids.add(str(vid))

    missing_ids = sorted([vid for vid in required_ids if vid not in catalog])
    unsupported = []
    for vid, rec in catalog.items():
        if not isinstance(rec, dict):
            unsupported.append({'verifier_id': str(vid), 'reason': 'bad_record'})
            continue
        vtype = str(rec.get('type') or '')
        if vtype not in getattr(verifier_runtime, 'SUPPORTED_TYPES', set()):
            unsupported.append({'verifier_id': str(vid), 'type': vtype})

    if missing_ids or unsupported:
        s.status = 'FAIL'
        s.message = 'Verifier catalog/runtime mismatch detected'
    else:
        s.status = 'PASS'
        s.message = 'Verifier catalog and runtime coverage aligned'
    s.data = {'missing_ids': missing_ids, 'unsupported': unsupported}
    return s


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
#   - ArgumentParser, add_argument, parse_args, abspath, makedirs, Reporter, add, exit_code, dirname, check_structure, check_sha256, check_forbidden
# Returns / emits: int
# Side effects:
#   - creates directories
# Key locals:
#   - ap, args, brain, f, out, rep, report
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    # This checker must never create __pycache__ / *.pyc in the seed tree.
    sys.dont_write_bytecode = True

    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="Path to seed/noemaforge")
    ap.add_argument("--out", required=True, help="Output report path (.json)")
    ap.add_argument("--deep", action="store_true", help="Enable heavier checks")
    args = ap.parse_args()

    brain = os.path.abspath(args.root)
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    rep = Reporter()

    # Always run core steps
    rep.add(check_structure(brain))
    rep.add(check_sha256(brain))
    rep.add(check_forbidden(brain))
    rep.add(check_json(brain))
    rep.add(check_yaml(brain))
    rep.add(check_compile(brain))
    rep.add(check_epoch_files(brain))
    rep.add(check_deps())
    rep.add(check_unicode(brain))
    rep.add(check_roles_prompts(brain))
    rep.add(check_config_contract_pairs(brain))
    rep.add(check_orphan_python_modules(brain))
    rep.add(check_autodoc_coverage(brain))
    rep.add(check_tool_activation_alignment(brain))
    rep.add(check_runtime_placeholder_markers(brain))
    rep.add(check_verifier_catalog_runtime(brain))

    # Optional heavier checks
    if args.deep:
        # Placeholder: in the future we can run go build, static lints, etc.
        pass

    report = {
        "apiVersion": "noemaforge.checker/v1",
        "kind": "SeedCheckReport",
        "created_at": _nowz(),
        "brain_root": brain,
        "summary": {"fails": rep.fail, "warns": rep.warn, "step_count": len(rep.steps)},
        "steps": [asdict(s) for s in rep.steps],
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)

    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
