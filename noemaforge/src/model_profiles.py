#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/model_profiles.py
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

Existing module notes:
Public-MWP model profile helper for NoemaForge.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_ROOT = _pp.root
API_VERSION = "noemaforge.model-profile/v1"
REQUIRED_PROFILE_NAMES = ["minimal", "balanced", "writer", "research", "gpu-heavy"]


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
from platform_paths import DEFAULT_PATHS as _pp
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


def validate_profiles(profiles: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    for name in REQUIRED_PROFILE_NAMES:
        spec = profiles.get(name)
        if not isinstance(spec, dict):
            failures.append(f"profile_missing:{name}")
            continue
        if int(spec.get("max_active_llms") or 0) != 1:
            failures.append(f"profile_max_active_llms_not_one:{name}")
        if not str(spec.get("description") or "").strip():
            failures.append(f"profile_description_missing:{name}")
        if not str(spec.get("default_runtime") or "").strip():
            failures.append(f"profile_default_runtime_missing:{name}")
        if not isinstance(spec.get("model_hints"), list) or not spec.get("model_hints"):
            failures.append(f"profile_model_hints_missing:{name}")
        if not isinstance(spec.get("roles"), list) or not spec.get("roles"):
            failures.append(f"profile_roles_missing:{name}")
        if float(spec.get("ram_gib_min") or 0) < 0:
            failures.append(f"profile_ram_floor_invalid:{name}")
        if float(spec.get("vram_gib_min") or 0) < 0:
            failures.append(f"profile_vram_floor_invalid:{name}")
    return {
        "apiVersion": API_VERSION,
        "kind": "ModelProfileValidationReport",
        "ok": not failures,
        "profile_count": len(profiles),
        "required_profiles": REQUIRED_PROFILE_NAMES,
        "failures": failures,
    }


def build_profile_manifest(profiles: dict[str, Any], profile_name: str) -> dict[str, Any]:
    profile_name = str(profile_name or "minimal").strip()
    if profile_name not in profiles:
        raise ValueError(f"unknown_profile:{profile_name}")
    spec = profiles[profile_name]
    hints = [str(item) for item in spec.get("model_hints") or []]
    roles = [str(item) for item in spec.get("roles") or []]
    return {
        "apiVersion": API_VERSION,
        "kind": "ModelProfileManifest",
        "profile": profile_name,
        "description": str(spec.get("description") or ""),
        "resource_floor": {
            "ram_gib_min": float(spec.get("ram_gib_min") or 0),
            "vram_gib_min": float(spec.get("vram_gib_min") or 0),
        },
        "runtime": {
            "default_runtime": str(spec.get("default_runtime") or "manual"),
            "max_active_llms": int(spec.get("max_active_llms") or 1),
            "heavy_llm_autostart": False,
        },
        "fetch_candidates": [
            {
                "artifact_hint": hint,
                "source": "operator_staged_or_existing_vault",
                "auto_download": False,
            }
            for hint in hints
        ],
        "stage_roles": roles,
        "selection_policy": {
            "operator_chooses_profile_not_individual_files": True,
            "candidate_hints_are_filters_not_downloads": True,
            "fallback_profile": "minimal",
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NoemaForge model profiles; no model download or runtime start.")
    ap.add_argument("cmd", nargs="?", default="list", choices=["list", "show", "recommend", "plan", "manifest", "validate"])
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
    if ns.cmd in {"plan", "manifest"}:
        name = ns.profile or "minimal"
        manifest = build_profile_manifest(profiles, name)
        print(json.dumps(manifest, ensure_ascii=False, indent=2) if ns.json else f"profile={name}\nmodel_hints: {', '.join(x['artifact_hint'] for x in manifest['fetch_candidates'])}\nstage_roles: {', '.join(manifest['stage_roles'])}\nauto_download=false\nmax_active_llms=1")
        return 0
    if ns.cmd == "validate":
        report = validate_profiles(profiles)
        print(json.dumps(report, ensure_ascii=False, indent=2) if ns.json else f"ok={str(report['ok']).lower()} profile_count={report['profile_count']} failures={len(report['failures'])}")
        return 0 if report["ok"] else 1
    ram = read_meminfo_gib()
    vram = detect_vram_gib()
    rec = recommend(profiles, ram, vram)
    doc = {"recommended_profile": rec, "ram_gib": round(ram, 1), "vram_gib": round(vram, 1), "profile": profiles[rec], "invariant": {"max_active_llms": 1, "heavy_llm_autostart": False}}
    print(json.dumps(doc, ensure_ascii=False, indent=2) if ns.json else f"recommended_profile={rec}\nram_gib={doc['ram_gib']} vram_gib={doc['vram_gib']}\nreason={profiles[rec]['description']}\ninvariant=max_active_llms=1 heavy_llm_autostart=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
