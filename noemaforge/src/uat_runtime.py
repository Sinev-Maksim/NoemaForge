#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/uat_runtime.py
Zone: src/runtime
Version: tracks the VERSION source of truth (noemaforge_version.RUNTIME_VERSION)
Purpose: One-command UAT orchestration ("the UAT button"). Sequentially:
           1. starts event recording (a dedicated event-log dir for the session),
           2. (optionally) launches the Admin GUI, display-safe, pointed at the
              same event log,
           3. runs every pipeline in the catalog in turn, saving each run's
              artifacts into the logging folder,
           4. stops the GUI and the event recording,
         then writes a self-describing evidence bundle (manifest + summary +
         per-pipeline artifacts + recorded events) and prints its path so the
         operator gets the artifacts back, not just side effects.
Inputs: pipeline catalog (configs/pipelines.json), CLI flags.
Outputs: a UAT evidence bundle under --out (events/, pipelines/<id>/,
         gui/, commands.log, manifest.json, summary.md).
Side effects: spawns pipeline runs (and optionally the GUI) as subprocesses,
              writing under --out and the per-session state dir only.
Tests: noemaforge/tests/test_uat_runtime.py
Notes: stdlib only. Cross-platform: pipeline runs use the pipeline_runtime Python
       API; the optional GUI is launched via sys.executable (no bash). Per the
       display-safety rule the GUI keeps the display alive.
       Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from noemaforge_version import RUNTIME_VERSION  # noqa: E402

# pipeline_id reaches both a subprocess argv and a filesystem path (the bundle's
# per-pipeline directory), so it must be a constrained token. Enforced at the call
# site in _run_pipeline as defense-in-depth, independent of the caller's allowlist.
_SAFE_PIPELINE_ID = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_PIPELINE_RUN_COMMAND = "pipeline_runtime_run"
_DEFAULT_UAT_VERSION = RUNTIME_VERSION
_DEFAULT_UAT_BRANCH = f"release/{_DEFAULT_UAT_VERSION}-dev"
_DEV_IMPORTS = ("pytest", "yaml", "jsonschema")
_UAT_DIR_ENV = "UAT_DIR"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_catalog(package_root: Path) -> Dict[str, Dict[str, Any]]:
    """Pipeline ids -> definition, via the pipeline runtime's own loader."""
    import pipeline_runtime  # imported lazily so --help works without the catalog
    return pipeline_runtime.load_pipeline_catalog(package_root)


def _project_root_from_package(package_root: Path) -> Path:
    package = package_root.resolve()
    return package.parent if package.name == "noemaforge" else package


def _run_check_command(
    cmd: Sequence[str],
    *,
    cwd: Path,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(cmd),
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _check_result(
    check_id: str,
    ok: bool,
    *,
    message: str = "",
    detail: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "id": check_id,
        "ok": bool(ok),
        "message": message,
        "detail": detail or {},
    }


def _check_git_branch_and_clean(
    project_root: Path,
    *,
    expected_branch: str,
    timeout: int,
) -> Dict[str, Any]:
    branch_cmd = ["git", "rev-parse", "--abbrev-ref", "HEAD"]
    status_cmd = ["git", "status", "--porcelain"]
    try:
        branch = _run_check_command(branch_cmd, cwd=project_root, timeout=timeout)
        status = _run_check_command(status_cmd, cwd=project_root, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return _check_result(
            "git_branch_clean",
            False,
            message="expected branch and clean worktree",
            detail={
                "expected_branch": expected_branch,
                "actual_branch": "",
                "dirty_entries": [],
                "branch_returncode": None,
                "status_returncode": None,
                "stderr": str(exc.stderr or "")[:4000],
                "error": "timeout",
                "cmd": list(exc.cmd) if exc.cmd else branch_cmd,
                "timeout": timeout,
            },
        )
    except OSError as exc:
        return _check_result(
            "git_branch_clean",
            False,
            message="expected branch and clean worktree",
            detail={
                "expected_branch": expected_branch,
                "actual_branch": "",
                "dirty_entries": [],
                "branch_returncode": None,
                "status_returncode": None,
                "stderr": repr(exc)[:4000],
                "error": "launch_error",
                "cmd": branch_cmd,
            },
        )
    actual_branch = (branch.stdout or "").strip()
    dirty = [line for line in (status.stdout or "").splitlines() if line.strip()]
    ok = branch.returncode == 0 and status.returncode == 0 and actual_branch == expected_branch and not dirty
    return _check_result(
        "git_branch_clean",
        ok,
        message="expected branch and clean worktree",
        detail={
            "expected_branch": expected_branch,
            "actual_branch": actual_branch,
            "dirty_entries": dirty[:50],
            "branch_returncode": branch.returncode,
            "status_returncode": status.returncode,
            "stderr": ((branch.stderr or "") + (status.stderr or "")).strip()[:4000],
        },
    )


def _check_version_files(project_root: Path, package_root: Path, *, expected_version: str) -> Dict[str, Any]:
    refs = [
        project_root / "VERSION",
        project_root / "docs" / "VERSION",
        package_root / "VERSION",
        package_root / "docs" / "VERSION",
    ]
    values: Dict[str, str] = {}
    failures: List[str] = []
    for path in refs:
        rel = str(path.relative_to(project_root)).replace(os.sep, "/")
        try:
            values[rel] = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            values[rel] = ""
            failures.append(f"missing:{rel}")
    if RUNTIME_VERSION != expected_version:
        failures.append("runtime_version_mismatch")
    for rel, value in values.items():
        if value != expected_version:
            failures.append(f"version_mismatch:{rel}")
    return _check_result(
        "version_files",
        not failures,
        message="VERSION files and runtime version match expected release",
        detail={"expected_version": expected_version, "runtime_version": RUNTIME_VERSION, "files": values, "failures": failures},
    )


def _normalize_requirement_name(requirement: str) -> str:
    return re.split(r"[<>=!~\[]", requirement, maxsplit=1)[0].strip().lower().replace("_", "-")


def _check_dev_dependency_contract(project_root: Path) -> Dict[str, Any]:
    pyproject = project_root / "pyproject.toml"
    try:
        payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - reported as a contract failure
        return _check_result("dev_dependency_contract", False, message="pyproject.toml is readable", detail={"error": repr(exc)})
    optional = payload.get("project", {}).get("optional-dependencies", {})
    dev = optional.get("dev") if isinstance(optional, dict) else None
    requirements = [_normalize_requirement_name(str(item)) for item in dev] if isinstance(dev, list) else []
    required = {"pytest", "pyyaml", "jsonschema"}
    present = set(requirements)
    missing = sorted(required - present)
    return _check_result(
        "dev_dependency_contract",
        not missing,
        message='pyproject dev extra covers pytest, PyYAML and jsonschema for clean-venv UAT collection',
        detail={"requirements": requirements, "missing": missing},
    )


def _check_imports(imports: Sequence[str]) -> Dict[str, Any]:
    missing: List[str] = []
    loaded: List[str] = []
    for name in imports:
        try:
            importlib.import_module(name)
            loaded.append(name)
        except Exception as exc:  # noqa: BLE001 - importability is the contract
            missing.append(f"{name}:{exc!r}")
    return _check_result(
        "dev_dependency_imports",
        not missing,
        message="clean-venv dev dependencies are importable",
        detail={"imports": list(imports), "loaded": loaded, "missing": missing},
    )


def _check_compileall(package_root: Path) -> Dict[str, Any]:
    failures: List[Dict[str, str]] = []
    src_root = package_root / "src"
    for path in sorted(src_root.rglob("*.py")):
        rel = str(path.relative_to(package_root)).replace(os.sep, "/")
        try:
            compile(path.read_bytes(), str(path), "exec")
        except Exception as exc:  # noqa: BLE001 - syntax/read failures are reported
            failures.append({"file": rel, "error": repr(exc)})
    return _check_result(
        "compileall_src",
        not failures,
        message="noemaforge/src compiles with current interpreter",
        detail={"failures": failures[:50], "failure_count": len(failures)},
    )


def _command_check(
    check_id: str,
    cmd: Sequence[str],
    *,
    cwd: Path,
    timeout: int,
    message: str,
) -> Dict[str, Any]:
    try:
        proc = _run_check_command(cmd, cwd=cwd, timeout=timeout)
        ok = proc.returncode == 0
        return _check_result(
            check_id,
            ok,
            message=message,
            detail={
                "cmd": list(cmd),
                "returncode": proc.returncode,
                "stdout_tail": (proc.stdout or "")[-4000:],
                "stderr_tail": (proc.stderr or "")[-4000:],
            },
        )
    except subprocess.TimeoutExpired as exc:
        return _check_result(
            check_id,
            False,
            message=message,
            detail={"cmd": list(cmd), "timeout": timeout, "stdout_tail": str(exc.stdout or "")[-4000:], "stderr_tail": str(exc.stderr or "")[-4000:]},
        )
    except OSError as exc:
        return _check_result(
            check_id,
            False,
            message=message,
            detail={"cmd": list(cmd), "error": "launch_error", "stderr_tail": repr(exc)[-4000:]},
        )


def build_uat_check_report(args: argparse.Namespace) -> Dict[str, Any]:
    package_root = Path(args.root).resolve()
    project_root = Path(args.project_root).resolve() if args.project_root else _project_root_from_package(package_root)
    checks: List[Dict[str, Any]] = []

    if not args.skip_git:
        checks.append(_check_git_branch_and_clean(project_root, expected_branch=args.expected_branch, timeout=args.command_timeout))
    checks.append(_check_version_files(project_root, package_root, expected_version=args.expected_version))
    checks.append(_check_dev_dependency_contract(project_root))
    checks.append(_check_imports(_DEV_IMPORTS))
    checks.append(_check_compileall(package_root))

    collect_target = args.pytest_target or str(package_root / "tests")
    checks.append(_command_check(
        "pytest_collect",
        [sys.executable, "-m", "pytest", "--collect-only", "-q", collect_target],
        cwd=project_root,
        timeout=args.collect_timeout,
        message="pytest collection succeeds before functional UAT execution",
    ))
    checks.append(_command_check(
        "docs_hygiene",
        [sys.executable, str(package_root / "src" / "docs_hygiene_runtime.py"), "--project-root", str(project_root), "--summary"],
        cwd=project_root,
        timeout=args.command_timeout,
        message="docs hygiene release gate passes",
    ))
    checks.append(_command_check(
        "uat_runner_help",
        [sys.executable, str(package_root / "src" / "uat_runtime.py"), "--help"],
        cwd=project_root,
        timeout=args.command_timeout,
        message="UAT runner entrypoint is importable and exposes help",
    ))

    failures = [check for check in checks if not check.get("ok")]
    return {
        "kind": "NoemaForgeUATBootstrapCheck",
        "version": RUNTIME_VERSION,
        "generated_at": _now(),
        "ok": not failures,
        "project_root": str(project_root),
        "package_root": str(package_root),
        "checks": checks,
        "summary": {
            "total": len(checks),
            "passed": len(checks) - len(failures),
            "failed": len(failures),
            "failed_ids": [str(check.get("id")) for check in failures],
        },
        "live_evidence_claimed": False,
    }


def check_uat_bootstrap(args: argparse.Namespace) -> int:
    report = build_uat_check_report(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


def _resolve_uat_out_dir(raw_out: str | None, *, env: Dict[str, str] | None = None) -> Path:
    env_map = os.environ if env is None else env
    requested = str(raw_out or "").strip()
    if requested:
        return Path(requested).expanduser().resolve()
    from_env = str(env_map.get(_UAT_DIR_ENV, "")).strip()
    if from_env:
        return Path(from_env).expanduser().resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return (Path(tempfile.gettempdir()) / f"noemaforge-uat-{stamp}-{os.getpid()}").resolve()


def _safe_pipeline_id(pipeline_id: str) -> str:
    match = _SAFE_PIPELINE_ID.fullmatch(str(pipeline_id))
    if match is None:
        raise ValueError(f"unsafe pipeline_id: {pipeline_id!r}")
    return match.group(0)


def _pipeline_run_cmd(package_root: Path, pipeline_id: str, request: str, run_id: str, dry_run: bool) -> List[str]:
    safe_pipeline_id = _safe_pipeline_id(pipeline_id)
    cmd = [
        sys.executable, str(package_root / "src" / "pipeline_runtime.py"),
        "run", safe_pipeline_id,
        "--task-id", f"uat_{safe_pipeline_id}",
        "--request", request,
        "--run-id", run_id,
        "--allow-degraded",
    ]
    if dry_run:
        cmd.append("--dry-run")
    return cmd


def _pipeline_run_command_allowlist(
    package_root: Path,
    pipeline_id: str,
    request: str,
    run_id: str,
    dry_run: bool,
) -> Dict[str, List[str]]:
    """Return the only command shape recorded for UAT pipeline runs."""
    return {
        _PIPELINE_RUN_COMMAND: _pipeline_run_cmd(
            package_root, pipeline_id, request, run_id, dry_run,
        ),
    }


def _run_pipeline_runtime_main(
    package_root: Path,
    pipeline_id: str,
    request: str,
    run_id: str,
    dry_run: bool,
    timeout: int,
    env: Dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run pipeline_runtime through its Python API, avoiding user-tainted subprocess argv."""
    import pipeline_runtime

    argv = [
        "run", pipeline_id,
        "--task-id", f"uat_{pipeline_id}",
        "--request", request,
        "--run-id", run_id,
        "--allow-degraded",
        "--root", str(package_root),
        "--state", str(env["NOEMAFORGE_PIPELINE_STATE"]),
    ]
    if dry_run:
        argv.append("--dry-run")

    stdout = io.StringIO()
    stderr = io.StringIO()
    old_cwd = Path.cwd()
    old_env = dict(os.environ)
    timer_supported = (
        threading.current_thread() is threading.main_thread()
        and hasattr(signal, "setitimer")
        and hasattr(signal, "SIGALRM")
    )
    old_timer = signal.getitimer(signal.ITIMER_REAL) if timer_supported else (0.0, 0.0)
    old_handler = signal.getsignal(signal.SIGALRM) if timer_supported else None

    def _timeout_handler(_signum: int, _frame: Any) -> None:
        raise TimeoutError(f"pipeline timed out after {timeout}s")

    try:
        os.chdir(package_root)
        os.environ.clear()
        os.environ.update(env)
        if timer_supported:
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.setitimer(signal.ITIMER_REAL, max(float(timeout), 0.001))
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                returncode = int(pipeline_runtime.main(argv) or 0)
            except SystemExit as exc:
                returncode = int(exc.code) if isinstance(exc.code, int) else 1
    finally:
        if timer_supported:
            signal.setitimer(signal.ITIMER_REAL, old_timer[0], old_timer[1])
            signal.signal(signal.SIGALRM, old_handler)
        os.environ.clear()
        os.environ.update(old_env)
        os.chdir(old_cwd)

    return subprocess.CompletedProcess(argv, returncode, stdout.getvalue(), stderr.getvalue())


def _append_event(events_dir: Path, event_type: str, data: Dict[str, Any]) -> None:
    import event_log
    event_log.EventLog(events_dir).append(event_type, data, actor="uat")


def _run_pipeline(
    pipeline_id: str,
    *,
    package_root: Path,
    bundle: Path,
    env: Dict[str, str],
    request: str,
    dry_run: bool,
    timeout: int,
) -> Dict[str, Any]:
    """Run one pipeline through pipeline_runtime; collect its artifacts into the bundle."""
    # Hard guard: reject any pipeline_id that is not a safe token before it is used in
    # the runtime argv or the bundle path. This also blocks path traversal below.
    pipeline_id = _safe_pipeline_id(pipeline_id)
    run_id = f"uat_{pipeline_id}_{int(time.time())}"
    command_allowlist = _pipeline_run_command_allowlist(
        package_root, pipeline_id, request, run_id, dry_run,
    )
    cmd = command_allowlist[_PIPELINE_RUN_COMMAND]
    # Display-safety: pipeline_runtime.run is orchestration with no display surface;
    # any model/GPU launch it triggers goes through model_selection_runtime, which
    # always passes --keep-display. The UAT runner never stops a display manager.
    record: Dict[str, Any] = {"pipeline": pipeline_id, "run_id": run_id, "cmd": cmd}
    out_dir = bundle / "pipelines" / pipeline_id
    out_dir.mkdir(parents=True, exist_ok=True)
    record["artifact_count"] = 0
    try:
        proc = _run_pipeline_runtime_main(
            package_root, pipeline_id, request, run_id, dry_run, timeout, env,
        )
        record["returncode"] = proc.returncode
        record["status"] = "ok" if proc.returncode == 0 else "failed"
        (out_dir / "stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
        (out_dir / "stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
        run_dir = ""
        try:
            run_dir = str(json.loads(proc.stdout).get("run_dir", ""))
        except Exception:  # noqa: BLE001 - non-JSON output is captured as-is
            pass
        if run_dir and Path(run_dir).is_dir():
            shutil.copytree(run_dir, out_dir / "run_dir", dirs_exist_ok=True)
            record["artifact_count"] = sum(
                1 for _ in (out_dir / "run_dir").rglob("*") if _.is_file()
            )
    except TimeoutError:
        record["status"] = "timeout"
        record["returncode"] = None
        (out_dir / "status.txt").write_text(f"timeout after {timeout}s\n", encoding="utf-8")
        (out_dir / "stdout.txt").write_text("", encoding="utf-8")
        (out_dir / "stderr.txt").write_text("", encoding="utf-8")
    except subprocess.TimeoutExpired as exc:
        record["status"] = "timeout"
        record["returncode"] = None
        (out_dir / "status.txt").write_text(f"timeout after {timeout}s\n", encoding="utf-8")
        (out_dir / "stdout.txt").write_text(exc.stdout or "", encoding="utf-8")
        (out_dir / "stderr.txt").write_text(exc.stderr or "", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - a pipeline crash is captured, not fatal
        record["status"] = "error"
        record["error"] = repr(exc)
        (out_dir / "status.txt").write_text(f"error: {exc!r}\n", encoding="utf-8")
    return record


def _launch_gui(package_root: Path, bundle: Path, env: Dict[str, str], keep_display: bool):
    """Best-effort: launch the Admin GUI as a background subprocess."""
    gui_dir = bundle / "gui"
    gui_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(package_root / "src" / "admin_gui_server.py")]
    if keep_display:
        cmd.append("--keep-display")
    log = open(gui_dir / "gui.log", "w", encoding="utf-8")
    try:
        proc = subprocess.Popen(cmd, cwd=str(package_root), env=env, stdout=log, stderr=log)
    except Exception as exc:  # noqa: BLE001
        (gui_dir / "gui.json").write_text(
            json.dumps({"launched": False, "error": repr(exc)}, indent=2), encoding="utf-8"
        )
        return None
    time.sleep(2)  # give it a moment to bind / fail fast
    alive = proc.poll() is None
    (gui_dir / "gui.json").write_text(
        json.dumps({"launched": alive, "pid": proc.pid, "cmd": cmd}, indent=2),
        encoding="utf-8",
    )
    # Drop the handle if the GUI died during startup so manifest.gui_launched is accurate.
    return proc if alive else None


def run_uat(args: argparse.Namespace) -> int:
    package_root = Path(args.root).resolve()
    bundle = _resolve_uat_out_dir(args.out)
    bundle.mkdir(parents=True, exist_ok=True)
    events_dir = bundle / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    state_dir = bundle / "state"

    env = dict(os.environ)
    env["NOEMAFORGE_ROOT"] = str(package_root)
    env["NOEMAFORGE_EVENT_LOG_DIR"] = str(events_dir)      # step 1: record here
    env["NOEMAFORGE_PIPELINE_STATE"] = str(state_dir)
    env["NOEMAFORGE_ALLOW_DEGRADED_MUTATION"] = "1"

    catalog = _load_catalog(package_root)
    if args.pipelines:
        requested = [p.strip() for p in args.pipelines.split(",") if p.strip()]
        unknown = [p for p in requested if p not in catalog]
        if unknown:
            print(json.dumps({"ok": False, "error": "unknown_pipelines", "unknown": unknown}),
                  file=sys.stderr)
            return 2
        catalog_ids = {p: p for p in catalog}
        selected = [catalog_ids[p] for p in requested]
    else:
        selected = sorted(catalog)

    # Step 1 — start recording.
    _append_event(events_dir, "uat_session_start", {
        "version": RUNTIME_VERSION, "pipelines": selected,
        "dry_run": args.dry_run, "gui": args.gui, "started_at": _now(),
    })

    # Step 2 — launch the GUI (display-safe, best-effort).
    gui_proc = _launch_gui(package_root, bundle, env, args.keep_display) if args.gui else None

    # Step 3 — run every pipeline, saving artifacts.
    results: List[Dict[str, Any]] = []
    for pid in selected:
        results.append(_run_pipeline(
            pid, package_root=package_root, bundle=bundle, env=env,
            request=args.request, dry_run=args.dry_run, timeout=args.timeout,
        ))

    # Step 4 — stop the GUI, then stop recording.
    if gui_proc is not None and gui_proc.poll() is None:
        gui_proc.terminate()
        try:
            gui_proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            gui_proc.kill()
    _append_event(events_dir, "uat_session_stop", {
        "stopped_at": _now(),
        "ok": sum(1 for r in results if r.get("status") == "ok"),
        "total": len(results),
    })

    event_count = 0
    events_file = events_dir / "events.jsonl"
    if events_file.is_file():
        event_count = sum(1 for line in events_file.read_text(encoding="utf-8").splitlines() if line.strip())

    manifest = {
        "kind": "NoemaForgeUATBundle",
        "version": RUNTIME_VERSION,
        "generated_at": _now(),
        "gui_launched": gui_proc is not None,
        "dry_run": args.dry_run,
        "event_count": event_count,
        "pipelines": results,
        "summary": {
            "total": len(results),
            "ok": sum(1 for r in results if r.get("status") == "ok"),
            "failed": sum(1 for r in results if r.get("status") not in ("ok",)),
            "artifacts": sum(int(r.get("artifact_count", 0)) for r in results),
        },
    }
    (bundle / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    s = manifest["summary"]
    lines = [
        f"# NoemaForge UAT run — {manifest['generated_at']}",
        "",
        f"- version: {RUNTIME_VERSION}",
        f"- pipelines: {s['ok']}/{s['total']} ok · artifacts: {s['artifacts']} · events: {event_count}",
        f"- gui launched: {manifest['gui_launched']} · dry_run: {args.dry_run}",
        "",
        "| pipeline | status | rc | artifacts |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['pipeline']} | {r.get('status')} | {r.get('returncode')} | {r.get('artifact_count', 0)} |")
    (bundle / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"ok": True, "bundle": str(bundle), "summary": s, "events": event_count}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="noemaforge uat", description="One-command UAT runner.")
    sub = p.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="validate clean-venv UAT bootstrap prerequisites without live execution")
    check.add_argument("--root", default=os.environ.get("NOEMAFORGE_ROOT", "noemaforge"),
                       help="package root (contains src/, configs/); defaults to $NOEMAFORGE_ROOT")
    check.add_argument("--project-root", default="", help="project root; default: parent of package root")
    check.add_argument("--expected-branch", default=_DEFAULT_UAT_BRANCH)
    check.add_argument("--expected-version", default=_DEFAULT_UAT_VERSION)
    check.add_argument("--pytest-target", default="", help="pytest collect target; default: <root>/tests")
    check.add_argument("--collect-timeout", type=int, default=180, help="pytest collection timeout in seconds")
    check.add_argument("--command-timeout", type=int, default=60, help="short command timeout in seconds")
    check.add_argument("--skip-git", action="store_true", help="skip branch/clean-tree validation for isolated test fixtures")
    check.set_defaults(func=check_uat_bootstrap)

    run = sub.add_parser("run", help="record events, (launch GUI,) run all pipelines, bundle artifacts")
    run.add_argument("--root", default=os.environ.get("NOEMAFORGE_ROOT", "noemaforge"),
                     help="package root (contains src/, configs/); defaults to $NOEMAFORGE_ROOT")
    run.add_argument("--out", default="", help="logging/evidence bundle directory; default: $UAT_DIR or a safe temp directory")
    run.add_argument("--request", default="UAT smoke run", help="request text passed to each pipeline")
    run.add_argument("--pipelines", default="", help="comma-separated pipeline ids (default: all in catalog)")
    run.add_argument("--timeout", type=int, default=300, help="per-pipeline timeout (seconds)")
    run.add_argument("--dry-run", action="store_true", help="plan pipelines without executing side effects")
    gui = run.add_mutually_exclusive_group()
    gui.add_argument("--gui", dest="gui", action="store_true", help="launch the Admin GUI (default)")
    gui.add_argument("--no-gui", dest="gui", action="store_false", help="headless: do not launch the GUI")
    run.set_defaults(gui=True)
    run.add_argument("--keep-display", action="store_true", default=True, help="keep the display alive (display-safety rule)")
    run.set_defaults(func=run_uat)
    return p


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
