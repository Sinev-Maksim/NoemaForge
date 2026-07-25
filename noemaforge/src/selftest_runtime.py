#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/selftest_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-14
Modified: 2026-05-25
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

Existing module notes:
NoemaForge self-test, telemetry and wiki-patch runtime.

0.32.2 scope:
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
import html
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import resource  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised on Windows hosts.
    class _ResourceFallback:
        RUSAGE_CHILDREN = 0
        RUSAGE_SELF = 1

        @staticmethod
        def getrusage(_scope: int) -> Any:
            return type("Usage", (), {"ru_utime": 0.0, "ru_stime": 0.0, "ru_maxrss": 0})()

    resource = _ResourceFallback()  # type: ignore[assignment]

from noemaforge_version import RUNTIME_VERSION
from platform_paths import DEFAULT_PATHS as _pp

DEFAULT_ROOT = _pp.root
DEFAULT_STATE = Path(os.environ.get("NOEMAFORGE_SELFTEST_STATE", str(_pp.data_root / "selftests")))
CATALOG_REL = Path("configs/selftest-case-catalog.json")
POLICY_REL = Path("configs/selftest-telemetry-policy.json")
TEST_EVENT_EXPORT_SELECT = (
    "SELECT event_id,run_id,case_id,event_type,status,severity,ts,summary_json,metrics_json,source_json "
    "FROM selftest_test_events ORDER BY ts ASC, event_type ASC, case_id ASC LIMIT ?"
)
TEST_EVENT_EXPORT_SELECT_BY_RUN = (
    "SELECT event_id,run_id,case_id,event_type,status,severity,ts,summary_json,metrics_json,source_json "
    "FROM selftest_test_events WHERE run_id = ? ORDER BY ts ASC, event_type ASC, case_id ASC LIMIT ?"
)


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


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


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
    conn.execute("CREATE TABLE IF NOT EXISTS selftest_test_events (event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, case_id TEXT NOT NULL DEFAULT '', event_type TEXT NOT NULL, status TEXT NOT NULL, severity TEXT NOT NULL, ts TEXT NOT NULL, summary_json TEXT NOT NULL DEFAULT '{}', metrics_json TEXT NOT NULL DEFAULT '{}', source_json TEXT NOT NULL DEFAULT '{}')")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_selftest_test_events_run ON selftest_test_events(run_id, event_type, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_selftest_test_events_case ON selftest_test_events(case_id, event_type)")
    conn.execute("CREATE TABLE IF NOT EXISTS wiki_patches (patch_id TEXT PRIMARY KEY, run_id TEXT, created_at TEXT NOT NULL, patch_file TEXT NOT NULL, metadata_json TEXT NOT NULL)")
    conn.commit()
    return conn


def _event_id(*parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _event_severity(status: str, problems: Optional[List[Any]] = None) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"fail", "failed", "error"}:
        return "error"
    if problems:
        return "warning"
    return "info"


def build_test_events_from_report(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    run_id = str(report.get("run_id") or "unknown")
    ts = str(report.get("finished_at") or report.get("started_at") or nowz())
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    run_status = "pass" if summary.get("ok") else "fail"
    events: List[Dict[str, Any]] = [
        {
            "event_id": _event_id(run_id, "", "selftest.run.summary", run_status),
            "run_id": run_id,
            "case_id": "",
            "event_type": "selftest.run.summary",
            "status": run_status,
            "severity": _event_severity(run_status),
            "ts": ts,
            "summary": summary,
            "metrics": {
                "case_count": int(summary.get("case_count") or 0),
                "passed": int(summary.get("passed") or 0),
                "failed": int(summary.get("failed") or 0),
                "duration_total_sec": float(summary.get("duration_total_sec") or 0.0),
                "max_rss_kib": int(summary.get("max_rss_kib") or 0),
            },
            "source": {"kind": str(report.get("kind") or "SelfTestReport"), "suite": str(report.get("suite") or "")},
        }
    ]
    for item in report.get("results") or []:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id") or "")
        status = str(item.get("status") or "unknown")
        problems = item.get("problems") if isinstance(item.get("problems"), list) else []
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        events.append(
            {
                "event_id": _event_id(run_id, case_id, "selftest.case.result", status),
                "run_id": run_id,
                "case_id": case_id,
                "event_type": "selftest.case.result",
                "status": status,
                "severity": _event_severity(status, problems),
                "ts": ts,
                "summary": {"module": item.get("module"), "tier": item.get("tier"), "description": item.get("description"), "problems": problems},
                "metrics": metrics,
                "source": {"exit_code": item.get("exit_code"), "stdout_path": item.get("stdout_path"), "stderr_path": item.get("stderr_path")},
            }
        )
    return events


def record_test_events_for_report(conn: sqlite3.Connection, report: Dict[str, Any]) -> List[Dict[str, Any]]:
    events = build_test_events_from_report(report)
    for event in events:
        conn.execute(
            "INSERT OR REPLACE INTO selftest_test_events(event_id,run_id,case_id,event_type,status,severity,ts,summary_json,metrics_json,source_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                event["event_id"],
                event["run_id"],
                event["case_id"],
                event["event_type"],
                event["status"],
                event["severity"],
                event["ts"],
                jdump(event.get("summary") or {}, pretty=False),
                jdump(event.get("metrics") or {}, pretty=False),
                jdump(event.get("source") or {}, pretty=False),
            ),
        )
    conn.commit()
    return events


def export_test_events(state: Path, *, run_id: str = "", limit: int = 500) -> Dict[str, Any]:
    conn = db_connect(state)
    conn.row_factory = sqlite3.Row
    try:
        params: List[Any] = []
        query = TEST_EVENT_EXPORT_SELECT
        if run_id:
            query = TEST_EVENT_EXPORT_SELECT_BY_RUN
            params.append(run_id)
        params.append(max(1, int(limit)))
        rows = conn.execute(query, params).fetchall()
        events = []
        for row in rows:
            events.append(
                {
                    "event_id": row["event_id"],
                    "run_id": row["run_id"],
                    "case_id": row["case_id"],
                    "event_type": row["event_type"],
                    "status": row["status"],
                    "severity": row["severity"],
                    "ts": row["ts"],
                    "summary": json.loads(row["summary_json"] or "{}"),
                    "metrics": json.loads(row["metrics_json"] or "{}"),
                    "source": json.loads(row["source_json"] or "{}"),
                }
            )
    finally:
        conn.close()
    return {"apiVersion": "noemaforge/v1", "kind": "SelfTestEventExport", "version": RUNTIME_VERSION, "ok": True, "run_id": run_id, "event_count": len(events), "events": events}


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


def run_internal_media_adapter_telemetry(root: Path, adapter: str, case_type: str, stdout_path: Path, stderr_path: Path) -> Dict[str, Any]:
    usage_before = resource.getrusage(resource.RUSAGE_SELF)
    start = time.perf_counter()
    exit_code = 0
    try:
        import media_adapter_telemetry_runtime as matr

        policy = matr.load_policy(root / "configs" / "media-adapter-telemetry-policy.json")
        result = matr.evaluate_adapter_selftest_case(adapter, case_type, policy)
        stdout_path.write_text(jdump(result) + "\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        if not result.get("ok"):
            exit_code = 1
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
                elif cmd and cmd[0] == "__media_adapter_telemetry__" and len(cmd) >= 3:
                    result = run_internal_media_adapter_telemetry(root, cmd[1], cmd[2], stdout, stderr)
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
    record_test_events_for_report(conn, report)
    conn.commit()
    if args.json:
        print(jdump(report))
    else:
        print(f"selftest run_id={run_id} suite={args.suite} status={status} passed={summary.get('passed')} failed={summary.get('failed')} report={path}")
    conn.close()
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


def default_premerge_release_guard_policy() -> Dict[str, Any]:
    return {
        "apiVersion": "noemaforge.premerge-release-guard/v1",
        "kind": "PremergeReleaseGuardPolicy",
        "version": RUNTIME_VERSION,
        "release_guard": {
            "require_baseline_report": True,
            "require_current_report": True,
            "block_failed_summary": True,
            "block_failed_cases": True,
            "block_failed_regressions": True,
            "block_warn_regressions_by_default": False,
            "required_case_ids": ["cli_status_json", "pipeline_validate"],
            "required_artifacts": ["selftest-report.json"],
        },
    }


def load_premerge_release_guard_policy(root: Path, policy_path: Optional[Path] = None) -> Dict[str, Any]:
    merged = default_premerge_release_guard_policy()
    user = load_json(policy_path or root / "configs" / "premerge-release-guard-policy.json", {})
    if isinstance(user, dict):
        for key, value in user.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
    return merged


def build_premerge_release_guard(
    baseline: Dict[str, Any],
    current: Dict[str, Any],
    telemetry_policy: Dict[str, Any],
    guard_policy: Optional[Dict[str, Any]] = None,
    *,
    fail_on_warn: bool = False,
) -> Dict[str, Any]:
    policy = guard_policy or default_premerge_release_guard_policy()
    guard = policy.get("release_guard") if isinstance(policy.get("release_guard"), dict) else {}
    blockers: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    baseline_results = baseline.get("results") if isinstance(baseline.get("results"), list) else []
    current_results = current.get("results") if isinstance(current.get("results"), list) else []

    if guard.get("require_baseline_report", True) and not baseline_results:
        blockers.append({"kind": "missing_baseline_report", "detail": "baseline report has no case results"})
    if guard.get("require_current_report", True) and not current_results:
        blockers.append({"kind": "missing_current_report", "detail": "current report has no case results"})

    summary = current.get("summary") if isinstance(current.get("summary"), dict) else {}
    if guard.get("block_failed_summary", True) and summary and not bool(summary.get("ok")):
        blockers.append({"kind": "current_summary_not_ok", "failed": int(summary.get("failed") or 0), "run_id": current.get("run_id")})

    current_by_id = {str(item.get("case_id")): item for item in current_results if isinstance(item, dict)}
    for case_id in _as_string_list(guard.get("required_case_ids")):
        item = current_by_id.get(case_id)
        if not item:
            blockers.append({"kind": "required_case_missing", "case_id": case_id})
        elif item.get("status") != "pass":
            blockers.append({"kind": "required_case_not_passing", "case_id": case_id, "status": item.get("status")})

    if guard.get("block_failed_cases", True):
        for item in current_results:
            if isinstance(item, dict) and item.get("status") != "pass":
                blockers.append({"kind": "current_case_not_passing", "case_id": item.get("case_id"), "status": item.get("status")})

    comparison = compare_reports(baseline, current, telemetry_policy) if baseline_results and current_results else {"ok": False, "regressions": [], "improvements": []}
    for regression in comparison.get("regressions") or []:
        severity = str(regression.get("severity") or "")
        if severity == "fail" and guard.get("block_failed_regressions", True):
            blockers.append({"kind": "baseline_regression", **regression})
        elif severity == "warn":
            target = blockers if (fail_on_warn or guard.get("block_warn_regressions_by_default", False)) else warnings
            target.append({"kind": "baseline_regression_warning", **regression})

    required_artifacts = _as_string_list(guard.get("required_artifacts"))
    artifact_status = [
        {"id": item, "required": True, "present": item == "selftest-report.json" and bool(current_results)}
        for item in required_artifacts
    ]
    for item in artifact_status:
        if item["required"] and not item["present"]:
            blockers.append({"kind": "required_artifact_missing", "artifact": item["id"]})

    doc = {
        "apiVersion": "noemaforge.premerge-release-guard/v1",
        "kind": "PremergeReleaseGuardDecision",
        "version": RUNTIME_VERSION,
        "created_at": nowz(),
        "ok": not blockers,
        "decision": "allow" if not blockers else "block",
        "baseline_run_id": baseline.get("run_id"),
        "current_run_id": current.get("run_id"),
        "blockers": blockers,
        "warnings": warnings,
        "comparison": comparison,
        "artifact_status": artifact_status,
        "rollback_plan": [
            "Keep the current release candidate out of merge/promotion.",
            "Review failed cases and baseline regressions.",
            "Regenerate the current selftest report after fixes and rerun this guard.",
        ],
    }
    return doc


def premerge_release_guard_cmd(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    baseline = load_json(Path(args.baseline), {})
    current_path = Path(args.current or args.report)
    current = load_json(current_path, {})
    policy_path = Path(args.policy).resolve() if args.policy else None
    guard = build_premerge_release_guard(
        baseline,
        current,
        load_policy(root),
        load_premerge_release_guard_policy(root, policy_path),
        fail_on_warn=bool(args.fail_on_warn),
    )
    if args.out:
        atomic_write(Path(args.out), jdump(guard))
    if args.json:
        print(jdump(guard))
    else:
        print(f"premerge-release-guard decision={guard['decision']} blockers={len(guard['blockers'])} warnings={len(guard['warnings'])}")
    if not guard.get("ok"):
        raise SystemExit(1)


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


def _parse_report_time(report: Dict[str, Any]) -> str:
    return str(report.get("finished_at") or report.get("started_at") or report.get("run_id") or "")


def _report_summary_row(report: Dict[str, Any]) -> Dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    return {
        "run_id": str(report.get("run_id") or ""),
        "suite": str(report.get("suite") or ""),
        "started_at": str(report.get("started_at") or ""),
        "finished_at": str(report.get("finished_at") or ""),
        "ok": bool(summary.get("ok", False)),
        "case_count": int(summary.get("case_count") or 0),
        "passed": int(summary.get("passed") or 0),
        "failed": int(summary.get("failed") or 0),
        "duration_total_sec": float(summary.get("duration_total_sec") or 0.0),
        "duration_max_sec": float(summary.get("duration_max_sec") or 0.0),
        "max_rss_kib": int(summary.get("max_rss_kib") or 0),
        "disk_write_bytes_total": int(summary.get("disk_write_bytes_total") or 0),
        "ecc_delta_total": int(summary.get("ecc_delta_total") or 0),
    }


def _case_point(report: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    return {
        "run_id": str(report.get("run_id") or ""),
        "suite": str(report.get("suite") or ""),
        "finished_at": str(report.get("finished_at") or report.get("started_at") or ""),
        "status": str(result.get("status") or "unknown"),
        "duration_sec": float(metrics.get("duration_sec") or 0.0),
        "max_rss_kib": int(metrics.get("max_rss_kib") or 0),
        "disk_write_bytes": int(metrics.get("disk_write_bytes") or 0),
        "module": str(result.get("module") or ""),
        "tier": str(result.get("tier") or ""),
    }


def build_trend_dashboard(reports: Iterable[Dict[str, Any]], *, title: str = "NoemaForge self-test trend") -> Dict[str, Any]:
    ordered = sorted([r for r in reports if isinstance(r, dict)], key=_parse_report_time)
    summary_rows = [_report_summary_row(report) for report in ordered]
    case_series: Dict[str, List[Dict[str, Any]]] = {}
    for report in ordered:
        for result in report.get("results") or []:
            if not isinstance(result, dict):
                continue
            case_id = str(result.get("case_id") or "").strip()
            if not case_id:
                continue
            case_series.setdefault(case_id, []).append(_case_point(report, result))

    warnings: List[Dict[str, Any]] = []
    for case_id, points in sorted(case_series.items()):
        if len(points) < 2:
            continue
        previous = points[-2]
        latest = points[-1]
        if previous.get("status") == "pass" and latest.get("status") != "pass":
            warnings.append({"kind": "case_status_regression", "case_id": case_id, "from": previous.get("status"), "to": latest.get("status"), "run_id": latest.get("run_id")})
        old_duration = float(previous.get("duration_sec") or 0.0)
        new_duration = float(latest.get("duration_sec") or 0.0)
        if old_duration > 0 and new_duration > old_duration * 1.50:
            warnings.append({"kind": "case_duration_spike", "case_id": case_id, "from": old_duration, "to": new_duration, "run_id": latest.get("run_id")})
        old_rss = int(previous.get("max_rss_kib") or 0)
        new_rss = int(latest.get("max_rss_kib") or 0)
        if old_rss > 0 and new_rss > int(old_rss * 1.60):
            warnings.append({"kind": "case_rss_spike", "case_id": case_id, "from": old_rss, "to": new_rss, "run_id": latest.get("run_id")})

    if len(summary_rows) >= 2 and summary_rows[-1]["failed"] > summary_rows[-2]["failed"]:
        warnings.append({"kind": "failed_count_increase", "from": summary_rows[-2]["failed"], "to": summary_rows[-1]["failed"], "run_id": summary_rows[-1]["run_id"]})

    latest = summary_rows[-1] if summary_rows else {}
    return {
        "apiVersion": "noemaforge/v1",
        "kind": "SelfTestTrendDashboard",
        "version": RUNTIME_VERSION,
        "title": title,
        "generated_at": nowz(),
        "ok": bool(summary_rows),
        "run_count": len(summary_rows),
        "case_count": len(case_series),
        "latest": latest,
        "summaries": summary_rows,
        "case_series": case_series,
        "warnings": warnings,
    }


def render_trend_dashboard_html(dashboard: Dict[str, Any]) -> str:
    title = html.escape(str(dashboard.get("title") or "NoemaForge self-test trend"))
    summaries = dashboard.get("summaries") if isinstance(dashboard.get("summaries"), list) else []
    warnings = dashboard.get("warnings") if isinstance(dashboard.get("warnings"), list) else []
    cases = dashboard.get("case_series") if isinstance(dashboard.get("case_series"), dict) else {}

    def td(value: Any) -> str:
        return f"<td>{html.escape(str(value))}</td>"

    summary_rows = "\n".join(
        "<tr>"
        + td(row.get("run_id"))
        + td(row.get("suite"))
        + td(row.get("finished_at"))
        + td(row.get("passed"))
        + td(row.get("failed"))
        + td(row.get("duration_total_sec"))
        + td(row.get("max_rss_kib"))
        + "</tr>"
        for row in summaries
    )
    warning_items = "\n".join(f"<li>{html.escape(json.dumps(item, ensure_ascii=False, sort_keys=True))}</li>" for item in warnings) or "<li>none</li>"
    case_rows = "\n".join(
        "<tr>"
        + td(case_id)
        + td(points[-1].get("status") if points else "")
        + td(points[-1].get("duration_sec") if points else "")
        + td(points[-1].get("max_rss_kib") if points else "")
        + td(len(points))
        + "</tr>"
        for case_id, points in sorted(cases.items())
    )
    data_json = html.escape(jdump(dashboard, pretty=False))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #f7f7f4; color: #202124; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0 2rem; background: #fff; }}
    th, td {{ border: 1px solid #ddd; padding: 0.45rem 0.55rem; text-align: left; font-size: 0.92rem; }}
    th {{ background: #ece9df; }}
    code, pre {{ white-space: pre-wrap; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p>Generated {html.escape(str(dashboard.get("generated_at") or ""))}; runs: {int(dashboard.get("run_count") or 0)}; cases: {int(dashboard.get("case_count") or 0)}.</p>
  <h2>Run Summaries</h2>
  <table><thead><tr><th>Run</th><th>Suite</th><th>Finished</th><th>Passed</th><th>Failed</th><th>Total seconds</th><th>Max RSS KiB</th></tr></thead><tbody>{summary_rows}</tbody></table>
  <h2>Warnings</h2>
  <ul>{warning_items}</ul>
  <h2>Latest Case Points</h2>
  <table><thead><tr><th>Case</th><th>Status</th><th>Duration</th><th>Max RSS KiB</th><th>Points</th></tr></thead><tbody>{case_rows}</tbody></table>
  <script type="application/json" id="selftest-trend-data">{data_json}</script>
</body>
</html>
"""


def write_trend_dashboard(dashboard: Dict[str, Any], out_dir: Path) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "selftest-trend.json"
    html_path = out_dir / "index.html"
    atomic_write(json_path, jdump(dashboard))
    atomic_write(html_path, render_trend_dashboard_html(dashboard))
    return {"json": str(json_path), "html": str(html_path)}


def discover_trend_reports(state: Path, limit: int) -> List[Path]:
    candidates = sorted((state / "runs").glob("*/selftest-report.json"))
    if limit > 0:
        candidates = candidates[-limit:]
    return candidates


def trend_cmd(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    report_paths = [Path(item).resolve() for item in (args.report or [])]
    if not report_paths:
        report_paths = discover_trend_reports(state, int(args.limit or 50))
    reports = [load_json(path, {}) for path in report_paths if path.exists()]
    if not reports:
        raise SystemExit("no selftest reports found; pass --report or run selftest first")
    dashboard = build_trend_dashboard(reports, title=args.title)
    outputs: Dict[str, str] = {}
    if args.out_dir:
        outputs = write_trend_dashboard(dashboard, Path(args.out_dir).resolve())
        dashboard["outputs"] = outputs
    if args.format == "json":
        print(jdump(dashboard))
    else:
        latest = dashboard.get("latest") or {}
        suffix = f" json={outputs.get('json')} html={outputs.get('html')}" if outputs else ""
        print(f"selftest trend runs={dashboard.get('run_count')} cases={dashboard.get('case_count')} latest={latest.get('run_id')} failed={latest.get('failed')} warnings={len(dashboard.get('warnings') or [])}{suffix}")


def _rss_slope_kib_per_repeat(values: List[int]) -> float:
    if len(values) < 2:
        return 0.0
    xs = [float(i + 1) for i in range(len(values))]
    ys = [float(value) for value in values]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom <= 0:
        return 0.0
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denom


def _repeat_rss_sequence(result: Dict[str, Any]) -> List[int]:
    repeats = result.get("repeats") if isinstance(result.get("repeats"), dict) else {}
    raw = repeats.get("max_rss_kib_sequence") if isinstance(repeats, dict) else []
    if not isinstance(raw, list):
        return []
    values: List[int] = []
    for value in raw:
        try:
            values.append(max(0, int(value)))
        except Exception:
            continue
    return values


def build_rss_slope_report(
    report: Dict[str, Any],
    *,
    title: str = "NoemaForge RSS slope stress report",
    warn_slope_kib: float = 512.0,
    fail_slope_kib: float = 2048.0,
    min_repeats: int = 3,
) -> Dict[str, Any]:
    cases: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for result in report.get("results") or []:
        if not isinstance(result, dict):
            continue
        case_id = str(result.get("case_id") or "")
        sequence = _repeat_rss_sequence(result)
        if len(sequence) < max(2, int(min_repeats)):
            skipped.append({"case_id": case_id, "reason": "insufficient_repeat_rss_samples", "sample_count": len(sequence)})
            continue
        slope = _rss_slope_kib_per_repeat(sequence)
        first = sequence[0]
        last = sequence[-1]
        delta = last - first
        delta_pct = round(delta / first, 6) if first > 0 else 0.0
        repeats = result.get("repeats") if isinstance(result.get("repeats"), dict) else {}
        explicit_leak = bool(repeats.get("memory_leak_suspect"))
        severity = "info"
        if explicit_leak or slope >= float(fail_slope_kib):
            severity = "fail"
        elif slope >= float(warn_slope_kib) or (first > 0 and last > int(first * 1.10)):
            severity = "warn"
        cases.append(
            {
                "case_id": case_id,
                "module": str(result.get("module") or ""),
                "tier": str(result.get("tier") or ""),
                "status": str(result.get("status") or "unknown"),
                "repeat_count": len(sequence),
                "max_rss_kib_sequence": sequence,
                "first_rss_kib": first,
                "last_rss_kib": last,
                "peak_rss_kib": max(sequence),
                "delta_kib": delta,
                "delta_pct": delta_pct,
                "slope_kib_per_repeat": round(slope, 6),
                "memory_leak_suspect": explicit_leak or severity == "fail",
                "severity": severity,
            }
        )
    findings = [item for item in cases if item.get("severity") in {"warn", "fail"}]
    failures = [item for item in cases if item.get("severity") == "fail"]
    max_slope = max([float(item.get("slope_kib_per_repeat") or 0.0) for item in cases], default=0.0)
    summary = {
        "run_id": str(report.get("run_id") or ""),
        "suite": str(report.get("suite") or ""),
        "analyzed_cases": len(cases),
        "skipped_cases": len(skipped),
        "findings": len(findings),
        "failures": len(failures),
        "max_slope_kib_per_repeat": round(max_slope, 6),
        "warn_slope_kib": float(warn_slope_kib),
        "fail_slope_kib": float(fail_slope_kib),
        "min_repeats": max(2, int(min_repeats)),
    }
    return {
        "apiVersion": "noemaforge/v1",
        "kind": "SelfTestRssSlopeReport",
        "version": RUNTIME_VERSION,
        "title": title,
        "generated_at": nowz(),
        "ok": bool(cases) and not failures,
        "source_run_id": str(report.get("run_id") or ""),
        "summary": summary,
        "cases": cases,
        "findings": findings,
        "skipped": skipped,
    }


def rss_slope_cmd(args: argparse.Namespace) -> None:
    source = load_json(Path(args.report).resolve(), {})
    slope_report = build_rss_slope_report(
        source,
        title=args.title,
        warn_slope_kib=float(args.warn_slope_kib),
        fail_slope_kib=float(args.fail_slope_kib),
        min_repeats=int(args.min_repeats),
    )
    if args.out:
        atomic_write(Path(args.out).resolve(), jdump(slope_report))
    if args.json:
        print(jdump(slope_report))
    else:
        summary = slope_report.get("summary") or {}
        suffix = f" out={Path(args.out).resolve()}" if args.out else ""
        print(f"selftest stress run={summary.get('run_id')} analyzed={summary.get('analyzed_cases')} findings={summary.get('findings')} failures={summary.get('failures')}{suffix}")
    if args.fail_on_leak and not slope_report.get("ok"):
        raise SystemExit(1)


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


def _safe_branch_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._/-" else "-" for ch in str(value or "").strip())
    cleaned = cleaned.strip("./-")
    return cleaned or "noemaforge/wiki-patch"


def _load_wiki_patch_manifest(patch_dir: Path) -> Dict[str, Any]:
    for name in ["wiki_patch_manifest.json", "manifest.json"]:
        path = patch_dir / name
        if path.exists():
            loaded = load_json(path, {})
            if isinstance(loaded, dict):
                loaded["manifest_path"] = str(path)
                return loaded
    return {"manifest_path": ""}


def build_wiki_patch_commit_plan(
    patch_dir: Path,
    wiki_repo: Path,
    *,
    branch: str,
    reviewed_by: str,
    review_id: str = "",
    message: str = "",
    out_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    patch_dir = patch_dir.resolve()
    wiki_repo = wiki_repo.resolve()
    if not patch_dir.exists():
        raise ValueError(f"patch_dir_not_found:{patch_dir}")
    if not str(reviewed_by or "").strip():
        raise ValueError("reviewed_by_required")
    manifest = _load_wiki_patch_manifest(patch_dir)
    patch_id = str(manifest.get("patch_id") or patch_dir.name)
    branch_name = _safe_branch_name(branch or f"noemaforge/wiki-patch/{patch_id}")
    destination = (out_dir or patch_dir / "reviewed_commit").resolve()
    commit_message = message or f"NoemaForge wiki patch: {patch_id}\n\nReviewed-by: {reviewed_by}\nReview-id: {review_id or 'manual'}\nPatch-dir: {patch_dir}\n"
    script = f"""#!/usr/bin/env bash
set -euo pipefail
WIKI_REPO="${{1:-{wiki_repo}}}"
PATCH_DIR="${{2:-{patch_dir}}}"
BRANCH="{branch_name}"

if [[ ! -d "$WIKI_REPO/.git" ]]; then
  echo "wiki repo is not a git checkout: $WIKI_REPO" >&2
  exit 2
fi
if [[ ! -d "$PATCH_DIR" ]]; then
  echo "patch dir not found: $PATCH_DIR" >&2
  exit 2
fi

git -C "$WIKI_REPO" status --short
git -C "$WIKI_REPO" checkout -B "$BRANCH"
if [[ -x "$PATCH_DIR/apply.sh" ]]; then
  "$PATCH_DIR/apply.sh" "$WIKI_REPO"
elif [[ -d "$PATCH_DIR/payload" ]]; then
  cp -a "$PATCH_DIR/payload/." "$WIKI_REPO/"
else
  echo "no apply.sh or payload directory found in $PATCH_DIR" >&2
  exit 2
fi
git -C "$WIKI_REPO" add .
git -C "$WIKI_REPO" commit -F "{destination / 'commit_message.txt'}"
echo "Created local wiki commit on $BRANCH; review and push manually if desired."
"""
    plan = {
        "apiVersion": "noemaforge/v1",
        "kind": "WikiPatchCommitPlan",
        "version": RUNTIME_VERSION,
        "ok": True,
        "created_at": nowz(),
        "patch_id": patch_id,
        "patch_dir": str(patch_dir),
        "wiki_repo": str(wiki_repo),
        "branch": branch_name,
        "review": {"required": True, "reviewed_by": reviewed_by, "review_id": review_id or "manual"},
        "no_push": True,
        "commands": [
            f"git -C {wiki_repo} checkout -B {branch_name}",
            f"{patch_dir / 'apply.sh'} {wiki_repo}",
            f"git -C {wiki_repo} add .",
            f"git -C {wiki_repo} commit -F {destination / 'commit_message.txt'}",
        ],
        "artifacts": {
            "plan": str(destination / "reviewed_commit_plan.json"),
            "script": str(destination / "commit_helper.sh"),
            "commit_message": str(destination / "commit_message.txt"),
        },
        "source_manifest": manifest.get("manifest_path", ""),
    }
    atomic_write(destination / "reviewed_commit_plan.json", jdump(plan))
    atomic_write(destination / "commit_message.txt", commit_message)
    atomic_write(destination / "commit_helper.sh", script)
    try:
        os.chmod(destination / "commit_helper.sh", 0o755)
    except Exception:
        pass
    return plan


def wiki_patch_commit_plan_cmd(args: argparse.Namespace) -> None:
    try:
        plan = build_wiki_patch_commit_plan(
            Path(args.patch_dir),
            Path(args.wiki_repo),
            branch=args.branch,
            reviewed_by=args.reviewed_by,
            review_id=args.review_id or "",
            message=args.message or "",
            out_dir=Path(args.out_dir) if args.out_dir else None,
        )
    except ValueError as exc:
        raise SystemExit(str(exc))
    print(jdump(plan) if args.json else f"wiki-patch commit-plan patch_id={plan['patch_id']} branch={plan['branch']} script={plan['artifacts']['script']}")


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


def events_ingest_cmd(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    report = load_json(Path(args.report), {})
    conn = db_connect(state)
    try:
        events = record_test_events_for_report(conn, report)
    finally:
        conn.close()
    doc = {"ok": True, "run_id": report.get("run_id"), "event_count": len(events), "state": str(state)}
    print(jdump(doc) if args.json else f"ok=true run_id={doc['run_id']} events={doc['event_count']}")


def events_export_cmd(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    doc = export_test_events(state, run_id=args.run_id or "", limit=int(args.limit or 500))
    if args.out:
        atomic_write(Path(args.out), jdump(doc))
    print(jdump(doc) if args.json else f"selftest events count={doc['event_count']} run_id={doc.get('run_id') or '*'}")


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
    guard = sub.add_parser("release-guard")
    guard.add_argument("--baseline", required=True)
    current_group = guard.add_mutually_exclusive_group(required=True)
    current_group.add_argument("--current")
    current_group.add_argument("--report")
    guard.add_argument("--policy")
    guard.add_argument("--out")
    guard.add_argument("--json", action="store_true")
    guard.add_argument("--fail-on-warn", action="store_true")
    guard.set_defaults(func=premerge_release_guard_cmd)
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
    trend = sub.add_parser("trend")
    trend.add_argument("--report", action="append", help="selftest-report.json path; may be supplied more than once")
    trend.add_argument("--out-dir")
    trend.add_argument("--title", default="NoemaForge self-test trend")
    trend.add_argument("--format", choices=["text", "json"], default="text")
    trend.add_argument("--limit", type=int, default=50, help="maximum discovered reports when --report is not supplied")
    trend.set_defaults(func=trend_cmd)
    events = sub.add_parser("events")
    evsub = events.add_subparsers(dest="events_action", required=True)
    eving = evsub.add_parser("ingest")
    eving.add_argument("--report", required=True)
    eving.add_argument("--json", action="store_true")
    eving.set_defaults(func=events_ingest_cmd)
    evexp = evsub.add_parser("export")
    evexp.add_argument("--run-id")
    evexp.add_argument("--limit", type=int, default=500)
    evexp.add_argument("--out")
    evexp.add_argument("--json", action="store_true")
    evexp.set_defaults(func=events_export_cmd)
    stress = sub.add_parser("stress")
    stress.add_argument("--report", required=True, help="selftest-report.json generated with --repeat")
    stress.add_argument("--out")
    stress.add_argument("--title", default="NoemaForge RSS slope stress report")
    stress.add_argument("--warn-slope-kib", type=float, default=512.0)
    stress.add_argument("--fail-slope-kib", type=float, default=2048.0)
    stress.add_argument("--min-repeats", type=int, default=3)
    stress.add_argument("--json", action="store_true")
    stress.add_argument("--fail-on-leak", action="store_true")
    stress.set_defaults(func=rss_slope_cmd)
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
    cplan = wiksub.add_parser("commit-plan")
    cplan.add_argument("--patch-dir", required=True)
    cplan.add_argument("--wiki-repo", required=True)
    cplan.add_argument("--branch", default="")
    cplan.add_argument("--reviewed-by", required=True)
    cplan.add_argument("--review-id")
    cplan.add_argument("--message")
    cplan.add_argument("--out-dir")
    cplan.add_argument("--json", action="store_true")
    cplan.set_defaults(func=wiki_patch_commit_plan_cmd)
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
