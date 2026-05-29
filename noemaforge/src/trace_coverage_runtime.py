#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/trace_coverage_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate trace_id coverage across operator-visible NoemaForge control-plane surfaces.
Inputs: Local source files under noemaforge/src.
Outputs: JSON-compatible TraceCoverageReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_trace_coverage_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


API_VERSION = "noemaforge.production-ai/v1"
REPORT_KIND = "TraceCoverageReport"

TRACE_SURFACES = [
    {
        "id": "admin_gui_messages",
        "path": "noemaforge/src/admin_gui_server.py",
        "description": "Persisted Admin GUI conversation messages carry trace_id.",
        "needles": [
            "def save_message(",
            "\"trace_id\": tid",
            "new_trace_id(\"gui-msg\")",
            "messages.jsonl",
        ],
    },
    {
        "id": "admin_gui_jobs",
        "path": "noemaforge/src/admin_gui_server.py",
        "description": "Persisted Admin GUI jobs carry trace_id.",
        "needles": [
            "def create_job(",
            "\"trace_id\": trace_id or production_ai_contracts.new_trace_id",
            "self._write_json(self.jobs_dir",
        ],
    },
    {
        "id": "admin_runtime",
        "path": "noemaforge/src/admin_runtime.py",
        "description": "Admin CLI/chat route creates and forwards trace_id to downstream commands.",
        "needles": [
            "NOEMAFORGE_TRACE_ID",
            "new_trace_id(\"admin\")",
            "\"trace_id\": trace_id",
            "\"--trace-id\", trace_id",
        ],
    },
    {
        "id": "model_selection",
        "path": "noemaforge/src/model_selection_runtime.py",
        "description": "Model-selection result, plan, decision and rollback artifacts carry trace_id.",
        "needles": [
            "NOEMAFORGE_TRACE_ID",
            "new_trace_id(\"model-selection\")",
            "\"trace_id\": trace_id",
            "candidate-selection-plan.json",
            "model-selection-decision.json",
            "rollback_plan.json",
            "plan.add_argument(\"--trace-id\"",
        ],
    },
    {
        "id": "pipeline_runs",
        "path": "noemaforge/src/pipeline_runtime.py",
        "description": "Pipeline run result, manifest and created event carry trace_id.",
        "needles": [
            "NOEMAFORGE_TRACE_ID",
            "new_trace_id(\"pipeline\")",
            "\"trace_id\": trace_id",
            "\"pipeline_created\"",
            "manifest.json",
            "run.add_argument(\"--trace-id\"",
        ],
    },
    {
        "id": "epoch_apply_release_evidence",
        "path": "noemaforge/src/brainctl.py",
        "description": "prestart apply-epoch accepts trace_id and writes it into release evidence.",
        "needles": [
            "p_a.add_argument(\"--trace-id\"",
            "build_epoch_release_evidence",
            "release_evidence.json",
            "trace_id: {trace_id}",
        ],
    },
    {
        "id": "toolproxy_calls",
        "path": "noemaforge/src/toolproxy.py",
        "description": "ToolProxy reads request meta.trace_id and emits trace_id in tool responses/events.",
        "needles": [
            "trace_id = str(((req.get(\"meta\") or {}).get(\"trace_id\"))",
            "\"trace_id\": trace_id",
            "TOOLPROXY_ALLOW",
            "TOOLPROXY_DENY",
            "telemetry.record_llm_call",
        ],
    },
    {
        "id": "telemetry_tool_calls",
        "path": "noemaforge/src/telemetry.py",
        "description": "Telemetry schemas preserve trace_id for LLM/tool call records.",
        "needles": [
            "def record_llm_call(",
            "def record_tool_call(",
            "\"kind\": \"LLMCall\"",
            "\"kind\": \"ToolCall\"",
            "\"trace_id\": trace_id",
        ],
    },
]


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def validate_trace_coverage(project_root: Path | str, *, surfaces: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    root = Path(project_root).resolve()
    rows: List[Dict[str, Any]] = []
    failures: List[str] = []
    selected = list(surfaces or TRACE_SURFACES)

    for surface in selected:
        surface_id = str(surface.get("id") or "").strip()
        rel_path = str(surface.get("path") or "").strip()
        path = root / rel_path
        needles = [str(item) for item in surface.get("needles") or [] if str(item)]
        if not surface_id:
            failures.append("surface_id_missing")
            continue
        if not path.exists():
            rows.append(
                {
                    "id": surface_id,
                    "ok": False,
                    "path": rel_path,
                    "description": str(surface.get("description") or ""),
                    "missing_needles": needles,
                    "present_needles": [],
                }
            )
            failures.append(f"surface_file_missing:{surface_id}:{rel_path}")
            continue
        text = _read_text(path)
        missing = [needle for needle in needles if needle not in text]
        present = [needle for needle in needles if needle in text]
        ok = not missing
        if not ok:
            failures.append(f"surface_trace_missing:{surface_id}")
        rows.append(
            {
                "id": surface_id,
                "ok": ok,
                "path": rel_path,
                "description": str(surface.get("description") or ""),
                "missing_needles": missing,
                "present_needles": present,
            }
        )

    failed = sum(1 for row in rows if not row["ok"])
    return {
        "apiVersion": API_VERSION,
        "kind": REPORT_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "project_root": str(root),
        "failures": sorted(failures),
        "metrics": {
            "surface_total": len(rows),
            "surface_passed": len(rows) - failed,
            "surface_failed": failed,
        },
        "surfaces": rows,
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate trace_id coverage across NoemaForge control-plane surfaces.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/.")
    parser.add_argument("--summary", action="store_true", help="Emit a compact trace coverage summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    report = validate_trace_coverage(args.project_root)
    if args.summary:
        payload = {
            "apiVersion": report["apiVersion"],
            "kind": "TraceCoverageSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "metrics": report["metrics"],
            "failures": report["failures"],
            "surfaces": [
                {"id": row["id"], "ok": row["ok"], "path": row["path"], "missing_needles": row["missing_needles"]}
                for row in report["surfaces"]
            ],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
