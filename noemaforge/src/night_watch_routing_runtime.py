#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/night_watch_routing_runtime.py
Zone: release/package
Created: 2026-08-13
Modified: 2026-08-13
Purpose: Evaluate Night Watch reviewer/provider readiness and review-gate routing.
Inputs: Strict local provider/persona state and an exact candidate SHA.
Outputs: Deterministic JSON-compatible review routing envelopes.
Side effects: None.
Tests: covered by immutable regression tests
Notes: This runtime has no file-header Version field; product release identity is sourced only from noemaforge/src/noemaforge_version.py.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


API_VERSION = "noemaforge.night-watch-routing/v1"
PROVENANCE = "UAT request findings resolution"

SHA40 = re.compile(r"^[0-9a-f]{40}$")

PROVIDER_AVAILABILITY = frozenset(
    {"available", "blocked_external", "unavailable", "unknown"}
)
SURFACE_READINESS = frozenset(
    {"ready", "interactive_only", "unavailable", "unverified"}
)
QUALITY_CALIBRATION = frozenset(
    {"calibrated", "failed", "unproven", "not_required"}
)
VOTE_ELIGIBILITY = frozenset({"eligible", "ineligible"})
METADATA_SIDE_EFFECTS = frozenset({"none_observed", "observed", "unknown"})

PROVIDER_KEYS = frozenset(
    {
        "provider_id",
        "provider_availability",
        "surface_readiness",
        "quality_calibration",
        "vote_eligibility",
        "metadata_side_effects",
        "independence_key",
        "capabilities",
        "request_attempted",
        "review_observed",
        "bound_candidate_sha",
        "optional",
    }
)
PERSONA_KEYS = frozenset(
    {"persona_id", "configured", "capabilities", "provider_candidates"}
)
ROUTE_KEYS = frozenset(
    {
        "apiVersion",
        "provenance",
        "candidate_sha",
        "change_scope",
        "persona_id",
        "implementer_provider",
        "coderabbit_required",
        "selected_reviewers",
        "blockers",
        "notices",
        "review_gate_pass",
        "route",
        "downstream",
        "provider_observations",
    }
)
DOWNSTREAM_KEYS = frozenset(
    {"build_reproducer", "call_cost_estimator", "route_budget", "start_gcp"}
)
OBSERVATION_KEYS = frozenset(
    {
        "provider_availability",
        "surface_readiness",
        "quality_calibration",
        "vote_eligibility",
        "metadata_side_effects",
        "independence_key",
        "review_observed",
        "bound_candidate_sha",
    }
)

CODE_SCOPES = frozenset({"code", "config", "infra"})
CHANGE_SCOPES = frozenset({"code", "config", "infra", "markdown"})
ROUTES = frozenset({
    "LOCAL_REVIEW_GATE_PASS",
    "YIELD_BLOCKED_REVIEW_QUALITY",
    "LOCAL_REVIEW_CODE_BLOCK",
    "YIELD_WAITING_EXTERNAL_REVIEW",
    "YIELD_BLOCKED_ENGINE_CAPABILITY",
    "BLOCKED_REVIEW_GATE",
})
CODERABBIT_SCOPE_CAPABILITIES = {
    "code": "code_review",
    "config": "config_review",
    "infra": "infra_review",
    "markdown": "markdown_review",
}


class NightWatchRoutingError(ValueError):
    """Raised when a routing document violates the strict local contract."""


def _require_exact_keys(document: Mapping[str, Any], expected: Iterable[str], kind: str) -> None:
    actual = set(document)
    missing = sorted(set(expected) - actual)
    extra = sorted(actual - set(expected))
    if missing or extra:
        raise NightWatchRoutingError(
            f"{kind} keys invalid; missing={missing}; extra={extra}"
        )


def _validate_sha(value: Optional[str], *, field: str, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if not isinstance(value, str) or not SHA40.fullmatch(value):
        raise NightWatchRoutingError(f"{field} must be a lowercase 40-character SHA")


def _stable_strings(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen: Set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value:
            raise NightWatchRoutingError("string collection contains an invalid value")
        if value not in seen:
            seen.add(value)
            result.append(value)
    return sorted(result)


def _validate_string_list(value: Any, *, field: str) -> List[str]:
    if not isinstance(value, list):
        raise NightWatchRoutingError(f"{field} must be a JSON array")
    stable = _stable_strings(value)
    if value != stable:
        raise NightWatchRoutingError(f"{field} must be sorted and duplicate-free")
    return stable


def _validate_change_scope(change_scope: Any) -> str:
    if not isinstance(change_scope, str) or change_scope not in CHANGE_SCOPES:
        raise NightWatchRoutingError(
            f"change_scope must be one of {sorted(CHANGE_SCOPES)!r}"
        )
    return change_scope


def validate_persona_state(document: Mapping[str, Any]) -> None:
    _require_exact_keys(document, PERSONA_KEYS, "persona")
    if not isinstance(document["persona_id"], str) or not document["persona_id"]:
        raise NightWatchRoutingError("persona_id is required")
    if not isinstance(document["configured"], bool):
        raise NightWatchRoutingError("configured must be boolean")
    _validate_string_list(document["capabilities"], field="persona capabilities")
    _validate_string_list(
        document["provider_candidates"], field="persona provider_candidates"
    )


def make_provider_state(
    *,
    provider_id: str,
    provider_availability: str,
    surface_readiness: str,
    quality_calibration: str,
    metadata_side_effects: str,
    independence_key: str,
    capabilities: Iterable[str],
    request_attempted: bool = False,
    review_observed: bool = False,
    bound_candidate_sha: Optional[str] = None,
    optional: bool = False,
) -> Dict[str, Any]:
    """Build a strict provider state and derive vote eligibility.

    A provider cannot be counted merely because a request succeeded or a surface
    responded. A vote requires provider availability, an automation-ready
    surface, sufficient quality calibration, observed review evidence, and an
    exact candidate binding.
    """
    if not isinstance(provider_id, str) or not provider_id:
        raise NightWatchRoutingError("provider_id is required")
    if provider_availability not in PROVIDER_AVAILABILITY:
        raise NightWatchRoutingError("invalid provider_availability")
    if surface_readiness not in SURFACE_READINESS:
        raise NightWatchRoutingError("invalid surface_readiness")
    if quality_calibration not in QUALITY_CALIBRATION:
        raise NightWatchRoutingError("invalid quality_calibration")
    if metadata_side_effects not in METADATA_SIDE_EFFECTS:
        raise NightWatchRoutingError("invalid metadata_side_effects")
    if not isinstance(independence_key, str) or not independence_key:
        raise NightWatchRoutingError("independence_key is required")
    if not isinstance(request_attempted, bool) or not isinstance(review_observed, bool):
        raise NightWatchRoutingError("request/review observations must be booleans")
    if not isinstance(optional, bool):
        raise NightWatchRoutingError("optional must be boolean")
    _validate_sha(bound_candidate_sha, field="bound_candidate_sha", allow_none=True)

    quality_ok = quality_calibration in {"calibrated", "not_required"}
    vote_eligible = (
        provider_availability == "available"
        and surface_readiness == "ready"
        and quality_ok
        and review_observed
        and bound_candidate_sha is not None
    )

    result = {
        "provider_id": provider_id,
        "provider_availability": provider_availability,
        "surface_readiness": surface_readiness,
        "quality_calibration": quality_calibration,
        "vote_eligibility": "eligible" if vote_eligible else "ineligible",
        "metadata_side_effects": metadata_side_effects,
        "independence_key": independence_key,
        "capabilities": _stable_strings(capabilities),
        "request_attempted": request_attempted,
        "review_observed": review_observed,
        "bound_candidate_sha": bound_candidate_sha,
        "optional": optional,
    }
    validate_provider_state(result)
    return result


def validate_provider_state(document: Mapping[str, Any]) -> None:
    _require_exact_keys(document, PROVIDER_KEYS, "provider")
    if not isinstance(document["provider_id"], str) or not document["provider_id"]:
        raise NightWatchRoutingError("provider_id is required")
    if not isinstance(document["independence_key"], str) or not document["independence_key"]:
        raise NightWatchRoutingError("independence_key is required")
    _validate_string_list(document["capabilities"], field="provider capabilities")
    if not isinstance(document["request_attempted"], bool):
        raise NightWatchRoutingError("request_attempted must be boolean")
    if not isinstance(document["review_observed"], bool):
        raise NightWatchRoutingError("review_observed must be boolean")
    if not isinstance(document["optional"], bool):
        raise NightWatchRoutingError("optional must be boolean")
    if document["provider_availability"] not in PROVIDER_AVAILABILITY:
        raise NightWatchRoutingError("invalid provider_availability")
    if document["surface_readiness"] not in SURFACE_READINESS:
        raise NightWatchRoutingError("invalid surface_readiness")
    if document["quality_calibration"] not in QUALITY_CALIBRATION:
        raise NightWatchRoutingError("invalid quality_calibration")
    if document["vote_eligibility"] not in VOTE_ELIGIBILITY:
        raise NightWatchRoutingError("invalid vote_eligibility")
    if document["metadata_side_effects"] not in METADATA_SIDE_EFFECTS:
        raise NightWatchRoutingError("invalid metadata_side_effects")
    _validate_sha(
        document["bound_candidate_sha"],
        field="bound_candidate_sha",
        allow_none=True,
    )
    quality_ok = document["quality_calibration"] in {"calibrated", "not_required"}
    derived = (
        document["provider_availability"] == "available"
        and document["surface_readiness"] == "ready"
        and quality_ok
        and document["review_observed"] is True
        and document["bound_candidate_sha"] is not None
    )
    expected_vote = "eligible" if derived else "ineligible"
    if document["vote_eligibility"] != expected_vote:
        raise NightWatchRoutingError(
            f"vote_eligibility must be derived as {expected_vote!r}"
        )


def make_persona_state(
    *,
    persona_id: str,
    capabilities: Iterable[str],
    provider_candidates: Iterable[str],
    configured: bool = True,
) -> Dict[str, Any]:
    """Create a persona configuration independent of provider availability."""
    if not isinstance(persona_id, str) or not persona_id:
        raise NightWatchRoutingError("persona_id is required")
    if not isinstance(configured, bool):
        raise NightWatchRoutingError("configured must be boolean")
    result = {
        "persona_id": persona_id,
        "configured": configured,
        "capabilities": _stable_strings(capabilities),
        "provider_candidates": _stable_strings(provider_candidates),
    }
    validate_persona_state(result)
    return result


def coderabbit_required(change_scope: str, affected_prior_reviewers: Iterable[str]) -> bool:
    """Apply the Night Watch CodeRabbit requirement and fail closed on unknown scope."""
    _validate_change_scope(change_scope)
    if isinstance(affected_prior_reviewers, (str, bytes)):
        raise NightWatchRoutingError("affected_prior_reviewers must be a collection")
    reviewers = _stable_strings(affected_prior_reviewers)
    if change_scope in CODE_SCOPES:
        return True
    return "coderabbit" in set(reviewers)


def _candidate_exact(provider: Mapping[str, Any], candidate_sha: str) -> bool:
    return provider.get("bound_candidate_sha") == candidate_sha


def _provider_can_vote(
    provider: Mapping[str, Any],
    *,
    candidate_sha: str,
    capability: Optional[str] = None,
) -> bool:
    validate_provider_state(provider)
    if provider["vote_eligibility"] != "eligible":
        return False
    if not _candidate_exact(provider, candidate_sha):
        return False
    if capability is not None and capability not in set(provider["capabilities"]):
        return False
    return True


def _classify_unavailable_provider(
    provider: Mapping[str, Any], *, candidate_sha: str
) -> str:
    """Return the most specific typed blocker for a non-voting provider."""
    validate_provider_state(provider)
    if provider["provider_availability"] != "available":
        return "BLOCKED_ENGINE_CAPABILITY"
    if provider["surface_readiness"] != "ready":
        return "BLOCKED_ENGINE_CAPABILITY"
    if provider["quality_calibration"] in {"failed", "unproven"}:
        return "BLOCKED_REVIEW_QUALITY_CAPABILITY"
    if provider["review_observed"] and not _candidate_exact(provider, candidate_sha):
        return "STALE_REVIEW_CANDIDATE"
    if not provider["review_observed"]:
        return "WAITING_FOR_REVIEW_EVIDENCE"
    return "BLOCKED_ENGINE_CAPABILITY"


def _choose_independent_provider(
    *,
    candidate_sha: str,
    implementer_provider: str,
    persona: Mapping[str, Any],
    providers: Mapping[str, Mapping[str, Any]],
) -> Tuple[Optional[str], List[str]]:
    validate_persona_state(persona)
    if not persona["configured"]:
        return None, ["PERSONA_NOT_CONFIGURED"]
    if "independent_review" not in persona["capabilities"]:
        return None, ["PERSONA_CAPABILITY_MISSING"]

    implementer = providers.get(implementer_provider)
    implementer_key = (
        implementer["independence_key"] if implementer is not None else None
    )

    blockers: List[str] = []
    for provider_id in persona["provider_candidates"]:
        if provider_id == implementer_provider:
            continue
        provider = providers.get(provider_id)
        if provider is None:
            blockers.append("BLOCKED_ENGINE_CAPABILITY")
            continue
        if _provider_can_vote(
            provider,
            candidate_sha=candidate_sha,
            capability="independent_review",
        ):
            if (
                implementer_key is not None
                and provider["independence_key"] == implementer_key
            ):
                blockers.append("IMPLEMENTER_SELF_REVIEW_REJECTED")
                continue
            return provider_id, []
        blockers.append(_classify_unavailable_provider(provider, candidate_sha=candidate_sha))

    if "IMPLEMENTER_SELF_REVIEW_REJECTED" in blockers:
        return None, ["IMPLEMENTER_SELF_REVIEW_REJECTED"]
    if "BLOCKED_REVIEW_QUALITY_CAPABILITY" in blockers:
        return None, ["BLOCKED_REVIEW_QUALITY_CAPABILITY"]
    if "STALE_REVIEW_CANDIDATE" in blockers:
        return None, ["STALE_REVIEW_CANDIDATE"]
    if "WAITING_FOR_REVIEW_EVIDENCE" in blockers:
        return None, ["WAITING_FOR_REVIEW_EVIDENCE"]
    return None, ["BLOCKED_ENGINE_CAPABILITY"]


def _add_unique(values: List[str], value: str) -> None:
    if value not in values:
        values.append(value)


def validate_review_identity(
    *,
    implementer_provider: str,
    reviewer_ids: Sequence[str],
    providers: Mapping[str, Mapping[str, Any]],
) -> Optional[str]:
    implementer = providers.get(implementer_provider)
    if implementer is None:
        return "IMPLEMENTER_UNAVAILABLE"
    implementer_key = implementer["independence_key"]

    seen: Set[str] = set()
    for reviewer_id in reviewer_ids:
        provider = providers.get(reviewer_id)
        if provider is None:
            return "UNKNOWN_REVIEW_PROVIDER"
        key = provider["independence_key"]
        if reviewer_id == implementer_provider or key == implementer_key:
            return "IMPLEMENTER_SELF_REVIEW_REJECTED"
        if key in seen:
            return "DUPLICATE_INDEPENDENCE_KEY_REJECTED"
        seen.add(key)
    return None


def evaluate_review_gate(
    *,
    candidate_sha: str,
    change_scope: str,
    persona: Mapping[str, Any],
    implementer_provider: str,
    providers: Mapping[str, Mapping[str, Any]],
    affected_prior_reviewers: Iterable[str] = (),
    require_independent_review: bool = True,
    require_git_helper: bool = True,
    optional_copilot: bool = True,
) -> Dict[str, Any]:
    """Evaluate only the review gate; never invoke reviewers or downstream work."""
    _validate_sha(candidate_sha, field="candidate_sha")
    _validate_change_scope(change_scope)
    validate_persona_state(persona)
    if not isinstance(implementer_provider, str) or not implementer_provider:
        raise NightWatchRoutingError("implementer_provider is required")
    if not isinstance(providers, Mapping):
        raise NightWatchRoutingError("providers must be an object")
    if not isinstance(require_independent_review, bool) or not isinstance(require_git_helper, bool) or not isinstance(optional_copilot, bool):
        raise NightWatchRoutingError("review policy switches must be booleans")
    if isinstance(affected_prior_reviewers, (str, bytes)):
        raise NightWatchRoutingError("affected_prior_reviewers must be a collection")
    affected_prior_reviewers = _stable_strings(affected_prior_reviewers)
    for provider_id, state in providers.items():
        if not isinstance(provider_id, str) or not provider_id:
            raise NightWatchRoutingError("provider mapping key must be a non-empty string")
        validate_provider_state(state)
        if state["provider_id"] != provider_id:
            raise NightWatchRoutingError(
                f"provider mapping key {provider_id!r} does not match provider_id {state['provider_id']!r}"
            )

    selected: List[str] = []
    blockers: List[str] = []
    notices: List[str] = []

    implementer = providers.get(implementer_provider)
    if implementer is None or implementer["provider_availability"] != "available":
        _add_unique(blockers, "IMPLEMENTER_UNAVAILABLE")

    if require_git_helper:
        git_helper = providers.get("git_helper")
        if git_helper and _provider_can_vote(
            git_helper, candidate_sha=candidate_sha, capability="git_integrity"
        ):
            _add_unique(selected, "git_helper")
        else:
            _add_unique(blockers, "GIT_HELPER_UNAVAILABLE")

    if require_independent_review:
        reviewer, reviewer_blockers = _choose_independent_provider(
            candidate_sha=candidate_sha,
            implementer_provider=implementer_provider,
            persona=persona,
            providers=providers,
        )
        if reviewer:
            _add_unique(selected, reviewer)
        for blocker in reviewer_blockers:
            _add_unique(blockers, blocker)

    cr_required = coderabbit_required(change_scope, affected_prior_reviewers)
    if cr_required:
        coderabbit = providers.get("coderabbit")
        coderabbit_capability = CODERABBIT_SCOPE_CAPABILITIES.get(
            change_scope,
            "code_review",
        )
        if coderabbit and _provider_can_vote(
            coderabbit,
            candidate_sha=candidate_sha,
            capability=coderabbit_capability,
        ):
            _add_unique(selected, "coderabbit")
        elif coderabbit is None:
            _add_unique(blockers, "CODERABBIT_REQUIRED_UNAVAILABLE")
        elif coderabbit["provider_availability"] != "available":
            _add_unique(blockers, "CODERABBIT_REQUIRED_UNAVAILABLE")
        elif coderabbit["quality_calibration"] in {"failed", "unproven"}:
            _add_unique(blockers, "BLOCKED_REVIEW_QUALITY_CAPABILITY")
        elif coderabbit["surface_readiness"] != "ready":
            _add_unique(blockers, "CODERABBIT_REQUIRED_UNAVAILABLE")
        elif coderabbit["review_observed"] and not _candidate_exact(coderabbit, candidate_sha):
            _add_unique(blockers, "STALE_REVIEW_CANDIDATE")
        elif coderabbit["quality_calibration"] in {"calibrated", "not_required"} and not coderabbit["review_observed"]:
            _add_unique(blockers, "WAITING_FOR_LIVE_PR_REVIEW")
        else:
            _add_unique(blockers, "CODERABBIT_REQUIRED_UNAVAILABLE")
    else:
        notices.append("CODERABBIT_NOT_REQUIRED")

    if optional_copilot:
        copilot = providers.get("copilot")
        if not copilot or not _provider_can_vote(copilot, candidate_sha=candidate_sha):
            notices.append("OPTIONAL_COPILOT_UNVERIFIED")

    identity_error = validate_review_identity(
        implementer_provider=implementer_provider,
        reviewer_ids=selected,
        providers=providers,
    )
    if identity_error:
        _add_unique(blockers, identity_error)

    review_gate_pass = not blockers
    if review_gate_pass:
        route = "LOCAL_REVIEW_GATE_PASS"
    elif "BLOCKED_REVIEW_QUALITY_CAPABILITY" in blockers:
        route = "YIELD_BLOCKED_REVIEW_QUALITY"
    elif "CODERABBIT_REQUIRED_UNAVAILABLE" in blockers:
        route = "LOCAL_REVIEW_CODE_BLOCK"
    elif (
        "WAITING_FOR_LIVE_PR_REVIEW" in blockers
        or "WAITING_FOR_REVIEW_EVIDENCE" in blockers
    ):
        route = "YIELD_WAITING_EXTERNAL_REVIEW"
    elif "BLOCKED_ENGINE_CAPABILITY" in blockers:
        route = "YIELD_BLOCKED_ENGINE_CAPABILITY"
    else:
        route = "BLOCKED_REVIEW_GATE"

    implementer_key = (
        implementer["independence_key"] if implementer is not None else None
    )

    def observation_vote_eligibility(provider_id: str, state: Mapping[str, Any]) -> str:
        context_eligible = (
            state["vote_eligibility"] == "eligible"
            and state["bound_candidate_sha"] == candidate_sha
            and provider_id != implementer_provider
            and implementer_key is not None
            and state["independence_key"] != implementer_key
        )
        return "eligible" if context_eligible else "ineligible"

    provider_observations = {
        provider_id: {
            "provider_availability": state["provider_availability"],
            "surface_readiness": state["surface_readiness"],
            "quality_calibration": state["quality_calibration"],
            "vote_eligibility": observation_vote_eligibility(provider_id, state),
            "metadata_side_effects": state["metadata_side_effects"],
            "independence_key": state["independence_key"],
            "review_observed": state["review_observed"],
            "bound_candidate_sha": state["bound_candidate_sha"],
        }
        for provider_id, state in sorted(providers.items())
    }

    result = {
        "apiVersion": API_VERSION,
        "provenance": PROVENANCE,
        "candidate_sha": candidate_sha,
        "change_scope": change_scope,
        "persona_id": persona["persona_id"],
        "implementer_provider": implementer_provider,
        "coderabbit_required": cr_required,
        "selected_reviewers": sorted(selected),
        "blockers": sorted(blockers),
        "notices": sorted(notices),
        "review_gate_pass": review_gate_pass,
        "route": route,
        "downstream": {
            "build_reproducer": review_gate_pass,
            "call_cost_estimator": False,
            "route_budget": False,
            "start_gcp": False,
        },
        "provider_observations": provider_observations,
    }
    validate_route_envelope(result)
    return result


def validate_route_envelope(document: Mapping[str, Any]) -> None:
    if not isinstance(document, Mapping):
        raise NightWatchRoutingError("route must be an object")
    _require_exact_keys(document, ROUTE_KEYS, "route")
    if document["apiVersion"] != API_VERSION:
        raise NightWatchRoutingError("unexpected apiVersion")
    if document["provenance"] != PROVENANCE:
        raise NightWatchRoutingError("unexpected provenance")
    _validate_sha(document["candidate_sha"], field="candidate_sha")
    change_scope = _validate_change_scope(document["change_scope"])
    for field in ("persona_id", "implementer_provider", "route"):
        if not isinstance(document[field], str) or not document[field]:
            raise NightWatchRoutingError(f"{field} must be a non-empty string")
    if document["route"] not in ROUTES:
        raise NightWatchRoutingError("unexpected route")
    if not isinstance(document["coderabbit_required"], bool):
        raise NightWatchRoutingError("coderabbit_required must be boolean")
    selected = _validate_string_list(document["selected_reviewers"], field="selected_reviewers")
    blockers = _validate_string_list(document["blockers"], field="blockers")
    _validate_string_list(document["notices"], field="notices")

    downstream = document["downstream"]
    if not isinstance(downstream, Mapping):
        raise NightWatchRoutingError("downstream must be an object")
    _require_exact_keys(downstream, DOWNSTREAM_KEYS, "downstream")
    for key in DOWNSTREAM_KEYS:
        if not isinstance(downstream[key], bool):
            raise NightWatchRoutingError(f"downstream.{key} must be boolean")

    observations = document["provider_observations"]
    if not isinstance(observations, Mapping):
        raise NightWatchRoutingError("provider_observations must be an object")
    for provider_id, observation in observations.items():
        if not isinstance(provider_id, str) or not provider_id:
            raise NightWatchRoutingError("provider observation id must be a non-empty string")
        if not isinstance(observation, Mapping):
            raise NightWatchRoutingError("provider observation must be an object")
        _require_exact_keys(observation, OBSERVATION_KEYS, "provider observation")
        if observation["provider_availability"] not in PROVIDER_AVAILABILITY:
            raise NightWatchRoutingError("invalid observation provider_availability")
        if observation["surface_readiness"] not in SURFACE_READINESS:
            raise NightWatchRoutingError("invalid observation surface_readiness")
        if observation["quality_calibration"] not in QUALITY_CALIBRATION:
            raise NightWatchRoutingError("invalid observation quality_calibration")
        if observation["vote_eligibility"] not in VOTE_ELIGIBILITY:
            raise NightWatchRoutingError("invalid observation vote_eligibility")
        if observation["metadata_side_effects"] not in METADATA_SIDE_EFFECTS:
            raise NightWatchRoutingError("invalid observation metadata_side_effects")
        if not isinstance(observation["independence_key"], str) or not observation["independence_key"]:
            raise NightWatchRoutingError("observation independence_key is required")
        if not isinstance(observation["review_observed"], bool):
            raise NightWatchRoutingError("observation review_observed must be boolean")
        _validate_sha(
            observation["bound_candidate_sha"],
            field="observation bound_candidate_sha",
            allow_none=True,
        )

    implementer_id = document["implementer_provider"]
    implementer_observation = observations.get(implementer_id)
    if not isinstance(implementer_observation, Mapping):
        raise NightWatchRoutingError("implementer observation is required")
    implementer_key = implementer_observation["independence_key"]

    expected_coderabbit = change_scope in CODE_SCOPES
    if expected_coderabbit and document["coderabbit_required"] is not True:
        raise NightWatchRoutingError("code/config/infra scope requires CodeRabbit")

    if not isinstance(document["review_gate_pass"], bool):
        raise NightWatchRoutingError("review_gate_pass must be boolean")
    if document["review_gate_pass"]:
        if blockers:
            raise NightWatchRoutingError("passing review gate cannot carry blockers")
        selected_keys: Set[str] = set()
        for reviewer_id in selected:
            if reviewer_id == implementer_id:
                raise NightWatchRoutingError("implementer cannot be a selected reviewer")
            observation = observations.get(reviewer_id)
            if not isinstance(observation, Mapping):
                raise NightWatchRoutingError("selected reviewer observation is required")
            if observation["vote_eligibility"] != "eligible":
                raise NightWatchRoutingError("selected reviewer must be vote eligible")
            if observation["bound_candidate_sha"] != document["candidate_sha"]:
                raise NightWatchRoutingError("selected reviewer must bind the exact candidate")
            key = observation["independence_key"]
            if key == implementer_key:
                raise NightWatchRoutingError("selected reviewer is not independent of implementer")
            if key in selected_keys:
                raise NightWatchRoutingError("selected reviewers must have unique independence keys")
            selected_keys.add(key)
        if document["coderabbit_required"] and "coderabbit" not in selected:
            raise NightWatchRoutingError("required CodeRabbit review is not selected")
        if downstream["build_reproducer"] is not True:
            raise NightWatchRoutingError("passing review gate must release reproducer")
    else:
        if not blockers:
            raise NightWatchRoutingError("blocked review gate requires a typed blocker")
        if any(downstream.values()):
            raise NightWatchRoutingError("blocked review gate cannot enable downstream work")

    if downstream["call_cost_estimator"]:
        raise NightWatchRoutingError("cost estimation requires a proven reproducer stage")
    if downstream["route_budget"] or downstream["start_gcp"]:
        raise NightWatchRoutingError("budget/GCP cannot start from the review gate")

    if document["review_gate_pass"] and document["route"] != "LOCAL_REVIEW_GATE_PASS":
        raise NightWatchRoutingError("passing gate has inconsistent route")
    if not document["review_gate_pass"] and document["route"] == "LOCAL_REVIEW_GATE_PASS":
        raise NightWatchRoutingError("blocked gate cannot use pass route")

