#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/storage_broker.py
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
# File: src/storage_broker.py
# Purpose: Provide the module 'storage_broker'.
# Invoked by / imported from:
#   - src/brainctl.py
#   - src/toolproxy.py
# Public API / entry functions:
#   - load_storage_policy
#   - class Mount
#   - mount_table
#   - mount_for_path
#   - disk_ptuuid_for_source
#   - ids_for_source
#   - match_allowlist_entry
#   - allow_mode_for_entry
#   - path_allowed
#   - enforce_mounts
# Inputs:
#   - Imports: __future__, json, os, re, subprocess, time, dataclasses, typing
# Output formats / side effects:
#   - Returns Python values and/or performs in-memory orchestration.
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""storage_broker.py (v0.13.0)

Stage-A goal
------------
NoemaForge должен уметь:
- Разрешать доступ к файлам по принципу "только origin-диск" по умолчанию.
- Опционально разрешать отдельные foreign volumes (обычно RO) через allowlist.
- Работать оффлайн и детерминированно: политика = epoch contract (storage-policy.yaml).
- Дать spine-слою возможность *best-effort enforcement* (guard) и *hard enforcement*
  на уровне ToolProxy (fs/db/exec mount roots).

Важно
-----
Этот модуль не пытается быть полноценным "mount daemon".
Он делает:
1) быстрые проверки "можно ли этому инструменту читать/писать путь"
2) best-effort guard: найти и (по политике) размонтировать/перемонтировать чужие тома

По умолчанию он консервативен: если не удаётся определить источник — DENY.
"""


import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import yaml


# ------------- helpers -------------

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
#   - tools/autodoc_inject_misc.py
# Calls:
#   - time
# Returns / emits: float
# === End NoemaForge Autodoc Function Header ===
def _now() -> float:
    return time.time()


# === NoemaForge Autodoc Function Header ===
# Function: _safe_realpath(p: str)
# Purpose: Implement the routine ' safe realpath'.
# Inputs:
#   - p: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - realpath, abspath
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _safe_realpath(p: str) -> str:
    try:
        return os.path.realpath(p)
    except Exception:
        return os.path.abspath(p)


# === NoemaForge Autodoc Function Header ===
# Function: _unescape_mountinfo(s: str)
# Purpose: Implement the routine ' unescape mountinfo'.
# Inputs:
#   - s: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sub, chr, int, group
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _unescape_mountinfo(s: str) -> str:
    # mountinfo escapes spaces and a few chars as octal sequences
    # e.g., \040 for space.
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), s)


# === NoemaForge Autodoc Function Header ===
# Function: _run(cmd: List[str], timeout: int = 3)
# Purpose: Implement the routine ' run'.
# Inputs:
#   - cmd: List[str]
#   - timeout: int = 3
# Called by:
#   - src/bootdoctor.py
#   - src/hwscan.py
#   - src/worktree_manager.py
# Calls:
#   - run, int, str
# Returns / emits: Tuple[int, str, str]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def _run(cmd: List[str], timeout: int = 3) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False, text=True)
        return int(p.returncode), p.stdout or "", p.stderr or ""
    except Exception as e:
        return 127, "", str(e)


# === NoemaForge Autodoc Function Header ===
# Function: load_storage_policy(path: str)
# Purpose: Implement the routine 'load storage policy'.
# Inputs:
#   - path: str
# Called by:
#   - src/brainctl.py
# Calls:
#   - open, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def load_storage_policy(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ------------- mount table -------------

@dataclass
class Mount:
    mount_point: str
    source: str
    fstype: str


_PSEUDO_FS = {
    "proc", "sysfs", "tmpfs", "devtmpfs", "devpts", "cgroup", "cgroup2",
    "pstore", "securityfs", "efivarfs", "mqueue", "hugetlbfs", "debugfs",
    "tracefs", "fusectl", "overlay", "squashfs", "ramfs",
}


# === NoemaForge Autodoc Function Header ===
# Function: mount_table()
# Purpose: Implement the routine 'mount table'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/brainctl.py
# Calls:
#   - sort, open, split, _unescape_mountinfo, append, len, index, Mount, strip
# Returns / emits: List[Mount]
# Side effects:
#   - reads or writes files
#   - appends to logs or files
# Key locals:
#   - f, fstype, line, mounts, mp, parts, sep, src
# === End NoemaForge Autodoc Function Header ===
def mount_table() -> List[Mount]:
    mounts: List[Mount] = []
    try:
        with open("/proc/self/mountinfo", "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if not parts:
                    continue
                try:
                    sep = parts.index("-")
                except ValueError:
                    continue
                # mountpoint is field 5 (0-index 4)
                mp = _unescape_mountinfo(parts[4])
                fstype = parts[sep + 1] if sep + 1 < len(parts) else ""
                src = parts[sep + 2] if sep + 2 < len(parts) else ""
                mounts.append(Mount(mount_point=mp, source=src, fstype=fstype))
    except Exception:
        return []

    # Longest mount point wins
    mounts.sort(key=lambda m: len(m.mount_point), reverse=True)
    return mounts


# === NoemaForge Autodoc Function Header ===
# Function: mount_for_path(path: str, mounts: Optional[List[Mount]] = None)
# Purpose: Implement the routine 'mount for path'.
# Inputs:
#   - path: str
#   - mounts: Optional[List[Mount]] = None
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _safe_realpath, mount_table, rstrip, startswith
# Returns / emits: Optional[Mount]
# Key locals:
#   - m, mounts, mp, p
# === End NoemaForge Autodoc Function Header ===
def mount_for_path(path: str, mounts: Optional[List[Mount]] = None) -> Optional[Mount]:
    p = _safe_realpath(path)
    if not mounts:
        mounts = mount_table()
    for m in mounts:
        mp = m.mount_point.rstrip("/")
        if mp == "":
            mp = "/"
        if p == mp or p.startswith(mp + "/"):
            return m
    return None


# ------------- device identity (lsblk cache) -------------

_LSBLK_CACHE: Dict[str, Any] = {"t": 0.0, "doc": None}

# === NoemaForge Autodoc Function Header ===
# Function: _lsblk_doc(max_age_sec: int = 5)
# Purpose: Implement the routine ' lsblk doc'.
# Inputs:
#   - max_age_sec: int = 5
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - float, _run, _now, get, strip, loads
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - doc, t
# === End NoemaForge Autodoc Function Header ===
def _lsblk_doc(max_age_sec: int = 5) -> Dict[str, Any]:
    t = float(_LSBLK_CACHE.get("t") or 0.0)
    if _LSBLK_CACHE.get("doc") is not None and (_now() - t) < max_age_sec:
        return _LSBLK_CACHE["doc"]  # type: ignore
    rc, out, _ = _run(["lsblk", "-J", "-o", "NAME,TYPE,PKNAME,PTUUID,UUID,PARTUUID,SERIAL,MODEL,PATH,MOUNTPOINT"], timeout=3)
    if rc != 0 or not out.strip():
        doc = {"blockdevices": []}
    else:
        try:
            doc = json.loads(out)
        except Exception:
            doc = {"blockdevices": []}
    _LSBLK_CACHE["t"] = _now()
    _LSBLK_CACHE["doc"] = doc
    return doc


# === NoemaForge Autodoc Function Header ===
# Function: _flatten_lsblk(doc: Dict[str, Any])
# Purpose: Implement the routine ' flatten lsblk'.
# Inputs:
#   - doc: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - append, get, isinstance, rec
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - bd, ch, out
# === End NoemaForge Autodoc Function Header ===
def _flatten_lsblk(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    # === NoemaForge Autodoc Function Header ===
    # Function: rec(node: Dict[str, Any])
    # Purpose: Implement the routine 'rec'.
    # Inputs:
    #   - node: Dict[str, Any]
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - append, get, isinstance, rec
    # Returns / emits: None
    # Side effects:
    #   - appends to logs or files
    # Key locals:
    #   - ch
    # === End NoemaForge Autodoc Function Header ===
    def rec(node: Dict[str, Any]) -> None:
        out.append(node)
        for ch in (node.get("children") or []):
            if isinstance(ch, dict):
                rec(ch)

    for bd in (doc.get("blockdevices") or []):
        if isinstance(bd, dict):
            rec(bd)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _dev_record_for_source(source: str, doc: Dict[str, Any])
# Purpose: Implement the routine ' dev record for source'.
# Inputs:
#   - source: str
#   - doc: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - startswith, _flatten_lsblk, replace, split, str, get
# Returns / emits: Optional[Dict[str, Any]]
# Key locals:
#   - n, nm, pu, src, uuid
# === End NoemaForge Autodoc Function Header ===
def _dev_record_for_source(source: str, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # source may be /dev/sda2, /dev/nvme0n1p2, /dev/mapper/...
    if not source:
        return None
    if source.startswith("UUID="):
        uuid = source.split("=", 1)[1]
        for n in _flatten_lsblk(doc):
            if str(n.get("uuid") or "") == uuid:
                return n
        return None
    if source.startswith("PARTUUID="):
        pu = source.split("=", 1)[1]
        for n in _flatten_lsblk(doc):
            if str(n.get("partuuid") or "") == pu:
                return n
        return None

    # normalize /dev/...
    src = source
    if src.startswith("/dev/"):
        # Try match by PATH first.
        for n in _flatten_lsblk(doc):
            if str(n.get("path") or "") == src:
                return n
        # Fallback: match by name.
        nm = src.replace("/dev/", "", 1)
        for n in _flatten_lsblk(doc):
            if str(n.get("name") or "") == nm:
                return n
    return None


# === NoemaForge Autodoc Function Header ===
# Function: disk_ptuuid_for_source(source: str)
# Purpose: Implement the routine 'disk ptuuid for source'.
# Inputs:
#   - source: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _lsblk_doc, _dev_record_for_source, str, strip, _flatten_lsblk, get
# Returns / emits: Optional[str]
# Key locals:
#   - doc, n, ntype, pk, ptuuid, x
# === End NoemaForge Autodoc Function Header ===
def disk_ptuuid_for_source(source: str) -> Optional[str]:
    doc = _lsblk_doc()
    n = _dev_record_for_source(source, doc)
    if not n:
        return None
    ntype = str(n.get("type") or "")
    if ntype == "disk":
        ptuuid = str(n.get("ptuuid") or "").strip()
        return ptuuid or None
    pk = str(n.get("pkname") or "").strip()
    if not pk:
        # maybe mapper: resolve via lsblk again (PATH to parent)
        return None
    for x in _flatten_lsblk(doc):
        if str(x.get("name") or "") == pk and str(x.get("type") or "") == "disk":
            ptuuid = str(x.get("ptuuid") or "").strip()
            return ptuuid or None
    return None


# === NoemaForge Autodoc Function Header ===
# Function: ids_for_source(source: str)
# Purpose: Implement the routine 'ids for source'.
# Inputs:
#   - source: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _lsblk_doc, _dev_record_for_source, strip, str, get
# Returns / emits: Dict[str, str]
# Key locals:
#   - doc, k, n, out, v
# === End NoemaForge Autodoc Function Header ===
def ids_for_source(source: str) -> Dict[str, str]:
    doc = _lsblk_doc()
    n = _dev_record_for_source(source, doc)
    if not n:
        return {}
    out = {}
    for k in ("uuid", "partuuid", "serial", "model", "path", "name", "type", "pkname", "ptuuid", "mountpoint"):
        v = str(n.get(k) or "").strip()
        if v:
            out[k] = v
    return out


# ------------- policy evaluation -------------

# === NoemaForge Autodoc Function Header ===
# Function: _origin_ptuuid(policy: Dict[str, Any])
# Purpose: Implement the routine ' origin ptuuid'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, get, mount_for_path, str, disk_ptuuid_for_source
# Returns / emits: Optional[str]
# Key locals:
#   - m, o, ptu, ptuuid
# === End NoemaForge Autodoc Function Header ===
def _origin_ptuuid(policy: Dict[str, Any]) -> Optional[str]:
    o = (policy.get("origin") or {})
    ptuuid = str(o.get("device_ptuuid") or "").strip()
    if not ptuuid or ptuuid == "SETUP_AUTODETECT":
        # Try detect from rootfs mount.
        m = mount_for_path("/")
        if m and m.source:
            ptu = disk_ptuuid_for_source(m.source)
            if ptu:
                return ptu
        return None
    return ptuuid


# === NoemaForge Autodoc Function Header ===
# Function: _allowlist(policy: Dict[str, Any])
# Purpose: Implement the routine ' allowlist'.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - src/localgateway.py
# Calls:
#   - isinstance, get, append
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - al, fv, out, x
# === End NoemaForge Autodoc Function Header ===
def _allowlist(policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    fv = (policy.get("foreign_volumes") or {})
    al = fv.get("allowlist") or []
    out: List[Dict[str, Any]] = []
    if isinstance(al, list):
        for x in al:
            if isinstance(x, dict):
                out.append(x)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: match_allowlist_entry(entry: Dict[str, Any], source_ids: Dict[str, str])
# Purpose: Implement the routine 'match allowlist entry'.
# Inputs:
#   - entry: Dict[str, Any]
#   - source_ids: Dict[str, str]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, str, get
# Returns / emits: bool
# Key locals:
#   - key, want
# === End NoemaForge Autodoc Function Header ===
def match_allowlist_entry(entry: Dict[str, Any], source_ids: Dict[str, str]) -> bool:
    # Allow matching by uuid/partuuid/serial/name/path
    for key in ("uuid", "partuuid", "serial", "name", "path", "ptuuid"):
        want = str(entry.get(key) or "").strip()
        if want:
            if str(source_ids.get(key) or "") == want:
                return True
    return False


# === NoemaForge Autodoc Function Header ===
# Function: allow_mode_for_entry(entry: Dict[str, Any])
# Purpose: Implement the routine 'allow mode for entry'.
# Inputs:
#   - entry: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, strip, str, get
# Returns / emits: str
# Key locals:
#   - mode
# === End NoemaForge Autodoc Function Header ===
def allow_mode_for_entry(entry: Dict[str, Any]) -> str:
    mode = str(entry.get("mode") or "ro").strip().lower()
    if mode not in ("ro", "rw"):
        mode = "ro"
    return mode


# === NoemaForge Autodoc Function Header ===
# Function: path_allowed(policy: Dict[str, Any], path: str, op: str)
# Purpose: Return (allowed, reason, context). op: read|write|exec|stat
# Inputs:
#   - policy: Dict[str, Any]
#   - path: str
#   - op: str
# Called by:
#   - src/brainctl.py
#   - src/toolproxy.py
# Calls:
#   - lower, mount_table, mount_for_path, _origin_ptuuid, disk_ptuuid_for_source, ids_for_source, _allowlist, _safe_realpath, get, strip, match_allowlist_entry, str
# Returns / emits: Tuple[bool, str, Dict[str, Any]]
# Key locals:
#   - ctx, default, ent, fv, m, mode, mount_root, mounts, mp, op2, origin, ptu
# === End NoemaForge Autodoc Function Header ===
def path_allowed(policy: Dict[str, Any], path: str, op: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Return (allowed, reason, context). op: read|write|exec|stat"""
    op2 = str(op or "read").strip().lower()
    if op2 not in ("read", "write", "exec", "stat"):
        op2 = "read"

    mounts = mount_table()
    m = mount_for_path(path, mounts)
    if not m:
        return False, "no_mount", {"path": path}

    ctx: Dict[str, Any] = {"path": _safe_realpath(path), "mount_point": m.mount_point, "source": m.source, "fstype": m.fstype}

    # Always allow pseudo fs reads? No: keep conservative; only allow within /proc,/sys,/dev reads from ToolProxy if explicit in tool-policy.
    if m.fstype in _PSEUDO_FS and m.fstype not in ("overlay",):
        ctx["pseudo"] = True
        return True, "pseudo_ok", ctx  # Tool-policy still gates; storage broker doesn't block pseudo FS.

    origin = _origin_ptuuid(policy)
    if not origin:
        return False, "origin_unknown", ctx

    if not m.source:
        return False, "source_unknown", ctx

    # Determine which disk this mount belongs to.
    ptu = disk_ptuuid_for_source(m.source)
    if ptu and ptu == origin:
        return True, "origin_ok", ctx

    ctx["source_ids"] = ids_for_source(m.source)
    ctx["origin_ptuuid"] = origin
    ctx["source_ptuuid"] = ptu or ""

    # Foreign volume policy
    fv = (policy.get("foreign_volumes") or {})
    default = str(fv.get("default") or "deny").strip().lower()
    mount_root = str(fv.get("mount_root") or "/mnt/foreign").strip() or "/mnt/foreign"

    # Allowlist matching
    for ent in _allowlist(policy):
        if match_allowlist_entry(ent, ctx.get("source_ids") or {}):
            mode = allow_mode_for_entry(ent)
            if op2 == "write" and mode != "rw":
                return False, "foreign_ro", ctx
            # Optional: require mount under mount_root unless explicitly disabled
            require_root = bool(ent.get("require_mount_root", True))
            if require_root:
                mp = str(m.mount_point or "")
                if not (mp == mount_root or mp.startswith(mount_root.rstrip("/") + "/")):
                    return False, "foreign_wrong_mountpoint", ctx
            return True, "foreign_allowlist", ctx

    # No allowlist match.
    if default == "ro":
        if op2 == "write":
            return False, "foreign_default_ro", ctx
        # even RO access is only allowed under mount_root
        mp = str(m.mount_point or "")
        if not (mp == mount_root or mp.startswith(mount_root.rstrip("/") + "/")):
            return False, "foreign_default_ro_wrong_mountpoint", ctx
        return True, "foreign_default_ro", ctx

    return False, "foreign_denied", ctx


# === NoemaForge Autodoc Function Header ===
# Function: enforce_mounts(policy: Dict[str, Any], dry_run: bool = False)
# Purpose: Best-effort enforcement: unmount/ro-remount foreign volumes not allowed.
# Inputs:
#   - policy: Dict[str, Any]
#   - dry_run: bool = False
# Called by:
#   - src/brainctl.py
# Calls:
#   - mount_table, _origin_ptuuid, lower, get, strip, str, path_allowed, append, len, bool, _allowlist, _run
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
#   - appends to logs or files
# Key locals:
#   - actions, default, ent, f, fv, line, m, mode, mount_root, mounts, mp, opts
# === End NoemaForge Autodoc Function Header ===
def enforce_mounts(policy: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    """Best-effort enforcement: unmount/ro-remount foreign volumes not allowed.

    This is not a full mount manager. It is a guard rail:
    - if something auto-mounted a foreign device, we try to unmount it
    - if allowlist permits only RO but mount is RW, we try remount ro
    """
    mounts = mount_table()
    origin = _origin_ptuuid(policy)
    fv = (policy.get("foreign_volumes") or {})
    default = str(fv.get("default") or "deny").strip().lower()
    mount_root = str(fv.get("mount_root") or "/mnt/foreign").strip() or "/mnt/foreign"

    actions: List[Dict[str, Any]] = []
    for m in mounts:
        if m.fstype in _PSEUDO_FS:
            continue
        mp = str(m.mount_point or "")
        src = str(m.source or "")
        if not mp or mp == "/":
            continue
        # skip if source not a block dev
        if not (src.startswith("/dev/") or src.startswith("UUID=") or src.startswith("PARTUUID=")):
            continue

        # Determine allow decision for a representative path: mount point itself.
        allow, reason, ctx = path_allowed(policy, mp, "stat")
        if allow:
            # if allowlist says RO and mount seems RW, try remount ro.
            # Cheap detection: look into /proc/mounts line options.
            mode = None
            for ent in _allowlist(policy):
                if match_allowlist_entry(ent, ctx.get("source_ids") or {}):
                    mode = allow_mode_for_entry(ent)
                    break
            if mode == "ro":
                # If mount options include rw, remount ro.
                try:
                    with open("/proc/mounts", "r", encoding="utf-8") as f:
                        for line in f:
                            if line.split()[1] == mp:
                                opts = line.split()[3]
                                if "rw" in opts.split(","):
                                    actions.append({"action": "remount_ro", "mount_point": mp, "source": src, "reason": "allowlist_ro_enforce"})
                                    if not dry_run:
                                        _run(["mount", "-o", "remount,ro", mp], timeout=5)
                                break
                except Exception:
                    pass
            continue

        # Not allowed: if it's foreign, try unmount (safer than remount).
        actions.append({"action": "unmount", "mount_point": mp, "source": src, "reason": reason})
        if not dry_run:
            _run(["umount", "-l", mp], timeout=5)

    return {
        "origin_ptuuid": origin or "",
        "mount_root": mount_root,
        "default": default,
        "actions": actions,
        "count": len(actions),
        "dry_run": bool(dry_run),
    }
