#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/intent_router_eval.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-18
Modified: 2026-05-25
Purpose: Evaluate Admin intent routing against a deterministic eval pack and emit per-route metrics.
Inputs: JSON eval-pack files and Admin natural-language route fixtures.
Outputs: JSON reports with pass/fail details and per-route metrics.
Side effects: Optional report file write when --out is provided.
Tests: noemaforge/tests/test_intent_router_eval.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import admin_runtime
import production_ai_contracts
from noemaforge_version import RUNTIME_VERSION
from platform_paths import DEFAULT_PATHS as _pp
DEFAULT_ROOT = _pp.root
DEFAULT_PACK = DEFAULT_ROOT / "configs" / "intent-router-eval-pack.json"


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def load_pack(path: Path) -> Dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("intent_router_eval_pack_not_object")
    obj.setdefault("cases", [])
    obj.setdefault("thresholds", {})
    return obj


def _metric_bucket(metrics: Dict[str, Any], key: str) -> Dict[str, Any]:
    by_route = metrics.setdefault("per_route", {})
    item = by_route.setdefault(key, {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0.0})
    return item


def evaluate_case(case: Dict[str, Any]) -> Dict[str, Any]:
    text = str(case.get("text") or "")
    route = admin_runtime.route_request(text)
    abstention = route.get("abstention") if isinstance(route.get("abstention"), dict) else production_ai_contracts.decide_abstention(route)
    expected_route = str(case.get("expected_route_id") or "")
    expected_intent = str(case.get("expected_intent") or "")
    expected_action = str(case.get("expected_abstention_action") or "")
    min_conf = float(case.get("min_confidence") or 0.0)

    checks: Dict[str, bool] = {}
    checks["route_id"] = not expected_route or str(route.get("id") or "") == expected_route
    checks["intent"] = not expected_intent or str(route.get("intent") or "") == expected_intent
    checks["abstention_action"] = not expected_action or str(abstention.get("action") or "") == expected_action
    checks["confidence"] = float(route.get("confidence") or 0.0) >= min_conf

    passed = all(checks.values())
    failures = [k for k, ok in checks.items() if not ok]
    return {
        "id": str(case.get("id") or ""),
        "text": text,
        "passed": passed,
        "failures": failures,
        "checks": checks,
        "expected": {
            "route_id": expected_route,
            "intent": expected_intent,
            "abstention_action": expected_action,
            "min_confidence": min_conf,
        },
        "actual": {
            "route_id": str(route.get("id") or ""),
            "intent": str(route.get("intent") or ""),
            "confidence": float(route.get("confidence") or 0.0),
            "abstention_action": str(abstention.get("action") or ""),
            "abstention_reason": str(abstention.get("reason") or ""),
        },
    }


def evaluate_pack(pack: Dict[str, Any], *, trace_id: str = "") -> Dict[str, Any]:
    tid = trace_id or production_ai_contracts.new_trace_id("intent-router-eval")
    cases = [c for c in (pack.get("cases") or []) if isinstance(c, dict)]
    results = [evaluate_case(case) for case in cases]
    passed = sum(1 for item in results if item.get("passed"))
    total = len(results)
    metrics: Dict[str, Any] = {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / max(1, total), 4),
        "per_route": {},
        "per_abstention_action": {},
    }

    for result in results:
        route_id = str((result.get("expected") or {}).get("route_id") or (result.get("actual") or {}).get("route_id") or "unknown")
        bucket = _metric_bucket(metrics, route_id)
        bucket["total"] += 1
        if result.get("passed"):
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1

        action = str((result.get("actual") or {}).get("abstention_action") or "unknown")
        action_bucket = metrics["per_abstention_action"].setdefault(action, {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0.0})
        action_bucket["total"] += 1
        if result.get("passed"):
            action_bucket["passed"] += 1
        else:
            action_bucket["failed"] += 1

    for group in [metrics["per_route"], metrics["per_abstention_action"]]:
        for item in group.values():
            item["pass_rate"] = round(int(item["passed"]) / max(1, int(item["total"])), 4)

    thresholds = dict(pack.get("thresholds") or {})
    min_overall = float(thresholds.get("overall_pass_rate_min") or 1.0)
    min_per_route = float(thresholds.get("per_route_pass_rate_min") or 1.0)
    threshold_failures = []
    if metrics["pass_rate"] < min_overall:
        threshold_failures.append("overall_pass_rate")
    for route_id, item in sorted(metrics["per_route"].items()):
        if float(item.get("pass_rate") or 0.0) < min_per_route:
            threshold_failures.append(f"per_route_pass_rate:{route_id}")

    return {
        "ok": not threshold_failures,
        "apiVersion": "noemaforge.intent-router-eval/v1",
        "kind": "IntentRouterEvalReport",
        "version": RUNTIME_VERSION,
        "trace_id": tid,
        "pack_id": str(pack.get("id") or ""),
        "thresholds": {
            "overall_pass_rate_min": min_overall,
            "per_route_pass_rate_min": min_per_route,
        },
        "threshold_failures": threshold_failures,
        "metrics": metrics,
        "results": results,
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="noemaforge intent-router-eval")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--pack", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--trace-id", default="")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    pack_path = Path(args.pack).resolve() if args.pack else root / "configs" / "intent-router-eval-pack.json"
    pack = load_pack(pack_path)
    report = evaluate_pack(pack, trace_id=args.trace_id)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json_dumps(report) + "\n", encoding="utf-8")
        report["report_path"] = str(out)
    print(json_dumps(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())


