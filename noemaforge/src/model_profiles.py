#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/model_profiles.py
Zone: release/package
Version: 0.31.13.alpha
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
Public-MWP model profile helper for NoemaForge.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path(os.environ.get("NOEMAFORGE_ROOT", "/opt/noemaforge"))


def load_profiles(root: Path) -> dict[str, Any]:
    path = root / "configs" / "model-profiles.json"
    if not path.exists():
        # Source-tree fallback when called directly from an unpacked archive.
        here = Path(__file__).resolve()
        cand = here.parents[1] / "configs" / "model-profiles.json"
        path = cand if cand.exists() else path
    return json.loads(path.read_text(encoding="utf-8"))


def read_meminfo_gib() -> float:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                kb = int(line.split()[1])
                return kb / 1024 / 1024
    except Exception:
        pass
    return 0.0


def detect_vram_gib() -> float:
    # Avoid hard dependency on nvidia-smi; public setup must work on CPU-only machines.
    try:
        import subprocess
        out = subprocess.check_output([
            "bash", "-lc", "nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1"
        ], text=True, timeout=3).strip()
        if out:
            return float(out.splitlines()[0]) / 1024
    except Exception:
        pass
    return 0.0


def recommend(profiles: dict[str, Any], ram: float, vram: float) -> str:
    if vram >= 12 and ram >= 32:
        return "gpu-heavy"
    if vram >= 10 and ram >= 24:
        return "research"
    if vram >= 8 and ram >= 16:
        return "balanced"
    return "minimal"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NoemaForge model profiles; no model download or runtime start.")
    ap.add_argument("cmd", nargs="?", default="list", choices=["list", "show", "recommend"])
    ap.add_argument("profile", nargs="?", default="")
    ap.add_argument("--root", default="")
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv)
    root = Path(ns.root).resolve() if ns.root else DEFAULT_ROOT
    profiles = load_profiles(root)
    if ns.cmd == "list":
        if ns.json:
            print(json.dumps(profiles, ensure_ascii=False, indent=2))
        else:
            for name, spec in profiles.items():
                print(f"{name}\tRAM>={spec.get('ram_gib_min')}GiB\tVRAM>={spec.get('vram_gib_min')}GiB\t{spec.get('description')}")
        return 0
    if ns.cmd == "show":
        name = ns.profile or "minimal"
        if name not in profiles:
            raise SystemExit(f"unknown profile: {name}")
        print(json.dumps({name: profiles[name]}, ensure_ascii=False, indent=2) if ns.json else f"{name}: {profiles[name]['description']}\nmodel_hints: {', '.join(profiles[name].get('model_hints', []))}\nruntime: {profiles[name].get('default_runtime')}\nmax_active_llms: {profiles[name].get('max_active_llms')}")
        return 0
    ram = read_meminfo_gib()
    vram = detect_vram_gib()
    rec = recommend(profiles, ram, vram)
    doc = {"recommended_profile": rec, "ram_gib": round(ram, 1), "vram_gib": round(vram, 1), "profile": profiles[rec], "invariant": {"max_active_llms": 1, "heavy_llm_autostart": False}}
    print(json.dumps(doc, ensure_ascii=False, indent=2) if ns.json else f"recommended_profile={rec}\nram_gib={doc['ram_gib']} vram_gib={doc['vram_gib']}\nreason={profiles[rec]['description']}\ninvariant=max_active_llms=1 heavy_llm_autostart=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
