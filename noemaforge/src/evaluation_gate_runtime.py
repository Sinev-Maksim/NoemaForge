#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/evaluation_gate_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate EvaluationGate behavior across production-AI change domains.
Inputs: Built-in local gate fixtures and production_ai_contracts.evaluate_gate.
Outputs: JSON-compatible EvaluationGateValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_evaluation_gate_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import production_ai_contracts as pac


REPORT_KIND = "EvaluationGateValidationReport"


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _passing_evidence(domain: str) -> Dict[str, Any]:
    return {
        "artifact_uri": f"reports/evaluation-gate/{domain}.json",
        "run_at": "2026-05-19T00:00:00Z",
        "checks": [
            {
                "id": check_id,
                "status": "passed",
                "score": 1.0,
                "threshold": 1.0,
            }
            for check_id in pac.DEFAULT_REQUIRED_CHECKS[domain]
        ],
    }


def _fixture_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for domain in sorted(pac.CHANGE_DOMAINS):
        rows.append(
            {
                "id": f"{domain}_happy_path",
                "domain": domain,
                "expected_ok": True,
                "change": {"change_id": f"{domain}-gate-smoke", "domain": domain},
                "evidence": _passing_evidence(domain),
            }
        )

    missing_router = _passing_evidence("router")
    missing_router["checks"] = [check for check in missing_router["checks"] if check["id"] != "per_route_metrics"]
    rows.append(
        {
            "id": "router_missing_required_check_blocks",
            "domain": "router",
            "expected_ok": False,
            "expected_failure": "check_missing:per_route_metrics",
            "change": {"change_id": "router-missing-check", "domain": "router"},
            "evidence": missing_router,
        }
    )

    low_score_rag = _passing_evidence("rag")
    low_score_rag["checks"] = [
        {**check, "score": 0.5, "threshold": 1.0} if check["id"] == "groundedness" else check
        for check in low_score_rag["checks"]
    ]
    rows.append(
        {
            "id": "rag_below_threshold_blocks",
            "domain": "rag",
            "expected_ok": False,
            "expected_failure": "check_below_threshold:groundedness",
            "change": {"change_id": "rag-low-groundedness", "domain": "rag"},
            "evidence": low_score_rag,
        }
    )

    failed_code = _passing_evidence("code")
    failed_code["checks"] = [
        {**check, "status": "failed"} if check["id"] == "unit_tests" else check
        for check in failed_code["checks"]
    ]
    rows.append(
        {
            "id": "code_failed_status_blocks",
            "domain": "code",
            "expected_ok": False,
            "expected_failure": "check_failed:unit_tests",
            "change": {"change_id": "code-failed-unit-tests", "domain": "code"},
            "evidence": failed_code,
        }
    )

    return rows


def validate_evaluation_gate(*, fixtures: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    failures: List[str] = []
    rows: List[Dict[str, Any]] = []
    selected = list(fixtures or _fixture_rows())

    for fixture in selected:
        fixture_id = str(fixture.get("id") or "").strip() or "unnamed_fixture"
        expected_ok = bool(fixture.get("expected_ok"))
        expected_failure = str(fixture.get("expected_failure") or "")
        try:
            result = pac.evaluate_gate(dict(fixture.get("change") or {}), dict(fixture.get("evidence") or {}))
            actual_ok = bool(result.get("ok"))
            expected_failure_seen = not expected_failure or expected_failure in set(result.get("failures") or [])
            ok = actual_ok == expected_ok and expected_failure_seen
            if not ok:
                failures.append(f"fixture_failed:{fixture_id}")
            rows.append(
                {
                    "id": fixture_id,
                    "ok": ok,
                    "domain": str(fixture.get("domain") or (fixture.get("change") or {}).get("domain") or ""),
                    "expected_ok": expected_ok,
                    "actual_ok": actual_ok,
                    "expected_failure": expected_failure,
                    "decision": str(result.get("decision") or ""),
                    "failures": list(result.get("failures") or []),
                    "warnings": list(result.get("warnings") or []),
                    "required_checks": list(result.get("required_checks") or []),
                    "passed_checks": list(result.get("passed_checks") or []),
                }
            )
        except Exception as exc:
            failures.append(f"fixture_error:{fixture_id}:{exc}")
            rows.append(
                {
                    "id": fixture_id,
                    "ok": False,
                    "domain": str(fixture.get("domain") or ""),
                    "expected_ok": expected_ok,
                    "actual_ok": False,
                    "expected_failure": expected_failure,
                    "decision": "error",
                    "failures": [repr(exc)],
                    "warnings": [],
                    "required_checks": [],
                    "passed_checks": [],
                }
            )

    failed = sum(1 for row in rows if not row["ok"])
    domain_coverage = sorted({row["domain"] for row in rows if row.get("domain")})
    missing_domains = sorted(pac.CHANGE_DOMAINS.difference(domain_coverage))
    for domain in missing_domains:
        failures.append(f"domain_missing:{domain}")

    return {
        "apiVersion": pac.API_VERSION,
        "kind": REPORT_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "failures": sorted(failures),
        "domain_coverage": domain_coverage,
        "missing_domains": missing_domains,
        "required_checks_by_domain": {domain: list(pac.DEFAULT_REQUIRED_CHECKS[domain]) for domain in sorted(pac.CHANGE_DOMAINS)},
        "metrics": {
            "fixture_total": len(rows),
            "fixture_passed": len(rows) - failed,
            "fixture_failed": failed,
            "domain_total": len(pac.CHANGE_DOMAINS),
            "domain_covered": len(domain_coverage),
        },
        "fixtures": rows,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge EvaluationGate behavior.")
    parser.add_argument("--summary", action="store_true", help="Emit a compact validation summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    report = validate_evaluation_gate()
    if args.summary:
        payload = {
            "apiVersion": report["apiVersion"],
            "kind": "EvaluationGateValidationSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "metrics": report["metrics"],
            "failures": report["failures"],
            "domain_coverage": report["domain_coverage"],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
