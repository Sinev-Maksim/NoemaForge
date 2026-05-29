#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/hwscan.py
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
# File: src/hwscan.py
# Purpose: Provide the module 'hwscan'.
# Invoked by / imported from:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/installer_plan.py
#   - src/offline_apt.py
# Public API / entry functions:
#   - collect_inventory
#   - fingerprint_inventory
#   - device_uid_from_fingerprint
#   - load_previous_fingerprint
#   - save_fingerprint
#   - main
# Inputs:
#   - Common path inputs: /var/lib/noemaforge/.sys/hardware-fingerprint.json, noemaforge.hwscan.inventory/v1
#   - Imports: __future__, hashlib, os, platform, re, shutil, subprocess, typing
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""hwscan.py (v0.11.0)

Offline-first hardware inventory + stable fingerprint.

Design goals:
- No network.
- Minimal dependencies.
- Useful even on very minimal Debian-like systems.
- Provide stable-ish device identity beyond SSID (for LocalGW):
  *device_uid* is derived from a fingerprint.

Security:
- Read-only probe (no writes except optional state file).
"""


import hashlib
import os
import platform
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_STATE_FILE = "/var/lib/noemaforge/.sys/hardware-fingerprint.json"


# === NoemaForge Autodoc Function Header ===
# Function: _read_text(path: str, limit: int = 1024 * 1024)
# Purpose: Implement the routine ' read text'.
# Inputs:
#   - path: str
#   - limit: int = 1024 * 1024
# Called by:
#   - src/lsm.py
#   - tools/autodoc_inject.py
#   - tools/checker/noemaforge_check.py
# Calls:
#   - decode, open, read
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - b, f
# === End NoemaForge Autodoc Function Header ===
def _read_text(path: str, limit: int = 1024 * 1024) -> str:
    try:
        with open(path, "rb") as f:
            b = f.read(limit)
        return b.decode("utf-8", errors="replace")
    except Exception:
        return ""


# === NoemaForge Autodoc Function Header ===
# Function: _run(cmd: List[str], timeout_sec: int = 8)
# Purpose: Implement the routine ' run'.
# Inputs:
#   - cmd: List[str]
#   - timeout_sec: int = 8
# Called by:
#   - src/bootdoctor.py
#   - src/storage_broker.py
#   - src/worktree_manager.py
# Calls:
#   - run, decode, int
# Returns / emits: Tuple[int, str, str]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - err, out, p
# === End NoemaForge Autodoc Function Header ===
def _run(cmd: List[str], timeout_sec: int = 8) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_sec)
        out = p.stdout.decode("utf-8", errors="replace")
        err = p.stderr.decode("utf-8", errors="replace")
        return int(p.returncode), out, err
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:
        return 127, "", f"exec_error:{e!r}"


# === NoemaForge Autodoc Function Header ===
# Function: _cpu_summary()
# Purpose: Implement the routine ' cpu summary'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _read_text, splitlines, startswith, machine, strip, split, lower
# Returns / emits: Dict[str, Any]
# Key locals:
#   - cores, flags, ln, model, txt
# === End NoemaForge Autodoc Function Header ===
def _cpu_summary() -> Dict[str, Any]:
    txt = _read_text("/proc/cpuinfo")
    model = ""
    cores = 0
    flags: List[str] = []
    for ln in txt.splitlines():
        if ln.lower().startswith("model name") and not model:
            model = ln.split(":", 1)[-1].strip()
        if ln.lower().startswith("processor"):
            cores += 1
        if ln.lower().startswith("flags") and not flags:
            flags = ln.split(":", 1)[-1].strip().split()
    return {
        "model": model,
        "cores": cores or None,
        "flags": flags[:80],
        "arch": platform.machine(),
    }


# === NoemaForge Autodoc Function Header ===
# Function: _mem_total_kb()
# Purpose: Implement the routine ' mem total kb'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _read_text, splitlines, startswith, search, int, group
# Returns / emits: Optional[int]
# Key locals:
#   - ln, m, txt
# === End NoemaForge Autodoc Function Header ===
def _mem_total_kb() -> Optional[int]:
    txt = _read_text("/proc/meminfo")
    for ln in txt.splitlines():
        if ln.startswith("MemTotal:"):
            m = re.search(r"MemTotal:\s+(\d+)", ln)
            if m:
                return int(m.group(1))
    return None


# === NoemaForge Autodoc Function Header ===
# Function: _pci_from_sysfs()
# Purpose: Implement the routine ' pci from sysfs'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sorted, isdir, listdir, join, strip, islink, append, _read_text, basename, readlink
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - base, cls, d, dev, device, drv, drvp, out, vendor
# === End NoemaForge Autodoc Function Header ===
def _pci_from_sysfs() -> List[Dict[str, Any]]:
    base = "/sys/bus/pci/devices"
    out: List[Dict[str, Any]] = []
    if not os.path.isdir(base):
        return out
    for dev in sorted(os.listdir(base)):
        d = os.path.join(base, dev)
        vendor = _read_text(os.path.join(d, "vendor")).strip()
        device = _read_text(os.path.join(d, "device")).strip()
        cls = _read_text(os.path.join(d, "class")).strip()
        drv = ""
        drvp = os.path.join(d, "driver")
        if os.path.islink(drvp):
            try:
                drv = os.path.basename(os.readlink(drvp))
            except Exception:
                drv = ""
        out.append({
            "slot": dev,
            "vendor": vendor,
            "device": device,
            "class": cls,
            "driver": drv,
        })
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _pci_from_lspci()
# Purpose: Implement the routine ' pci from lspci'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _run, splitlines, which, append, strip, startswith, search, split, lower, group
# Returns / emits: Optional[List[Dict[str, Any]]]
# Side effects:
#   - spawns subprocesses or workers
#   - appends to logs or files
# Key locals:
#   - cur, items, ln, m, t
# === End NoemaForge Autodoc Function Header ===
def _pci_from_lspci() -> Optional[List[Dict[str, Any]]]:
    if shutil.which("lspci") is None:
        return None
    # lspci -nnk: includes [vvvv:dddd] and Kernel driver in use
    rc, out, _ = _run(["lspci", "-nnk"], timeout_sec=12)
    if rc != 0 or not out:
        return None
    items: List[Dict[str, Any]] = []
    cur: Dict[str, Any] = {}
    for ln in out.splitlines():
        if not ln.strip():
            continue
        if not ln.startswith("\t"):
            # new device line
            if cur:
                items.append(cur)
            cur = {"raw": ln.strip()}
            cur["slot"] = ln.split()[0]
            m = re.search(r"\[(?P<vendor>[0-9a-fA-F]{4}):(?P<device>[0-9a-fA-F]{4})\]", ln)
            if m:
                cur["vendor"] = "0x" + m.group("vendor").lower()
                cur["device"] = "0x" + m.group("device").lower()
        else:
            t = ln.strip()
            if t.lower().startswith("kernel driver in use:"):
                cur["driver"] = t.split(":", 1)[-1].strip()
            if t.lower().startswith("kernel modules:"):
                cur["modules"] = [x.strip() for x in t.split(":", 1)[-1].split(",") if x.strip()]
    if cur:
        items.append(cur)
    return items


# === NoemaForge Autodoc Function Header ===
# Function: _net_ifaces()
# Purpose: Implement the routine ' net ifaces'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sorted, isdir, listdir, join, strip, append, islink, _read_text, basename, bool, readlink
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - base, dp, drv, ifn, mac, out, p, wireless
# === End NoemaForge Autodoc Function Header ===
def _net_ifaces() -> List[Dict[str, Any]]:
    base = "/sys/class/net"
    out: List[Dict[str, Any]] = []
    if not os.path.isdir(base):
        return out
    for ifn in sorted(os.listdir(base)):
        if ifn == "lo":
            continue
        p = os.path.join(base, ifn)
        mac = _read_text(os.path.join(p, "address")).strip()
        drv = ""
        try:
            dp = os.path.join(p, "device", "driver")
            if os.path.islink(dp):
                drv = os.path.basename(os.readlink(dp))
        except Exception:
            drv = ""
        wireless = os.path.isdir(os.path.join(p, "wireless"))
        out.append({"name": ifn, "mac": mac, "driver": drv, "wireless": bool(wireless)})
    return out


# === NoemaForge Autodoc Function Header ===
# Function: collect_inventory()
# Purpose: Implement the routine 'collect inventory'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/offline_apt.py
# Calls:
#   - _pci_from_lspci, _cpu_summary, _mem_total_kb, _net_ifaces, _pci_from_sysfs, join, release, uname
# Returns / emits: Dict[str, Any]
# Key locals:
#   - inv, pci_lspci
# === End NoemaForge Autodoc Function Header ===
def collect_inventory() -> Dict[str, Any]:
    inv: Dict[str, Any] = {
        "schema": "noemaforge.hwscan.inventory/v1",
        "platform": {
            "uname": " ".join(platform.uname()),
            "kernel": platform.release(),
        },
        "cpu": _cpu_summary(),
        "mem_total_kb": _mem_total_kb(),
        "pci": [],
        "net": _net_ifaces(),
    }

    pci_lspci = _pci_from_lspci()
    if pci_lspci is not None:
        inv["pci"] = pci_lspci
        inv["pci_source"] = "lspci"
    else:
        inv["pci"] = _pci_from_sysfs()
        inv["pci_source"] = "sysfs"

    return inv


# === NoemaForge Autodoc Function Header ===
# Function: fingerprint_inventory(inv: Dict[str, Any])
# Purpose: Compute a stable-ish fingerprint.
# Inputs:
#   - inv: Dict[str, Any]
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/installer_plan.py
# Calls:
#   - sha256, update, sorted, hexdigest, get, encode, str, append, isinstance, join
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - cls, cpu, d, device, drv, h, lines, ln, n, pci, raw, slot
# === End NoemaForge Autodoc Function Header ===
def fingerprint_inventory(inv: Dict[str, Any]) -> str:
    """Compute a stable-ish fingerprint.

    Avoid volatile fields; sort for determinism.
    """
    h = hashlib.sha256()

    cpu = inv.get("cpu") or {}
    h.update(str(cpu.get("model") or "").encode("utf-8"))
    h.update(b"\n")
    h.update(str(cpu.get("cores") or "").encode("utf-8"))
    h.update(b"\n")
    h.update(str(inv.get("mem_total_kb") or "").encode("utf-8"))
    h.update(b"\n")

    pci = inv.get("pci") or []
    lines: List[str] = []
    for d in pci:
        if not isinstance(d, dict):
            continue
        vendor = str(d.get("vendor") or "")
        device = str(d.get("device") or "")
        cls = str(d.get("class") or "")
        drv = str(d.get("driver") or "")
        slot = str(d.get("slot") or "")
        raw = str(d.get("raw") or "")
        lines.append("|".join([vendor, device, cls, drv, slot, raw[:120]]))
    for ln in sorted(lines):
        h.update(ln.encode("utf-8"))
        h.update(b"\n")

    for n in sorted(inv.get("net") or [], key=lambda x: str((x or {}).get("name") or "")):
        if not isinstance(n, dict):
            continue
        h.update(str(n.get("mac") or "").encode("utf-8"))
        h.update(b"\n")
        h.update(str(n.get("driver") or "").encode("utf-8"))
        h.update(b"\n")

    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: device_uid_from_fingerprint(fp: str)
# Purpose: Implement the routine 'device uid from fingerprint'.
# Inputs:
#   - fp: str
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def device_uid_from_fingerprint(fp: str) -> str:
    return "hw:" + fp[:32]


# === NoemaForge Autodoc Function Header ===
# Function: load_previous_fingerprint(state_file: str = DEFAULT_STATE_FILE)
# Purpose: Implement the routine 'load previous fingerprint'.
# Inputs:
#   - state_file: str = DEFAULT_STATE_FILE
# Called by:
#   - src/bootdoctor.py
# Calls:
#   - load, exists, open, str, get
# Returns / emits: Optional[str]
# Side effects:
#   - reads or writes files
# Key locals:
#   - obj
# === End NoemaForge Autodoc Function Header ===
def load_previous_fingerprint(state_file: str = DEFAULT_STATE_FILE) -> Optional[str]:
    try:
        import json
        if not os.path.exists(state_file):
            return None
        obj = json.load(open(state_file, "r", encoding="utf-8"))
        return str(obj.get("fingerprint") or "") or None
    except Exception:
        return None


# === NoemaForge Autodoc Function Header ===
# Function: save_fingerprint(fp: str, state_file: str = DEFAULT_STATE_FILE)
# Purpose: Implement the routine 'save fingerprint'.
# Inputs:
#   - fp: str
#   - state_file: str = DEFAULT_STATE_FILE
# Called by:
#   - src/bootdoctor.py
# Calls:
#   - makedirs, dump, dirname, open
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# === End NoemaForge Autodoc Function Header ===
def save_fingerprint(fp: str, state_file: str = DEFAULT_STATE_FILE) -> None:
    try:
        import json
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        json.dump({"fingerprint": fp}, open(state_file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        return


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
#   - collect_inventory, fingerprint_inventory, print
# Returns / emits: int
# Key locals:
#   - fp, inv
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    inv = collect_inventory()
    fp = fingerprint_inventory(inv)
    print(fp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
