#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/selftest_runtime.py
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
NoemaForge self-test, telemetry and wiki-patch runtime.

0.31.13.alpha scope:
- module-level test case catalog runner;
- resource telemetry per case: wall time, CPU, RSS, proc I/O, optional GPU/VRAM/ECC;
- baseline comparison and regression classification;
- SQLite log for self-improvement loops;
- incremental wiki patch generator for functional + metric deltas.

The runner is deliberately conservative: default suites never start a heavy LLM
and never require live systemd/GPU. Live cases must be explicitly allowed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
import resource
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

DEFAULT_ROOT = Path(os.environ.get("NOEMAFORGE_ROOT", "/opt/noemaforge"))
DEFAULT_STATE = Path(os.environ.get("NOEMAFORGE_SELFTEST_STATE", "/var/lib/noemaforge/selftests"))
RUNTIME_VERSION = "0.31.13.alpha"
CATALOG_REL = Path("configs/selftest-case-catalog.json")
POLICY_REL = Path("configs/selftest-telemetry-policy.json")


def nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def jdump(data: Any, *, pretty: bool = True) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2 if pretty else None, sort_keys=False)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        pass
    return default


def default_catalog() -> Dict[str, Any]:
    return {
        "apiVersion": "noemaforge/v1",
        "kind": "SelfTestCaseCatalog",
        "version": RUNTIME_VERSION,
        "invariant": {"llm_mode": "switchable", "max_active_llms": 1, "heavy_llm_autostart": False},
        "suites": {
            "core": [
                "cli_status_json",
                "pipeline_validate",
                "schema_validate",
                "persona_validate",
                "pipeline_metrics_prometheus",
                "toolproxy_offline_smoke",
                "dashboard_state",
                "code_qa_team_select",
                "code_qa_run_offline",
            ],
            "pipeline": ["pipeline_run_public_mwp", "pipeline_template_import"],
            "full_safe": [
                "cli_status_json",
                "pipeline_validate",
                "schema_validate",
                "persona_validate",
                "pipeline_metrics_prometheus",
                "toolproxy_offline_smoke",
                "dashboard_state",
                "pipeline_run_public_mwp",
                "pipeline_template_import",
                "mvp_smoke_offline",
            ],
        },
        "cases": [
            {
                "id": "cli_status_json",
                "module": "operator_cli",
                "tier": "smoke",
                "description": "noemaforge status JSON shape",
                "command": ["{{noemaforge}}", "status", "--json"],
                "expect": {"exit_code": [0, 2], "stdout_contains": ["\"health\""]},
                "live": False,
            },
            {
                "id": "pipeline_validate",
                "module": "pipeline_runtime",
                "tier": "unit",
                "description": "Pipeline/persona/pattern catalogs validate",
                "command": ["{{noemaforge}}", "pipeline", "validate"],
                "expect": {"exit_code": 0, "stdout_contains": ["\"ok\": true"]},
                "live": False,
            },
            {
                "id": "schema_validate",
                "module": "schema_validation",
                "tier": "unit",
                "description": "NoemaForge native schemas validate",
                "command": ["{{noemaforge}}", "schema", "validate"],
                "expect": {"exit_code": 0, "stdout_contains": ["\"ok\": true"]},
                "live": False,
            },
            {
                "id": "persona_validate",
                "module": "persona_runtime",
                "tier": "unit",
                "description": "Persona catalog and portraits validate",
                "command": ["{{noemaforge}}", "persona", "validate"],
                "expect": {"exit_code": 0, "stdout_contains": ["\"ok\": true"]},
                "live": False,
            },
            {
                "id": "pipeline_metrics_prometheus",
                "module": "observability",
                "tier": "unit",
                "description": "Prometheus metrics exporter emits core metrics",
                "command": ["{{noemaforge}}", "pipeline", "metrics", "--format", "prometheus"],
                "expect": {"exit_code": 0, "stdout_contains": ["noemaforge_pipeline_runs_total"]},
                "live": False,
            },
            {
                "id": "toolproxy_offline_smoke",
                "module": "toolproxy",
                "tier": "integration_offline",
                "description": "Offline capability token issue/verify smoke",
                "command": ["{{noemaforge}}", "toolproxy", "smoke", "--tokens-dir", "{{tmp}}/cap_tokens"],
                "expect": {"exit_code": 0, "stdout_contains": ["\"ok\": true"]},
                "live": False,
            },
            {
                "id": "dashboard_state",
                "module": "dashboard",
                "tier": "integration_offline",
                "description": "Dashboard state can be generated without launching LLM",
                "command": ["{{noemaforge}}", "dashboard", "state", "--out", "{{tmp}}/dashboard-state.json"],
                "expect": {"exit_code": 0, "file_exists": ["{{tmp}}/dashboard-state.json"]},
                "live": False,
            },
            {
                "id": "pipeline_run_public_mwp",
                "module": "pipeline_runtime",
                "tier": "integration_offline",
                "description": "Create public_mwp run and typed context sidecars",
                "command": ["{{noemaforge}}", "pipeline", "run", "public_mwp", "--task-id", "selftest", "--request", "selftest public MWP run"],
                "expect": {"exit_code": 0, "stdout_contains": ["\"run_id\""]},
                "live": False,
            },
            {
                "id": "pipeline_template_import",
                "module": "pipeline_import",
                "tier": "integration_offline",
                "description": "Import external workflow/template draft safely",
                "setup_files": {"{{tmp}}/template.json": "{\"name\":\"SelfTest Template\",\"nodes\":[{\"name\":\"Webhook\"},{\"name\":\"Review\"}],\"connections\":{}}"},
                "command": ["{{noemaforge}}", "pipeline", "template-import", "{{tmp}}/template.json", "--family", "n8n", "--pipeline-id", "selftest_import"],
                "expect": {"exit_code": 0, "stdout_contains": ["\"pipeline\""]},
                "live": False,
            },
            {
                "id": "mvp_smoke_offline",
                "module": "public_mwp",
                "tier": "system_offline",
                "description": "Full public MVP smoke without live LLM",
                "command": ["{{noemaforge}}", "mvp-smoke", "--json"],
                "expect": {"exit_code": 0, "stdout_contains": ["\"failed\": 0"]},
                "live": False,
                "timeout_sec": 120,
            },

            {
                "id": "code_qa_team_select",
                "module": "code_qa",
                "tier": "unit",
                "description": "Select two code-capable QA reviewers distinct from producer model",
                "command": ["{{noemaforge}}", "qa", "code", "team", "--producer", "qwen25-coder-14b", "--json"],
                "expect": {"exit_code": 0, "stdout_contains": ["\"ok\": true"]},
                "live": False,
            },
            {
                "id": "code_qa_run_offline",
                "module": "code_qa",
                "tier": "integration_offline",
                "description": "Run offline code QA sub-team and emit consensus/handoff context",
                "setup_files": {"{{tmp}}/sample_project/app.py": "def add(a,b):\n    return a+b\n"},
                "command": ["{{noemaforge}}", "qa", "code", "run", "--project", "{{tmp}}/sample_project", "--producer", "qwen25-coder-14b", "--state", "{{tmp}}/qa_state", "--run-id", "selftest_codeqa", "--json"],
                "expect": {"exit_code": 0, "stdout_contains": ["\"ok\": true", "\"consensus\""], "file_exists": ["{{tmp}}/qa_state/runs/selftest_codeqa/next_participant_handoff_context.md"]},
                "live": False,
            },
            {
                "id": "gateway_live_smoke_plan",
                "module": "llm_gateway",
                "tier": "system_live",
                "description": "Placeholder live gate: must be run on NoemaForge with explicit --allow-live",
                "command": ["{{noemaforge}}", "smoke"],
                "expect": {"exit_code": 0},
                "live": True,
                "timeout_sec": 180,
            },
        ],
    }


def default_policy() -> Dict[str, Any]:
    return {
        "apiVersion": "noemaforge/v1",
        "kind": "SelfTestTelemetryPolicy",
        "version": RUNTIME_VERSION,
        "thresholds": {
            "duration_warn_pct": 0.25,
            "duration_fail_pct": 0.50,
            "max_rss_warn_pct": 0.30,
            "max_rss_fail_pct": 0.60,
            "disk_write_warn_bytes": 50 * 1024 * 1024,
            "memory_leak_warn_pct": 0.10,
            "ecc_delta_fail": 1,
        },
        "retention": {"keep_reports_days": 60, "keep_metric_samples_days": 120},
        "auto_rollback_policy": {
            "enabled_by_default": False,
            "block_apply_on_failed_cases": True,
            "block_apply_on_resource_regression": True,
            "requires_admin_approval": True,
        },
    }


def load_catalog(root: Path) -> Dict[str, Any]:
    return load_json(root / CATALOG_REL, default_catalog())


def load_policy(root: Path) -> Dict[str, Any]:
    merged = default_policy()
    user = load_json(root / POLICY_REL, {})
    if isinstance(user, dict):
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k].update(v)  # shallow merge is enough for MVP policy
            else:
                merged[k] = v
    return merged


def db_connect(state: Path) -> sqlite3.Connection:
    state.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(state / "selftest_registry.sqlite")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS selftest_runs (run_id TEXT PRIMARY KEY, version TEXT NOT NULL, suite TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, report_path TEXT NOT NULL, summary_json TEXT NOT NULL DEFAULT '{}')")
    conn.execute("CREATE TABLE IF NOT EXISTS selftest_case_results (run_id TEXT NOT NULL, case_id TEXT NOT NULL, module TEXT NOT NULL, tier TEXT NOT NULL, status TEXT NOT NULL, exit_code INTEGER, duration_sec REAL, max_rss_kib INTEGER, cpu_user_sec REAL, cpu_system_sec REAL, disk_read_bytes INTEGER, disk_write_bytes INTEGER, gpu_json TEXT NOT NULL DEFAULT '{}', stdout_path TEXT NOT NULL, stderr_path TEXT NOT NULL, result_json TEXT NOT NULL, PRIMARY KEY(run_id, case_id))")
    conn.execute("CREATE TABLE IF NOT EXISTS selftest_metric_samples (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, case_id TEXT NOT NULL, ts TEXT NOT NULL, metric TEXT NOT NULL, value REAL NOT NULL, unit TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS selftest_regressions (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, case_id TEXT NOT NULL, severity TEXT NOT NULL, metric TEXT NOT NULL, baseline REAL, current REAL, delta_pct REAL, details TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS wiki_patches (patch_id TEXT PRIMARY KEY, run_id TEXT, created_at TEXT NOT NULL, patch_file TEXT NOT NULL, metadata_json TEXT NOT NULL)")
    conn.commit()
    return conn


def nvidia_snapshot() -> Dict[str, Any]:
    # GPU/ECC probing can be expensive or hang on hosts with half-configured drivers.
    # Keep default suites lightweight; enable on NoemaForge with --gpu or NOEMAFORGE_SELFTEST_ENABLE_GPU=1.
    if os.environ.get("NOEMAFORGE_SELFTEST_ENABLE_GPU", "0").lower() not in {"1", "true", "yes"}:
        return {"available": False, "reason": "gpu probe disabled; pass --gpu for nvidia-smi/ECC capture"}
    exe = shutil.which("nvidia-smi")
    if not exe:
        return {"available": False, "reason": "nvidia-smi not found"}
    q = "index,name,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,ecc.errors.volatile.total,ecc.errors.aggregate.total"
    try:
        out = subprocess.check_output([exe, f"--query-gpu={q}", "--format=csv,noheader,nounits"], text=True, stderr=subprocess.STDOUT, timeout=5)
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
    gpus: List[Dict[str, Any]] = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 9:
            continue
        def to_int(x: str) -> Optional[int]:
            try:
                return int(float(x))
            except Exception:
                return None
        gpus.append({
            "index": to_int(parts[0]),
            "name": parts[1],
            "gpu_util_pct": to_int(parts[2]),
            "memory_util_pct": to_int(parts[3]),
            "vram_used_mib": to_int(parts[4]),
            "vram_total_mib": to_int(parts[5]),
            "temperature_c": to_int(parts[6]),
            "ecc_volatile_total": to_int(parts[7]),
            "ecc_aggregate_total": to_int(parts[8]),
        })
    return {"available": True, "gpus": gpus}


def proc_io(pid: int) -> Dict[str, int]:
    path = Path(f"/proc/{pid}/io")
    data: Dict[str, int] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                try:
                    data[k.strip()] = int(v.strip())
                except Exception:
                    pass
    except Exception:
        pass
    return data


def proc_rss_kib(pid: int) -> int:
    try:
        txt = Path(f"/proc/{pid}/status").read_text(encoding="utf-8", errors="replace")
        for line in txt.splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except Exception:
        pass
    return 0


def substitute(value: str, repl: Dict[str, str]) -> str:
    for k, v in repl.items():
        value = value.replace("{{" + k + "}}", v)
    return value


def prepare_case(case: Dict[str, Any], repl: Dict[str, str]) -> List[str]:
    for raw_path, content in (case.get("setup_files") or {}).items():
        path = Path(substitute(str(raw_path), repl))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(substitute(str(content), repl), encoding="utf-8")
    return [substitute(str(x), repl) for x in case.get("command", [])]


def evaluate_expect(case: Dict[str, Any], result: Dict[str, Any], repl: Dict[str, str]) -> List[str]:
    exp = case.get("expect") or {}
    problems: List[str] = []
    if "exit_code" in exp:
        expected = exp["exit_code"]
        actual = int(result.get("exit_code", -999))
        if isinstance(expected, list):
            ok_exit = actual in [int(x) for x in expected]
        else:
            ok_exit = actual == int(expected)
        if not ok_exit:
            problems.append(f"exit_code expected {expected} got {actual}")
    stdout = Path(str(result.get("stdout_path", ""))).read_text(encoding="utf-8", errors="replace") if result.get("stdout_path") else ""
    stderr = Path(str(result.get("stderr_path", ""))).read_text(encoding="utf-8", errors="replace") if result.get("stderr_path") else ""
    for needle in exp.get("stdout_contains") or []:
        if str(needle) not in stdout:
            problems.append(f"stdout missing {needle!r}")
    for needle in exp.get("stderr_contains") or []:
        if str(needle) not in stderr:
            problems.append(f"stderr missing {needle!r}")
    for fp in exp.get("file_exists") or []:
        path = Path(substitute(str(fp), repl))
        if not path.exists():
            problems.append(f"missing expected file {path}")
    return problems


def run_command(command: List[str], env: Dict[str, str], cwd: Path, stdout_path: Path, stderr_path: Path, timeout_sec: int) -> Dict[str, Any]:
    gpu_before = nvidia_snapshot()
    usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.perf_counter()
    max_rss = 0
    io_start: Dict[str, int] = {}
    io_last: Dict[str, int] = {}
    with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        proc = subprocess.Popen(command, cwd=str(cwd), env=env, stdout=out, stderr=err)
        io_start = proc_io(proc.pid)
        deadline = time.monotonic() + int(timeout_sec)
        timed_out = False
        while True:
            ret = proc.poll()
            max_rss = max(max_rss, proc_rss_kib(proc.pid))
            latest = proc_io(proc.pid)
            if latest:
                io_last = latest
            if ret is not None:
                break
            if time.monotonic() > deadline:
                timed_out = True
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                break
            time.sleep(0.025)
    finish = time.perf_counter()
    usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    gpu_after = nvidia_snapshot()
    read_bytes = max(0, int(io_last.get("read_bytes", 0)) - int(io_start.get("read_bytes", 0))) if io_last else 0
    write_bytes = max(0, int(io_last.get("write_bytes", 0)) - int(io_start.get("write_bytes", 0))) if io_last else 0
    return {
        "exit_code": int(proc.returncode if proc.returncode is not None else -9),
        "timed_out": bool(timed_out),
        "duration_sec": round(finish - start, 6),
        "max_rss_kib": int(max_rss),
        "cpu_user_sec": round(usage_after.ru_utime - usage_before.ru_utime, 6),
        "cpu_system_sec": round(usage_after.ru_stime - usage_before.ru_stime, 6),
        "disk_read_bytes": read_bytes,
        "disk_write_bytes": write_bytes,
        "gpu_before": gpu_before,
        "gpu_after": gpu_after,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def run_internal_py_compile(path: str, stdout_path: Path, stderr_path: Path) -> Dict[str, Any]:
    import py_compile
    usage_before = resource.getrusage(resource.RUSAGE_SELF)
    start = time.perf_counter()
    exit_code = 0
    try:
        py_compile.compile(path, doraise=True)
        stdout_path.write_text(f"compiled {path}\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
    except Exception as exc:
        exit_code = 1
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(str(exc) + "\n", encoding="utf-8")
    finish = time.perf_counter()
    usage_after = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "exit_code": exit_code,
        "timed_out": False,
        "duration_sec": round(finish - start, 6),
        "max_rss_kib": int(usage_after.ru_maxrss),
        "cpu_user_sec": round(usage_after.ru_utime - usage_before.ru_utime, 6),
        "cpu_system_sec": round(usage_after.ru_stime - usage_before.ru_stime, 6),
        "disk_read_bytes": 0,
        "disk_write_bytes": 0,
        "gpu_before": nvidia_snapshot(),
        "gpu_after": nvidia_snapshot(),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def select_cases(catalog: Dict[str, Any], suite: str, case_ids: Optional[List[str]], allow_live: bool) -> List[Dict[str, Any]]:
    if suite == "quick":
        suite = "core"
    cases = {c.get("id"): c for c in catalog.get("cases") or [] if isinstance(c, dict)}
    selected_ids: List[str] = []
    if case_ids:
        selected_ids = case_ids
    elif suite in {"all", "safe_all"}:
        selected_ids = [cid for cid, case in cases.items() if allow_live or not case.get("live")]
    else:
        selected_ids = list((catalog.get("suites") or {}).get(suite, []))
    selected: List[Dict[str, Any]] = []
    for cid in selected_ids:
        case = cases.get(cid)
        if not case:
            raise SystemExit(f"unknown selftest case: {cid}")
        if case.get("live") and not allow_live:
            continue
        selected.append(case)
    return selected


def summarize_report(report: Dict[str, Any]) -> Dict[str, Any]:
    results = report.get("results") or []
    failed = [r for r in results if r.get("status") != "pass"]
    durations = [float(r.get("metrics", {}).get("duration_sec") or 0) for r in results]
    rss = [int(r.get("metrics", {}).get("max_rss_kib") or 0) for r in results]
    writes = [int(r.get("metrics", {}).get("disk_write_bytes") or 0) for r in results]
    ecc_deltas: List[int] = []
    for r in results:
        ecc = r.get("metrics", {}).get("ecc_delta_total")
        if isinstance(ecc, int):
            ecc_deltas.append(ecc)
    return {
        "ok": not failed,
        "case_count": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "duration_total_sec": round(sum(durations), 6),
        "duration_max_sec": round(max(durations) if durations else 0, 6),
        "max_rss_kib": max(rss) if rss else 0,
        "disk_write_bytes_total": sum(writes),
        "ecc_delta_total": sum(ecc_deltas),
    }


def ecc_delta(before: Dict[str, Any], after: Dict[str, Any]) -> Optional[int]:
    if not before.get("available") or not after.get("available"):
        return None
    def total(doc: Dict[str, Any]) -> int:
        return sum(int(g.get("ecc_volatile_total") or 0) + int(g.get("ecc_aggregate_total") or 0) for g in doc.get("gpus") or [])
    return max(0, total(after) - total(before))


def run_selftests(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    catalog = load_catalog(root)
    cases = select_cases(catalog, args.suite, args.case, args.allow_live)
    if not cases:
        raise SystemExit("no cases selected")
    run_id = args.run_id or "selftest_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_value = getattr(args, "out_dir", None) or args.out
    out_dir = Path(out_value).resolve() if out_value else state / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    noemaforge = root / "bin" / "noemaforge"
    env = os.environ.copy()
    env.update({
        "NOEMAFORGE_ROOT": str(root),
        "NOEMAFORGE_PIPELINE_STATE": str(out_dir / "pipeline_state"),
        "NOEMAFORGE_PERSONA_STATE": str(out_dir / "persona_state"),
        "NOEMAFORGE_SELFTEST_STATE": str(state),
        "NOEMAFORGE_ALLOW_DEGRADED_MUTATION": "1",
    })
    if getattr(args, "gpu", False):
        env["NOEMAFORGE_SELFTEST_ENABLE_GPU"] = "1"
    repl = {"root": str(root), "state": str(out_dir / "pipeline_state"), "tmp": str(tmp), "out": str(out_dir), "noemaforge": str(noemaforge)}
    started = nowz()
    report: Dict[str, Any] = {
        "apiVersion": "noemaforge/v1",
        "kind": "SelfTestReport",
        "version": RUNTIME_VERSION,
        "run_id": run_id,
        "suite": args.suite,
        "started_at": started,
        "finished_at": None,
        "root": str(root),
        "state": str(state),
        "out_dir": str(out_dir),
        "invariant": catalog.get("invariant", {}),
        "results": [],
    }
    conn = db_connect(state)
    conn.execute("INSERT OR REPLACE INTO selftest_runs(run_id,version,suite,status,started_at,report_path,summary_json) VALUES(?,?,?,?,?,?,?)", (run_id, RUNTIME_VERSION, args.suite, "running", started, str(out_dir / "selftest-report.json"), "{}"))
    conn.commit()
    for case in cases:
        repeats = max(1, int(args.repeat or 1))
        rep_results: List[Dict[str, Any]] = []
        for n in range(repeats):
            cid = str(case.get("id"))
            cdir = out_dir / "cases" / cid / f"repeat_{n+1}"
            cdir.mkdir(parents=True, exist_ok=True)
            cmd = prepare_case(case, repl)
            timeout_sec = int(case.get("timeout_sec") or args.timeout or 60)
            stdout = cdir / "stdout.txt"
            stderr = cdir / "stderr.txt"
            try:
                if cmd and cmd[0] == "__py_compile__" and len(cmd) >= 2:
                    result = run_internal_py_compile(cmd[1], stdout, stderr)
                else:
                    result = run_command(cmd, env, root, stdout, stderr, timeout_sec)
            except Exception as exc:
                result = {"exit_code": -127, "timed_out": False, "duration_sec": 0, "max_rss_kib": 0, "cpu_user_sec": 0, "cpu_system_sec": 0, "disk_read_bytes": 0, "disk_write_bytes": 0, "stdout_path": str(stdout), "stderr_path": str(stderr), "gpu_before": {}, "gpu_after": {}, "error": str(exc)}
                stderr.write_text(str(exc), encoding="utf-8")
            result["ecc_delta_total"] = ecc_delta(result.get("gpu_before", {}), result.get("gpu_after", {}))
            problems = evaluate_expect(case, result, repl)
            if result.get("timed_out"):
                problems.append("timeout")
            status = "pass" if not problems else "fail"
            rep = {
                "case_id": cid,
                "repeat": n + 1,
                "module": case.get("module"),
                "tier": case.get("tier"),
                "description": case.get("description"),
                "command": cmd,
                "status": status,
                "problems": problems,
                "metrics": {k: result.get(k) for k in ["duration_sec", "max_rss_kib", "cpu_user_sec", "cpu_system_sec", "disk_read_bytes", "disk_write_bytes", "ecc_delta_total"]},
                "gpu": {"before": result.get("gpu_before"), "after": result.get("gpu_after")},
                "stdout_path": result.get("stdout_path"),
                "stderr_path": result.get("stderr_path"),
                "exit_code": result.get("exit_code"),
            }
            atomic_write(cdir / "result.json", jdump(rep))
            rep_results.append(rep)
        # Aggregate by choosing the final repeat plus leak signal.
        final = dict(rep_results[-1])
        rss_seq = [int(r.get("metrics", {}).get("max_rss_kib") or 0) for r in rep_results]
        leak_suspect = False
        if len(rss_seq) >= 3 and rss_seq[0] > 0 and rss_seq[-1] > int(rss_seq[0] * 1.10):
            leak_suspect = True
            final.setdefault("problems", []).append("memory_leak_suspect_repeat_rss_growth")
            final["status"] = "fail" if args.fail_on_leak else final["status"]
        final["repeats"] = {"count": len(rep_results), "max_rss_kib_sequence": rss_seq, "memory_leak_suspect": leak_suspect}
        report["results"].append(final)
        m = final.get("metrics", {})
        conn.execute(
            "INSERT OR REPLACE INTO selftest_case_results(run_id,case_id,module,tier,status,exit_code,duration_sec,max_rss_kib,cpu_user_sec,cpu_system_sec,disk_read_bytes,disk_write_bytes,gpu_json,stdout_path,stderr_path,result_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, final["case_id"], str(final.get("module") or ""), str(final.get("tier") or ""), final["status"], int(final.get("exit_code") or 0), float(m.get("duration_sec") or 0), int(m.get("max_rss_kib") or 0), float(m.get("cpu_user_sec") or 0), float(m.get("cpu_system_sec") or 0), int(m.get("disk_read_bytes") or 0), int(m.get("disk_write_bytes") or 0), jdump(final.get("gpu") or {}, pretty=False), str(final.get("stdout_path") or ""), str(final.get("stderr_path") or ""), jdump(final, pretty=False)),
        )
        for metric, unit in [("duration_sec", "seconds"), ("max_rss_kib", "KiB"), ("cpu_user_sec", "seconds"), ("cpu_system_sec", "seconds"), ("disk_read_bytes", "bytes"), ("disk_write_bytes", "bytes")]:
            conn.execute("INSERT INTO selftest_metric_samples(run_id,case_id,ts,metric,value,unit) VALUES(?,?,?,?,?,?)", (run_id, final["case_id"], nowz(), metric, float(m.get(metric) or 0), unit))
        conn.commit()
    report["finished_at"] = nowz()
    report["summary"] = summarize_report(report)
    if args.baseline:
        comp = compare_reports(load_json(Path(args.baseline), {}), report, load_policy(root))
        report["baseline_comparison"] = comp
        if args.fail_on_regression and comp.get("regressions"):
            report["summary"]["ok"] = False
    path = out_dir / "selftest-report.json"
    atomic_write(path, jdump(report))
    summary = report.get("summary") or {}
    status = "passed" if summary.get("ok") else "failed"
    conn.execute("UPDATE selftest_runs SET status=?, finished_at=?, report_path=?, summary_json=? WHERE run_id=?", (status, report["finished_at"], str(path), jdump(summary, pretty=False), run_id))
    conn.commit()
    if args.json:
        print(jdump(report))
    else:
        print(f"selftest run_id={run_id} suite={args.suite} status={status} passed={summary.get('passed')} failed={summary.get('failed')} report={path}")
    if not summary.get("ok"):
        raise SystemExit(1)


def compare_reports(baseline: Dict[str, Any], current: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    thresholds = policy.get("thresholds") or {}
    b_cases = {r.get("case_id"): r for r in baseline.get("results") or []}
    regressions: List[Dict[str, Any]] = []
    improvements: List[Dict[str, Any]] = []
    for cur in current.get("results") or []:
        cid = cur.get("case_id")
        base = b_cases.get(cid)
        if not base:
            improvements.append({"case_id": cid, "metric": "coverage", "detail": "new case in current report"})
            continue
        if base.get("status") == "pass" and cur.get("status") != "pass":
            regressions.append({"case_id": cid, "severity": "fail", "metric": "status", "baseline": "pass", "current": cur.get("status"), "delta_pct": None})
        for metric, warn_key, fail_key in [
            ("duration_sec", "duration_warn_pct", "duration_fail_pct"),
            ("max_rss_kib", "max_rss_warn_pct", "max_rss_fail_pct"),
        ]:
            b = float((base.get("metrics") or {}).get(metric) or 0)
            c = float((cur.get("metrics") or {}).get(metric) or 0)
            if b <= 0 or c <= 0:
                continue
            delta = (c - b) / b
            if delta >= float(thresholds.get(fail_key, 999)):
                regressions.append({"case_id": cid, "severity": "fail", "metric": metric, "baseline": b, "current": c, "delta_pct": round(delta, 6)})
            elif delta >= float(thresholds.get(warn_key, 999)):
                regressions.append({"case_id": cid, "severity": "warn", "metric": metric, "baseline": b, "current": c, "delta_pct": round(delta, 6)})
            elif delta < -0.05:
                improvements.append({"case_id": cid, "metric": metric, "baseline": b, "current": c, "delta_pct": round(delta, 6)})
        ecc = cur.get("metrics", {}).get("ecc_delta_total")
        if isinstance(ecc, int) and ecc >= int(thresholds.get("ecc_delta_fail", 1)):
            regressions.append({"case_id": cid, "severity": "fail", "metric": "ecc_delta_total", "baseline": 0, "current": ecc, "delta_pct": None})
    return {"ok": not [r for r in regressions if r.get("severity") == "fail"], "regressions": regressions, "improvements": improvements, "baseline_run_id": baseline.get("run_id"), "current_run_id": current.get("run_id")}


def catalog_cmd(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    catalog = load_catalog(root)
    cases = catalog.get("cases") or []
    if args.module:
        cases = [c for c in cases if c.get("module") == args.module]
    if args.tier:
        cases = [c for c in cases if c.get("tier") == args.tier]
    doc = {"ok": True, "version": RUNTIME_VERSION, "case_count": len(cases), "suites": catalog.get("suites", {}), "cases": cases}
    if args.json:
        print(jdump(doc))
    else:
        for c in cases:
            live = " live" if c.get("live") else ""
            print(f"{c.get('id')} [{c.get('module')}/{c.get('tier')}{live}] — {c.get('description')}")


def compare_cmd(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    doc = compare_reports(load_json(Path(args.baseline), {}), load_json(Path(args.current), {}), load_policy(root))
    print(jdump(doc))
    if args.fail_on_regression and [r for r in doc.get("regressions", []) if r.get("severity") == "fail"]:
        raise SystemExit(1)


def prometheus_from_report(report: Dict[str, Any]) -> str:
    lines = ["# HELP noemaforge_selftest_case_duration_seconds NoemaForge self-test case duration", "# TYPE noemaforge_selftest_case_duration_seconds gauge"]
    for r in report.get("results") or []:
        labels = f'case_id="{r.get("case_id")}",module="{r.get("module")}",tier="{r.get("tier")}",status="{r.get("status")}"'
        m = r.get("metrics") or {}
        lines.append(f"noemaforge_selftest_case_duration_seconds{{{labels}}} {float(m.get('duration_sec') or 0):.6f}")
        lines.append(f"noemaforge_selftest_case_max_rss_kib{{{labels}}} {int(m.get('max_rss_kib') or 0)}")
        lines.append(f"noemaforge_selftest_case_disk_read_bytes{{{labels}}} {int(m.get('disk_read_bytes') or 0)}")
        lines.append(f"noemaforge_selftest_case_disk_write_bytes{{{labels}}} {int(m.get('disk_write_bytes') or 0)}")
        ecc = m.get("ecc_delta_total")
        if ecc is not None:
            lines.append(f"noemaforge_selftest_case_ecc_delta_total{{{labels}}} {int(ecc)}")
    s = report.get("summary") or {}
    lines.append(f"noemaforge_selftest_cases_total {int(s.get('case_count') or 0)}")
    lines.append(f"noemaforge_selftest_cases_failed {int(s.get('failed') or 0)}")
    return "\n".join(lines) + "\n"


def metrics_cmd(args: argparse.Namespace) -> None:
    report = load_json(Path(args.report), {})
    if args.format == "prometheus":
        print(prometheus_from_report(report), end="")
    else:
        print(jdump({"ok": True, "summary": report.get("summary", {}), "results": report.get("results", [])}))


def _patch_for_new_file(path: str, content: str) -> str:
    lines = content.splitlines()
    out = [f"diff --git a/{path} b/{path}", "new file mode 100644", "index 0000000..1111111", "--- /dev/null", f"+++ b/{path}"]
    out.extend(list(difflib.unified_diff([], lines, fromfile="/dev/null", tofile=f"b/{path}", lineterm=""))[2:])
    # difflib hunk above may contain file headers if slicing breaks for empty; rebuild hunk manually if needed.
    if not any(line.startswith("@@") for line in out):
        out.append(f"@@ -0,0 +1,{len(lines)} @@")
        out.extend("+" + line for line in lines)
    return "\n".join(out) + "\n"


def _flatten_numeric(data: Any, prefix: str = "") -> Dict[str, float]:
    out: Dict[str, float] = {}
    if isinstance(data, dict):
        for k, v in data.items():
            out.update(_flatten_numeric(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(data, list):
        for i, v in enumerate(data):
            out.update(_flatten_numeric(v, f"{prefix}.{i}"))
    elif isinstance(data, (int, float)) and not isinstance(data, bool):
        out[prefix] = float(data)
    return out


def _metrics_delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    b = _flatten_numeric(before)
    a = _flatten_numeric(after)
    rows: Dict[str, Dict[str, Any]] = {}
    for key in sorted(set(b) | set(a)):
        bv = b.get(key); av = a.get(key)
        if bv is None or av is None:
            rows[key] = {"before": bv, "after": av, "delta": None, "pct": None}
        else:
            delta = av - bv
            rows[key] = {"before": bv, "after": av, "delta": delta, "pct": (delta / bv * 100.0) if bv else 0.0}
    return {"metric_count": len(rows), "metrics": rows}


def wiki_patch_legacy_create(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    source_root = Path(args.source_root).resolve() if getattr(args, "source_root", None) else root
    wiki_repo = Path(args.wiki_repo).resolve() if getattr(args, "wiki_repo", None) else Path.cwd()
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    title = args.title or args.summary or "NoemaForge wiki patch"
    patch_id = args.patch_id or "wiki_patch_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(getattr(args, "out_dir", None) or args.out or state / patch_id).resolve()
    payload_dir = out_dir / "payload"
    payload_dir.mkdir(parents=True, exist_ok=True)
    copied: List[Dict[str, str]] = []
    includes = list(getattr(args, "include", None) or []) or ["docs/wiki/README.md"]
    for raw in includes:
        src = Path(raw)
        if not src.is_absolute():
            src = source_root / src
        if src.exists() and src.is_file():
            try:
                rel = src.relative_to(source_root)
            except Exception:
                rel = Path("imports") / src.name
            dst = payload_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            copied.append({"source": str(src), "relative_path": str(rel), "status": "copied"})
        else:
            copied.append({"source": str(src), "status": "missing"})
    before = load_json(Path(args.metrics_before), {}) if getattr(args, "metrics_before", None) else {}
    after = load_json(Path(args.metrics_after), {}) if getattr(args, "metrics_after", None) else {}
    delta = _metrics_delta(before, after)
    desc = args.description or args.user_note or args.summary or "No functional description supplied."
    functional = f"# Functional Delta — {title}\n\n- patch_id: `{patch_id}`\n- created_at: `{nowz()}`\n- description: {desc}\n\n## Included payload\n\n" + "".join(f"- `{x.get('relative_path', x.get('source'))}` — {x.get('status')}\n" for x in copied)
    atomic_write(out_dir / "functional_delta.md", functional)
    atomic_write(out_dir / "metrics_delta.json", jdump(delta))
    patch = "".join(_patch_for_new_file(str(Path("docs/wiki/patches") / patch_id / Path(x.get("relative_path", "payload.txt")).name), (payload_dir / x["relative_path"]).read_text(encoding="utf-8", errors="replace")) for x in copied if x.get("status") == "copied") or "# No textual payload diff generated.\n"
    atomic_write(out_dir / "patch.diff", patch)
    apply_sh = """#!/usr/bin/env bash
set -euo pipefail
WIKI_REPO="${1:-}"
if [[ -z "$WIKI_REPO" ]]; then echo "Usage: ./apply.sh /path/to/wiki-repo" >&2; exit 2; fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -a "$SCRIPT_DIR/payload/." "$WIKI_REPO/"
echo "Applied NoemaForge wiki patch payload to $WIKI_REPO"
"""
    atomic_write(out_dir / "apply.sh", apply_sh)
    os.chmod(out_dir / "apply.sh", 0o755)
    manifest = {"ok": True, "apiVersion": "noemaforge/v1", "kind": "WikiIncrementalPatch", "version": RUNTIME_VERSION, "patch_id": patch_id, "patch_dir": str(out_dir), "wiki_repo": str(wiki_repo), "payload": copied, "metric_count": delta.get("metric_count", 0)}
    atomic_write(out_dir / "wiki_patch_manifest.json", jdump(manifest))
    doc = {"ok": True, "patch_id": patch_id, "patch_dir": str(out_dir), "payload_files": len([x for x in copied if x.get("status") == "copied"]), "metric_count": delta.get("metric_count", 0)}
    print(jdump(doc) if getattr(args, "json", False) else f"ok=true patch_dir={out_dir} patch_id={patch_id}")


def wiki_patch_apply_cmd(args: argparse.Namespace) -> None:
    patch_dir = Path(args.patch_dir).resolve()
    wiki_repo = Path(args.wiki_repo).resolve()
    payload = patch_dir / "payload"
    actions = []
    if payload.exists():
        for src in payload.rglob("*"):
            if src.is_file():
                rel = src.relative_to(payload)
                actions.append({"source": str(src), "target": str(wiki_repo / rel)})
                if not args.dry_run:
                    (wiki_repo / rel).parent.mkdir(parents=True, exist_ok=True)
                    (wiki_repo / rel).write_bytes(src.read_bytes())
    print(jdump({"ok": True, "dry_run": bool(args.dry_run), "patch_dir": str(patch_dir), "wiki_repo": str(wiki_repo), "actions": actions}))


def wiki_patch_cmd(args: argparse.Namespace) -> None:
    if not getattr(args, "report", None) and (getattr(args, "metrics_after", None) or getattr(args, "include", None) or getattr(args, "wiki_repo", None)):
        return wiki_patch_legacy_create(args)
    report = load_json(Path(args.report), {}) if args.report else {}
    before = load_json(Path(args.before), {}) if args.before else {}
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    policy = load_policy(root)
    comparison = compare_reports(before, report, policy) if before and report else report.get("baseline_comparison", {})
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rid = str(report.get("run_id") or "manual")
    patch_id = args.patch_id or f"wiki_patch_{ts}_{rid}"
    rel_dir = Path("docs/wiki/patches") / patch_id
    summary = args.summary or args.user_note or "NoemaForge self-improvement patch"
    metrics_md = [
        f"# Metrics delta — {patch_id}",
        "",
        f"- Created: `{nowz()}`",
        f"- Self-test run: `{rid}`",
        f"- Task: `{args.task or report.get('suite') or 'manual'}`",
        f"- Summary: {summary}",
        "",
        "## Current summary",
        "",
    ]
    for k, v in (report.get("summary") or {}).items():
        metrics_md.append(f"- `{k}`: `{v}`")
    metrics_md += ["", "## Regressions / improvements", ""]
    for r in comparison.get("regressions") or []:
        metrics_md.append(f"- REGRESSION `{r.get('severity')}` `{r.get('case_id')}` `{r.get('metric')}`: {r.get('baseline')} -> {r.get('current')} delta={r.get('delta_pct')}")
    for r in comparison.get("improvements") or []:
        metrics_md.append(f"- IMPROVEMENT `{r.get('case_id')}` `{r.get('metric')}`: {r.get('baseline')} -> {r.get('current')} delta={r.get('delta_pct')}")
    if not comparison.get("regressions") and not comparison.get("improvements"):
        metrics_md.append("- No baseline delta available or no significant changes detected.")
    func_md = [
        f"# Functional delta — {patch_id}",
        "",
        f"- User note: {args.user_note or 'not provided'}",
        f"- Original task: {args.task or 'not provided'}",
        f"- Functional summary: {summary}",
        "",
        "## Case coverage",
        "",
    ]
    for r in report.get("results") or []:
        func_md.append(f"- `{r.get('case_id')}` — {r.get('module')}/{r.get('tier')} — `{r.get('status')}` — {r.get('description')}")
    manifest = {
        "apiVersion": "noemaforge/v1",
        "kind": "WikiIncrementalPatch",
        "version": RUNTIME_VERSION,
        "patch_id": patch_id,
        "created_at": nowz(),
        "report_run_id": rid,
        "summary": summary,
        "task": args.task,
        "user_note": args.user_note,
        "files": [str(rel_dir / "metrics_delta.md"), str(rel_dir / "functional_delta.md"), str(rel_dir / "selftest-report.json")],
        "comparison": comparison,
    }
    files = {
        str(rel_dir / "metrics_delta.md"): "\n".join(metrics_md) + "\n",
        str(rel_dir / "functional_delta.md"): "\n".join(func_md) + "\n",
        str(rel_dir / "selftest-report.json"): jdump(report),
        str(rel_dir / "manifest.json"): jdump(manifest),
    }
    patch_text = "".join(_patch_for_new_file(path, content) + "\n" for path, content in files.items())
    out_dir = Path(args.out).resolve() if args.out else Path.cwd() / patch_id
    out_dir.mkdir(parents=True, exist_ok=True)
    patch_file = out_dir / f"{patch_id}.patch"
    atomic_write(patch_file, patch_text)
    for path, content in files.items():
        atomic_write(out_dir / path, content)
    atomic_write(out_dir / "manifest.json", jdump(manifest))
    manifest["patch_file"] = str(patch_file)
    manifest["patch_sha256"] = sha256_file(patch_file)
    atomic_write(out_dir / "manifest.json", jdump(manifest))
    if args.apply:
        target = Path(args.repo).resolve() if args.repo else Path.cwd()
        for path, content in files.items():
            atomic_write(target / path, content)
    conn = db_connect(Path(args.state).resolve() if args.state else DEFAULT_STATE)
    conn.execute("INSERT OR REPLACE INTO wiki_patches(patch_id,run_id,created_at,patch_file,metadata_json) VALUES(?,?,?,?,?)", (patch_id, rid, manifest["created_at"], str(patch_file), jdump(manifest, pretty=False)))
    conn.commit()
    print(jdump({"ok": True, "patch_id": patch_id, "patch_file": str(patch_file), "out_dir": str(out_dir), "apply": bool(args.apply), "manifest": manifest}))



def baseline_create_cmd(args: argparse.Namespace) -> None:
    if not (args.summary or args.report):
        raise SystemExit("baseline create requires --summary or --report")
    src = Path(args.summary or args.report).resolve()
    report = load_json(src, {})
    label = args.label or f"baseline_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (Path(args.state).resolve() if args.state else DEFAULT_STATE) / "baselines"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{label}.json"
    doc = {"apiVersion": "noemaforge/v1", "kind": "SelfTestBaseline", "version": RUNTIME_VERSION, "label": label, "created_at": nowz(), "report": report}
    atomic_write(out, jdump(doc))
    print(jdump({"ok": True, "baseline": str(out), "label": label}))


def baseline_compare_cmd(args: argparse.Namespace) -> None:
    baseline_doc = load_json(Path(args.baseline), {})
    base_report = baseline_doc.get("report") or baseline_doc
    current = load_json(Path(args.candidate or args.current), {})
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    doc = compare_reports(base_report, current, load_policy(root))
    print(jdump(doc))
    if args.fail_on_regression and [r for r in doc.get("regressions", []) if r.get("severity") == "fail"]:
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="NoemaForge self-test telemetry and wiki-patch runtime")
    p.add_argument("--root", default=str(DEFAULT_ROOT))
    p.add_argument("--state", default=str(DEFAULT_STATE))
    sub = p.add_subparsers(dest="cmd", required=True)
    cat = sub.add_parser("catalog")
    cat.add_argument("--json", action="store_true")
    cat.add_argument("--module")
    cat.add_argument("--tier")
    cat.set_defaults(func=catalog_cmd)
    run = sub.add_parser("run")
    run.add_argument("--suite", default="core")
    run.add_argument("--case", action="append")
    run.add_argument("--out")
    run.add_argument("--out-dir", dest="out_dir")
    run.add_argument("--run-id")
    run.add_argument("--json", action="store_true")
    run.add_argument("--allow-live", action="store_true")
    run.add_argument("--timeout", type=int, default=60)
    run.add_argument("--repeat", type=int, default=1)
    run.add_argument("--baseline")
    run.add_argument("--fail-on-regression", action="store_true")
    run.add_argument("--fail-on-leak", action="store_true")
    run.add_argument("--gpu", action="store_true", help="enable nvidia-smi GPU/VRAM/ECC sampling for this run")
    run.set_defaults(func=run_selftests)
    comp = sub.add_parser("compare")
    comp.add_argument("--baseline", required=True)
    comp.add_argument("--current", required=True)
    comp.add_argument("--fail-on-regression", action="store_true")
    comp.set_defaults(func=compare_cmd)
    base = sub.add_parser("baseline")
    bsub = base.add_subparsers(dest="baseline_action", required=True)
    bc = bsub.add_parser("create")
    bc.add_argument("--summary")
    bc.add_argument("--report")
    bc.add_argument("--label")
    bc.add_argument("--out-dir")
    bc.set_defaults(func=baseline_create_cmd)
    bcmp = bsub.add_parser("compare")
    bcmp.add_argument("--baseline", required=True)
    bcmp.add_argument("--candidate")
    bcmp.add_argument("--current")
    bcmp.add_argument("--fail-on-regression", action="store_true")
    bcmp.set_defaults(func=baseline_compare_cmd)
    met = sub.add_parser("metrics")
    met.add_argument("--report", required=True)
    met.add_argument("--format", choices=["json", "prometheus"], default="json")
    met.set_defaults(func=metrics_cmd)
    wiki = sub.add_parser("wiki-patch")
    wiksub = wiki.add_subparsers(dest="wiki_action", required=True)
    create = wiksub.add_parser("create")
    create.add_argument("--report")
    create.add_argument("--before")
    create.add_argument("--out")
    create.add_argument("--out-dir", dest="out_dir")
    create.add_argument("--repo")
    create.add_argument("--apply", action="store_true")
    create.add_argument("--summary")
    create.add_argument("--user-note")
    create.add_argument("--task")
    create.add_argument("--patch-id")
    # Compatibility with the older wiki-patch runtime surface.
    create.add_argument("--wiki-repo")
    create.add_argument("--source-root")
    create.add_argument("--title")
    create.add_argument("--description")
    create.add_argument("--metrics-before")
    create.add_argument("--metrics-after")
    create.add_argument("--include", action="append")
    create.add_argument("--json", action="store_true")
    create.set_defaults(func=wiki_patch_cmd)
    applyp = wiksub.add_parser("apply")
    applyp.add_argument("--patch-dir", required=True)
    applyp.add_argument("--wiki-repo", required=True)
    applyp.add_argument("--dry-run", action="store_true")
    applyp.set_defaults(func=wiki_patch_apply_cmd)
    return p


def normalize_global_argv(argv: Optional[List[str]]) -> List[str]:
    items = list(sys.argv[1:] if argv is None else argv)
    global_opts: List[str] = []
    rest: List[str] = []
    i = 0
    while i < len(items):
        item = items[i]
        if item in {"--root", "--state"} and i + 1 < len(items):
            global_opts.extend([item, items[i + 1]])
            i += 2
            continue
        rest.append(item)
        i += 1
    return global_opts + rest


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_global_argv(argv))
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
