#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/noema_start.py
Zone: runtime/cli
Version: 0.33.0
Created: 2026-06-07
Modified: 2026-06-07
Purpose: "One-button" start. Orchestrates the safe, non-privileged bring-up of NoemaForge:
  readiness check (noema doctor) -> ensure user-writable data/state dirs exist -> launch the
  localhost Admin GUI control plane -> open the dashboard in the browser. The privileged,
  display-affecting first-start (model selection / GPU) is NOT performed here — it stays
  operator-gated through the dashboard (plan-then-apply, always with --keep-display).
Inputs: optional --host/--port/--root; flags --check-only/--no-browser/--no-doctor/--background/--force.
Outputs: a start plan + readiness summary; launches the Admin GUI unless --check-only.
Side effects: creates user-writable data dirs (best-effort); spawns the Admin GUI server process.
  No GPU/model/display actions -> display-safe and privilege-free by construction.
Tests: python3 -m unittest noemaforge/tests/test_noema_start.py
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_PKG_ROOT = Path(__file__).resolve().parents[1]  # noemaforge/

# Injectable seams so the launch path is unit-testable without a real server/browser.
_spawn: Callable[[List[str]], Any] = None  # set lazily to subprocess.Popen
_open_browser: Callable[[str], bool] = webbrowser.open


def _default_paths():
    try:
        from platform_paths import DEFAULT_PATHS
        return DEFAULT_PATHS
    except Exception:
        return None


def build_start_plan(*, root: Optional[Path] = None, host: Optional[str] = None,
                     port: Optional[int] = None, paths: Any = None) -> Dict[str, Any]:
    """Compute the (pure) start plan: host/port/url, the Admin GUI launch argv, and the set of
    data dirs to ensure. Does not touch the filesystem or network."""
    paths = paths if paths is not None else _default_paths()

    gui_host, gui_port = "127.0.0.1", 8765
    if paths is not None:
        try:
            gui_host, gui_port = paths.gui_listen_address
        except Exception:
            pass
    host = host or gui_host
    port = int(port if port is not None else gui_port)

    root = Path(root) if root else _PKG_ROOT
    server = root / "src" / "admin_gui_server.py"

    data_dirs: List[str] = []
    if paths is not None:
        for attr in ("data_root", "gui_state_dir", "session_state_dir",
                     "model_selection_state_dir", "model_evolution_state_dir",
                     "dev_team_state_dir", "persona_state_dir", "log_dir"):
            d = getattr(paths, attr, None)
            if d:
                data_dirs.append(str(d))

    launch_argv = [sys.executable, str(server), "--host", str(host), "--port", str(port)]
    return {
        "host": host,
        "port": port,
        "url": f"http://{host}:{port}/",
        "root": str(root),
        "server": str(server),
        "data_dirs": sorted(set(data_dirs)),
        "launch_argv": launch_argv,
    }


def ensure_dirs(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Create the plan's data dirs if writable. Best-effort: a dir that needs privilege
    (e.g. /var/lib on Linux) is reported as skipped, never fatal."""
    created, skipped = [], []
    for d in plan.get("data_dirs", []):
        try:
            Path(d).mkdir(parents=True, exist_ok=True)
            created.append(d)
        except OSError as exc:
            skipped.append({"dir": d, "error": str(exc)})
    return {"created": created, "skipped": skipped}


def readiness(root: Path) -> Dict[str, Any]:
    """Run the read-only doctor report; degrade gracefully if doctor is unavailable."""
    try:
        import noema_doctor
        return noema_doctor.collect_report(package_root=Path(root), probe_admin=False)
    except Exception as exc:  # never let a doctor failure block start
        return {"ok": True, "summary": {"critical": 0}, "checks": [],
                "doctor_error": str(exc)}


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def launch(plan: Dict[str, Any], *, open_browser: bool = True, wait: bool = True,
           startup_timeout: float = 20.0) -> int:
    """Launch the Admin GUI (or attach to an already-running one) and open the browser.

    If the port is already serving, do NOT spawn a second server — just open the browser.
    """
    host, port, url = plan["host"], plan["port"], plan["url"]

    if _port_open(host, port):
        print(f"NoemaForge Admin GUI already running at {url}", flush=True)
        if open_browser:
            _open_browser(url)
        return 0

    spawn = _spawn
    if spawn is None:
        import subprocess
        spawn = subprocess.Popen
    proc = spawn(plan["launch_argv"])

    deadline = time.time() + startup_timeout
    while time.time() < deadline:
        if getattr(proc, "poll", lambda: None)() is not None:
            print("FAIL: Admin GUI process exited during startup.", file=sys.stderr)
            return 1
        if _port_open(host, port):
            break
        time.sleep(0.3)

    print(f"NoemaForge Admin GUI: {url}", flush=True)
    if open_browser:
        _open_browser(url)

    if wait:
        try:
            return int(proc.wait() or 0)
        except KeyboardInterrupt:
            try:
                proc.terminate()
            except Exception:
                pass
            return 0
    print(f"  (running in background; pid={getattr(proc, 'pid', '?')})", flush=True)
    return 0


def _print_plan(plan: Dict[str, Any], rep: Dict[str, Any], ensured: Optional[Dict[str, Any]],
                *, as_json: bool) -> None:
    if as_json:
        out = {"plan": plan, "readiness": rep.get("summary", {}), "ensured": ensured}
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    print(f"NoemaForge one-button start -> {plan['url']}")
    crit = rep.get("summary", {}).get("critical", 0)
    print(f"  readiness: {'READY' if rep.get('ok') else 'NOT READY'} (critical={crit})")
    print(f"  data dirs: {len(plan['data_dirs'])} target(s)")
    if ensured is not None:
        print(f"  created {len(ensured['created'])}, skipped {len(ensured['skipped'])}")
        for s in ensured["skipped"]:
            print(f"    [skip] {s['dir']} ({s['error']})")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="noema start",
        description="One-button start: readiness check, ensure data dirs, launch the localhost "
                    "Admin GUI, open the browser. Display-safe; no GPU/model/privileged actions.",
    )
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--root", default=None, help="package root (default: this install)")
    parser.add_argument("--check-only", action="store_true",
                        help="report the plan + readiness without creating dirs or launching")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-doctor", action="store_true", help="skip the readiness check")
    parser.add_argument("--background", action="store_true", help="do not wait on the server")
    parser.add_argument("--force", action="store_true",
                        help="launch even if readiness reports critical issues")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    plan = build_start_plan(root=args.root, host=args.host, port=args.port)
    rep = {"ok": True, "summary": {"critical": 0}} if args.no_doctor else readiness(Path(plan["root"]))
    critical = int(rep.get("summary", {}).get("critical", 0))

    if args.check_only:
        _print_plan(plan, rep, None, as_json=args.json)
        return 0 if critical == 0 else 1

    if critical and not args.force:
        _print_plan(plan, rep, None, as_json=args.json)
        print("FAIL: readiness reports critical issues; fix them or pass --force.", file=sys.stderr)
        return 1

    ensured = ensure_dirs(plan)
    if not args.json:
        _print_plan(plan, rep, ensured, as_json=False)
    return launch(plan, open_browser=not args.no_browser, wait=not args.background)


if __name__ == "__main__":
    raise SystemExit(main())
