#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/seclog.py
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
# File: src/seclog.py
# Purpose: Provide the module 'seclog'.
# Invoked by / imported from:
#   - src/audit_remediation.py
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/bundles.py
#   - src/firstboot_eval.py
#   - src/incidents.py
#   - src/llm_backends_manager.py
#   - src/localgateway.py
#   - src/maintenance.py
# Public API / entry functions:
#   - append
#   - append_event
#   - verify
#   - seal
#   - verify_anchors
#   - main
# Inputs:
#   - Environment: NOEMAFORGE_SEL_DIR
#   - Common path inputs: /var/lib/noemaforge/sel/segments
#   - Imports: __future__, datetime, fcntl, hashlib, json, os, subprocess, sys
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""seclog.py (v0.11.0)

SEL/WORM-lite for NoemaForge: append-only JSONL with hash chains.

What this *is*:
  - A local, tamper-evident security event log (SEL).
  - Daily segment files, each with a line-by-line hash chain.
  - Optional cross-day anchors chain ("blockchain-like", but local).
  - Optional best-effort filesystem hardening with chattr (+a / +i).

What this is *not*:
  - A decentralized consensus blockchain.
  - An unbreakable guarantee against root.

Threat model:
  - We want tampering to be *detectable* and preferably *annoying*.
  - Root can still remove chattr flags; the system should then report anomalies.

Layout (defaults):
  SEL_DIR=/var/lib/noemaforge/sel/segments
    - YYYY-MM-DD.jsonl
    - YYYY-MM-DD.chain
    - YYYY-MM-DD.seal.json (optional)
  SEL_ROOT=/var/lib/noemaforge/sel
    - anchors.chain (optional)

Env knobs:
  - NOEMAFORGE_SEL_DIR: override segments directory
  - NOEMAFORGE_SEL_CHATTR=1|0: enable/disable best-effort chattr usage (default: 1)
  - NOEMAFORGE_SEL_SEAL_IMMUTABLE=1|0: if enabled, seal() tries to chattr +i segment
"""


import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
import uuid
from typing import Any, Dict, Optional

try:
    import fcntl  # POSIX advisory file locking; absent on Windows/macOS dev hosts
except ImportError:  # pragma: no cover - non-POSIX hosts
    fcntl = None  # type: ignore[assignment]

from platform_paths import DEFAULT_PATHS as _pp


def _flock_exclusive(fh) -> None:
    """Best-effort exclusive lock on an open file handle.

    POSIX advisory locking (fcntl.flock) on Unix; a no-op on hosts without
    fcntl (Windows/macOS dev). The security log's concurrent-writer guarantee
    is a property of the Linux production target; integrity is still protected
    by the per-record hash chain on every platform.
    """
    if fcntl is not None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)


def _flock_unlock(fh) -> None:
    """Release a lock taken by _flock_exclusive (no-op without fcntl)."""
    if fcntl is not None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


SEL_DIR = os.environ.get("NOEMAFORGE_SEL_DIR", str(_pp.data_root / "sel/segments"))
SEL_ROOT = os.path.dirname(SEL_DIR.rstrip("/"))
ANCHORS_CHAIN = os.path.join(SEL_ROOT, "anchors.chain")


# === NoemaForge Autodoc Function Header ===
# Function: _env_bool(name: str, default: bool)
# Purpose: Implement the routine ' env bool'.
# Inputs:
#   - name: str
#   - default: bool
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, lower, strip, str
# Returns / emits: bool
# Key locals:
#   - v
# === End NoemaForge Autodoc Function Header ===
def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    v = str(v).strip().lower()
    return v in ("1", "true", "yes", "y", "on")


# === NoemaForge Autodoc Function Header ===
# Function: _today()
# Purpose: Implement the routine ' today'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/planned_sweep.py
#   - src/scary_sweep.py
#   - src/sr_lite.py
#   - src/ssr_cycle.py
# Calls:
#   - strftime, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _today() -> str:
    return _dt.datetime.utcnow().strftime("%Y-%m-%d")


# === NoemaForge Autodoc Function Header ===
# Function: _paths(day: str)
# Purpose: Implement the routine ' paths'.
# Inputs:
#   - day: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - makedirs, join
# Returns / emits: tuple[str, str]
# Side effects:
#   - creates directories
# Key locals:
#   - chain, seg
# === End NoemaForge Autodoc Function Header ===
def _paths(day: str) -> tuple[str, str]:
    os.makedirs(SEL_DIR, exist_ok=True)
    os.makedirs(SEL_ROOT, exist_ok=True)
    seg = os.path.join(SEL_DIR, f"{day}.jsonl")
    chain = os.path.join(SEL_DIR, f"{day}.chain")
    return seg, chain


# === NoemaForge Autodoc Function Header ===
# Function: _sha256_bytes(b: bytes)
# Purpose: Implement the routine ' sha256 bytes'.
# Inputs:
#   - b: bytes
# Called by:
#   - src/quarantine.py
#   - src/quarantine_samples.py
#   - src/task_tools.py
# Calls:
#   - sha256, update, hexdigest
# Returns / emits: str
# Key locals:
#   - h
# === End NoemaForge Autodoc Function Header ===
def _sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


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
# Function: _read_last_hash(chain_path: str)
# Purpose: Implement the routine ' read last hash'.
# Inputs:
#   - chain_path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - exists, open, split, strip, readlines
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, lines
# === End NoemaForge Autodoc Function Header ===
def _read_last_hash(chain_path: str) -> str:
    if not os.path.exists(chain_path):
        return "0" * 64
    try:
        with open(chain_path, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        if not lines:
            return "0" * 64
        return lines[-1].split(" ", 1)[0]
    except Exception:
        return "0" * 64


# === NoemaForge Autodoc Function Header ===
# Function: _read_last_anchor()
# Purpose: Implement the routine ' read last anchor'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - exists, open, split, strip, readlines
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, lines
# === End NoemaForge Autodoc Function Header ===
def _read_last_anchor() -> str:
    if not os.path.exists(ANCHORS_CHAIN):
        return "0" * 64
    try:
        with open(ANCHORS_CHAIN, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]
        if not lines:
            return "0" * 64
        return lines[-1].split(" ", 1)[0]
    except Exception:
        return "0" * 64


# === NoemaForge Autodoc Function Header ===
# Function: _try_chattr(path: str, flag: str)
# Purpose: Best-effort chattr.
# Inputs:
#   - path: str
#   - flag: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _env_bool, run
# Returns / emits: None
# Side effects:
#   - spawns subprocesses or workers
# === End NoemaForge Autodoc Function Header ===
def _try_chattr(path: str, flag: str) -> None:
    """Best-effort chattr.

    flag: "+a" append-only, "+i" immutable.
    """
    if not _env_bool("NOEMAFORGE_SEL_CHATTR", True):
        return
    try:
        subprocess.run(["chattr", flag, path], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return


# === NoemaForge Autodoc Function Header ===
# Function: _ensure_append_only(path: str)
# Purpose: Implement the routine ' ensure append only'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _try_chattr
# Returns / emits: None
# === End NoemaForge Autodoc Function Header ===
def _ensure_append_only(path: str) -> None:
    _try_chattr(path, "+a")


# === NoemaForge Autodoc Function Header ===
# Function: append(event: Dict[str, Any])
# Purpose: Implement the routine 'append'.
# Inputs:
#   - event: Dict[str, Any]
# Called by:
#   - src/audit_remediation.py
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/bundles.py
#   - src/casebase.py
#   - src/coordinator_fanout.py
#   - src/daily_scheduler.py
# Calls:
#   - _today, _paths, dumps, encode, exists, str, open, flock, uuid4, isoformat, fileno, _read_last_hash
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - serializes structured data
# Key locals:
#   - chain_new, chf, day, h, last_hash, new_hash, payload, payload_bytes, seg_new, segf
# === End NoemaForge Autodoc Function Header ===
def append(event: Dict[str, Any]) -> Dict[str, Any]:
    day = _today()
    seg_path, chain_path = _paths(day)

    seg_new = not os.path.exists(seg_path)
    chain_new = not os.path.exists(chain_path)

    if "evt_id" not in event:
        event["evt_id"] = str(uuid.uuid4())
    if "ts" not in event:
        event["ts"] = _dt.datetime.utcnow().isoformat() + "Z"

    payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    payload_bytes = payload.encode("utf-8")

    # Lock segment file for consistent chain
    with open(seg_path, "a+", encoding="utf-8") as segf:
        _flock_exclusive(segf)

        # Lock chain too
        with open(chain_path, "a+", encoding="utf-8") as chf:
            _flock_exclusive(chf)

            last_hash = _read_last_hash(chain_path)

            h = hashlib.sha256()
            h.update(last_hash.encode("ascii"))
            h.update(payload_bytes)
            new_hash = h.hexdigest()

            segf.write(payload + "\n")
            segf.flush()
            os.fsync(segf.fileno())

            chf.write(f"{new_hash} {event['evt_id']}\n")
            chf.flush()
            os.fsync(chf.fileno())

            _flock_unlock(chf)
        _flock_unlock(segf)

    # Best-effort WORM hardening: make files append-only.
    try:
        if seg_new:
            _ensure_append_only(seg_path)
        if chain_new:
            _ensure_append_only(chain_path)
        if not os.path.exists(ANCHORS_CHAIN):
            os.makedirs(os.path.dirname(ANCHORS_CHAIN), exist_ok=True)
            with open(ANCHORS_CHAIN, "a", encoding="utf-8"):
                pass
            _ensure_append_only(ANCHORS_CHAIN)
    except Exception:
        pass

    event["_sel_hash"] = new_hash
    return event


# === NoemaForge Autodoc Function Header ===
# Function: append_event(phase: str, event_type: str, actor: Dict[str, Any], decision: str, trace_id: str, details: Dict[str, Any])
# Purpose: Backward-compatible structured append helper.
# Inputs:
#   - phase: str
#   - event_type: str
#   - actor: Dict[str, Any]
#   - decision: str
#   - trace_id: str
#   - details: Dict[str, Any]
# Called by:
#   - src/bundles.py
#   - src/localgateway.py
#   - src/nids_lite.py
#   - src/webgateway.py
# Calls:
#   - append, str
# Returns / emits: Dict[str, Any]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - evt
# === End NoemaForge Autodoc Function Header ===
def append_event(
    *,
    phase: str,
    event_type: str,
    actor: Dict[str, Any],
    decision: str,
    trace_id: str,
    details: Dict[str, Any],
) -> Dict[str, Any]:
    """Backward-compatible structured append helper.

    Several NoemaForge modules call seclog.append_event(...) to write SEL/WORM-lite records.
    Earlier versions of the seed kit implemented only append(event).

    This wrapper keeps the record format consistent and avoids leaking policy context
    by construction: callers pass structured fields instead of composing raw strings.
    """

    evt = {
        "phase": str(phase or ""),
        "event_type": str(event_type or ""),
        "actor": actor or {},
        "decision": str(decision or ""),
        "trace_id": str(trace_id or ""),
        "details": details or {},
    }
    return append(evt)


# === NoemaForge Autodoc Function Header ===
# Function: verify(day: Optional[str] = None)
# Purpose: Implement the routine 'verify'.
# Inputs:
#   - day: Optional[str] = None
# Called by:
#   - src/toolvault.py
# Calls:
#   - _paths, enumerate, _today, open, len, sha256, update, hexdigest, exists, rstrip, encode, strip
# Returns / emits: bool
# Side effects:
#   - reads or writes files
# Key locals:
#   - chains, chf, day, events, h, last, segf
# === End NoemaForge Autodoc Function Header ===
def verify(day: Optional[str] = None) -> bool:
    day = day or _today()
    seg_path, chain_path = _paths(day)
    if not os.path.exists(seg_path) or not os.path.exists(chain_path):
        # No logs is not a failure.
        return True

    with open(seg_path, "r", encoding="utf-8") as segf:
        events = [ln.rstrip("\n") for ln in segf if ln.strip()]
    with open(chain_path, "r", encoding="utf-8") as chf:
        chains = [ln.strip().split(" ", 1)[0] for ln in chf if ln.strip()]

    if len(events) != len(chains):
        return False

    last = "0" * 64
    for i, payload in enumerate(events):
        h = hashlib.sha256()
        h.update(last.encode("ascii"))
        h.update(payload.encode("utf-8"))
        last = h.hexdigest()
        if last != chains[i]:
            return False
    return True


# === NoemaForge Autodoc Function Header ===
# Function: seal(day: Optional[str] = None)
# Purpose: Seal a day segment: write seal file + advance anchors chain.
# Inputs:
#   - day: Optional[str] = None
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _paths, verify, _read_last_hash, _read_last_anchor, sha256, update, hexdigest, join, _env_bool, _today, encode, int
# Returns / emits: Dict[str, Any]
# Key locals:
#   - af, anchor_hash, count, day, f, h, last_hash, ok, prev_anchor, seal_obj, seal_path
# === End NoemaForge Autodoc Function Header ===
def seal(day: Optional[str] = None) -> Dict[str, Any]:
    """Seal a day segment: write seal file + advance anchors chain."""
    day = day or _today()
    seg_path, chain_path = _paths(day)

    ok = verify(day)
    if not ok:
        return {"ok": False, "day": day, "error": "verify_failed"}

    last_hash = _read_last_hash(chain_path)
    try:
        with open(seg_path, "r", encoding="utf-8") as f:
            count = sum(1 for ln in f if ln.strip())
    except Exception:
        count = 0

    prev_anchor = _read_last_anchor()
    h = hashlib.sha256()
    h.update(prev_anchor.encode("ascii"))
    h.update(day.encode("ascii"))
    h.update(last_hash.encode("ascii"))
    anchor_hash = h.hexdigest()

    seal_obj = {
        "ok": True,
        "day": day,
        "sealed_at": _dt.datetime.utcnow().isoformat() + "Z",
        "segment_last_hash": last_hash,
        "events": int(count),
        "anchor_prev": prev_anchor,
        "anchor_hash": anchor_hash,
    }

    seal_path = os.path.join(SEL_DIR, f"{day}.seal.json")
    try:
        with open(seal_path, "w", encoding="utf-8") as f:
            json.dump(seal_obj, f, ensure_ascii=False, indent=2)

        os.makedirs(os.path.dirname(ANCHORS_CHAIN), exist_ok=True)
        with open(ANCHORS_CHAIN, "a", encoding="utf-8") as af:
            af.write(f"{anchor_hash} {day} {last_hash} {count}\n")
            af.flush()
            os.fsync(af.fileno())
        _ensure_append_only(ANCHORS_CHAIN)
        _ensure_append_only(seal_path)
    except Exception as e:
        return {"ok": False, "day": day, "error": f"seal_write_failed:{e!r}"}

    if _env_bool("NOEMAFORGE_SEL_SEAL_IMMUTABLE", False):
        # Immutable means no further appends for that day.
        _try_chattr(seg_path, "+i")
        _try_chattr(chain_path, "+i")
        _try_chattr(seal_path, "+i")

    return seal_obj


# === NoemaForge Autodoc Function Header ===
# Function: verify_anchors()
# Purpose: Implement the routine 'verify anchors'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - exists, sha256, update, _paths, open, len, encode, hexdigest, _read_last_hash, split, strip
# Returns / emits: bool
# Side effects:
#   - reads or writes files
# Key locals:
#   - f, got, h, prev, row, rows
# === End NoemaForge Autodoc Function Header ===
def verify_anchors() -> bool:
    if not os.path.exists(ANCHORS_CHAIN):
        return True
    try:
        with open(ANCHORS_CHAIN, "r", encoding="utf-8") as f:
            rows = [ln.strip().split(" ") for ln in f if ln.strip()]
    except Exception:
        return False

    prev = "0" * 64
    for row in rows:
        if len(row) < 4:
            return False
        ah, day, last_hash = row[0], row[1], row[2]

        h = hashlib.sha256()
        h.update(prev.encode("ascii"))
        h.update(day.encode("ascii"))
        h.update(last_hash.encode("ascii"))
        if h.hexdigest() != ah:
            return False

        _seg, chain_path = _paths(day)
        if os.path.exists(chain_path):
            got = _read_last_hash(chain_path)
            if got != last_hash:
                return False
        prev = ah
    return True


# === NoemaForge Autodoc Function Header ===
# Function: main(argv: list[str])
# Purpose: Implement the routine 'main'.
# Inputs:
#   - argv: list[str]
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
#   - print, len, read, loads, append, verify, seal, verify_anchors, dumps, get
# Returns / emits: int
# Side effects:
#   - serializes structured data
#   - appends to logs or files
# Key locals:
#   - cmd, day, event, ok, out, raw
# === End NoemaForge Autodoc Function Header ===
def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: seclog.py append|verify|seal|verify-anchors [day]")
        return 2
    cmd = argv[1]
    if cmd == "append":
        raw = sys.stdin.read()
        event = json.loads(raw)
        out = append(event)
        print(json.dumps(out, ensure_ascii=False))
        return 0
    if cmd == "verify":
        day = argv[2] if len(argv) > 2 else None
        ok = verify(day)
        print("OK" if ok else "FAIL")
        return 0 if ok else 1
    if cmd == "seal":
        day = argv[2] if len(argv) > 2 else None
        out = seal(day)
        print(json.dumps(out, ensure_ascii=False))
        return 0 if out.get("ok") else 1
    if cmd == "verify-anchors":
        ok = verify_anchors()
        print("OK" if ok else "FAIL")
        return 0 if ok else 1
    print("unknown cmd:", cmd)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
