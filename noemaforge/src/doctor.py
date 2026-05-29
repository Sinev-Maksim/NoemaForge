#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/doctor.py
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
# File: src/doctor.py
# Purpose: Provide the module 'doctor'.
# Invoked by / imported from:
#   - src/bootdoctor.py
#   - src/brainctl.py
# Public API / entry functions:
#   - class CheckResult
#   - run_doctor
#   - main
# Inputs:
#   - --base-dir
#   - --full
#   - --json
#   - Imports: __future__, argparse, hashlib, json, os, re, sys, dataclasses
# Output formats / side effects:
#   - JSON files
#   - YAML files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""
doctor.py

Offline-first self-checks for NoemaForge seed/runtime trees.

Design goals:
- Fast by default (no full hashing unless requested).
- Deterministic output (JSON report).
- Never require network.
- Never read quarantine payload bodies (hashes only).
"""


import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml  # type: ignore

try:
    import jsonschema  # type: ignore
except Exception:  # pragma: no cover
    jsonschema = None  # type: ignore


FORBIDDEN_FILE_NAMES = {".DS_Store", "Thumbs.db"}
FORBIDDEN_PATH_SUFFIXES = {
    str(Path("src") / "noemaforge-llm-gateway"),
    str(Path("src") / "noemaforge-llm-gateway.exe"),
}
FORBIDDEN_GLOBS = ["**/*.pyc"]
FORBIDDEN_DIR_NAMES = {"__pycache__"}


@dataclass
class CheckResult:
    id: str
    ok: bool
    severity: str  # info|warn|fail
    summary: str
    details: List[str]


# === NoemaForge Autodoc Function Header ===
# Function: _sha256_file(path: Path)
# Purpose: Implement the routine ' sha256 file'.
# Inputs:
#   - path: Path
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/casebase.py
#   - src/glove_agent.py
#   - src/localgw_uplink_agent.py
#   - src/model_registry.py
#   - src/pipelines/finance_budget.py
#   - src/prestart.py
# Calls:
#   - sha256, hexdigest, open, iter, update, read
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - chunk, f, h
# === End NoemaForge Autodoc Function Header ===
def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _iter_text_files(base: Path)
# Purpose: Implement the routine ' iter text files'.
# Inputs:
#   - base: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - rglob, is_file, lower, append
# Returns / emits: List[Path]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - exts, out, p
# === End NoemaForge Autodoc Function Header ===
def _iter_text_files(base: Path) -> List[Path]:
    exts = {".py", ".yaml", ".yml", ".json", ".md", ".sh", ".ps1", ".go", ".txt"}
    out: List[Path] = []
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in exts:
            out.append(p)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _scan_forbidden(base: Path)
# Purpose: Implement the routine ' scan forbidden'.
# Inputs:
#   - base: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - rglob, sorted, glob, set, is_dir, append, is_file, len, str, relative_to
# Returns / emits: Tuple[bool, List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - bad, g, p, rel
# === End NoemaForge Autodoc Function Header ===
def _scan_forbidden(base: Path) -> Tuple[bool, List[str]]:
    bad: List[str] = []
    # forbidden names
    for p in base.rglob("*"):
        if p.is_dir() and p.name in FORBIDDEN_DIR_NAMES:
            bad.append(str(p))
        elif p.is_file():
            if p.name in FORBIDDEN_FILE_NAMES:
                bad.append(str(p))
            rel = str(p.relative_to(base))
            if rel in FORBIDDEN_PATH_SUFFIXES:
                bad.append(str(p))
    # forbidden globs
    for g in FORBIDDEN_GLOBS:
        for p in base.glob(g):
            bad.append(str(p))
    bad = sorted(set(bad))
    return (len(bad) == 0), bad


# === NoemaForge Autodoc Function Header ===
# Function: _parse_yaml_dir(configs_dir: Path)
# Purpose: Implement the routine ' parse yaml dir'.
# Inputs:
#   - configs_dir: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sorted, list, len, rglob, open, safe_load, append
# Returns / emits: Tuple[bool, List[str]]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - f, p, problems
# === End NoemaForge Autodoc Function Header ===
def _parse_yaml_dir(configs_dir: Path) -> Tuple[bool, List[str]]:
    problems: List[str] = []
    for p in sorted(list(configs_dir.rglob("*.yaml")) + list(configs_dir.rglob("*.yml"))):
        try:
            with p.open("r", encoding="utf-8") as f:
                yaml.safe_load(f)
        except Exception as e:
            problems.append(f"{p}: {e}")
    return (len(problems) == 0), problems


# === NoemaForge Autodoc Function Header ===
# Function: _parse_json_dir(base: Path)
# Purpose: Implement the routine ' parse json dir'.
# Inputs:
#   - base: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sorted, rglob, len, open, load, append
# Returns / emits: Tuple[bool, List[str]]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - f, p, problems
# === End NoemaForge Autodoc Function Header ===
def _parse_json_dir(base: Path) -> Tuple[bool, List[str]]:
    problems: List[str] = []
    for p in sorted(base.rglob("*.json")):
        try:
            with p.open("r", encoding="utf-8") as f:
                json.load(f)
        except Exception as e:
            problems.append(f"{p}: {e}")
    return (len(problems) == 0), problems


# === NoemaForge Autodoc Function Header ===
# Function: _validate_schemas(contracts_dir: Path)
# Purpose: Implement the routine ' validate schemas'.
# Inputs:
#   - contracts_dir: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sorted, rglob, check_schema, len, open, load, append
# Returns / emits: Tuple[bool, List[str]]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - f, p, problems, schema
# === End NoemaForge Autodoc Function Header ===
def _validate_schemas(contracts_dir: Path) -> Tuple[bool, List[str]]:
    if jsonschema is None:
        return True, ["jsonschema not installed; schema checks skipped"]
    problems: List[str] = []
    for p in sorted(contracts_dir.rglob("*.schema.json")):
        try:
            with p.open("r", encoding="utf-8") as f:
                schema = json.load(f)
            jsonschema.Draft7Validator.check_schema(schema)
        except Exception as e:
            problems.append(f"{p}: {e}")
    return (len(problems) == 0), problems


# === NoemaForge Autodoc Function Header ===
# Function: _extract_canary_test_ids_from_prestart(prestart_py: Path)
# Purpose: Implement the routine ' extract canary test ids from prestart'.
# Inputs:
#   - prestart_py: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - read_text, findall, sorted, set
# Returns / emits: List[str]
# Key locals:
#   - ids, txt
# === End NoemaForge Autodoc Function Header ===
def _extract_canary_test_ids_from_prestart(prestart_py: Path) -> List[str]:
    txt = prestart_py.read_text(encoding="utf-8")
    ids = re.findall(r'if tid == "([^"]+)"', txt)
    # also include elif tid == ...
    ids += re.findall(r'elif tid == "([^"]+)"', txt)
    return sorted(set(ids))


# === NoemaForge Autodoc Function Header ===
# Function: _check_canary_policy(canary_policy: Path, prestart_py: Path)
# Purpose: Implement the routine ' check canary policy'.
# Inputs:
#   - canary_policy: Path
#   - prestart_py: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - items, sorted, set, get, _extract_canary_test_ids_from_prestart, append, safe_load, isinstance, len, read_text, join
# Returns / emits: Tuple[bool, List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - known, missing, pol, problems, suites, t, tests, used
# === End NoemaForge Autodoc Function Header ===
def _check_canary_policy(canary_policy: Path, prestart_py: Path) -> Tuple[bool, List[str]]:
    problems: List[str] = []
    try:
        pol = yaml.safe_load(canary_policy.read_text(encoding="utf-8")) or {}
    except Exception as e:
        return False, [f"cannot parse canary-policy: {e}"]
    suites = (pol.get("suites") or {})
    used: List[str] = []
    for sname, sd in suites.items():
        tests = (sd or {}).get("tests") or []
        for t in tests:
            if isinstance(t, str):
                used.append(t)
    used = sorted(set(used))
    known = set(_extract_canary_test_ids_from_prestart(prestart_py))
    missing = [t for t in used if t not in known]
    if missing:
        problems.append("unknown canary test ids: " + ", ".join(missing))
    return (len(problems) == 0), problems


# === NoemaForge Autodoc Function Header ===
# Function: _check_epoch_files_exist(configs_dir: Path, prestart_py: Path)
# Purpose: Implement the routine ' check epoch files exist'.
# Inputs:
#   - configs_dir: Path
#   - prestart_py: Path
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - read_text, search, group, findall, sorted, set, exists, append, len
# Returns / emits: Tuple[bool, List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - body, files, fn, m, problems, txt
# === End NoemaForge Autodoc Function Header ===
def _check_epoch_files_exist(configs_dir: Path, prestart_py: Path) -> Tuple[bool, List[str]]:
    problems: List[str] = []
    txt = prestart_py.read_text(encoding="utf-8")
    # naive extract of EPOCH_FILES list of strings
    # Matches: EPOCH_FILES = [ "a.yaml", "b.yaml", ... ]
    m = re.search(r"EPOCH_FILES\s*=\s*\[(.*?)\]", txt, flags=re.S)
    if not m:
        return True, ["EPOCH_FILES not found in prestart.py (skipped)"]
    body = m.group(1)
    files = re.findall(r'"([^"]+\.ya?ml)"', body)
    for fn in sorted(set(files)):
        if not (configs_dir / fn).exists():
            problems.append(f"missing configs/{fn} (referenced by EPOCH_FILES)")
    return (len(problems) == 0), problems


# === NoemaForge Autodoc Function Header ===
# Function: _check_checksums(base: Path, full: bool)
# Purpose: Implement the routine ' check checksums'.
# Inputs:
#   - base: Path
#   - full: bool
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - splitlines, exists, strip, split, lower, lstrip, append, read_text, len, _sha256_file
# Returns / emits: Tuple[bool, List[str]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - actual, entries, lines, ln, p, parts, problems, rel, sha, sums
# === End NoemaForge Autodoc Function Header ===
def _check_checksums(base: Path, full: bool) -> Tuple[bool, List[str]]:
    problems: List[str] = []
    sums = base / "checksums" / "SHA256SUMS"
    if not sums.exists():
        return False, [f"missing {sums}"]
    # parse
    lines = sums.read_text(encoding="utf-8").splitlines()
    entries: List[Tuple[str, str]] = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        parts = ln.split()
        if len(parts) < 2:
            problems.append(f"bad line: {ln}")
            continue
        sha = parts[0].lower()
        rel = parts[1].lstrip("./")
        entries.append((sha, rel))
    for sha, rel in entries:
        p = base / rel
        if not p.exists():
            problems.append(f"MISSING: {rel}")
            continue
        if full:
            actual = _sha256_file(p)
            if actual != sha:
                problems.append(f"HASH MISMATCH: {rel} expected={sha} actual={actual}")
    return (len(problems) == 0), problems


# === NoemaForge Autodoc Function Header ===
# Function: run_doctor(base_dir: Optional[str] = None, full: bool = False)
# Purpose: Returns a deterministic JSON-serializable report.
# Inputs:
#   - base_dir: Optional[str] = None
#   - full: bool = False
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
# Calls:
#   - _scan_forbidden, append, _parse_yaml_dir, _parse_json_dir, _validate_schemas, _check_checksums, all, Path, CheckResult, exists, _check_canary_policy, _check_epoch_files_exist
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - base, c, canary_policy, checks, configs_dir, contracts_dir, ok, prestart_py, problems, warnings
# === End NoemaForge Autodoc Function Header ===
def run_doctor(*, base_dir: Optional[str] = None, full: bool = False) -> Dict[str, Any]:
    """
    Returns a deterministic JSON-serializable report.
    """
    base = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
    configs_dir = base / "configs"
    contracts_dir = base / "contracts"
    prestart_py = base / "src" / "prestart.py"
    canary_policy = configs_dir / "canary-policy.yaml"

    checks: List[CheckResult] = []

    ok_forb, forb = _scan_forbidden(base)
    checks.append(CheckResult(
        id="forbidden_artifacts",
        ok=ok_forb,
        severity="fail" if not ok_forb else "info",
        summary="no forbidden build artifacts" if ok_forb else "forbidden artifacts present",
        details=forb,
    ))

    ok_yaml, yprobs = _parse_yaml_dir(configs_dir)
    checks.append(CheckResult(
        id="yaml_parse",
        ok=ok_yaml,
        severity="fail" if not ok_yaml else "info",
        summary="configs YAML parse ok" if ok_yaml else "some YAML files failed to parse",
        details=yprobs,
    ))

    ok_json, jprobs = _parse_json_dir(contracts_dir)
    checks.append(CheckResult(
        id="json_parse",
        ok=ok_json,
        severity="fail" if not ok_json else "info",
        summary="contracts JSON parse ok" if ok_json else "some JSON files failed to parse",
        details=jprobs,
    ))

    ok_sch, sprobs = _validate_schemas(contracts_dir)
    checks.append(CheckResult(
        id="schema_validity",
        ok=ok_sch,
        severity="warn" if (not ok_sch) else ("warn" if (sprobs and "skipped" in sprobs[0]) else "info"),
        summary="json schemas valid" if ok_sch else "schema validation problems",
        details=sprobs,
    ))

    if prestart_py.exists() and canary_policy.exists():
        ok_can, cprobs = _check_canary_policy(canary_policy, prestart_py)
        checks.append(CheckResult(
            id="canary_policy_tests_known",
            ok=ok_can,
            severity="fail" if not ok_can else "info",
            summary="canary-policy tests match prestart implementation" if ok_can else "canary-policy references unknown tests",
            details=cprobs,
        ))
        ok_ep, eprobs = _check_epoch_files_exist(configs_dir, prestart_py)
        checks.append(CheckResult(
            id="epoch_files_exist",
            ok=ok_ep,
            severity="fail" if not ok_ep else "info",
            summary="all EPOCH_FILES exist under configs/" if ok_ep else "some EPOCH_FILES missing",
            details=eprobs,
        ))

    ok_sum, sumprobs = _check_checksums(base, full=full)
    checks.append(CheckResult(
        id="checksums",
        ok=ok_sum,
        severity="fail" if not ok_sum else ("info" if not full else "info"),
        summary="SHA256SUMS paths ok" if ok_sum and not full else ("SHA256SUMS verified" if ok_sum else "checksum problems"),
        details=sumprobs,
    ))

    ok = all(c.ok or c.severity != "fail" for c in checks)
    problems: List[str] = []
    warnings: List[str] = []
    for c in checks:
        if not c.ok:
            if c.severity == "fail":
                problems.extend([f"{c.id}:{d}" for d in c.details] if c.details else [c.id])
            elif c.severity == "warn":
                warnings.extend([f"{c.id}:{d}" for d in c.details] if c.details else [c.id])

    return {
        "ok": bool(ok),
        "base_dir": str(base),
        "full": bool(full),
        "checks": [c.__dict__ for c in checks],
        "problems": problems,
        "warnings": warnings,
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
#   - src/dream_cycle.py
#   - src/firstboot_eval.py
# Calls:
#   - ArgumentParser, add_argument, parse_args, run_doctor, print, dumps, get, bool
# Returns / emits: int
# Side effects:
#   - serializes structured data
#   - spawns subprocesses or workers
# Key locals:
#   - ap, args, rep
# === End NoemaForge Autodoc Function Header ===
def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", default="", help="NoemaForge root (default: inferred from this file)")
    ap.add_argument("--full", action="store_true", help="verify SHA256SUMS content hashes (slow)")
    ap.add_argument("--json", action="store_true", help="print JSON (default)")
    args = ap.parse_args(argv)

    rep = run_doctor(base_dir=(args.base_dir or None), full=bool(args.full))
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
