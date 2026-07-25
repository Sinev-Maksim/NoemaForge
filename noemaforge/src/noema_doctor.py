#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/noema_doctor.py
Zone: runtime/diagnostics
Version: 0.33.0
Created: 2026-06-07
Modified: 2026-06-07
Purpose: Read-only readiness command ("noema doctor"). Reports a structured health/readiness
  matrix: Python runtime, platform, version source-of-truth, resolved data roots and state
  directories, active contract epoch (best-effort), ToolProxy policy and schema presence, the
  localhost Admin control-plane reachability, and detected model backends. Pure diagnosis: it
  never starts services, never performs privileged or GPU/display actions, and never raises.
Inputs: Optional package_root override; optional admin-probe toggle.
Outputs: A report dict / human text; process exit 0 when no critical check fails, else 1.
Side effects: Read-only filesystem stat and one short, optional localhost TCP connect attempt.
Tests: python3 -m unittest noemaforge/tests/test_noema_doctor.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

Stdlib-only by design so `noema doctor` works on a bare host before any optional dependency is
installed, on both the Linux target and the Windows/macOS control hosts.
"""
from __future__ import annotations

import argparse
import json
import os
import platform as _platform
import shutil
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

API_VERSION = "noemaforge.doctor-report/v1"

# Severity levels, ordered. A "critical" failure makes the overall report not-ok.
LEVEL_OK = "ok"
LEVEL_INFO = "info"
LEVEL_WARN = "warn"
LEVEL_CRITICAL = "critical"

# Known model-backend executables to probe for (best-effort; absence is informational).
BACKEND_EXECUTABLES = (
    "llama-server",
    "llama-server-cpu",
    "llama-server-cuda",
    "noemaforge-llm-gateway",
    "vllm",
    "ollama",
)

MIN_PYTHON = (3, 10)


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _package_root(package_root: Optional[Path] = None) -> Path:
    """Return the noemaforge package directory (the one holding src/, policies/, schemas/)."""
    if package_root is not None:
        return Path(package_root)
    # noemaforge/src/noema_doctor.py -> noemaforge/
    return Path(__file__).resolve().parents[1]


def _check(checks: List[Dict[str, Any]], check_id: str, level: str, detail: str, **extra: Any) -> None:
    row: Dict[str, Any] = {"id": check_id, "level": level, "detail": detail}
    row.update(extra)
    checks.append(row)


def _safe_runtime_version() -> Optional[str]:
    try:
        from noemaforge_version import RUNTIME_VERSION  # local import; never fatal
        return str(RUNTIME_VERSION)
    except Exception:
        return None


def _safe_paths():
    """Return platform_paths.DEFAULT_PATHS or None, never raising."""
    try:
        import platform_paths  # type: ignore
        return platform_paths.DEFAULT_PATHS
    except Exception:
        return None


def _dir_status(p: Path) -> str:
    try:
        if p.is_dir():
            return "exists"
        if p.exists():
            return "not-a-directory"
        return "absent"
    except OSError:
        return "unknown"


def _probe_admin(address: Any) -> Dict[str, Any]:
    """Best-effort: is something listening on the Admin control-plane address?

    Accepts "host:port" strings or (host, port) pairs. Uses a short timeout and never raises.
    """
    host, port = None, None
    try:
        if isinstance(address, (tuple, list)) and len(address) == 2:
            host, port = str(address[0]), int(address[1])
        elif isinstance(address, str) and ":" in address:
            h, _, p = address.rpartition(":")
            host, port = h or "127.0.0.1", int(p)
    except (ValueError, TypeError):
        return {"address": str(address), "listening": None, "note": "unparseable address"}
    if host is None or port is None:
        return {"address": str(address), "listening": None, "note": "no address resolved"}
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return {"address": f"{host}:{port}", "listening": True}
    except OSError:
        return {"address": f"{host}:{port}", "listening": False}


def collect_report(package_root: Optional[Path] = None, *, probe_admin: bool = True) -> Dict[str, Any]:
    """Collect the readiness report. Pure/read-only; never raises."""
    checks: List[Dict[str, Any]] = []
    pkg = _package_root(package_root)

    # 1. Python runtime
    pyver = ".".join(str(x) for x in sys.version_info[:3])
    if sys.version_info[:2] >= MIN_PYTHON:
        _check(checks, "python_runtime", LEVEL_OK, f"Python {pyver}")
    else:
        _check(checks, "python_runtime", LEVEL_CRITICAL,
               f"Python {pyver} < required {'.'.join(map(str, MIN_PYTHON))}")

    # 2. Platform
    _check(checks, "platform", LEVEL_INFO,
           f"{_platform.system()} {_platform.machine()}",
           system=_platform.system(), machine=_platform.machine())

    # 3. Version source of truth
    rv = _safe_runtime_version()
    if rv:
        _check(checks, "runtime_version", LEVEL_OK, f"RUNTIME_VERSION={rv}", version=rv)
    else:
        _check(checks, "runtime_version", LEVEL_CRITICAL,
               "cannot import noemaforge_version.RUNTIME_VERSION")

    # 4/5. Data roots + state directories
    paths = _safe_paths()
    if paths is None:
        _check(checks, "data_roots", LEVEL_WARN, "platform_paths unavailable; cannot resolve data roots")
    else:
        try:
            data_root = Path(paths.data_root)
            _check(checks, "data_roots", LEVEL_INFO, f"data_root={data_root} ({_dir_status(data_root)})",
                   data_root=str(data_root), status=_dir_status(data_root))
        except Exception:
            _check(checks, "data_roots", LEVEL_WARN, "platform_paths.data_root raised")
        state = {}
        for name in ("jobs_dir", "session_state_dir", "event_log_dir", "model_selection_state_dir"):
            try:
                p = Path(getattr(paths, name))
                state[name] = {"path": str(p), "status": _dir_status(p)}
            except Exception:
                state[name] = {"path": None, "status": "error"}
        _check(checks, "state_dirs", LEVEL_INFO, "resolved orchestration state directories", dirs=state)

    # 6. Contract epoch (best-effort)
    if paths is not None:
        try:
            epoch_dir = Path(paths.epoch_dir)
            active = None
            if epoch_dir.is_dir():
                subs = sorted([c.name for c in epoch_dir.iterdir() if c.is_dir()])
                active = subs[-1] if subs else None
            _check(checks, "contract_epoch", LEVEL_INFO,
                   f"epoch_dir={epoch_dir} active={active or 'none'}",
                   epoch_dir=str(epoch_dir), active=active)
        except Exception:
            _check(checks, "contract_epoch", LEVEL_INFO, "epoch directory not resolvable")

    # 7. ToolProxy policy files
    pol = pkg / "policies"
    pol_present = [n for n in ("toolproxy.rego", "release.rego") if (pol / n).is_file()]
    if len(pol_present) == 2:
        _check(checks, "policies", LEVEL_OK, "ToolProxy + release policies present", found=pol_present)
    else:
        _check(checks, "policies", LEVEL_WARN, f"policy files present: {pol_present or 'none'}", found=pol_present)

    # 8. Published schemas
    sch = pkg / "schemas"
    sch_present = [n for n in ("capability-token.schema.json", "release-manifest.schema.json")
                   if (sch / n).is_file()]
    if len(sch_present) == 2:
        _check(checks, "schemas", LEVEL_OK, "capability-token + release-manifest schemas present", found=sch_present)
    else:
        _check(checks, "schemas", LEVEL_WARN, f"schemas present: {sch_present or 'none'}", found=sch_present)

    # 9. Admin control-plane reachability (optional probe)
    # Always emit exactly one admin_control_plane row so the report shape is stable.
    if not probe_admin:
        _check(checks, "admin_control_plane", LEVEL_INFO, "probe skipped")
    elif paths is None:
        _check(checks, "admin_control_plane", LEVEL_INFO,
               "address unavailable (platform_paths missing)")
    else:
        try:
            addr = paths.gui_listen_address
        except Exception:
            addr = None
        if addr is None:
            _check(checks, "admin_control_plane", LEVEL_INFO, "address unavailable")
        else:
            info = _probe_admin(addr)
            listening = info.get("listening")
            # not-listening is normal when the dashboard is stopped → informational.
            _check(checks, "admin_control_plane", LEVEL_INFO,
                   f"admin {info.get('address')} listening={listening}", **info)

    # 10. Model backends (best-effort which)
    backends = {name: (shutil.which(name) or None) for name in BACKEND_EXECUTABLES}
    found = sorted([n for n, p in backends.items() if p])
    _check(checks, "model_backends", LEVEL_INFO,
           f"detected backends: {found or 'none on PATH'}", backends=backends)

    # 11. Sudo availability (best-effort, non-interactive)
    sudo_path = shutil.which("sudo") or None
    geteuid = getattr(os, "geteuid", None)
    effective_uid = int(geteuid()) if callable(geteuid) else None
    sudo_available = bool(sudo_path) and effective_uid == 0
    sudo_level = LEVEL_INFO if sudo_available else LEVEL_WARN
    sudo_detail = {
        "available": sudo_available,
        "sudo_path": sudo_path,
        "effective_uid": effective_uid,
        "interactive_prompt_expected": bool(sudo_path) and not sudo_available,
    }
    _check(
        checks,
        "sudo_available",
        sudo_level,
        "sudo is available without an interactive prompt" if sudo_available else "sudo is not available without an interactive prompt",
        **sudo_detail,
    )

    # 12. Display-safety reminder (always informational)
    _check(checks, "display_safety", LEVEL_INFO,
           "model-selection / heavy-GPU commands must carry --keep-display to preserve the desktop")

    summary = {lvl: sum(1 for c in checks if c["level"] == lvl)
               for lvl in (LEVEL_OK, LEVEL_INFO, LEVEL_WARN, LEVEL_CRITICAL)}
    ok = summary[LEVEL_CRITICAL] == 0

    return {
        "apiVersion": API_VERSION,
        "kind": "DoctorReport",
        "generated_at": _nowz(),
        "version": rv,
        "platform": _platform.system(),
        "ok": ok,
        "summary": summary,
        "checks": checks,
    }


_LEVEL_GLYPH = {LEVEL_OK: "[OK]  ", LEVEL_INFO: "[info]", LEVEL_WARN: "[WARN]", LEVEL_CRITICAL: "[FAIL]"}


def format_human(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"NoemaForge doctor - version {report.get('version') or 'unknown'} "
                 f"on {report.get('platform')}  ({report.get('generated_at')})")
    lines.append("")
    for c in report.get("checks", []):
        glyph = _LEVEL_GLYPH.get(c["level"], "[?]   ")
        lines.append(f"  {glyph} {c['id']}: {c['detail']}")
    s = report.get("summary", {})
    lines.append("")
    lines.append(f"summary: ok={s.get('ok', 0)} info={s.get('info', 0)} "
                 f"warn={s.get('warn', 0)} critical={s.get('critical', 0)}")
    lines.append("OVERALL: READY" if report.get("ok") else "OVERALL: NOT READY (critical checks failed)")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="noema doctor",
                                     description="Read-only NoemaForge readiness report.")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--package-root", default=None, help="override the noemaforge package directory")
    parser.add_argument("--no-admin-probe", action="store_true",
                        help="skip the localhost Admin control-plane reachability probe")
    args = parser.parse_args(argv)

    report = collect_report(
        package_root=Path(args.package_root) if args.package_root else None,
        probe_admin=not args.no_admin_probe,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_human(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
