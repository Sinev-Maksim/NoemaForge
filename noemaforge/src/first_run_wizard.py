#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/first_run_wizard.py
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
Tiny NoemaForge first-run wizard for the public MVP/MWP path.
"""
from __future__ import annotations
import argparse, json
from typing import Any, Dict, List

def choose_model_policy(ram_gb: int, vram_gb: int, no_gpu: bool) -> Dict[str, str]:
    if no_gpu or vram_gb <= 0:
        return {"tier": "cpu_or_no_gpu", "recommendation": "keep GPU backends off; use safe-start only when needed"}
    if ram_gb < 16:
        return {"tier": "low_ram", "recommendation": "use a small CPU-safe model; do not autostart heavy LLMs"}
    if vram_gb >= 12:
        return {"tier": "12gb_gpu", "recommendation": "GPU-on-demand is acceptable; preserve max_active_llms=1"}
    if vram_gb >= 8:
        return {"tier": "mid_gpu", "recommendation": "prefer small/medium Q4 models; avoid boot autostart"}
    return {"tier": "cpu_baseline", "recommendation": "start with CPU baseline and explicit manual LLM start"}

def build_plan(args: argparse.Namespace) -> Dict[str, Any]:
    commands: List[str] = [
        "noemaforge status --brief",
        "noemaforge doctor",
        "noemaforge pipeline validate",
        "noemaforge trixie-preflight --json --skip-modelstore",
        "sudo noemaforge safe-start --wait",
        "noemaforge smoke",
        "noemaforge pipeline run public_mwp --request '<first task>'",
    ]
    if args.no_gpu:
        commands.insert(4, "sudo noemaforge pause --wait  # keep heavy GPU runtime stopped")
    return {
        "ok": True,
        "runtime_policy": {"mode": "switchable", "max_active_llms": 1, "heavy_llm_autostart": False},
        "machine_hint": {"ram_gb": args.ram_gb, "vram_gb": args.vram_gb, "no_gpu": args.no_gpu},
        "model_policy": choose_model_policy(args.ram_gb, args.vram_gb, args.no_gpu),
        "commands": commands,
        "notes": [
            "Run commands one by one and stop at the first failed health gate.",
            "Do not enable parallel heavy LLM runtime in the MVP path.",
            "Use task/project/stage context packets for role handoff.",
        ],
    }

def main() -> int:
    ap = argparse.ArgumentParser(prog="noemaforge first-run-wizard")
    ap.add_argument("--ram-gb", type=int, default=16)
    ap.add_argument("--vram-gb", type=int, default=0)
    ap.add_argument("--no-gpu", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    plan = build_plan(args)
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        print("NoemaForge first-run wizard")
        print(f"Model tier: {plan['model_policy']['tier']} — {plan['model_policy']['recommendation']}")
        print("\nCommands:")
        for i, cmd in enumerate(plan["commands"], 1):
            print(f"  {i}. {cmd}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
