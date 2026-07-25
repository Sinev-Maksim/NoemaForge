#!/usr/bin/env python3
"""
NoemaForge release decision helper.

The helper is intentionally source-only and offline: it consumes already
collected source-gate and known-finding JSON, then writes a small decision or
failure report. It does not start services, contact GitHub, or mutate runtime
state.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

from noemaforge_version import RUNTIME_VERSION


API_VERSION = "noemaforge.release-decision-helper/v1"
DECISION_KIND = "ReleaseDecisionReport"
FAILURE_KIND = "ReleaseDecisionFailureReport"
VALID_EVIDENCE = {"repo-evidenced", "target-evidenced", "partial", "missing", "not_applicable"}


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_arg(value: str) -> Any:
    if value == "-":
        return json.loads(sys.stdin.read())
    path = Path(value)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return json.loads(value)


def _as_dict(value: Any, *, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label}_not_object")
    return value


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _known_finding_records(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = payload.get("known_findings", payload.get("findings", []))
    records: List[Dict[str, Any]] = []
    for index, item in enumerate(_as_list(raw)):
        if not isinstance(item, dict):
            raise ValueError(f"known_finding_not_object:{index}")
        records.append(item)
    return records


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "pass", "passed", "ok"}
    return bool(value)


def _finding_is_blocking(item: Dict[str, Any]) -> bool:
    if _truthy(item.get("resolved")) or _truthy(item.get("waived")):
        return False
    if _truthy(item.get("blocking")):
        return True
    severity = str(item.get("severity") or item.get("level") or "").strip().lower()
    status = str(item.get("status") or "").strip().lower()
    return severity in {"blocker", "blocking", "critical", "p0"} or status in {"open", "failed", "fail"}


def _source_gate_ok(source_gate: Dict[str, Any]) -> bool:
    if "ok" in source_gate:
        return source_gate.get("ok") is True
    if "passed" in source_gate:
        return source_gate.get("passed") is True
    raise ValueError("source_gate_missing_ok")


def build_release_decision_report(source_gate: Dict[str, Any], known_findings: Dict[str, Any]) -> Dict[str, Any]:
    source_gate = _as_dict(source_gate, label="source_gate")
    known_findings = _as_dict(known_findings, label="known_findings")
    source_ok = _source_gate_ok(source_gate)
    records = _known_finding_records(known_findings)
    blocking = [item for item in records if _finding_is_blocking(item)]
    evidence = str(source_gate.get("evidence") or known_findings.get("evidence") or "repo-evidenced")
    if evidence not in VALID_EVIDENCE:
        evidence = "partial"
    decision = "pass" if source_ok and not blocking else "block"
    return {
        "apiVersion": API_VERSION,
        "kind": DECISION_KIND,
        "version": RUNTIME_VERSION,
        "created_at": _nowz(),
        "ok": decision == "pass",
        "decision": decision,
        "evidence": evidence,
        "live_evidence_claimed": False,
        "source_gate": {
            "ok": source_ok,
            "failures": _as_list(source_gate.get("failures")),
            "warnings": _as_list(source_gate.get("warnings")),
        },
        "known_findings": {
            "total": len(records),
            "blocking": len(blocking),
            "blocking_ids": [str(item.get("id") or item.get("number") or index) for index, item in enumerate(blocking)],
        },
    }


def build_failure_report(exc: BaseException, *, phase: str = "source_gate_construction") -> Dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": FAILURE_KIND,
        "version": RUNTIME_VERSION,
        "created_at": _nowz(),
        "ok": False,
        "decision": "failure",
        "phase": phase,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "evidence": "repo-evidenced",
        "live_evidence_claimed": False,
        "traceback_tail": traceback.format_exception_only(type(exc), exc)[-1].strip(),
    }


def _markdown_lines(report: Dict[str, Any]) -> List[str]:
    lines = [
        f"# {report.get('kind', 'ReleaseDecisionReport')}",
        "",
        f"- ok: {str(bool(report.get('ok'))).lower()}",
        f"- decision: {report.get('decision', 'unknown')}",
        f"- evidence: {report.get('evidence', 'repo-evidenced')}",
        f"- live_evidence_claimed: {str(bool(report.get('live_evidence_claimed'))).lower()}",
    ]
    if report.get("kind") == FAILURE_KIND:
        lines.extend([
            f"- phase: {report.get('phase', '')}",
            f"- error_type: {report.get('error_type', '')}",
        ])
    else:
        findings = report.get("known_findings") if isinstance(report.get("known_findings"), dict) else {}
        lines.append(f"- blocking_findings: {findings.get('blocking', 0)}")
    return lines


def write_reports(out_dir: Path | str, report: Dict[str, Any], *, stem: str = "release-decision-report") -> Dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"{stem}.json"
    md_path = out / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text("\n".join(_markdown_lines(report)) + "\n", encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def run_release_decision_helper(
    *,
    source_gate_payload: Any,
    known_findings_payload: Any,
    out_dir: Path | str,
) -> Dict[str, Any]:
    try:
        report = build_release_decision_report(
            _as_dict(source_gate_payload, label="source_gate"),
            _as_dict(known_findings_payload, label="known_findings"),
        )
        paths = write_reports(out_dir, report)
    except Exception as exc:
        report = build_failure_report(exc)
        paths = write_reports(out_dir, report, stem="release-decision-failure")
    return {**report, "paths": paths}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an offline NoemaForge release decision report.")
    parser.add_argument("--source-gate", required=True, help="JSON string, JSON file path, or '-' for stdin")
    parser.add_argument("--known-findings", required=True, help="JSON string or JSON file path")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_release_decision_helper(
            source_gate_payload=_json_arg(args.source_gate),
            known_findings_payload=_json_arg(args.known_findings),
            out_dir=args.out_dir,
        )
    except Exception as exc:
        report = build_failure_report(exc)
        paths = write_reports(args.out_dir, report, stem="release-decision-failure")
        result = {**report, "paths": paths}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
