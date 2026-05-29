#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/memsentinel.py
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
# File: src/memsentinel.py
# Purpose: Provide the module 'memsentinel'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - tick
#   - main
# Inputs:
#   - Common path inputs: /var/lib/noemaforge, /opt/noemaforge/configs/memsentinel.yaml
#   - Imports: __future__, datetime, os, time, uuid, typing, yaml, seclog
# Output formats / side effects:
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""
memsentinel.py (MVP)

Monitors:
- /proc/meminfo (MemAvailable)
- /proc/pressure/memory (PSI)

Escalates M1/M2/M3 and writes:
- SEL/WORM events (via seclog.append)
- a flagfile for checkpoint requests:
    /var/lib/noemaforge/.sys/memergency.checkpoint

Critical: memory pressure and near-OOM events are treated as CRITICAL class,
as requested (attempted overflow and near overflow).
"""

import datetime as dt
import os
import time
import uuid
from typing import Dict, Any

import yaml  # requires python3-yaml

from seclog import append as sel_append

BASE = "/var/lib/noemaforge"
SYS_DIR = os.path.join(BASE, ".sys")
CFG = "/opt/noemaforge/configs/memsentinel.yaml"


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
# Function: _read_mem_available_mib()
# Purpose: Implement the routine ' read mem available mib'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, startswith, split, float
# Returns / emits: float
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, kb, line, parts
# === End NoemaForge Autodoc Function Header ===
def _read_mem_available_mib() -> float:
    # Parse /proc/meminfo MemAvailable (kB)
    with open("/proc/meminfo", "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                parts = line.split()
                kb = float(parts[1])
                return kb / 1024.0
    return 0.0


# === NoemaForge Autodoc Function Header ===
# Function: _read_psi_memory()
# Purpose: Implement the routine ' read psi memory'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, strip, startswith, float, _kv
# Returns / emits: Dict[str, float]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, line, res
# === End NoemaForge Autodoc Function Header ===
def _read_psi_memory() -> Dict[str, float]:
    # Parse /proc/pressure/memory line: some avg10=.. avg60=.. avg300=.. total=..
    res = {"some_avg10": 0.0, "full_avg10": 0.0}
    try:
        with open("/proc/pressure/memory", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("some "):
                    res["some_avg10"] = float(_kv(line, "avg10"))
                if line.startswith("full "):
                    res["full_avg10"] = float(_kv(line, "avg10"))
    except Exception:
        pass
    return res


# === NoemaForge Autodoc Function Header ===
# Function: _kv(line: str, key: str)
# Purpose: Implement the routine ' kv'.
# Inputs:
#   - line: str
#   - key: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - split, startswith
# Returns / emits: str
# Key locals:
#   - part
# === End NoemaForge Autodoc Function Header ===
def _kv(line: str, key: str) -> str:
    for part in line.split():
        if part.startswith(key + "="):
            return part.split("=", 1)[1]
    return "0"


# === NoemaForge Autodoc Function Header ===
# Function: _load_cfg()
# Purpose: Implement the routine ' load cfg'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/role_runner.py
# Calls:
#   - open, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_cfg() -> Dict[str, Any]:
    with open(CFG, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# === NoemaForge Autodoc Function Header ===
# Function: _flag(path: str)
# Purpose: Implement the routine ' flag'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - makedirs, dirname, open, write, _nowz
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _flag(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_nowz() + "\n")


# === NoemaForge Autodoc Function Header ===
# Function: tick()
# Purpose: Implement the routine 'tick'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/maintenance.py
# Calls:
#   - _load_cfg, get, _read_mem_available_mib, _read_psi_memory, sel_append, str, _nowz, _flag, float, uuid4, join, lower
# Returns / emits: None
# Side effects:
#   - appends to logs or files
# Key locals:
#   - actions, cfg, chk, evt, free, full, level, m1, m2, m3, psi, some
# === End NoemaForge Autodoc Function Header ===
def tick() -> None:
    cfg = _load_cfg()
    thr = cfg.get("thresholds", {})
    m1 = thr.get("m1", {})
    m2 = thr.get("m2", {})
    m3 = thr.get("m3", {})
    actions = cfg.get("actions", {})

    free = _read_mem_available_mib()
    psi = _read_psi_memory()
    some = psi["some_avg10"]
    full = psi["full_avg10"]

    level = None
    if free < float(m3.get("free_mem_mib_below", 0)) or full > float(m3.get("psi_full_avg10_above", 1e9)):
        level = "M3"
    elif free < float(m2.get("free_mem_mib_below", 0)) or full > float(m2.get("psi_full_avg10_above", 1e9)):
        level = "M2"
    elif free < float(m1.get("free_mem_mib_below", 0)) or some > float(m1.get("psi_some_avg10_above", 1e9)):
        level = "M1"

    if not level:
        return

    evt = {
        "evt_id": str(uuid.uuid4()),
        "ts": _nowz(),
        "severity": "S3" if level in ("M2","M3") else "S2",
        "type": f"MEM_PRESSURE_{level}",
        "actor": {"subsystem": "memsentinel"},
        "decision": "escalate",
        "trace_id": str(uuid.uuid4()),
        "free_mem_mib": free,
        "psi_some_avg10": some,
        "psi_full_avg10": full,
        "actions": actions.get(level.lower(), []) or actions.get(level, []),
    }
    sel_append(evt)

    # If M2/M3: request checkpoint/spill via flagfile
    if level in ("M2","M3"):
        chk = (cfg.get("checkpoint_signal") or {}).get("path", os.path.join(SYS_DIR, "memergency.checkpoint"))
        _flag(chk)


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
#   - tick, sleep
# Returns / emits: int
# Key locals:
#   - interval
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    # loop
    interval = 2.0
    while True:
        tick()
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
