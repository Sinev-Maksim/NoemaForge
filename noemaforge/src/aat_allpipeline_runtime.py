#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/aat_allpipeline_runtime.py
Zone: runtime/quality
Purpose: U-004 -- GUI-tier AAT: run every catalog pipeline in safe test mode
         from one control, collect a per-pipeline case report, never let one
         pipeline's failure stop the batch.
Inputs: the pipeline catalog (noemaforge/configs/pipelines.json + media
         catalog, via pipeline_runtime.load_pipeline_catalog), an injected
         pipeline-run callable, an injected persona-lookup callable.
Outputs: a report dict (see run_all_pipelines_aat) and, via
         write_aat_allpipeline_report, a JSON+Markdown artifact pair.
Side effects: none directly -- this module never runs a pipeline itself; the
         caller injects run_pipeline_fn (normally AdminGuiServer.pipeline_run,
         which already enforces model-selection/approval/safety gates).
Tests: noemaforge/tests/test_aat_allpipeline_runtime.py
Notes: Code comments are English-only. "Safe test mode" is not a new concept
         bolted onto pipeline_runtime -- it reuses the existing per-pipeline
         permission_mode taxonomy already declared in pipelines.json:
           plan_only          -> runs end-to-end automatically (no real
                                  mutation is possible in this mode)
           ask_before_write,
           guided_readmostly  -> run is started; the pipeline's own approval
                                  gate is expected to stop it, which is
                                  reported as "blocked_pending_approval", not
                                  a failure
           guided_admin,
           explicit_only,
           manual_only        -> excluded from the automated batch entirely
                                  (reported as "skipped"), since these modes
                                  exist specifically to require a human in
                                  the loop
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

SAFE_AUTO_RUN_MODES = {"plan_only"}
GATED_RUN_MODES = {"ask_before_write", "guided_readmostly"}
# Everything else (guided_admin, explicit_only, manual_only, unknown/missing
# permission_mode) is treated as "skip" -- fail-safe default.

AAT_CASE_NAME = "aat_smoke_test"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def classify_pipeline_for_aat(permission_mode: str) -> str:
    """Return 'run', 'run_expect_gate', or 'skip' for a pipeline's permission_mode.

    Fail-safe: any mode not explicitly recognized as safe-to-automate is
    skipped, never auto-run.
    """
    mode = str(permission_mode or "").strip()
    if mode in SAFE_AUTO_RUN_MODES:
        return "run"
    if mode in GATED_RUN_MODES:
        return "run_expect_gate"
    return "skip"


def build_aat_sample_request(pipeline_id: str, description: str) -> str:
    """Build the small built-in test prompt for a pipeline from its own registered description."""
    text = str(description or "").strip() or f"Run pipeline {pipeline_id} in AAT smoke-test mode."
    return f"[AAT smoke test] {text}"


def classify_pipeline_run_result(result: Any) -> str:
    """Classify a pipeline_run()-shaped result dict into an AAT case status."""
    if not isinstance(result, dict):
        return "error"
    status = str(result.get("status") or "").strip().lower()
    if result.get("clarification_required") or status in {
        "needs_clarification",
        "waiting_for_clarification",
        "ready_for_admin_approval",
    }:
        return "blocked_pending_approval"
    if result.get("ok") is False:
        return "error"
    if status in {"failed", "error"}:
        return "error"
    return "passed"


def _artifact_ref(result: Dict[str, Any]) -> str:
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return ""
    first = artifacts[0]
    if not isinstance(first, dict):
        return ""
    return str(first.get("path") or first.get("open_url") or first.get("preview_url") or "")


def _error_text(result: Dict[str, Any]) -> str:
    for key in ("error", "reply"):
        value = result.get(key)
        if value:
            return str(value)
    return ""


def run_all_pipelines_aat(
    *,
    catalog: Dict[str, Dict[str, Any]],
    run_pipeline_fn: Callable[[str, str], Dict[str, Any]],
    persona_fn: Callable[[str], str] = lambda pipeline_id: "Admin",
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """Run every catalog pipeline in safe test mode; never let one failure stop the batch.

    ``catalog`` is a ``{pipeline_id: spec}`` mapping as returned by
    ``pipeline_runtime.load_pipeline_catalog`` (each spec carries at least
    ``description`` and ``permission_mode``). ``run_pipeline_fn(pipeline_id,
    request_text)`` is injected so this stays testable without a live
    runtime -- in production it is ``AdminGuiServer.pipeline_run`` bound with
    ``allow_degraded=True`` and stripped to the 2-arg shape.
    """
    entries = sorted((k, v) for k, v in catalog.items() if isinstance(v, dict))
    total = len(entries)
    cases: List[Dict[str, Any]] = []

    for index, (pipeline_id, spec) in enumerate(entries, start=1):
        permission_mode = str(spec.get("permission_mode") or "")
        classification = classify_pipeline_for_aat(permission_mode)
        persona = persona_fn(pipeline_id)

        if classification == "skip":
            cases.append({
                "pipeline": pipeline_id,
                "case": AAT_CASE_NAME,
                "status": "skipped",
                "artifact": "",
                "error": (
                    f"permission_mode={permission_mode!r} requires manual/explicit/admin "
                    "invocation; excluded from the automated all-pipeline AAT run by design"
                ),
                "duration_s": 0.0,
                "persona": persona,
            })
            if on_progress is not None:
                on_progress(index, total, pipeline_id)
            continue

        request_text = build_aat_sample_request(pipeline_id, str(spec.get("description") or ""))
        started = time.monotonic()
        try:
            result = run_pipeline_fn(pipeline_id, request_text)
        except Exception as exc:  # a broken pipeline must not abort the batch
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        duration_s = round(time.monotonic() - started, 3)
        if not isinstance(result, dict):
            result = {"ok": False, "error": f"non-dict result: {result!r}"}

        status = classify_pipeline_run_result(result)
        cases.append({
            "pipeline": pipeline_id,
            "case": AAT_CASE_NAME,
            "status": status,
            "artifact": _artifact_ref(result),
            "error": "" if status == "passed" else _error_text(result),
            "duration_s": duration_s,
            "persona": persona,
        })
        if on_progress is not None:
            on_progress(index, total, pipeline_id)

    counts = dict(Counter(str(c["status"]) for c in cases))
    return {
        "ok": True,  # the batch always completes; per-case status carries pass/fail
        "generated": _now_iso(),
        "total": total,
        "counts": counts,
        "cases": cases,
    }


def write_aat_allpipeline_report(out_dir: Path, report: Dict[str, Any], *, stem: str = "aat-allpipeline-report") -> Dict[str, str]:
    """Write JSON and Markdown summaries, matching the pre_release_uat_fix_runtime
    write_*_summary()/write_failure_report() convention used elsewhere in this repo.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    counts = report.get("counts") if isinstance(report.get("counts"), dict) else {}
    lines = [
        f"# {stem}",
        "",
        f"- generated: {report.get('generated', '')}",
        f"- total pipelines: {report.get('total', 0)}",
        f"- counts: {', '.join(f'{k}={v}' for k, v in sorted(counts.items())) or 'none'}",
        "",
        "| Pipeline | Case | Status | Duration (s) | Persona | Artifact | Error |",
        "|---|---|---|---:|---|---|---|",
    ]
    cases = report.get("cases") if isinstance(report.get("cases"), list) else []
    for case in cases:
        if not isinstance(case, dict):
            continue
        error = str(case.get("error") or "").replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {case.get('pipeline', '')} | {case.get('case', '')} | {case.get('status', '')} | "
            f"{case.get('duration_s', 0)} | {case.get('persona', '')} | {case.get('artifact', '')} | {error} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
