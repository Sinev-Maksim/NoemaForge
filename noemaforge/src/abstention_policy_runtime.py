#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/abstention_policy_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate AbstentionPolicy thresholds, actions and deterministic routing scenarios.
Inputs: noemaforge/configs/abstention-policy.json.
Outputs: JSON-compatible AbstentionPolicyValidationReport artifacts.
Side effects: None unless run as a CLI, which writes JSON to stdout.
Tests: noemaforge/tests/test_abstention_policy_runtime.py
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


VALIDATION_KIND = "AbstentionPolicyValidationReport"


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_policy(path: Path | str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _float_field(policy: Dict[str, Any], field: str, failures: List[str]) -> float:
    try:
        value = float(policy.get(field))
    except (TypeError, ValueError):
        failures.append(f"{field}_not_number")
        return 0.0
    if value < 0.0 or value > 1.0:
        failures.append(f"{field}_outside_0_1")
    return value


def _scenario_fixtures(policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    auto_route = float(policy.get("auto_route_min_confidence") or 0.8)
    clarify = float(policy.get("clarify_min_confidence") or 0.5)
    mid_confidence = min(auto_route - 0.01, max(clarify + 0.05, 0.55))
    low_confidence = max(0.0, clarify - 0.05)
    return [
        {
            "id": "route_low_risk_high_confidence",
            "route": {"confidence": min(1.0, auto_route + 0.05), "risk_level": "low"},
            "expected_action": "route",
        },
        {
            "id": "ask_when_confidence_needs_confirmation",
            "route": {"confidence": mid_confidence, "risk_level": "low"},
            "expected_action": "ask_clarification",
        },
        {
            "id": "defer_admin_when_confidence_too_low",
            "route": {"confidence": low_confidence, "risk_level": "low"},
            "expected_action": "defer_admin",
        },
        {
            "id": "ask_when_missing_context",
            "route": {"confidence": min(1.0, auto_route + 0.05), "missing_context": ["project path"]},
            "expected_action": "ask_clarification",
        },
        {
            "id": "defer_sr_when_ungrounded",
            "route": {"confidence": 0.95, "requires_grounding": True, "grounded": False},
            "expected_action": str(policy.get("ungrounded_action") or "defer_sr"),
        },
        {
            "id": "defer_ssr_when_high_risk",
            "route": {"confidence": 0.95, "risk_level": "high"},
            "expected_action": str(policy.get("high_risk_action") or "defer_ssr"),
        },
        {
            "id": "block_when_critical_risk",
            "route": {"confidence": 0.95, "risk_level": "critical"},
            "expected_action": str(policy.get("critical_risk_action") or "block"),
        },
        {
            "id": "block_when_unsafe",
            "route": {"confidence": 0.95, "safety_flags": ["unsafe_tool_request"]},
            "expected_action": str(policy.get("unsafe_action") or "block"),
        },
    ]


def validate_abstention_policy(policy: Dict[str, Any], *, policy_path: Path | str = "") -> Dict[str, Any]:
    failures: List[str] = []
    if not isinstance(policy, dict):
        return {
            "apiVersion": pac.API_VERSION,
            "kind": VALIDATION_KIND,
            "ok": False,
            "created_at": _nowz(),
            "policy_path": str(policy_path or ""),
            "failures": ["policy_not_object"],
            "metrics": {"scenario_total": 0, "scenario_passed": 0, "scenario_failed": 0},
            "scenario_results": [],
        }

    if policy.get("apiVersion") != pac.API_VERSION:
        failures.append("apiVersion_mismatch")
    if policy.get("kind") != "AbstentionPolicy":
        failures.append("kind_mismatch")

    auto_route = _float_field(policy, "auto_route_min_confidence", failures)
    clarify = _float_field(policy, "clarify_min_confidence", failures)
    if clarify > auto_route:
        failures.append("clarify_threshold_above_auto_route")

    actions = policy.get("actions") if isinstance(policy.get("actions"), dict) else {}
    missing_actions = sorted(pac.ABSTENTION_ACTIONS.difference(set(actions)))
    for action in missing_actions:
        failures.append(f"action_missing:{action}")

    for field in ["high_risk_action", "critical_risk_action", "ungrounded_action", "unsafe_action"]:
        action = str(policy.get(field) or "").strip()
        if action not in pac.ABSTENTION_ACTIONS:
            failures.append(f"{field}_invalid:{action}")

    scenario_results: List[Dict[str, Any]] = []
    for fixture in _scenario_fixtures(policy):
        decision = pac.decide_abstention(fixture["route"], policy)
        expected = str(fixture["expected_action"])
        actual = str(decision.get("action") or "")
        ok = actual == expected
        if not ok:
            failures.append(f"scenario_failed:{fixture['id']}:{actual}!={expected}")
        scenario_results.append(
            {
                "id": fixture["id"],
                "ok": ok,
                "expected_action": expected,
                "actual_action": actual,
                "decision": decision,
            }
        )

    scenario_failed = sum(1 for row in scenario_results if not row["ok"])
    return {
        "apiVersion": pac.API_VERSION,
        "kind": VALIDATION_KIND,
        "ok": not failures,
        "created_at": _nowz(),
        "policy_path": str(policy_path or ""),
        "failures": sorted(failures),
        "thresholds": {
            "auto_route_min_confidence": auto_route,
            "clarify_min_confidence": clarify,
        },
        "actions": {key: str(actions.get(key) or "") for key in sorted(pac.ABSTENTION_ACTIONS)},
        "metrics": {
            "scenario_total": len(scenario_results),
            "scenario_passed": len(scenario_results) - scenario_failed,
            "scenario_failed": scenario_failed,
            "missing_actions": len(missing_actions),
        },
        "scenario_results": scenario_results,
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate NoemaForge AbstentionPolicy behavior.")
    parser.add_argument("--project-root", default=str(_default_project_root()), help="Project root containing noemaforge/.")
    parser.add_argument(
        "--policy",
        default="noemaforge/configs/abstention-policy.json",
        help="Policy path, absolute or relative to project root.",
    )
    parser.add_argument("--summary", action="store_true", help="Emit a compact validation summary.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = Path(args.project_root).resolve()
    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = project_root / policy_path
    report = validate_abstention_policy(load_policy(policy_path), policy_path=policy_path)
    if args.summary:
        payload = {
            "apiVersion": report["apiVersion"],
            "kind": "AbstentionPolicyValidationSummary",
            "ok": report["ok"],
            "created_at": report["created_at"],
            "policy_path": report["policy_path"],
            "metrics": report["metrics"],
            "failures": report["failures"],
        }
    else:
        payload = report
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
