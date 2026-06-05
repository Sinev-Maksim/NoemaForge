#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/quarantine_samples.py
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
# File: src/quarantine_samples.py
# Purpose: Provide the module 'quarantine_samples'.
# Invoked by / imported from:
#   - src/fixture_autogen.py
# Public API / entry functions:
#   - build_slim_signature_from_quarantine_dir
#   - maybe_store_quarantine_slim_sample
# Inputs:
#   - Common path inputs: /var/lib/noemaforge/.sys/fixture_samples/quarantine, quarantine_slim/v1
#   - Imports: __future__, datetime, gzip, hashlib, json, os, typing
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""quarantine_samples.py (v0.12.5)

Create *sterile* (non-leaking) snapshots of quarantine incidents for later canary evolution.

Why this exists
---------------
We want to auto-generate canary scenarios from real-world quarantine events without
copying toxic/indirect-prompt content into open zones.

So we store only:
  - hashes
  - structural signatures (keys, types, lengths)
  - bounded metadata

The resulting "sample" is a gzipped JSON signature (NOT the raw content).

Important constraints
---------------------
- No runtime canaries.
- No network.
- Best-effort: failures must not break normal operation.
"""


import datetime as dt
import gzip
import hashlib
import json
import os
from typing import Any, Dict, Optional, Tuple
from platform_paths import DEFAULT_PATHS as _pp


DEFAULT_STORE_DIR = str(_pp.data_root / ".sys/fixture_samples/quarantine")


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
# Function: _sha256_bytes(b: bytes)
# Purpose: Implement the routine ' sha256 bytes'.
# Inputs:
#   - b: bytes
# Called by:
#   - src/quarantine.py
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
# Function: _sha256_str(s: str)
# Purpose: Implement the routine ' sha256 str'.
# Inputs:
#   - s: str
# Called by:
#   - src/quarantine.py
# Calls:
#   - _sha256_bytes, encode
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _sha256_str(s: str) -> str:
    return _sha256_bytes((s or "").encode("utf-8", errors="ignore"))


# === NoemaForge Autodoc Function Header ===
# Function: _canon(obj)
# Purpose: Implement the routine ' canon'.
# Inputs:
#   - obj
# Called by:
#   - src/prestart.py
# Calls:
#   - dumps, str
# Returns / emits: str
# Side effects:
#   - serializes structured data
# === End NoemaForge Autodoc Function Header ===
def _canon(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(obj)


# === NoemaForge Autodoc Function Header ===
# Function: _value_sig(v)
# Purpose: Return a structural signature for a value (no raw content).
# Inputs:
#   - v
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - isinstance, _sha256_str, len, str, _canon, _value_sig, type, repr, get, list, keys
# Returns / emits: Dict[str, Any]
# Key locals:
#   - keys, s, sig
# === End NoemaForge Autodoc Function Header ===
def _value_sig(v: Any) -> Dict[str, Any]:
    """Return a structural signature for a value (no raw content)."""

    if v is None:
        return {"type": "null"}

    if isinstance(v, bool):
        return {"type": "bool"}

    if isinstance(v, (int, float)):
        # Avoid leaking exact amounts. Keep type only.
        return {"type": "number"}

    if isinstance(v, str):
        s = v
        return {"type": "string", "len": len(s), "sha256": _sha256_str(s)}

    if isinstance(v, list):
        return {"type": "list", "len": len(v), "head": [_value_sig(x) for x in v[:8]]}

    if isinstance(v, dict):
        keys = [str(k) for k in list(v.keys())[:64]]
        sig: Dict[str, Any] = {"type": "dict", "keys": keys}
        # Hash full dict canonical form to bind the signature.
        sig["sha256"] = _sha256_str(_canon({k: v.get(k) for k in keys}))
        sig["values"] = {k: _value_sig(v.get(k)) for k in keys[:16]}
        return sig

    return {"type": type(v).__name__, "sha256": _sha256_str(repr(v))}


# === NoemaForge Autodoc Function Header ===
# Function: build_slim_signature_from_quarantine_dir(quarantine_dir: str, store_dir: str = DEFAULT_STORE_DIR)
# Purpose: Create a gzipped *signature* sample from an on-disk quarantine snapshot.
# Inputs:
#   - quarantine_dir: str
#   - store_dir: str = DEFAULT_STORE_DIR
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, join, load, isinstance, exists, dict, pop, _sha256_str, makedirs, ValueError, FileNotFoundError, open
# Returns / emits: Tuple[str, str, Dict[str, Any]]
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - actor, args, canon_for_id, f, file_meta_path, files, fm, inc, incident_path, it, k, ks
# === End NoemaForge Autodoc Function Header ===
def build_slim_signature_from_quarantine_dir(
    *,
    quarantine_dir: str,
    store_dir: str = DEFAULT_STORE_DIR,
) -> Tuple[str, str, Dict[str, Any]]:
    """Create a gzipped *signature* sample from an on-disk quarantine snapshot.

    Returns (sample_sha256, sample_path, signature_obj).

    The signature object stores only hashes/lengths/keys.
    """

    qdir = str(quarantine_dir or "").strip()
    if not qdir:
        raise ValueError("missing_quarantine_dir")

    incident_path = os.path.join(qdir, "incident.json")
    if not os.path.exists(incident_path):
        raise FileNotFoundError("quarantine_incident_missing")

    inc = json.load(open(incident_path, "r", encoding="utf-8"))
    if not isinstance(inc, dict):
        raise ValueError("quarantine_incident_invalid")

    actor = inc.get("actor") if isinstance(inc.get("actor"), dict) else {}
    req = inc.get("request") if isinstance(inc.get("request"), dict) else {}
    resp = inc.get("response") if isinstance(inc.get("response"), dict) else {}

    sig: Dict[str, Any] = {
        "schema_version": "v1",
        "kind": "QuarantineSlimSample",
        "created_at": _nowz(),
        "quarantine_id": str(inc.get("quarantine_id") or ""),
        "trace_id": str(inc.get("trace_id") or ""),
        "ts": str(inc.get("ts") or ""),
        "action": str(inc.get("action") or ""),
        "reason_sha256": _sha256_str(str(inc.get("reason") or "")),
        "actor": {
            "stream_id": str(actor.get("stream_id") or ""),
            "role": str(actor.get("role") or ""),
            "project_id": str(actor.get("project_id") or ""),
            "process_id": str(actor.get("process_id") or ""),
        },
        "request_sig": {
            "action": str(req.get("action") or ""),
            "args_keys": sorted([str(k) for k in ((req.get("args") or {}) if isinstance(req.get("args"), dict) else {}).keys()])[:128],
            "args_values": {},
        },
        "response_sig": {
            "ok": bool(resp.get("ok", False)) if isinstance(resp, dict) else False,
            "trace_id": str(resp.get("trace_id") or "") if isinstance(resp, dict) else "",
        },
        # Do not store absolute paths.
        "quarantine_dir_hint": "<redacted>",
    }

    args = req.get("args") if isinstance(req.get("args"), dict) else {}
    if isinstance(args, dict):
        for k in list(args.keys())[:32]:
            ks = str(k)
            sig["request_sig"]["args_values"][ks] = _value_sig(args.get(k))

    # If file_meta exists, include the sample hashes only.
    file_meta_path = os.path.join(qdir, "file_meta.json")
    if os.path.exists(file_meta_path):
        try:
            fm = json.load(open(file_meta_path, "r", encoding="utf-8"))
            files = fm.get("files") if isinstance(fm, dict) else None
            if isinstance(files, list):
                sig["file_meta"] = []
                for it in files[:16]:
                    if not isinstance(it, dict):
                        continue
                    sig["file_meta"].append(
                        {
                            "exists": bool(it.get("exists", False)),
                            "size": int(it.get("size") or 0),
                            "sample_sha256": str(it.get("sample_sha256") or ""),
                            "sample_bytes": int(it.get("sample_bytes") or 0),
                            "path_sha256": _sha256_str(str(it.get("path") or "")),
                        }
                    )
        except Exception:
            pass

    # Sample id is hash of canonical signature WITHOUT created_at.
    canon_for_id = dict(sig)
    canon_for_id.pop("created_at", None)
    sample_id = _sha256_str(_canon(canon_for_id))

    os.makedirs(store_dir, exist_ok=True)
    out_path = os.path.join(store_dir, f"{sample_id}.json.gz")

    # Idempotent: do not rewrite if already present.
    if not os.path.exists(out_path):
        tmp = out_path + ".tmp"
        with gzip.open(tmp, "wt", encoding="utf-8", newline="\n") as f:
            json.dump(sig, f, ensure_ascii=False, indent=2)
        os.replace(tmp, out_path)
        try:
            os.chmod(store_dir, 0o700)
            os.chmod(out_path, 0o600)
        except Exception:
            pass

    return sample_id, out_path, sig


# === NoemaForge Autodoc Function Header ===
# Function: maybe_store_quarantine_slim_sample(quarantine_dir: str, store_dir: str = DEFAULT_STORE_DIR)
# Purpose: Best-effort wrapper that returns a reference dict or None.
# Inputs:
#   - quarantine_dir: str
#   - store_dir: str = DEFAULT_STORE_DIR
# Called by:
#   - src/fixture_autogen.py
# Calls:
#   - build_slim_signature_from_quarantine_dir
# Returns / emits: Optional[Dict[str, Any]]
# === End NoemaForge Autodoc Function Header ===
def maybe_store_quarantine_slim_sample(
    *,
    quarantine_dir: str,
    store_dir: str = DEFAULT_STORE_DIR,
) -> Optional[Dict[str, Any]]:
    """Best-effort wrapper that returns a reference dict or None."""

    try:
        sid, spath, _sig = build_slim_signature_from_quarantine_dir(quarantine_dir=quarantine_dir, store_dir=store_dir)
        # Do NOT return path by default; callers should not embed absolute paths into fixtures.
        return {"kind": "quarantine_slim/v1", "sha256": sid, "_stored": True}
    except Exception:
        return None
