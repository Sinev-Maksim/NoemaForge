#!/usr/bin/env python3
from __future__ import annotations
# === NoemaForge File Header ===
# File: src/noemaforge_monitor.py
# Zone: operator/ux
# Purpose: Operator monitor for NoemaForge services, timers, resources, model runtime and tasks.
# Safety: read-only diagnostics.
# === End NoemaForge File Header ===

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


def sh(cmd: list[str], timeout: int = 10) -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    except Exception as e:
        return f"ERROR: {e}\n"


def active_llama_units() -> list[str]:
    out = sh(["systemctl", "list-units", "--all", "--plain", "--no-legend", "noemaforge-llama@*.service"])
    lines = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[2] == "active":
            lines.append(line)
    return lines


def collect() -> dict[str, Any]:
    failed = sh(["systemctl", "--failed", "--no-pager"])
    units = active_llama_units()
    timers = sh(["bash", "-lc", "systemctl list-timers --all | grep -E 'noemaforge-llm-backends-manager|noemaforge-modelscan|NEXT|UNIT' || true"])
    manager_show = sh(["bash", "-lc", "systemctl show noemaforge-llm-backends-manager.timer noemaforge-modelscan.timer -p ActiveState -p SubState -p UnitFileState -p NextElapseUSecRealtime --no-pager || true"])
    free = sh(["free", "-h"])
    nvidia = sh(["bash", "-lc", "nvidia-smi 2>/dev/null | head -40 || true"], timeout=10)
    main_model = sh(["bash", "-lc", "readlink -f /var/lib/modelstore/models/main/model.gguf 2>/dev/null || true"]).strip()
    smoke_status = "unknown"
    try:
        out = subprocess.check_output(["noemaforge", "smoke"], stderr=subprocess.STDOUT, text=True, timeout=120)
        smoke_status = "ok" if "overall:        ok" in out else "fail"
    except Exception as e:
        smoke_status = f"error:{e}"
    tasks_path = Path("/var/lib/noemaforge/tasks/tasks.jsonl")
    task_count = 0
    if tasks_path.exists():
        try:
            task_count = sum(1 for _ in tasks_path.open(encoding="utf-8"))
        except Exception:
            task_count = -1
    return {
        "smoke": smoke_status,
        "active_llama_count": len(units),
        "active_llama_units": units,
        "main_model": main_model,
        "failed_units_raw": failed,
        "timers_raw": timers,
        "timer_properties_raw": manager_show,
        "free_raw": free,
        "nvidia_raw": nvidia,
        "task_count": task_count,
    }


def print_human(obj: dict[str, Any]) -> None:
    print("=== NoemaForge monitor ===")
    print(f"smoke={obj['smoke']}")
    print(f"active_llama_count={obj['active_llama_count']}")
    for line in obj["active_llama_units"]:
        print("  " + line)
    print(f"main_model={obj['main_model']}")
    print(f"task_count={obj['task_count']}")
    print("\n=== timers ===")
    print(obj["timers_raw"].rstrip())
    print("\n=== failed units ===")
    print(obj["failed_units_raw"].rstrip())
    print("\n=== memory ===")
    print(obj["free_raw"].rstrip())
    if obj["nvidia_raw"].strip():
        print("\n=== nvidia ===")
        print(obj["nvidia_raw"].rstrip())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NoemaForge monitor")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--watch", type=float, default=0, help="Refresh every N seconds")
    ns = ap.parse_args(argv)
    while True:
        obj = collect()
        if ns.json:
            print(json.dumps(obj, ensure_ascii=False, indent=2))
        else:
            print_human(obj)
        if not ns.watch:
            return 0
        time.sleep(ns.watch)
        print("\033[2J\033[H", end="")

if __name__ == "__main__":
    raise SystemExit(main())
