#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/noemaforge_status.py
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

Existing module notes:
NoemaForge public-friendly status and next-action summary.

This module intentionally avoids mutating runtime state.  It is suitable for
MVP/MWP operator onboarding: one command, plain language, and optional JSON for
the local dashboard or support bundles.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_ROOT = Path(os.environ.get("NOEMAFORGE_ROOT", "/opt/noemaforge"))
DEFAULT_SHARE = Path(os.environ.get("NOEMAFORGE_SHARE", "/mnt/noemaforge-share"))
DEFAULT_DATASET = Path(os.environ.get("NOEMAFORGE_ROLE_EVAL_DATASET", "/opt/noemaforge/datasets/role_eval_cases"))
SOCKETS = {
    "gateway": Path("/run/noemaforge/llm/gateway.sock"),
    "main_backend": Path("/run/noemaforge/llm/backends/main.sock"),
    "toolproxy": Path("/run/noemaforge/toolproxy.sock"),
}
SERVICES = ["noemaforge-llm-gateway.service", "noemaforge-toolproxy.service", "noemaforge-llama@main.service"]
TIMERS = ["noemaforge-modelscan.timer", "noemaforge-llm-backends-manager.timer"]
AUTOSTART_UNITS = ["noemaforge-autostart-gui.service", "noemaforge-autostart-wogui.service"]


def run_cmd(cmd: List[str], timeout: float = 2.0) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"missing command: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s: {' '.join(cmd)}"


def systemctl_available() -> bool:
    rc, _, _ = run_cmd(["systemctl", "--version"], timeout=1.0)
    return rc == 0


def systemctl_is_active(unit: str) -> str:
    rc, out, _ = run_cmd(["systemctl", "is-active", unit], timeout=1.5)
    if rc == 0:
        return out or "active"
    return out or "inactive"


def systemctl_is_enabled(unit: str) -> str:
    rc, out, _ = run_cmd(["systemctl", "is-enabled", unit], timeout=1.5)
    if rc == 0:
        return out or "enabled"
    return out or "disabled"


def findmnt(path: Path) -> bool:
    rc, _, _ = run_cmd(["findmnt", str(path)], timeout=1.5)
    return rc == 0


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None



def read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return None


def degraded_readonly_state() -> Dict[str, Any]:
    path = Path(os.environ.get("NOEMAFORGE_FIRSTBOOT_STAFFING_SUMMARY", "/var/lib/noemaforge/bootstrap/firstboot-staffing-summary.json"))
    obj = read_json(path) or {}
    state = str(obj.get("staffing_state") or obj.get("state") or "unknown") if isinstance(obj, dict) else "unknown"
    active = state in {"degraded_selected", "unstaffed", "malformed"}
    return {"active": active, "state": state, "mode": "degraded_readonly" if active else "normal", "path": str(path)}

def collect(args: argparse.Namespace) -> Dict[str, Any]:
    share = Path(args.share or DEFAULT_SHARE)
    dataset = Path(args.dataset or DEFAULT_DATASET)
    has_systemctl = systemctl_available()
    services = {u: systemctl_is_active(u) for u in SERVICES} if has_systemctl else {}
    timers = {u: systemctl_is_enabled(u) for u in TIMERS} if has_systemctl else {}
    autostart_units = {u: systemctl_is_enabled(u) for u in AUTOSTART_UNITS} if has_systemctl else {}
    boot_mode = read_text(Path(os.environ.get("NOEMAFORGE_BOOT_MODE_FILE", "/etc/noemaforge/boot-mode"))) or "manual"
    degraded = degraded_readonly_state()
    sockets = {name: path.exists() and path.is_socket() for name, path in SOCKETS.items()}
    failed_units: List[str] = []
    if has_systemctl:
        rc, out, _ = run_cmd(["systemctl", "--failed", "--no-legend", "--no-pager"], timeout=2.0)
        if rc == 0 and out:
            failed_units = [line.split()[0] for line in out.splitlines() if line.strip()]

    modelstore_validation = read_json(Path("/var/lib/noemaforge/bootstrap/modelstore-validation.safe.json"))
    firstboot = read_json(Path("/var/lib/noemaforge/bootstrap/firstboot-status.json"))
    inventory = read_json(Path("/var/lib/noemaforge/bootstrap/model-inventory.json"))

    heavy_autostart_enabled = [unit for unit, state in timers.items() if state in {"enabled", "static"}]
        # Gateway/ToolProxy are not LLM backends.  The runtime invariant is about backend sockets.
    backend_sock_count = 1 if sockets.get("main_backend") else 0

    checks = []
    def add(cid: str, ok: bool, message: str, severity: str = "warn") -> None:
        checks.append({"id": cid, "ok": bool(ok), "severity": "ok" if ok else severity, "message": message})

    add("share.mount", share.exists() and findmnt(share), f"canonical share mount at {share}", "warn")
    add("dataset.role_eval_cases", dataset.exists() and dataset.is_dir(), f"role eval dataset at {dataset}", "error")
    add("socket.gateway", sockets["gateway"], "gateway socket present", "warn")
    add("socket.main_backend", sockets["main_backend"], "main backend socket present", "warn")
    add("socket.toolproxy", sockets["toolproxy"], "ToolProxy socket present", "warn")
    add("runtime.single_llm", backend_sock_count <= 1, "runtime_desired_count=1 preserved", "error")
    add("timers.heavy_autostart_disabled", not heavy_autostart_enabled, "heavy modelscan/manager timers disabled by default", "warn")
    add("autostart.boot_mode_valid", boot_mode in {"manual", "gui", "wogui"}, f"boot mode is {boot_mode}", "error")
    add("runtime.degraded_readonly_clear", not degraded.get("active"), "mutating workflows are not blocked by degraded firstboot", "warn")
    add("system.failed_units", not failed_units, "no failed systemd units", "warn")

    score = sum(1 for c in checks if c["ok"])
    error_failures = [c for c in checks if not c["ok"] and c["severity"] == "error"]
    warn_failures = [c for c in checks if not c["ok"] and c["severity"] == "warn"]
    if error_failures:
        health = "blocked"
    elif warn_failures:
        health = "degraded"
    else:
        health = "ready"

    next_actions: List[str] = []
    if failed_units:
        next_actions.append("Run: systemctl --failed --no-pager")
    if not (share.exists() and findmnt(share)):
        next_actions.append("Normalize/mount the share to /mnt/noemaforge-share, then run: noemaforge trixie-preflight")
    if not (dataset.exists() and dataset.is_dir()):
        next_actions.append("Restore /opt/noemaforge/datasets/role_eval_cases or run the dataset assurance step before firstboot.")
    if not sockets["main_backend"]:
        next_actions.append("For manual local LLM use: sudo noemaforge safe-start --wait && noemaforge smoke")
    if heavy_autostart_enabled:
        next_actions.append("Keep heavy backend timers disabled until full evaluation passes: sudo noemaforge manager disable")
    if degraded.get("active"):
        next_actions.append("System is in degraded_readonly; mutating pipeline flows require --allow-degraded after admin approval.")
    if not next_actions:
        next_actions.append("System looks ready for controlled MVP/MWP use. Next: noemaforge pipeline catalog")

    return {
        "ok": health == "ready",
        "health": health,
        "score": {"passed": score, "total": len(checks)},
        "runtime_invariant": {"runtime_desired_count": 1, "mode": "switchable", "backend_socket_count": backend_sock_count, "heavy_llm_autostart": "conditional_safe_start_only"},
        "boot_mode": boot_mode,
        "autostart_units": autostart_units,
        "degraded_readonly": degraded,
        "paths": {"share": str(share), "dataset": str(dataset)},
        "sockets": {k: {"path": str(SOCKETS[k]), "present": v} for k, v in sockets.items()},
        "services": services,
        "timers": timers,
        "failed_units": failed_units,
        "modelstore_validation": modelstore_validation,
        "firstboot": firstboot,
        "inventory_summary": (inventory or {}).get("summary") if isinstance(inventory, dict) else None,
        "checks": checks,
        "next_actions": next_actions,
    }


def print_plain(doc: Dict[str, Any]) -> None:
    print("NoemaForge status")
    print("==============")
    print(f"health: {doc['health']}  score: {doc['score']['passed']}/{doc['score']['total']}")
    ri = doc["runtime_invariant"]
    print(f"runtime: {ri['mode']} LLM, active backends {ri['backend_socket_count']}/{ri['runtime_desired_count']}")
    print()
    print("Checks:")
    for c in doc["checks"]:
        mark = "OK" if c["ok"] else ("ERR" if c["severity"] == "error" else "WARN")
        print(f"  [{mark}] {c['id']}: {c['message']}")
    print()
    print("Next safe action:")
    for action in doc["next_actions"][:3]:
        print(f"  - {action}")


def print_brief(doc: Dict[str, Any]) -> None:
    ri = doc["runtime_invariant"]
    print(
        f"NoemaForge health={doc['health']} "
        f"score={doc['score']['passed']}/{doc['score']['total']} "
        f"runtime={ri['mode']} active_backends={ri['backend_socket_count']}/{ri['runtime_desired_count']}"
    )
    if doc.get("next_actions"):
        print(f"next: {doc['next_actions'][0]}")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="noemaforge status")
    p.add_argument("--json", action="store_true")
    p.add_argument("--brief", action="store_true", help="print one-line status plus next action")
    p.add_argument("--share")
    p.add_argument("--dataset")
    p.add_argument("--strict", action="store_true", help="return non-zero on degraded/warn state")
    args = p.parse_args(argv)
    doc = collect(args)
    if args.json:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
    elif args.brief:
        print_brief(doc)
    else:
        print_plain(doc)
    if doc["health"] == "blocked":
        return 2
    if args.strict and doc["health"] != "ready":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
