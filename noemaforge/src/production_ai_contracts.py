#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/production_ai_contracts.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-18
Modified: 2026-05-18
Purpose: Provide executable production-AI lifecycle contracts for registry, evaluation gates and release evidence.
Inputs: In-memory contract dictionaries plus optional JSON/YAML contract files.
Outputs: Normalized dictionaries suitable for JSON/YAML persistence and audit logs.
Side effects: None unless the caller explicitly writes returned data.
Tests: noemaforge/tests/test_production_ai_contracts.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import re
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


API_VERSION = "noemaforge.production-ai/v1"
UNIFIED_REGISTRY_KIND = "UnifiedRegistry"
RELEASE_EVIDENCE_KIND = "ReleaseEvidence"
PRODUCTION_AI_CARD_SET_KIND = "ProductionAICardSet"
DATA_ERROR_LOOP_KIND = "DataCentricErrorLoopArtifact"
REGISTRY_PROMOTION_RESULT_KIND = "RegistryPromotionResult"
RAG_EVAL_REPORT_KIND = "RAGEvalReport"
TRAJECTORY_EVAL_REPORT_KIND = "TrajectoryEvalReport"

REGISTRY_KINDS = {
    "model",
    "prompt",
    "retriever",
    "reranker",
    "tool-policy",
    "pipeline",
    "persona",
    "task",
    "epoch",
    "eval-pack",
}

CHANGE_DOMAINS = {"code", "prompt", "model", "rag", "pipeline", "router"}
ROLLOUT_STATES = {"draft", "shadow", "canary", "promoted", "rolled_back"}
ACTIVE_REGISTRY_STATES = {"shadow", "canary", "promoted"}
ABSTENTION_ACTIONS = {"route", "ask_clarification", "defer_admin", "defer_sr", "defer_ssr", "block"}
ERROR_LOOP_SEVERITIES = {"info", "low", "medium", "high", "critical"}
DEFAULT_CHANGE_DOMAIN_BY_REGISTRY_KIND = {
    "model": "model",
    "prompt": "prompt",
    "retriever": "rag",
    "reranker": "rag",
    "tool-policy": "code",
    "pipeline": "pipeline",
    "persona": "prompt",
    "task": "pipeline",
    "epoch": "model",
    "eval-pack": "pipeline",
}
CARD_KINDS_BY_REGISTRY_KIND = {
    "model": "ModelCard",
    "prompt": "PromptCard",
    "pipeline": "PipelineCard",
    "epoch": "EpochCard",
    "tool-policy": "ToolPolicyCard",
}
CARD_KINDS = set(CARD_KINDS_BY_REGISTRY_KIND.values())

DEFAULT_REQUIRED_CHECKS = {
    "code": ["unit_tests", "static_contract_scan"],
    "prompt": ["prompt_eval", "safety_eval"],
    "model": ["model_eval", "safety_eval"],
    "rag": ["retrieval_hit_rate", "citation_coverage", "groundedness", "answer_helpfulness"],
    "pipeline": ["pipeline_eval", "rollback_plan"],
    "router": ["intent_router_eval", "per_route_metrics"],
}

DEFAULT_ABSTENTION_POLICY = {
    "auto_route_min_confidence": 0.8,
    "clarify_min_confidence": 0.5,
    "high_risk_action": "defer_ssr",
    "critical_risk_action": "block",
    "ungrounded_action": "defer_sr",
    "unsafe_action": "block",
}

DEFAULT_RAG_EVAL_THRESHOLDS = {
    "retrieval_hit_rate_min": 1.0,
    "citation_coverage_min": 1.0,
    "groundedness_min": 1.0,
    "answer_helpfulness_min": 1.0,
}

SAFE_TRAJECTORY_FINAL_STATES = {
    "completed",
    "completed_budget_exhausted",
    "completed_time_exhausted",
    "stopped_by_operator",
    "no_further_improvement_found",
    "blocked_by_safety_gate",
    "waiting_for_operator_approval",
}

DEFAULT_TRAJECTORY_THRESHOLDS = {
    "step_success_rate_min": 1.0,
    "artifact_coverage_min": 1.0,
    "max_safety_flags": 0,
    "require_budget_compliance": True,
    "require_safe_final_state": True,
}

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,127}$")


def _nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_trace_id(prefix: str = "nf") -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(prefix or "nf")).strip(".-") or "nf"
    return f"{clean}-{uuid.uuid4().hex[:20]}"


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _clean_id(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field}_missing")
    if not _SAFE_ID_RE.match(text):
        raise ValueError(f"{field}_unsafe:{text}")
    return text


def _slug(value: Any, *, prefix: str = "item", limit: int = 96) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip(".-")
    text = text[:limit].strip(".-")
    return text or prefix


def registry_key(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def normalize_registry_entry(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("registry_entry_not_object")

    kind = _clean_id(raw.get("kind"), "kind")
    if kind not in REGISTRY_KINDS:
        raise ValueError(f"registry_kind_unknown:{kind}")

    entry = {
        "kind": kind,
        "id": _clean_id(raw.get("id"), "id"),
        "version": _clean_id(raw.get("version"), "version"),
        "status": str(raw.get("status") or "draft").strip() or "draft",
        "channels": sorted({_clean_id(x, "channel") for x in _as_list(raw.get("channels"))}),
        "digest": str(raw.get("digest") or "").strip(),
        "refs": sorted({_clean_id(x, "ref") for x in _as_list(raw.get("refs"))}),
        "eval_pack_refs": sorted({_clean_id(x, "eval_pack_ref") for x in _as_list(raw.get("eval_pack_refs"))}),
        "metadata": dict(raw.get("metadata") or {}),
    }
    if entry["status"] not in ROLLOUT_STATES:
        raise ValueError(f"registry_status_unknown:{entry['status']}")
    if not entry["channels"]:
        entry["channels"] = ["local"]
    return entry


def normalize_registry(doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = copy.deepcopy(doc or {})
    entries = [normalize_registry_entry(x) for x in raw.get("entries") or []]

    seen = set()
    for entry in entries:
        key = registry_key(entry)
        if key in seen:
            raise ValueError(f"registry_duplicate:{key}")
        seen.add(key)

    return {
        "apiVersion": str(raw.get("apiVersion") or API_VERSION),
        "kind": str(raw.get("kind") or UNIFIED_REGISTRY_KIND),
        "updated_at": str(raw.get("updated_at") or _nowz()),
        "entries": sorted(entries, key=registry_key),
    }


def registry_index(registry: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    normalized = normalize_registry(registry)
    return {registry_key(entry): entry for entry in normalized["entries"]}


def upsert_registry_entry(registry: Dict[str, Any], entry: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_registry(registry)
    new_entry = normalize_registry_entry(entry)
    key = registry_key(new_entry)
    kept = [x for x in normalized["entries"] if registry_key(x) != key]
    kept.append(new_entry)
    normalized["entries"] = sorted(kept, key=registry_key)
    normalized["updated_at"] = _nowz()
    return normalized


def select_registry_entries(
    registry: Dict[str, Any],
    *,
    kind: str = "",
    item_id: str = "",
    channel: str = "",
    status: str = "",
) -> List[Dict[str, Any]]:
    selected = []
    for entry in normalize_registry(registry)["entries"]:
        if kind and entry["kind"] != kind:
            continue
        if item_id and entry["id"] != item_id:
            continue
        if channel and channel not in entry.get("channels", []):
            continue
        if status and entry["status"] != status:
            continue
        selected.append(entry)
    return selected


def active_registry_refs(registry: Dict[str, Any], channel: str = "stable") -> List[str]:
    refs = []
    for entry in select_registry_entries(registry, channel=channel):
        if entry["status"] in ACTIVE_REGISTRY_STATES:
            refs.append(registry_key(entry))
    return sorted(refs)


def load_contract_doc(path: str) -> Dict[str, Any]:
    suffix = os.path.splitext(path)[1].lower()
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if suffix == ".json":
        obj = json.loads(text)
    else:
        if yaml is None:
            raise RuntimeError("python3-yaml is required for YAML contract files")
        obj = yaml.safe_load(text) or {}
    if not isinstance(obj, dict):
        raise ValueError("contract_doc_not_object")
    return obj


def _check_passed(check: Dict[str, Any]) -> Tuple[bool, str]:
    status = str(check.get("status") or "").strip().lower()
    if status in {"fail", "failed", "error", "blocked"}:
        return False, f"check_failed:{check.get('id')}"
    if "score" in check and "threshold" in check:
        try:
            score = float(check.get("score"))
            threshold = float(check.get("threshold"))
        except Exception:
            return False, f"check_score_invalid:{check.get('id')}"
        if score >= threshold:
            return True, ""
        return False, f"check_below_threshold:{check.get('id')}"
    if status in {"pass", "passed", "ok"}:
        return True, ""
    return False, f"check_status_unknown:{check.get('id')}"


def evaluate_gate(change: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
    change_id = _clean_id(change.get("change_id"), "change_id")
    domain = _clean_id(change.get("domain"), "domain")
    if domain not in CHANGE_DOMAINS:
        raise ValueError(f"change_domain_unknown:{domain}")

    required = list(change.get("required_checks") or DEFAULT_REQUIRED_CHECKS[domain])
    required = [_clean_id(x, "required_check") for x in required]

    checks_by_id: Dict[str, Dict[str, Any]] = {}
    for raw in evidence.get("checks") or []:
        if not isinstance(raw, dict):
            continue
        check_id = str(raw.get("id") or "").strip()
        if check_id:
            checks_by_id[check_id] = dict(raw)

    failures = []
    passed = []
    for check_id in required:
        check = checks_by_id.get(check_id)
        if check is None:
            failures.append(f"check_missing:{check_id}")
            continue
        ok, reason = _check_passed(check)
        if ok:
            passed.append(check_id)
        else:
            failures.append(reason)

    warnings = []
    if not evidence.get("artifact_uri"):
        warnings.append("artifact_uri_missing")
    if not evidence.get("run_at"):
        warnings.append("run_at_missing")

    ok = not failures
    return {
        "apiVersion": API_VERSION,
        "kind": "EvaluationGateResult",
        "change_id": change_id,
        "domain": domain,
        "decision": "allow" if ok else "block",
        "ok": ok,
        "required_checks": required,
        "passed_checks": sorted(passed),
        "failures": failures,
        "warnings": warnings,
        "evidence": {
            "artifact_uri": str(evidence.get("artifact_uri") or ""),
            "run_at": str(evidence.get("run_at") or ""),
        },
    }


def rollout_transition(current: str, requested: str, gate_result: Dict[str, Any], *, approved: bool = False) -> Dict[str, Any]:
    cur = str(current or "draft").strip()
    req = str(requested or "").strip()
    if cur not in ROLLOUT_STATES:
        raise ValueError(f"rollout_state_unknown:{cur}")
    if req not in ROLLOUT_STATES:
        raise ValueError(f"rollout_state_unknown:{req}")

    gate_ok = bool(gate_result.get("ok"))
    failures = []
    if req == "rolled_back":
        decision = "allow"
    elif req == cur:
        decision = "allow"
    elif req == "shadow":
        decision = "allow" if gate_ok else "block"
    elif req == "canary":
        decision = "allow" if cur in {"shadow", "canary"} and gate_ok else "block"
    elif req == "promoted":
        decision = "allow" if cur == "canary" and gate_ok and approved else "block"
        if not approved:
            failures.append("operator_approval_missing")
    else:
        decision = "block"

    if not gate_ok and req != "rolled_back":
        failures.append("evaluation_gate_not_passing")
    if decision == "block" and not failures:
        failures.append(f"rollout_transition_not_allowed:{cur}->{req}")

    return {
        "apiVersion": API_VERSION,
        "kind": "RolloutDecision",
        "from": cur,
        "to": req,
        "decision": decision,
        "ok": decision == "allow",
        "approved": bool(approved),
        "failures": failures,
    }


def decide_abstention(route: Dict[str, Any], policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    pol = dict(DEFAULT_ABSTENTION_POLICY)
    pol.update(policy or {})
    confidence = float(route.get("confidence") or 0.0)
    risk = str(route.get("risk_level") or route.get("risk") or "low").strip().lower()
    missing = [str(x) for x in _as_list(route.get("missing_context")) if str(x).strip()]
    safety_flags = {str(x).strip().lower() for x in _as_list(route.get("safety_flags")) if str(x).strip()}
    grounded = route.get("grounded")
    requires_grounding = bool(route.get("requires_grounding", False))

    action = "route"
    reason = "confidence_sufficient"
    reviewers: List[str] = []
    questions: List[str] = []

    if "unsafe_tool_request" in safety_flags or "policy_violation" in safety_flags:
        action = str(pol.get("unsafe_action") or "block")
        reason = "unsafe_request"
    elif risk == "critical":
        action = str(pol.get("critical_risk_action") or "block")
        reason = "critical_risk"
    elif risk == "high":
        action = str(pol.get("high_risk_action") or "defer_ssr")
        reason = "high_risk"
    elif requires_grounding and grounded is False:
        action = str(pol.get("ungrounded_action") or "defer_sr")
        reason = "ungrounded_answer"
    elif missing:
        action = "ask_clarification"
        reason = "missing_context"
        questions = [f"Provide {item}." for item in missing]
    elif confidence < float(pol.get("clarify_min_confidence") or 0.5):
        action = "defer_admin"
        reason = "confidence_too_low"
    elif confidence < float(pol.get("auto_route_min_confidence") or 0.8):
        action = "ask_clarification"
        reason = "confidence_needs_confirmation"
        questions = ["Confirm the intended route or provide more context."]

    if action not in ABSTENTION_ACTIONS:
        action = "block"
        reason = "invalid_policy_action"
    if action == "defer_admin":
        reviewers = ["Admin"]
    elif action == "defer_sr":
        reviewers = ["SR"]
    elif action == "defer_ssr":
        reviewers = ["SR", "SSR"]

    return {
        "apiVersion": API_VERSION,
        "kind": "AbstentionDecision",
        "action": action,
        "ok_to_route": action == "route",
        "reason": reason,
        "confidence": confidence,
        "risk_level": risk,
        "reviewers_required": reviewers,
        "questions": questions,
        "missing_context": missing,
        "safety_flags": sorted(safety_flags),
    }


def build_release_evidence(
    change: Dict[str, Any],
    gate_result: Dict[str, Any],
    rollout: Dict[str, Any],
    *,
    registry_refs: Optional[Sequence[str]] = None,
    trace_id: str = "",
    actor: str = "operator",
) -> Dict[str, Any]:
    change_id = _clean_id(change.get("change_id"), "change_id")
    tid = str(trace_id or change.get("trace_id") or new_trace_id("release")).strip()
    refs = sorted({_clean_id(x, "registry_ref") for x in (registry_refs or [])})
    return {
        "apiVersion": API_VERSION,
        "kind": RELEASE_EVIDENCE_KIND,
        "created_at": _nowz(),
        "trace_id": tid,
        "actor": str(actor or "operator"),
        "change": {
            "change_id": change_id,
            "domain": str(change.get("domain") or ""),
            "summary": str(change.get("summary") or ""),
        },
        "gate": {
            "decision": str(gate_result.get("decision") or ""),
            "ok": bool(gate_result.get("ok")),
            "failures": list(gate_result.get("failures") or []),
            "evidence": dict(gate_result.get("evidence") or {}),
        },
        "rollout": {
            "from": str(rollout.get("from") or ""),
            "to": str(rollout.get("to") or ""),
            "decision": str(rollout.get("decision") or ""),
            "ok": bool(rollout.get("ok")),
        },
        "registry_refs": refs,
    }


def registry_entry_change_domain(entry: Dict[str, Any]) -> str:
    normalized = normalize_registry_entry(entry)
    metadata = dict(normalized.get("metadata") or {})
    explicit = str(metadata.get("change_domain") or "").strip().lower()
    if explicit in CHANGE_DOMAINS:
        return explicit
    domains = [str(x).strip().lower() for x in _as_list(metadata.get("domains"))]
    for domain in ["router", "rag", "pipeline", "model", "prompt", "code"]:
        if domain in domains:
            return domain
    if normalized["kind"] == "prompt" and any(x in normalized["id"].lower() for x in ["route", "routing", "router"]):
        return "router"
    return DEFAULT_CHANGE_DOMAIN_BY_REGISTRY_KIND[normalized["kind"]]


def build_registry_release_evidence(
    entry: Dict[str, Any],
    evaluation_evidence: Dict[str, Any],
    *,
    requested_status: str = "promoted",
    approved: bool = False,
    registry_refs: Optional[Sequence[str]] = None,
    trace_id: str = "",
    actor: str = "operator",
) -> Dict[str, Any]:
    normalized = normalize_registry_entry(entry)
    requested = str(requested_status or "promoted").strip()
    if requested not in ROLLOUT_STATES:
        raise ValueError(f"rollout_state_unknown:{requested}")
    domain = registry_entry_change_domain(normalized)
    required_checks = _clean_text_list((normalized.get("metadata") or {}).get("promotion_required_checks"))
    change = {
        "change_id": registry_key(normalized),
        "domain": domain,
        "summary": str((normalized.get("metadata") or {}).get("summary") or f"Promote {registry_key(normalized)} to {requested}."),
    }
    if required_checks:
        change["required_checks"] = required_checks
    gate = evaluate_gate(change, evaluation_evidence)
    rollout = rollout_transition(normalized["status"], requested, gate, approved=approved)
    refs = list(registry_refs or [])
    refs.append(registry_key(normalized))
    return build_release_evidence(
        change,
        gate,
        rollout,
        registry_refs=refs,
        trace_id=trace_id,
        actor=actor,
    )


def promote_registry_entry(
    registry: Dict[str, Any],
    entry_ref: str,
    evaluation_evidence: Dict[str, Any],
    *,
    requested_status: str = "promoted",
    approved: bool = False,
    trace_id: str = "",
    actor: str = "operator",
) -> Dict[str, Any]:
    normalized_registry = normalize_registry(registry)
    index = registry_index(normalized_registry)
    key = _clean_id(entry_ref, "registry_ref")
    entry = index.get(key)
    if entry is None:
        raise ValueError(f"registry_ref_unknown:{key}")

    release_evidence = build_registry_release_evidence(
        entry,
        evaluation_evidence,
        requested_status=requested_status,
        approved=approved,
        registry_refs=active_registry_refs(normalized_registry),
        trace_id=trace_id,
        actor=actor,
    )
    gate_ok = bool((release_evidence.get("gate") or {}).get("ok"))
    rollout_ok = bool((release_evidence.get("rollout") or {}).get("ok"))
    ok = gate_ok and rollout_ok
    updated_registry = normalized_registry
    updated_entry = dict(entry)
    if ok:
        updated_entry["status"] = str(requested_status or "promoted")
        metadata = dict(updated_entry.get("metadata") or {})
        metadata["last_release_evidence_trace_id"] = str(release_evidence.get("trace_id") or "")
        metadata["last_release_evidence_created_at"] = str(release_evidence.get("created_at") or "")
        updated_entry["metadata"] = metadata
        updated_registry = upsert_registry_entry(normalized_registry, updated_entry)

    return {
        "apiVersion": API_VERSION,
        "kind": REGISTRY_PROMOTION_RESULT_KIND,
        "ok": ok,
        "entry_ref": key,
        "requested_status": str(requested_status or "promoted"),
        "entry": updated_entry if ok else entry,
        "registry": updated_registry,
        "release_evidence": release_evidence,
        "failures": list((release_evidence.get("gate") or {}).get("failures") or [])
        + list((release_evidence.get("rollout") or {}).get("failures") or []),
    }


def _clean_text_list(value: Any) -> List[str]:
    return sorted({str(x).strip() for x in _as_list(value) if str(x).strip()})


def normalize_artifact_card(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("artifact_card_not_object")

    card_kind = _clean_id(raw.get("kind"), "card_kind")
    if card_kind not in CARD_KINDS:
        raise ValueError(f"artifact_card_kind_unknown:{card_kind}")

    artifact = raw.get("artifact")
    if not isinstance(artifact, dict):
        raise ValueError("artifact_card_artifact_missing")
    entry = normalize_registry_entry(artifact)
    expected = CARD_KINDS_BY_REGISTRY_KIND.get(entry["kind"])
    if expected != card_kind:
        raise ValueError(f"artifact_card_kind_mismatch:{card_kind}!={expected}")

    card_id = _clean_id(raw.get("card_id") or registry_key(entry), "card_id")
    return {
        "apiVersion": str(raw.get("apiVersion") or API_VERSION),
        "kind": card_kind,
        "card_id": card_id,
        "created_at": str(raw.get("created_at") or _nowz()),
        "trace_id": str(raw.get("trace_id") or ""),
        "artifact": {
            "kind": entry["kind"],
            "id": entry["id"],
            "version": entry["version"],
            "status": entry["status"],
            "channels": list(entry.get("channels") or []),
            "digest": str(entry.get("digest") or ""),
            "refs": list(entry.get("refs") or []),
            "eval_pack_refs": list(entry.get("eval_pack_refs") or []),
        },
        "summary": str(raw.get("summary") or ""),
        "ownership": dict(raw.get("ownership") or {}),
        "intended_use": _clean_text_list(raw.get("intended_use")),
        "limitations": _clean_text_list(raw.get("limitations")),
        "safety": dict(raw.get("safety") or {}),
        "evaluation": dict(raw.get("evaluation") or {}),
        "rollout": dict(raw.get("rollout") or {}),
        "rollback": dict(raw.get("rollback") or {}),
        "release_evidence_refs": _clean_text_list(raw.get("release_evidence_refs")),
    }


def build_artifact_card(
    entry: Dict[str, Any],
    *,
    release_evidence: Optional[Dict[str, Any]] = None,
    trace_id: str = "",
) -> Dict[str, Any]:
    registry_entry = normalize_registry_entry(entry)
    card_kind = CARD_KINDS_BY_REGISTRY_KIND.get(registry_entry["kind"])
    if not card_kind:
        raise ValueError(f"artifact_card_registry_kind_unsupported:{registry_entry['kind']}")

    metadata = dict(registry_entry.get("metadata") or {})
    evidence = dict(release_evidence or {})
    gate = dict(evidence.get("gate") or {})
    rollout = dict(evidence.get("rollout") or {})
    evidence_refs: List[str] = []
    if evidence.get("trace_id"):
        evidence_refs.append(f"trace:{evidence.get('trace_id')}")
    gate_evidence = gate.get("evidence") if isinstance(gate.get("evidence"), dict) else {}
    if gate_evidence and gate_evidence.get("artifact_uri"):
        evidence_refs.append(str(gate_evidence.get("artifact_uri")))

    summary = str(metadata.get("summary") or metadata.get("description") or "")
    rollback_plan = str(metadata.get("rollback_plan") or "")
    if not rollback_plan and rollout:
        rollback_plan = "Use rollout_transition(current, 'rolled_back', gate_result) and restore prior registry ref."

    return normalize_artifact_card(
        {
            "apiVersion": API_VERSION,
            "kind": card_kind,
            "card_id": registry_key(registry_entry),
            "trace_id": trace_id or str(evidence.get("trace_id") or ""),
            "artifact": registry_entry,
            "summary": summary,
            "ownership": {
                "owner": str(metadata.get("owner") or "Admin"),
                "reviewers": _clean_text_list(metadata.get("reviewers")),
            },
            "intended_use": metadata.get("intended_use") or [],
            "limitations": metadata.get("limitations") or [],
            "safety": {
                "risk_level": str(metadata.get("risk_level") or "not_recorded"),
                "policy_refs": _clean_text_list(metadata.get("policy_refs")),
            },
            "evaluation": {
                "eval_pack_refs": list(registry_entry.get("eval_pack_refs") or []),
                "latest_gate": gate,
            },
            "rollout": {
                "status": registry_entry["status"],
                "channels": list(registry_entry.get("channels") or []),
                "latest_rollout": rollout,
            },
            "rollback": {
                "available": bool(rollback_plan or registry_entry["status"] in ACTIVE_REGISTRY_STATES),
                "plan": rollback_plan,
            },
            "release_evidence_refs": evidence_refs,
        }
    )


def build_registry_cards(
    registry: Dict[str, Any],
    *,
    release_evidence_by_ref: Optional[Dict[str, Dict[str, Any]]] = None,
    trace_id: str = "",
) -> Dict[str, Any]:
    evidence_index = release_evidence_by_ref or {}
    cards = []
    skipped = []
    for entry in normalize_registry(registry)["entries"]:
        key = registry_key(entry)
        if entry["kind"] not in CARD_KINDS_BY_REGISTRY_KIND:
            skipped.append(key)
            continue
        cards.append(build_artifact_card(entry, release_evidence=evidence_index.get(key), trace_id=trace_id))

    produced_kinds = {card["kind"] for card in cards}
    return {
        "apiVersion": API_VERSION,
        "kind": PRODUCTION_AI_CARD_SET_KIND,
        "created_at": _nowz(),
        "trace_id": str(trace_id or ""),
        "cards": sorted(cards, key=lambda item: item["card_id"]),
        "coverage": {
            "required_card_kinds": sorted(CARD_KINDS),
            "present_card_kinds": sorted(produced_kinds),
            "missing_card_kinds": sorted(CARD_KINDS - produced_kinds),
            "skipped_registry_refs": sorted(skipped),
        },
    }


def _infer_error_domain(observation: Dict[str, Any]) -> str:
    explicit = str(observation.get("domain") or "").strip().lower()
    if explicit in CHANGE_DOMAINS:
        return explicit
    component = str(observation.get("component") or "").strip().lower()
    if any(x in component for x in ["router", "route", "intent"]):
        return "router"
    if any(x in component for x in ["rag", "retriev", "ground", "citation", "knowledge"]):
        return "rag"
    if any(x in component for x in ["model", "selection", "evolution"]):
        return "model"
    if "prompt" in component:
        return "prompt"
    if any(x in component for x in ["pipeline", "flow", "team"]):
        return "pipeline"
    return "code"


def _infer_error_type(observation: Dict[str, Any], domain: str) -> str:
    explicit = str(observation.get("error_type") or "").strip()
    if explicit:
        return _slug(explicit, prefix="error_type")

    expected = observation.get("expected") if isinstance(observation.get("expected"), dict) else {}
    actual = observation.get("actual") if isinstance(observation.get("actual"), dict) else {}
    if domain == "router" and str(expected.get("route_id") or expected.get("id") or "") != str(actual.get("route_id") or actual.get("id") or ""):
        return "intent_routing_mismatch"
    if domain == "router" and str(expected.get("abstention_action") or "") != str(actual.get("abstention_action") or ""):
        return "abstention_action_mismatch"
    if domain == "rag" and (observation.get("grounded") is False or actual.get("grounded") is False):
        return "groundedness_failure"
    if domain == "pipeline" and str(actual.get("status") or "").lower() in {"failed", "error", "blocked"}:
        return "pipeline_execution_failure"
    if domain == "model" and str(actual.get("decision") or "").lower() in {"failed", "block", "rejected"}:
        return "model_eval_failure"
    return "behavioral_regression"


def classify_error_observation(observation: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(observation, dict):
        raise ValueError("error_observation_not_object")

    component = _slug(observation.get("component") or "general", prefix="component")
    domain = _infer_error_domain(observation)
    error_type = _infer_error_type(observation, domain)
    severity = str(observation.get("severity") or "medium").strip().lower()
    if severity not in ERROR_LOOP_SEVERITIES:
        severity = "medium"

    source_defect = bool(observation.get("source_defect", False))
    safety_flags = {str(x).strip().lower() for x in _as_list(observation.get("safety_flags")) if str(x).strip()}
    review_required = severity in {"high", "critical"} or source_defect or bool(safety_flags)
    reviewers = ["SR"] if review_required else []
    if severity == "critical" or safety_flags:
        reviewers = ["SR", "SSR"]

    return {
        "apiVersion": API_VERSION,
        "kind": "ErrorTaxonomyEntry",
        "component": component,
        "domain": domain,
        "error_type": error_type,
        "severity": severity,
        "source_defect": source_defect,
        "safety_flags": sorted(safety_flags),
        "review_required": review_required,
        "reviewers_required": reviewers,
        "labels": sorted({domain, component, error_type, severity}),
    }


def build_regression_case_from_error(observation: Dict[str, Any], taxonomy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    tax = dict(taxonomy or classify_error_observation(observation))
    input_payload = observation.get("input") if isinstance(observation.get("input"), dict) else {}
    expected_payload = observation.get("expected") if isinstance(observation.get("expected"), dict) else {}
    error_id = str(observation.get("error_id") or new_trace_id("error")).strip()
    case_id = _slug(observation.get("regression_case_id") or f"regr-{tax.get('component')}-{tax.get('error_type')}-{error_id}", prefix="regr")
    acceptance_policy = observation.get("acceptance_policy") if isinstance(observation.get("acceptance_policy"), dict) else {}
    if not acceptance_policy:
        acceptance_policy = {"must_match_expected": True, "prevent_regression": True}

    return {
        "regression_case_id": case_id,
        "source_error_id": error_id,
        "component": str(tax.get("component") or "general"),
        "error_type": str(tax.get("error_type") or "behavioral_regression"),
        "input_payload": dict(input_payload),
        "expected_payload": dict(expected_payload),
        "acceptance_policy": dict(acceptance_policy),
        "case_status": "active",
    }


def build_eval_case_from_error(observation: Dict[str, Any], taxonomy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    tax = dict(taxonomy or classify_error_observation(observation))
    regression = build_regression_case_from_error(observation, tax)
    expected = observation.get("expected") if isinstance(observation.get("expected"), dict) else {}
    input_payload = observation.get("input") if isinstance(observation.get("input"), dict) else {}
    text = str(input_payload.get("text") or observation.get("text") or "")
    if str(tax.get("domain")) == "router" and text:
        case = {
            "id": regression["regression_case_id"],
            "text": text,
            "expected_route_id": str(expected.get("route_id") or expected.get("id") or ""),
            "expected_intent": str(expected.get("intent") or ""),
            "expected_abstention_action": str(expected.get("abstention_action") or "route"),
            "min_confidence": float(expected.get("min_confidence") or observation.get("min_confidence") or 0.0),
        }
        return {"kind": "intent_router", "target_pack_kind": "IntentRouterEvalPack", "case": case}

    goal = str(input_payload.get("goal") or input_payload.get("request") or text or observation.get("summary") or "")
    case = {
        "id": regression["regression_case_id"],
        "goal": goal,
        "constraints": dict(input_payload.get("constraints") or {}),
        "rubric": dict(expected.get("rubric") or {"expected": expected}),
    }
    return {"kind": "flow", "target_pack_kind": "FlowEvalSuite", "suite": "smoke", "flow_id": str(tax.get("component") or "general"), "case": case}


def build_data_error_loop_artifact(
    observation: Dict[str, Any],
    *,
    correction: Optional[Dict[str, Any]] = None,
    trace_id: str = "",
) -> Dict[str, Any]:
    tax = classify_error_observation(observation)
    regression = build_regression_case_from_error(observation, tax)
    eval_case = build_eval_case_from_error(observation, tax)
    error_id = regression["source_error_id"]
    tid = str(trace_id or observation.get("trace_id") or new_trace_id("error-loop")).strip()
    fix = dict(correction or {})
    if not fix:
        fix = {
            "status": "candidate",
            "summary": f"Correct {tax['component']} {tax['error_type']} and keep {regression['regression_case_id']} passing.",
            "suggested_refs": _clean_text_list(observation.get("suggested_refs")),
        }

    task_id = _slug(f"task-{tax['component']}-{tax['error_type']}-{error_id}", prefix="task")
    task_item = {
        "id": task_id,
        "title": f"Fix {tax['component']} {tax['error_type']}",
        "priority": "P0" if tax["severity"] in {"high", "critical"} else "P1",
        "labels": list(tax["labels"]),
        "evidence_refs": [f"error:{error_id}", f"trace:{tid}"],
    }

    return {
        "apiVersion": API_VERSION,
        "kind": DATA_ERROR_LOOP_KIND,
        "created_at": _nowz(),
        "trace_id": tid,
        "error": {
            "error_id": error_id,
            "component": tax["component"],
            "domain": tax["domain"],
            "error_type": tax["error_type"],
            "severity": tax["severity"],
            "source_address": dict(observation.get("source_address") or {}),
            "input": dict(observation.get("input") or {}),
            "expected": dict(observation.get("expected") or {}),
            "actual": dict(observation.get("actual") or {}),
        },
        "taxonomy": tax,
        "regression_case": regression,
        "eval_case": eval_case,
        "task_item": task_item,
        "fix_candidate": fix,
        "review": {
            "required": bool(tax["review_required"]),
            "reviewers_required": list(tax["reviewers_required"]),
        },
    }


def append_error_loop_eval_case(eval_pack: Dict[str, Any], artifact: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(eval_pack, dict):
        raise ValueError("eval_pack_not_object")
    if not isinstance(artifact, dict) or artifact.get("kind") != DATA_ERROR_LOOP_KIND:
        raise ValueError("data_error_loop_artifact_required")

    updated = copy.deepcopy(eval_pack)
    eval_case = artifact.get("eval_case") if isinstance(artifact.get("eval_case"), dict) else {}
    case = eval_case.get("case") if isinstance(eval_case.get("case"), dict) else {}
    case_id = str(case.get("id") or "").strip()
    if not case_id:
        raise ValueError("eval_case_id_missing")

    pack_kind = str(updated.get("kind") or "")
    target_kind = str(eval_case.get("target_pack_kind") or "")
    if pack_kind != target_kind:
        raise ValueError(f"eval_pack_kind_mismatch:{pack_kind}!={target_kind}")

    if pack_kind == "IntentRouterEvalPack":
        cases = [dict(x) for x in (updated.get("cases") or []) if isinstance(x, dict)]
        if not any(str(x.get("id") or "") == case_id for x in cases):
            cases.append(dict(case))
        updated["cases"] = cases
    elif pack_kind == "FlowEvalSuite":
        suite_name = str(eval_case.get("suite") or "smoke")
        flow_id = str(eval_case.get("flow_id") or "general")
        suites = dict(updated.get("suites") or {})
        suite = dict(suites.get(suite_name) or {})
        case_groups = dict(suite.get("cases") or {})
        group = [dict(x) for x in (case_groups.get(flow_id) or []) if isinstance(x, dict)]
        if not any(str(x.get("id") or "") == case_id for x in group):
            group.append(dict(case))
        case_groups[flow_id] = group
        suite["cases"] = case_groups
        suites[suite_name] = suite
        updated["suites"] = suites
    else:
        raise ValueError(f"eval_pack_kind_unsupported:{pack_kind}")

    sources = [str(x) for x in _as_list(updated.get("error_loop_sources")) if str(x).strip()]
    error_id = str(((artifact.get("error") or {}).get("error_id")) or "")
    if error_id and error_id not in sources:
        sources.append(error_id)
    updated["error_loop_sources"] = sorted(sources)
    return updated


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _extract_ref_list(value: Any) -> List[str]:
    refs: List[str] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            ref = item.get("source_ref") or item.get("ref") or item.get("path") or item.get("source_path") or item.get("id")
        else:
            ref = item
        text = str(ref or "").strip()
        if text:
            refs.append(text)
    return sorted(set(refs))


def _has_expected_ref(expected_refs: Sequence[str], actual_refs: Sequence[str]) -> bool:
    if not expected_refs:
        return bool(actual_refs)
    actual = {str(x).strip().lower() for x in actual_refs if str(x).strip()}
    for ref in expected_refs:
        needle = str(ref).strip().lower()
        if needle in actual:
            return True
        if any(needle and needle in item for item in actual):
            return True
    return False


def _answer_has_terms(answer: Any, terms: Sequence[str]) -> bool:
    text = _norm_text(answer)
    if not terms:
        return bool(text)
    return all(_norm_text(term) in text for term in terms)


def evaluate_rag_eval_cases(
    cases: Sequence[Dict[str, Any]],
    results: Sequence[Dict[str, Any]],
    *,
    thresholds: Optional[Dict[str, Any]] = None,
    trace_id: str = "",
    pack_id: str = "",
) -> Dict[str, Any]:
    tid = str(trace_id or new_trace_id("rag-eval"))
    pol = dict(DEFAULT_RAG_EVAL_THRESHOLDS)
    pol.update(thresholds or {})
    result_by_id = {str(item.get("case_id") or item.get("id") or ""): item for item in results if isinstance(item, dict)}
    rows: List[Dict[str, Any]] = []
    totals = {
        "retrieval_hit": 0,
        "citation_covered": 0,
        "grounded": 0,
        "helpful": 0,
    }
    normalized_cases = [case for case in cases if isinstance(case, dict)]

    for case in normalized_cases:
        case_id = str(case.get("id") or "").strip()
        result = result_by_id.get(case_id, {})
        expected_refs = _extract_ref_list(case.get("expected_source_refs") or case.get("expected_refs"))
        retrieved_refs = _extract_ref_list(
            result.get("retrieved_refs")
            or result.get("source_refs")
            or result.get("retrieved_source_refs")
            or result.get("sources")
        )
        citation_refs = _extract_ref_list(result.get("citations") or result.get("citation_refs"))
        answer = result.get("answer") or result.get("text") or ""
        expected_terms = [str(x) for x in _as_list(case.get("expected_answer_terms")) if str(x).strip()]

        retrieval_hit = _has_expected_ref(expected_refs, retrieved_refs)
        citation_covered = _has_expected_ref(expected_refs, citation_refs)
        grounded = bool(result.get("grounded")) and (not expected_refs or bool(citation_refs))
        helpful = _answer_has_terms(answer, expected_terms)
        checks = {
            "retrieval_hit": retrieval_hit,
            "citation_covered": citation_covered,
            "grounded": grounded,
            "helpful": helpful,
        }
        for key, ok in checks.items():
            totals[key] += 1 if ok else 0
        rows.append(
            {
                "id": case_id,
                "query": str(case.get("query") or ""),
                "checks": checks,
                "expected_source_refs": expected_refs,
                "retrieved_refs": retrieved_refs,
                "citation_refs": citation_refs,
                "expected_answer_terms": expected_terms,
            }
        )

    total = len(normalized_cases)
    metrics = {
        "total_cases": total,
        "retrieval_hit_rate": round(totals["retrieval_hit"] / max(1, total), 4),
        "citation_coverage": round(totals["citation_covered"] / max(1, total), 4),
        "groundedness": round(totals["grounded"] / max(1, total), 4),
        "answer_helpfulness": round(totals["helpful"] / max(1, total), 4),
    }
    threshold_failures = []
    mapping = {
        "retrieval_hit_rate": "retrieval_hit_rate_min",
        "citation_coverage": "citation_coverage_min",
        "groundedness": "groundedness_min",
        "answer_helpfulness": "answer_helpfulness_min",
    }
    for metric, threshold_key in mapping.items():
        if float(metrics[metric]) < float(pol.get(threshold_key) or 0.0):
            threshold_failures.append(metric)

    checks = []
    for metric, threshold_key in mapping.items():
        checks.append(
            {
                "id": metric,
                "status": "passed" if metric not in threshold_failures else "failed",
                "score": metrics[metric],
                "threshold": float(pol.get(threshold_key) or 0.0),
            }
        )

    return {
        "apiVersion": API_VERSION,
        "kind": RAG_EVAL_REPORT_KIND,
        "ok": not threshold_failures,
        "created_at": _nowz(),
        "trace_id": tid,
        "pack_id": str(pack_id or ""),
        "thresholds": pol,
        "threshold_failures": threshold_failures,
        "metrics": metrics,
        "checks": checks,
        "results": rows,
    }


def rag_eval_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != RAG_EVAL_REPORT_KIND:
        raise ValueError("rag_eval_report_required")
    return {
        "artifact_uri": str(artifact_uri or report.get("artifact_uri") or ""),
        "run_at": str(report.get("created_at") or _nowz()),
        "checks": list(report.get("checks") or []),
    }


def _step_tool_call_count(step: Dict[str, Any]) -> int:
    calls = step.get("tool_calls")
    if isinstance(calls, list):
        return len(calls)
    return 1 if step.get("tool_call") or step.get("tool") else 0


def _step_artifact_refs(step: Dict[str, Any]) -> List[str]:
    return _clean_text_list(step.get("artifact_refs") or step.get("artifacts") or step.get("outputs"))


def evaluate_trajectory(
    trajectory: Dict[str, Any],
    *,
    thresholds: Optional[Dict[str, Any]] = None,
    trace_id: str = "",
    pack_id: str = "",
) -> Dict[str, Any]:
    if not isinstance(trajectory, dict):
        raise ValueError("trajectory_not_object")

    tid = str(trace_id or trajectory.get("trace_id") or new_trace_id("trajectory-eval"))
    pol = dict(DEFAULT_TRAJECTORY_THRESHOLDS)
    pol.update(thresholds or {})
    steps = [dict(x) for x in (trajectory.get("steps") or []) if isinstance(x, dict)]
    budget = dict(trajectory.get("budget") or {})
    final_state = str(trajectory.get("final_state") or "").strip() or "unknown"

    total_steps = len(steps)
    failed_steps = sum(1 for step in steps if not bool(step.get("ok", True)))
    tool_calls = sum(_step_tool_call_count(step) for step in steps)
    safety_flags = sorted(
        {
            str(flag).strip().lower()
            for step in steps
            for flag in _as_list(step.get("safety_flags"))
            if str(flag).strip()
        }
    )
    artifact_required_steps = [
        step for step in steps
        if bool(step.get("requires_artifact")) or str(step.get("type") or "").strip().lower() in {"artifact", "eval", "final", "handoff"}
    ]
    artifact_present = sum(1 for step in artifact_required_steps if _step_artifact_refs(step))
    step_success_rate = 1.0 if total_steps == 0 else round((total_steps - failed_steps) / max(1, total_steps), 4)
    artifact_coverage = 1.0 if not artifact_required_steps else round(artifact_present / max(1, len(artifact_required_steps)), 4)

    budget_failures = []
    max_steps = int(budget.get("max_steps") or 0)
    max_tool_calls = int(budget.get("max_tool_calls") or 0)
    if max_steps and total_steps > max_steps:
        budget_failures.append("max_steps_exceeded")
    if max_tool_calls and tool_calls > max_tool_calls:
        budget_failures.append("max_tool_calls_exceeded")
    if bool(budget.get("human_interrupt")) and not bool(trajectory.get("interruptible", True)):
        budget_failures.append("human_interrupt_not_available")

    threshold_failures = []
    if step_success_rate < float(pol.get("step_success_rate_min") or 0.0):
        threshold_failures.append("step_success_rate")
    if artifact_coverage < float(pol.get("artifact_coverage_min") or 0.0):
        threshold_failures.append("artifact_coverage")
    if len(safety_flags) > int(pol.get("max_safety_flags") or 0):
        threshold_failures.append("safety_flags")
    if bool(pol.get("require_budget_compliance", True)) and budget_failures:
        threshold_failures.append("budget_compliance")
    if bool(pol.get("require_safe_final_state", True)) and final_state not in SAFE_TRAJECTORY_FINAL_STATES:
        threshold_failures.append("safe_final_state")

    metrics = {
        "total_steps": total_steps,
        "failed_steps": failed_steps,
        "tool_calls": tool_calls,
        "step_success_rate": step_success_rate,
        "artifact_coverage": artifact_coverage,
        "safety_flag_count": len(safety_flags),
        "budget_compliant": not budget_failures,
        "safe_final_state": final_state in SAFE_TRAJECTORY_FINAL_STATES,
    }
    checks = [
        {
            "id": "trajectory_step_success_rate",
            "status": "passed" if "step_success_rate" not in threshold_failures else "failed",
            "score": metrics["step_success_rate"],
            "threshold": float(pol.get("step_success_rate_min") or 0.0),
        },
        {
            "id": "trajectory_artifact_coverage",
            "status": "passed" if "artifact_coverage" not in threshold_failures else "failed",
            "score": metrics["artifact_coverage"],
            "threshold": float(pol.get("artifact_coverage_min") or 0.0),
        },
        {
            "id": "trajectory_budget_compliance",
            "status": "passed" if "budget_compliance" not in threshold_failures else "failed",
            "score": 1.0 if metrics["budget_compliant"] else 0.0,
            "threshold": 1.0 if bool(pol.get("require_budget_compliance", True)) else 0.0,
        },
        {
            "id": "trajectory_safety_flags",
            "status": "passed" if "safety_flags" not in threshold_failures else "failed",
            "score": len(safety_flags),
            "threshold": int(pol.get("max_safety_flags") or 0),
        },
        {
            "id": "trajectory_safe_final_state",
            "status": "passed" if "safe_final_state" not in threshold_failures else "failed",
            "score": 1.0 if metrics["safe_final_state"] else 0.0,
            "threshold": 1.0 if bool(pol.get("require_safe_final_state", True)) else 0.0,
        },
    ]

    return {
        "apiVersion": API_VERSION,
        "kind": TRAJECTORY_EVAL_REPORT_KIND,
        "ok": not threshold_failures,
        "created_at": _nowz(),
        "trace_id": tid,
        "pack_id": str(pack_id or ""),
        "trajectory_id": str(trajectory.get("id") or trajectory.get("trajectory_id") or ""),
        "loop_type": str(trajectory.get("loop_type") or ""),
        "final_state": final_state,
        "thresholds": pol,
        "threshold_failures": threshold_failures,
        "budget_failures": budget_failures,
        "safety_flags": safety_flags,
        "metrics": metrics,
        "checks": checks,
        "steps": [
            {
                "id": str(step.get("id") or step.get("step_id") or ""),
                "type": str(step.get("type") or ""),
                "ok": bool(step.get("ok", True)),
                "tool_calls": _step_tool_call_count(step),
                "artifact_refs": _step_artifact_refs(step),
                "safety_flags": _clean_text_list(step.get("safety_flags")),
            }
            for step in steps
        ],
    }


def trajectory_eval_report_to_gate_evidence(report: Dict[str, Any], *, artifact_uri: str = "") -> Dict[str, Any]:
    if not isinstance(report, dict) or report.get("kind") != TRAJECTORY_EVAL_REPORT_KIND:
        raise ValueError("trajectory_eval_report_required")
    return {
        "artifact_uri": str(artifact_uri or report.get("artifact_uri") or ""),
        "run_at": str(report.get("created_at") or _nowz()),
        "checks": list(report.get("checks") or []),
    }


def evaluate_epoch_apply_gate(
    epoch_id: str,
    build_report: Dict[str, Any],
    scary_report: Dict[str, Any],
    *,
    build_report_path: str = "",
    scary_report_path: str = "",
) -> Dict[str, Any]:
    change_id = _clean_id(f"epoch-apply-{epoch_id}", "change_id")
    checks = [
        {
            "id": "prestart_build_report",
            "status": "passed" if str(build_report.get("overall_decision") or "").lower().strip() == "pass" else "failed",
            "artifact_uri": build_report_path,
        },
        {
            "id": "final_canary",
            "status": "passed" if str(scary_report.get("decision") or "").lower().strip() == "pass" and bool(scary_report.get("overall_ok")) else "failed",
            "artifact_uri": scary_report_path,
        },
    ]
    return evaluate_gate(
        {
            "change_id": change_id,
            "domain": "pipeline",
            "summary": f"Promote candidate epoch {epoch_id}.",
            "required_checks": ["prestart_build_report", "final_canary"],
        },
        {
            "artifact_uri": scary_report_path or build_report_path,
            "run_at": str(scary_report.get("completed_at") or scary_report.get("created_at") or build_report.get("completed_at") or build_report.get("created_at") or _nowz()),
            "checks": checks,
        },
    )


def build_epoch_release_evidence(
    epoch_id: str,
    build_report: Dict[str, Any],
    scary_report: Dict[str, Any],
    *,
    build_report_path: str = "",
    scary_report_path: str = "",
    registry_refs: Optional[Sequence[str]] = None,
    trace_id: str = "",
    actor: str = "brainctl",
) -> Dict[str, Any]:
    change = {
        "change_id": _clean_id(f"epoch-apply-{epoch_id}", "change_id"),
        "domain": "pipeline",
        "summary": f"Promote candidate epoch {epoch_id}.",
    }
    gate = evaluate_epoch_apply_gate(
        epoch_id,
        build_report,
        scary_report,
        build_report_path=build_report_path,
        scary_report_path=scary_report_path,
    )
    rollout = rollout_transition("canary", "promoted", gate, approved=True)
    return build_release_evidence(
        change,
        gate,
        rollout,
        registry_refs=registry_refs or [],
        trace_id=trace_id,
        actor=actor,
    )


def summarize_contract_status(registry: Dict[str, Any], required_kinds: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    kinds = set(required_kinds or REGISTRY_KINDS)
    present = {entry["kind"] for entry in normalize_registry(registry)["entries"]}
    missing = sorted(kinds - present)
    return {
        "ok": not missing,
        "present_kinds": sorted(present),
        "missing_kinds": missing,
    }
