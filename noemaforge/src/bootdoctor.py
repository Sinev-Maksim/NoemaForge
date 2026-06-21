#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/bootdoctor.py
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
# File: src/bootdoctor.py
# Purpose: Provide the module 'bootdoctor'.
# Invoked by / imported from:
#   - src/brainctl.py
# Public API / entry functions:
#   - load_policy
#   - collect
#   - write_reports
#   - make_support_bundle
#   - boot
#   - onfailure
#   - quick
#   - bundle
#   - main
# Inputs:
#   - --mode
#   - --unit
#   - --level
#   - Environment: NOEMAFORGE_SEL_DIR
#   - Common path inputs: /opt/noemaforge/configs, noemaforge.bootdoctor/v1, /var/lib/noemaforge/boot/reports, /var/lib/noemaforge/boot/onfailure, /workspace/outbox/bootreports, /workspace/outbox/support, /var/lib/noemaforge/.sys/bootdoctor-state.json, /var/lib/noemaforge/.sys/hardware-fingerprint.json
#   - Imports: __future__, argparse, datetime, hashlib, json, os, re, shutil
# Output formats / side effects:
#   - JSON files
#   - YAML files
#   - Markdown files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""bootdoctor.py (v0.17.1)

BootDoctor: fast, offline-first startup diagnostics.

Goals:
- Make boot/startup failures cheap to debug.
- Produce *structured* reports + a portable support bundle.
- Never require network.
- Never expose quarantine payloads.

Modes:
- --mode boot       : run at boot (systemd oneshot)
- --mode onfailure  : run when a specific unit fails (OnFailure handler)
- --mode quick      : interactive quick report
- --mode bundle     : interactive support bundle

Security posture:
- Writes full report into /var/lib/noemaforge/boot (protected).
- Writes a *redacted* support bundle into /workspace/outbox/support.
"""


import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import yaml

from seclog import append as sel_append
from prestart import DEFAULT_CONTRACTS_ROOT
from epoch import current_epoch_id, current_epoch_dir
from platform_paths import DEFAULT_PATHS as _pp


CONFIG_DIR = str(_pp.root / "configs")
DEFAULT_POLICY = {
    "apiVersion": "noemaforge.bootdoctor/v1",
    "kind": "BootDoctorPolicy",
    "enabled": True,
    "report": {
        "reports_dir": str(_pp.data_root / "boot/reports"),
        "onfailure_dir": str(_pp.data_root / "boot/onfailure"),
        "outbox_reports_dir": "/workspace/outbox/bootreports",
        "outbox_support_dir": "/workspace/outbox/support",
        "keep_reports": 50,
        "keep_support_bundles": 20,
    },
    "collection": {
        "level": "auto",
        "journal_lines_boot": 1200,
        "journal_lines_per_unit": 400,
        "dmesg_lines": 500,
        "include_systemd_analyze": True,
        "include_lsblk": True,
        "include_mounts": True,
        "include_df": True,
        "include_free": True,
    },
    "failure_policy": {
        "watch_units": ["noemaforge-llm-gateway.service", "noemaforge-toolproxy.service", "noemaforge-memsentinel.service"],
        "bundle_on_failed_units": True,
        "onfailure_collect_unit_journal_lines": 900,
    },
    "first_run": {"force_full": True, "state_file": str(_pp.data_root / ".sys/bootdoctor-state.json")},
    "hardware": {
        "enabled": True,
        "include_inventory": "auto",  # auto|summary|full
        "state_file": str(_pp.data_root / ".sys/hardware-fingerprint.json"),
        "emit_installer_plan": {"on_first_seen": True, "on_hardware_change": True},
    },
    "redaction": {"enabled": True, "patterns": []},
}


# === NoemaForge Autodoc Function Header ===
# Function: _now()
# Purpose: Implement the routine ' now'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/flow_metrics.py
#   - src/localgw_ratelimit.py
#   - src/resource_recovery.py
#   - src/storage_broker.py
#   - tools/autodoc_inject_misc.py
# Calls:
#   - strftime, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _now() -> str:
    return dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


# === NoemaForge Autodoc Function Header ===
# Function: _read_text(path: str, limit: int = 1024 * 1024)
# Purpose: Implement the routine ' read text'.
# Inputs:
#   - path: str
#   - limit: int = 1024 * 1024
# Called by:
#   - src/hwscan.py
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
# Function: _run(cmd: List[str], timeout_sec: int = 15)
# Purpose: Implement the routine ' run'.
# Inputs:
#   - cmd: List[str]
#   - timeout_sec: int = 15
# Called by:
#   - src/hwscan.py
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
def _run(cmd: List[str], timeout_sec: int = 15) -> Tuple[int, str, str]:
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
# Function: _sha256_file(path: str)
# Purpose: Implement the routine ' sha256 file'.
# Inputs:
#   - path: str
# Called by:
#   - src/brainctl.py
#   - src/casebase.py
#   - src/doctor.py
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
def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: load_policy(epoch_dir: Optional[str] = None)
# Purpose: Implement the routine 'load policy'.
# Inputs:
#   - epoch_dir: Optional[str] = None
# Called by:
#   - src/audit_remediation.py
#   - src/brainctl.py
#   - src/daily_scheduler.py
#   - src/lsm.py
#   - src/maintenance.py
#   - src/resource_policy.py
#   - src/role_runner.py
#   - src/task_tools.py
# Calls:
#   - dict, join, exists, current_epoch_dir, isinstance, open, items, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - base, epoch_dir, f, out, p, y
# === End NoemaForge Autodoc Function Header ===
def load_policy(epoch_dir: Optional[str] = None) -> Dict[str, Any]:
    # Prefer epoch policy if present, fallback to /opt/noemaforge/configs.
    if epoch_dir is None:
        try:
            epoch_dir = current_epoch_dir(DEFAULT_CONTRACTS_ROOT)
        except Exception:
            epoch_dir = None
    for base in [epoch_dir, CONFIG_DIR, None]:
        if not base:
            continue
        p = os.path.join(base, "bootdoctor.yaml")
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    y = yaml.safe_load(f) or {}
                if isinstance(y, dict):
                    out = dict(DEFAULT_POLICY)
                    # shallow merge is enough for MVP
                    for k, v in y.items():
                        out[k] = v
                    return out
            except Exception:
                continue
    return dict(DEFAULT_POLICY)


# === NoemaForge Autodoc Function Header ===
# Function: _ensure_dirs(pol: Dict[str, Any])
# Purpose: Implement the routine ' ensure dirs'.
# Inputs:
#   - pol: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, strip, makedirs, str
# Returns / emits: None
# Side effects:
#   - creates directories
# Key locals:
#   - k, p, rep
# === End NoemaForge Autodoc Function Header ===
def _ensure_dirs(pol: Dict[str, Any]) -> None:
    rep = pol.get("report") or {}
    for k in ["reports_dir", "onfailure_dir", "outbox_reports_dir", "outbox_support_dir"]:
        p = str(rep.get(k) or "").strip()
        if p:
            os.makedirs(p, exist_ok=True)


# === NoemaForge Autodoc Function Header ===
# Function: _prune_dir(path: str, keep: int, suffix: str = '')
# Purpose: Implement the routine ' prune dir'.
# Inputs:
#   - path: str
#   - keep: int
#   - suffix: str = ''
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - sort, join, listdir, remove, isfile, getmtime, endswith
# Returns / emits: None
# Key locals:
#   - files, p
# === End NoemaForge Autodoc Function Header ===
def _prune_dir(path: str, keep: int, suffix: str = "") -> None:
    try:
        files = [os.path.join(path, fn) for fn in os.listdir(path)]
        files = [p for p in files if os.path.isfile(p) and (not suffix or p.endswith(suffix))]
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for p in files[keep:]:
            try:
                os.remove(p)
            except Exception:
                pass
    except Exception:
        pass


# === NoemaForge Autodoc Function Header ===
# Function: _redact_text(pol: Dict[str, Any], s: str)
# Purpose: Implement the routine ' redact text'.
# Inputs:
#   - pol: Dict[str, Any]
#   - s: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, bool, sub
# Returns / emits: str
# Key locals:
#   - out, pat, pats, red
# === End NoemaForge Autodoc Function Header ===
def _redact_text(pol: Dict[str, Any], s: str) -> str:
    red = pol.get("redaction") or {}
    if not bool(red.get("enabled", True)):
        return s
    pats = red.get("patterns") or []
    out = s
    for pat in pats:
        try:
            out = re.sub(pat, "[REDACTED]", out)
        except re.error:
            continue
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _first_run_level(pol: Dict[str, Any])
# Purpose: Implement the routine ' first run level'.
# Inputs:
#   - pol: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - makedirs, get, bool, strip, dirname, exists, str, open, dump, _now
# Returns / emits: Optional[str]
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f, fr, state_path
# === End NoemaForge Autodoc Function Header ===
def _first_run_level(pol: Dict[str, Any]) -> Optional[str]:
    fr = pol.get("first_run") or {}
    if not bool(fr.get("force_full", True)):
        return None
    state_path = str(fr.get("state_file") or "").strip() or str(_pp.data_root / ".sys/bootdoctor-state.json")
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    if not os.path.exists(state_path):
        # mark state now
        try:
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump({"first_seen": _now()}, f)
        except Exception:
            pass
        return "full"
    return None


# === NoemaForge Autodoc Function Header ===
# Function: _detect_failed_units()
# Purpose: Implement the routine ' detect failed units'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _run, splitlines, strip, split, endswith, append
# Returns / emits: List[str]
# Side effects:
#   - spawns subprocesses or workers
#   - appends to logs or files
# Key locals:
#   - failed, ln, unit
# === End NoemaForge Autodoc Function Header ===
def _detect_failed_units() -> List[str]:
    rc, out, _ = _run(["systemctl", "--failed", "--no-legend"], timeout_sec=10)
    if rc != 0:
        return []
    failed: List[str] = []
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        # Format: UNIT LOAD ACTIVE SUB DESCRIPTION
        unit = ln.split()[0]
        if unit.endswith(".service") or unit.endswith(".timer"):
            failed.append(unit)
    return failed


# === NoemaForge Autodoc Function Header ===
# Function: _boot_id()
# Purpose: Implement the routine ' boot id'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, read, open
# Returns / emits: str
# Side effects:
#   - reads or writes files
# === End NoemaForge Autodoc Function Header ===
def _boot_id() -> str:
    try:
        return open("/proc/sys/kernel/random/boot_id", "r", encoding="utf-8").read().strip()
    except Exception:
        return ""


# === NoemaForge Autodoc Function Header ===
# Function: _write_runtime_mode()
# Purpose: Implement the routine ' write runtime mode'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - makedirs, open, write
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - creates directories
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _write_runtime_mode() -> None:
    try:
        os.makedirs(str(_pp.runtime_dir), exist_ok=True)
        with open(str(_pp.runtime_dir / "mode"), "w", encoding="utf-8") as f:
            f.write("runtime\n")
    except Exception:
        pass


# === NoemaForge Autodoc Function Header ===
# Function: _sel_tail(max_lines: int = 200)
# Purpose: Return last N lines of today's SEL segment (best-effort).
# Inputs:
#   - max_lines: int = 200
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strftime, get, join, exists, open, utcnow, rstrip, strip
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - day, f, lines, p, sel_dir
# === End NoemaForge Autodoc Function Header ===
def _sel_tail(max_lines: int = 200) -> str:
    """Return last N lines of today's SEL segment (best-effort)."""
    try:
        day = dt.datetime.utcnow().strftime("%Y-%m-%d")
        sel_dir = os.environ.get("NOEMAFORGE_SEL_DIR", str(_pp.data_root / "sel/segments"))
        p = os.path.join(sel_dir, f"{day}.jsonl")
        if not os.path.exists(p):
            return ""
        with open(p, "r", encoding="utf-8") as f:
            lines = [ln.rstrip("\n") for ln in f if ln.strip()]
        return "\n".join(lines[-max_lines:])
    except Exception:
        return ""


# === NoemaForge Autodoc Function Header ===
# Function: _diagnose(report: Dict[str, Any])
# Purpose: Cheap heuristics for "what likely broke".
# Inputs:
#   - report: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, get, append, add, bool, join
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - checks, findings, state, sysd
# === End NoemaForge Autodoc Function Header ===
def _diagnose(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Cheap heuristics for "what likely broke"."""
    findings: List[Dict[str, Any]] = []
    checks = report.get("checks") or {}
    sysd = ((report.get("data") or {}).get("systemd") or {})
    state = str(sysd.get("state") or "")

    # === NoemaForge Autodoc Function Header ===
    # Function: add(fid: str, severity: str, msg: str, rec: str, evidence: Optional[Dict[str, Any]] = None)
    # Purpose: Implement the routine 'add'.
    # Inputs:
    #   - fid: str
    #   - severity: str
    #   - msg: str
    #   - rec: str
    #   - evidence: Optional[Dict[str, Any]] = None
    # Called by:
    #   - src/brainctl.py
    #   - src/noemaforge_core.py
    #   - src/flow_catalog.py
    #   - src/glove_agent.py
    #   - src/incidents.py
    #   - src/installer_plan.py
    #   - src/localgateway.py
    #   - src/localgw_uplink_agent.py
    # Calls:
    #   - append
    # Returns / emits: None
    # Side effects:
    #   - appends to logs or files
    # === End NoemaForge Autodoc Function Header ===
    def add(fid: str, severity: str, msg: str, rec: str, evidence: Optional[Dict[str, Any]] = None) -> None:
        findings.append({
            "id": fid,
            "severity": severity,
            "message": msg,
            "recommendation": rec,
            "evidence": evidence or {},
        })

    if state and state not in ("running", "degraded"):
        add(
            "systemd_not_running",
            "high",
            f"systemd state is '{state}'",
            "Check failing units in report; consider: systemctl --failed; journalctl -b.",
            {"systemd_state": state},
        )

    if not bool(checks.get("bin.gateway_exists")):
        add(
            "missing_llm_gateway_bin",
            "critical",
            f"Missing {_pp.root / 'bin' / 'noemaforge-llm-gateway'}",
            f"Re-run bootstrap/provision step that installs NoemaForge bins into {_pp.root / 'bin'}.",
            {"path": str(_pp.root / "bin" / "noemaforge-llm-gateway")},
        )

    if not bool(checks.get("sandbox.bwrap")) and not bool(checks.get("sandbox.podman")):
        add(
            "no_sandbox_backend",
            "critical",
            "No sandbox backend detected (bubblewrap and podman missing)",
            "Install bubblewrap (preferred) or podman+uidmap. Without a sandbox, tool execution must be denied.",
            {"bwrap": bool(checks.get("sandbox.bwrap")), "podman": bool(checks.get("sandbox.podman"))},
        )

    if report.get("watched_failed_units"):
        add(
            "watched_units_failed",
            "high",
            f"Watched units failed: {', '.join(report.get('watched_failed_units') or [])}",
            "Inspect unit status and journal tails in this report. If persistent, generate a support bundle.",
            {"failed": report.get("watched_failed_units")},
        )

    return findings


# === NoemaForge Autodoc Function Header ===
# Function: collect(pol: Dict[str, Any], mode: str, unit: str = '', requested_level: str = 'auto')
# Purpose: Implement the routine 'collect'.
# Inputs:
#   - pol: Dict[str, Any]
#   - mode: str
#   - unit: str = ''
#   - requested_level: str = 'auto'
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _ensure_dirs, _first_run_level, _detect_failed_units, set, exists, bool, get, int, list, _diagnose, str, _boot_id
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - changed, checks, col, dmesg_n, emit, epoch_dir, failed_units, first_seen, fp, fr, hw_block, hw_pol
# === End NoemaForge Autodoc Function Header ===
def collect(pol: Dict[str, Any], *, mode: str, unit: str = "", requested_level: str = "auto") -> Dict[str, Any]:
    _ensure_dirs(pol)

    level = requested_level
    if (pol.get("collection") or {}).get("level") and requested_level == "auto":
        level = str((pol.get("collection") or {}).get("level") or "auto")

    # First boot -> full
    fr = _first_run_level(pol)
    if fr:
        level = fr

    # auto means: quick unless we see failures
    failed_units = _detect_failed_units()
    watch = set((pol.get("failure_policy") or {}).get("watch_units") or [])
    watched_failed = [u for u in failed_units if (not watch) or (u in watch)]

    if level == "auto":
        level = "full" if watched_failed else "quick"

    col = pol.get("collection") or {}

    report: Dict[str, Any] = {
        "schema": "noemaforge.bootdoctor.report/v1",
        "ts": dt.datetime.utcnow().isoformat() + "Z",
        "mode": mode,
        "level": level,
        "boot_id": _boot_id(),
        "epoch_id": current_epoch_id(DEFAULT_CONTRACTS_ROOT),
        "failed_units": failed_units,
        "watched_failed_units": watched_failed,
        "unit": unit or "",
        "checks": {},
        "data": {},
    }

    # quick checks: binaries + sandbox backends
    checks: Dict[str, Any] = {}
    checks["bin.gateway_exists"] = os.path.exists(str(_pp.root / "bin" / "noemaforge-llm-gateway"))
    checks["bin.llama_server_exists"] = os.path.exists(str(_pp.root / "bin" / "llama-server"))
    checks["sandbox.bwrap"] = shutil.which("bwrap") is not None
    checks["sandbox.podman"] = shutil.which("podman") is not None
    checks["mode_file"] = os.path.exists(str(_pp.runtime_dir / "mode"))

    report["checks"] = checks

    # Hardware inventory + fingerprint (helps portability: disk moved to new machine)
    hw_pol = pol.get("hardware") or {}
    if bool(hw_pol.get("enabled", True)):
        try:
            from hwscan import collect_inventory, fingerprint_inventory, load_previous_fingerprint, save_fingerprint, device_uid_from_fingerprint
            from installer_plan import load_policy as load_installer_policy, build_plan, write_plan

            inv = collect_inventory()
            fp = fingerprint_inventory(inv)
            prev_fp = load_previous_fingerprint(str(hw_pol.get("state_file") or str(_pp.data_root / ".sys/hardware-fingerprint.json")))
            changed = bool(prev_fp) and (prev_fp != fp)
            first_seen = prev_fp is None

            # Persist new fingerprint (best-effort)
            save_fingerprint(fp, str(hw_pol.get("state_file") or str(_pp.data_root / ".sys/hardware-fingerprint.json")))

            # include inventory level
            inv_mode = str(hw_pol.get("include_inventory") or "auto").lower().strip()
            if inv_mode == "auto":
                inv_mode = "full" if level == "full" else "summary"

            hw_block: Dict[str, Any] = {
                "fingerprint": fp,
                "prev_fingerprint": prev_fp,
                "hardware_changed": changed,
                "first_seen": first_seen,
                "device_uid": device_uid_from_fingerprint(fp),
                "source": inv.get("pci_source"),
                "summary": {
                    "cpu": (inv.get("cpu") or {}).get("model"),
                    "cores": (inv.get("cpu") or {}).get("cores"),
                    "mem_total_kb": inv.get("mem_total_kb"),
                    "pci_count": len(inv.get("pci") or []),
                    "net_ifaces": [x.get("name") for x in (inv.get("net") or []) if isinstance(x, dict)],
                },
            }
            if inv_mode == "full":
                hw_block["inventory"] = inv

            report["data"]["hardware"] = hw_block

            # Optionally emit installer plan (first boot = FULL anyway)
            emit = hw_pol.get("emit_installer_plan") or {}
            should_emit = (bool(emit.get("on_first_seen", True)) and first_seen) or (bool(emit.get("on_hardware_change", True)) and changed)
            if should_emit:
                try:
                    epoch_dir = current_epoch_dir(DEFAULT_CONTRACTS_ROOT)
                except Exception:
                    epoch_dir = None
                ipol = load_installer_policy(epoch_dir)
                plan = build_plan(inv, ipol)
                paths = write_plan(plan, ipol)
                report["data"]["installer_plan"] = {
                    "plan_id": plan.get("plan_id"),
                    "plan_json": paths.get("plan_json"),
                    "plan_md": paths.get("plan_md"),
                    "prestart_skeleton": paths.get("prestart_skeleton"),
                    "reason": "first_seen" if first_seen else "hardware_change",
                }
        except Exception as e:
            report["data"]["hardware"] = {"error": f"hwscan_failed:{e!r}"}

    # systemd status summary
    if True:
        rc, out, err = _run(["systemctl", "is-system-running", "--wait"], timeout_sec=6)
        report["data"]["systemd"] = {"rc": rc, "state": (out.strip() or err.strip())}

    if col.get("include_lsblk", True):
        rc, out, err = _run(["lsblk", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,UUID,PTUUID"], timeout_sec=8)
        report["data"]["lsblk"] = {"rc": rc, "out": out, "err": err}

    if col.get("include_mounts", True):
        rc, out, err = _run(["mount"], timeout_sec=6)
        report["data"]["mounts"] = {"rc": rc, "out": out, "err": err}

    if col.get("include_df", True):
        rc, out, err = _run(["df", "-h"], timeout_sec=6)
        report["data"]["df"] = {"rc": rc, "out": out, "err": err}

    if col.get("include_free", True):
        rc, out, err = _run(["free", "-h"], timeout_sec=6)
        report["data"]["free"] = {"rc": rc, "out": out, "err": err}

    # dmesg + journal: level-based
    dmesg_n = int(col.get("dmesg_lines", 500) or 500)
    if level in ("quick", "full"):
        rc, out, err = _run(["dmesg", "--color=never"], timeout_sec=10)
        if out:
            out_lines = out.splitlines()[-dmesg_n:]
            report["data"]["dmesg_tail"] = "\n".join(out_lines)
        else:
            report["data"]["dmesg_tail"] = err

    # journal boot tail
    j_boot = int(col.get("journal_lines_boot", 1200) or 1200)
    if level == "full":
        rc, out, err = _run(["journalctl", "-b", "--no-pager", "-n", str(j_boot)], timeout_sec=18)
        report["data"]["journal_boot_tail"] = out or err

    # per-unit excerpts (always)
    j_unit = int(col.get("journal_lines_per_unit", 400) or 400)
    units = list(dict.fromkeys((pol.get("failure_policy") or {}).get("watch_units") or []))
    if unit:
        units = list(dict.fromkeys([unit] + units))
    unit_logs: Dict[str, Any] = {}
    for u in units[:20]:
        rc, out, err = _run(["systemctl", "status", u, "--no-pager"], timeout_sec=10)
        st = out or err
        rc2, out2, err2 = _run(["journalctl", "-u", u, "-b", "--no-pager", "-n", str(j_unit)], timeout_sec=18)
        jl = out2 or err2
        unit_logs[u] = {"status": st, "journal_tail": jl, "rc": rc, "rc_j": rc2}
    report["data"]["units"] = unit_logs

    # systemd-analyze (optional)
    if bool(col.get("include_systemd_analyze", True)) and level in ("quick", "full"):
        rc, out, err = _run(["systemd-analyze"], timeout_sec=10)
        report["data"]["systemd_analyze"] = out.strip() or err.strip()
        rc, out, err = _run(["systemd-analyze", "blame"], timeout_sec=20)
        report["data"]["systemd_analyze_blame"] = "\n".join(out.splitlines()[:120]) if out else err

    # Heuristic diagnosis (cheap, but often enough)
    report["diagnosis"] = _diagnose(report)

    # Small SEL tail for correlation (full only)
    if level == "full":
        st = _sel_tail(250)
        if st:
            report["data"]["sel_tail"] = st

    return report


# === NoemaForge Autodoc Function Header ===
# Function: write_reports(pol: Dict[str, Any], report: Dict[str, Any])
# Purpose: Implement the routine 'write reports'.
# Inputs:
#   - pol: Dict[str, Any]
#   - report: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _now, str, makedirs, join, items, append, _prune_dir, get, open, dump, write, int
# Returns / emits: Dict[str, str]
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
#   - spawns subprocesses or workers
#   - appends to logs or files
# Key locals:
#   - base, df, diag, dp, drep, ef, ep, f, fnd, md, outbox_reports, p_json
# === End NoemaForge Autodoc Function Header ===
def write_reports(pol: Dict[str, Any], report: Dict[str, Any]) -> Dict[str, str]:
    rep = pol.get("report") or {}
    ts = _now()
    rid = report.get("boot_id") or "no-boot-id"
    base = f"{ts}-{rid[:8]}"

    reports_dir = str(rep.get("reports_dir") or str(_pp.data_root / "boot/reports"))
    outbox_reports = str(rep.get("outbox_reports_dir") or "/workspace/outbox/bootreports")

    os.makedirs(reports_dir, exist_ok=True)
    os.makedirs(outbox_reports, exist_ok=True)

    p_json = os.path.join(reports_dir, f"bootreport-{base}.json")
    with open(p_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

        # include doctor report (offline self-checks) if available
        try:
            from doctor import run_doctor  # type: ignore
            drep = run_doctor(full=False)
            dp = os.path.join(reports_dir, f"doctor-{base}.json")
            with open(dp, "w", encoding="utf-8") as df:
                json.dump(drep, df, ensure_ascii=False, indent=2)
        except Exception as e:
            ep = os.path.join(reports_dir, f"doctor-error-{base}.txt")
            with open(ep, "w", encoding="utf-8") as ef:
                ef.write(_redact_text(pol, f"doctor failed: {e}"))


    # small md summary in outbox
    md = [
        f"# BootDoctor report {base}",
        f"- ts: {report.get('ts')}",
        f"- mode: {report.get('mode')} level: {report.get('level')}",
        f"- epoch: {report.get('epoch_id')}",
        f"- boot_id: {report.get('boot_id')}",
        f"- failed_units: {', '.join(report.get('failed_units') or [])}",
        "",
        "## Quick checks",
    ]
    for k, v in (report.get("checks") or {}).items():
        md.append(f"- {k}: {v}")

    diag = report.get("diagnosis") or []
    if diag:
        md.append("")
        md.append("## Diagnosis (heuristics)")
        for fnd in diag[:12]:
            md.append(f"- [{fnd.get('severity')}] {fnd.get('id')}: {fnd.get('message')}")
    md.append("")
    p_md = os.path.join(outbox_reports, f"bootreport-{base}.md")
    with open(p_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    # prune
    _prune_dir(reports_dir, int(rep.get("keep_reports", 50) or 50), suffix=".json")
    _prune_dir(outbox_reports, int(rep.get("keep_reports", 50) or 50), suffix=".md")

    return {"report_json": p_json, "report_md": p_md}


# === NoemaForge Autodoc Function Header ===
# Function: make_support_bundle(pol: Dict[str, Any], report: Dict[str, Any], tag: str)
# Purpose: Implement the routine 'make support bundle'.
# Inputs:
#   - pol: Dict[str, Any]
#   - report: Dict[str, Any]
#   - tag: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - str, makedirs, _now, join, _sha256_file, _prune_dir, get, TemporaryDirectory, items, dump, int, open
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
#   - spawns subprocesses or workers
# Key locals:
#   - base, f, fn, out_path, outbox_support, p, rep, rid, rp, safe, sha, st
# === End NoemaForge Autodoc Function Header ===
def make_support_bundle(pol: Dict[str, Any], report: Dict[str, Any], *, tag: str) -> Dict[str, Any]:
    rep = pol.get("report") or {}
    outbox_support = str(rep.get("outbox_support_dir") or "/workspace/outbox/support")
    os.makedirs(outbox_support, exist_ok=True)

    ts = _now()
    rid = report.get("boot_id") or "no-boot-id"
    base = f"{tag}-{ts}-{rid[:8]}"
    out_path = os.path.join(outbox_support, f"noemaforge-support-{base}.tar.gz")

    # stage files
    with tempfile.TemporaryDirectory(prefix="noemaforge-support-") as td:
        # report
        rp = os.path.join(td, "bootreport.json")
        with open(rp, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # text dumps (redacted)
        # === NoemaForge Autodoc Function Header ===
        # Function: dump(name: str, content: str)
        # Purpose: Implement the routine 'dump'.
        # Inputs:
        #   - name: str
        #   - content: str
        # Called by:
        #   - src/audit_remediation.py
        #   - src/brainctl.py
        #   - src/noemaforge_core.py
        #   - src/bundles.py
        #   - src/canary_runner.py
        #   - src/caps.py
        #   - src/daily_stats.py
        #   - src/fixture_bundle.py
        # Calls:
        #   - join, open, write, _redact_text
        # Returns / emits: None
        # Side effects:
        #   - reads or writes files
        # Key locals:
        #   - f, p
        # === End NoemaForge Autodoc Function Header ===
        def dump(name: str, content: str) -> None:
            p = os.path.join(td, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(_redact_text(pol, content))

        # include unit logs
        units = (report.get("data") or {}).get("units") or {}
        for u, dd in units.items():
            safe = u.replace("/", "_")
            dump(f"unit_{safe}_status.txt", str(dd.get("status") or ""))
            dump(f"unit_{safe}_journal_tail.txt", str(dd.get("journal_tail") or ""))

        dump("dmesg_tail.txt", str((report.get("data") or {}).get("dmesg_tail") or ""))
        dump("journal_boot_tail.txt", str((report.get("data") or {}).get("journal_boot_tail") or ""))
        dump("systemd.txt", json.dumps((report.get("data") or {}).get("systemd") or {}, ensure_ascii=False, indent=2))
        dump("lsblk.txt", str(((report.get("data") or {}).get("lsblk") or {}).get("out") or ""))
        dump("mounts.txt", str(((report.get("data") or {}).get("mounts") or {}).get("out") or ""))
        dump("df.txt", str(((report.get("data") or {}).get("df") or {}).get("out") or ""))
        dump("free.txt", str(((report.get("data") or {}).get("free") or {}).get("out") or ""))
        dump("systemd_analyze.txt", str((report.get("data") or {}).get("systemd_analyze") or ""))
        dump("systemd_analyze_blame.txt", str((report.get("data") or {}).get("systemd_analyze_blame") or ""))

        # SEL tail (correlates security events with failures)
        st = str((report.get("data") or {}).get("sel_tail") or "")
        if not st:
            st = _sel_tail(400)
        if st:
            dump("sel_tail.jsonl", st)

        # pack
        with tarfile.open(out_path, "w:gz") as tf:
            for fn in sorted(os.listdir(td)):
                tf.add(os.path.join(td, fn), arcname=fn)

    sha = _sha256_file(out_path)

    # prune
    _prune_dir(outbox_support, int(rep.get("keep_support_bundles", 20) or 20), suffix=".tar.gz")

    return {"path": out_path, "sha256": sha}


# === NoemaForge Autodoc Function Header ===
# Function: boot(pol: Dict[str, Any], requested_level: str = 'auto')
# Purpose: Implement the routine 'boot'.
# Inputs:
#   - pol: Dict[str, Any]
#   - requested_level: str = 'auto'
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _write_runtime_mode, collect, write_reports, sel_append, get, bool, make_support_bundle
# Returns / emits: int
# Side effects:
#   - spawns subprocesses or workers
#   - appends to logs or files
# Key locals:
#   - b, paths, report
# === End NoemaForge Autodoc Function Header ===
def boot(pol: Dict[str, Any], requested_level: str = "auto") -> int:
    _write_runtime_mode()
    report = collect(pol, mode="boot", requested_level=requested_level)
    paths = write_reports(pol, report)

    # WORM log
    sel_append(
        {
            "type": "BOOT_REPORT",
            "epoch_id": report.get("epoch_id"),
            "boot_id": report.get("boot_id"),
            "level": report.get("level"),
            "report_json": paths.get("report_json"),
            "report_md": paths.get("report_md"),
            "failed_units": report.get("failed_units"),
        }
    )

    # bundle if failures
    if report.get("watched_failed_units") and bool((pol.get("failure_policy") or {}).get("bundle_on_failed_units", True)):
        b = make_support_bundle(pol, report, tag="boot")
        sel_append({"type": "BOOT_SUPPORT_BUNDLE", "path": b.get("path"), "sha256": b.get("sha256"), "boot_id": report.get("boot_id")})

    return 0


# === NoemaForge Autodoc Function Header ===
# Function: onfailure(pol: Dict[str, Any], unit: str, requested_level: str = 'auto')
# Purpose: Implement the routine 'onfailure'.
# Inputs:
#   - pol: Dict[str, Any]
#   - unit: str
#   - requested_level: str = 'auto'
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _write_runtime_mode, collect, str, makedirs, _now, replace, join, sel_append, make_support_bundle, get, open, dump
# Returns / emits: int
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
#   - spawns subprocesses or workers
#   - appends to logs or files
# Key locals:
#   - b, f, onf_dir, p_json, rep, report, safe_unit, ts, udir
# === End NoemaForge Autodoc Function Header ===
def onfailure(pol: Dict[str, Any], unit: str, requested_level: str = "auto") -> int:
    _write_runtime_mode()
    report = collect(pol, mode="onfailure", unit=unit, requested_level=requested_level)

    rep = pol.get("report") or {}
    onf_dir = str(rep.get("onfailure_dir") or str(_pp.data_root / "boot/onfailure"))
    os.makedirs(onf_dir, exist_ok=True)

    ts = _now()
    safe_unit = unit.replace("/", "_")
    udir = os.path.join(onf_dir, safe_unit)
    os.makedirs(udir, exist_ok=True)
    p_json = os.path.join(udir, f"onfailure-{ts}.json")
    with open(p_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    sel_append({"type": "UNIT_FAILURE_REPORT", "unit": unit, "path": p_json, "boot_id": report.get("boot_id")})

    # Always create a bundle for onfailure (small)
    b = make_support_bundle(pol, report, tag=f"fail-{safe_unit}")
    sel_append({"type": "UNIT_FAILURE_BUNDLE", "unit": unit, "path": b.get("path"), "sha256": b.get("sha256"), "boot_id": report.get("boot_id")})

    return 0


# === NoemaForge Autodoc Function Header ===
# Function: quick(pol: Dict[str, Any])
# Purpose: Implement the routine 'quick'.
# Inputs:
#   - pol: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - collect, print, get, safe_dump
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - out, report
# === End NoemaForge Autodoc Function Header ===
def quick(pol: Dict[str, Any]) -> int:
    report = collect(pol, mode="quick", requested_level="quick")
    # print minimal yaml
    out = {
        "ok": True,
        "epoch_id": report.get("epoch_id"),
        "boot_id": report.get("boot_id"),
        "failed_units": report.get("failed_units"),
        "checks": report.get("checks"),
        "hint": "Run: brainctl bootdoctor bundle (or check /workspace/outbox/support)"
    }
    print(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: bundle(pol: Dict[str, Any])
# Purpose: Implement the routine 'bundle'.
# Inputs:
#   - pol: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - collect, write_reports, make_support_bundle, print, safe_dump
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - b, report
# === End NoemaForge Autodoc Function Header ===
def bundle(pol: Dict[str, Any]) -> int:
    report = collect(pol, mode="bundle", requested_level="full")
    write_reports(pol, report)
    b = make_support_bundle(pol, report, tag="manual")
    print(yaml.safe_dump({"ok": True, **b}, sort_keys=False, allow_unicode=True))
    return 0


# === NoemaForge Autodoc Function Header ===
# Function: main(argv: Optional[List[str]] = None)
# Purpose: Implement the routine 'main'.
# Inputs:
#   - argv: Optional[List[str]] = None
# Called by:
#   - bootstrap/microvm/noemaforge-microvm-run.py
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/brainui.py
#   - src/canary_runner.py
#   - src/doctor.py
#   - src/dream_cycle.py
#   - src/firstboot_eval.py
# Calls:
#   - ArgumentParser, add_argument, parse_args, load_policy, boot, onfailure, quick, bundle, str
# Returns / emits: int
# Key locals:
#   - ap, args, pol
# === End NoemaForge Autodoc Function Header ===
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="boot", choices=["boot", "onfailure", "quick", "bundle"])
    ap.add_argument("--unit", default="")
    ap.add_argument("--level", default="auto", choices=["auto", "quick", "full"])
    args = ap.parse_args(argv)

    pol = load_policy(None)

    if args.mode == "boot":
        return boot(pol, requested_level=str(args.level))
    if args.mode == "onfailure":
        return onfailure(pol, unit=str(args.unit), requested_level=str(args.level))
    if args.mode == "quick":
        return quick(pol)
    if args.mode == "bundle":
        return bundle(pol)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
