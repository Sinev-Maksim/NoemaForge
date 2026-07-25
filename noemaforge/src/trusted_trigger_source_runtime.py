#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/trusted_trigger_source_runtime.py
Zone: release/package
Version: 0.33.0
Created: 2026-07-21
Modified: 2026-07-23
Purpose: Evaluate whether normalized external events may create bounded work items without granting approval authority.
Inputs: Trusted trigger-source policy, untrusted trigger envelope, and trusted verification context.
Outputs: JSON-compatible TrustedTriggerSourceDecision reports.
Side effects: None; CLI writes JSON to stdout.
Tests: noemaforge/tests/test_trusted_trigger_source_runtime.py
Notes: The pure evaluator binds trusted-adapter evidence to an untrusted envelope; connector identity/signature verification remains an integration boundary.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from jsonschema import Draft202012Validator, FormatChecker
except Exception:  # Optional accelerator; a closed-schema fallback is bundled below.
    Draft202012Validator = None  # type: ignore[assignment]
    FormatChecker = None  # type: ignore[assignment]

BUILTIN_SCHEMA_PROFILE_AVAILABLE = True
SUPPORTED_SCHEMA_KEYWORDS = {
    "$schema", "$id", "title", "description", "type", "required", "properties",
    "additionalProperties", "const", "enum", "minLength", "minItems", "uniqueItems",
    "minimum", "pattern", "format", "items", "oneOf", "allOf", "if", "then", "else",
}

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "trusted-trigger-source-policy.json"
DEFAULT_EXAMPLES = PROJECT_ROOT / "prelaunch" / "governance" / "trusted_trigger_source.example.json"
POLICY_SCHEMA = PACKAGE_ROOT / "contracts" / "trusted_trigger_source_policy.schema.json"
ENVELOPE_SCHEMA = PACKAGE_ROOT / "contracts" / "trusted_trigger_source.schema.json"
VERIFICATION_SCHEMA = PACKAGE_ROOT / "contracts" / "trusted_trigger_verification_context.schema.json"
DECISION_SCHEMA = PACKAGE_ROOT / "contracts" / "trusted_trigger_source_decision.schema.json"

POLICY_VERSION = "noemaforge.trusted-trigger-source-policy/v1"
POLICY_KIND = "TrustedTriggerSourcePolicy"
ENVELOPE_VERSION = "noemaforge.trusted-trigger-source/v1"
ENVELOPE_KIND = "TrustedTriggerSourceEnvelope"
VERIFICATION_VERSION = "noemaforge.trusted-trigger-verification-context/v1"
VERIFICATION_KIND = "TrustedTriggerVerificationContext"
DECISION_VERSION = "noemaforge.trusted-trigger-source-decision/v1"
DECISION_KIND = "TrustedTriggerSourceDecision"
EXAMPLE_VERSION = "noemaforge.trusted-trigger-source.examples/v1"
EXAMPLE_KIND = "TrustedTriggerSourceExampleSet"
VALID_STATUSES = {"draft", "shadow", "stable", "retired"}

REQUIRED_CONTROLS = {
    "verification_context_required",
    "verification_bindings_must_match",
    "require_repository_match",
    "trigger_authority_does_not_grant_approval",
    "approval_must_be_separate",
    "login_is_not_authority",
    "raw_envelope_is_untrusted",
    "only_active_policy_authorizes",
    "verification_freshness_required",
    "decision_binds_policy_and_evidence",
}
REQUIRED_REFS = {
    "noemaforge/configs/trusted-trigger-source-policy.json",
    "noemaforge/contracts/trusted_trigger_source_policy.schema.json",
    "noemaforge/contracts/trusted_trigger_source.schema.json",
    "noemaforge/contracts/trusted_trigger_verification_context.schema.json",
    "noemaforge/contracts/trusted_trigger_source_decision.schema.json",
    "noemaforge/src/trusted_trigger_source_runtime.py",
    "noemaforge/tests/test_trusted_trigger_source_runtime.py",
    "noemaforge/docs/architecture/trusted-trigger-source-boundary.md",
    "prelaunch/governance/trusted_trigger_source.example.json",
}
RUNTIME_REASON_CODES = {
    "allowed_explicit_owner_message",
    "allowed_verified_github_app_event",
    "policy_invalid",
    "schema_validator_unavailable",
    "envelope_invalid",
    "verification_context_missing",
    "verification_context_invalid",
    "verifier_not_allowlisted",
    "verification_binding_mismatch",
    "requested_authority_not_trigger",
    "content_origin_untrusted",
    "repository_not_allowlisted",
    "owner_principal_not_allowlisted",
    "owner_message_metadata_missing",
    "github_app_not_allowlisted",
    "github_app_metadata_missing",
    "event_type_not_allowlisted",
    "metadata_contradiction",
    "actor_type_unsupported",
    "policy_not_active",
    "verification_stale",
    "verification_from_future",
}


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _strings(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _strict_int(value: Any) -> bool:
    return type(value) is int and value >= 1


def _policy(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _dict(payload.get("policy"))


def _reject_duplicate_keys(pairs: List[tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path | str) -> Dict[str, Any]:
    value = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
    )
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return value


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("evaluated_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_datetime(value: str) -> datetime:
    text = str(value or "").strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid RFC3339 date-time") from exc
    if parsed.tzinfo is None:
        raise ValueError("date-time must include timezone")
    return parsed.astimezone(timezone.utc)


def _format_datetime(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def load_policy(path: Path | str = DEFAULT_POLICY) -> Dict[str, Any]:
    return load_json(path)


def load_examples(path: Path | str = DEFAULT_EXAMPLES) -> Dict[str, Any]:
    return load_json(path)


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


def _type_matches(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": type(value) is bool,
        "integer": type(value) is int,
        "number": (type(value) is int or type(value) is float),
        "null": value is None,
    }.get(expected, False)


def _valid_datetime(value: str) -> bool:
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})",
        value,
    ):
        return False
    try:
        _parse_datetime(value)
    except ValueError:
        return False
    return True


def _profile_errors(instance: Any, schema: Any, path: tuple[Any, ...] = ()) -> List[tuple[tuple[Any, ...], str]]:
    if schema is True:
        return []
    if schema is False:
        return [(path, "falseSchema")]
    if not isinstance(schema, dict):
        return [(path, "invalidSchema")]

    unsupported = sorted(set(schema) - SUPPORTED_SCHEMA_KEYWORDS)
    if unsupported:
        return [(path, f"unsupportedKeyword:{keyword}") for keyword in unsupported]

    errors: List[tuple[tuple[Any, ...], str]] = []
    expected_type = schema.get("type")
    if expected_type is not None:
        expected = expected_type if isinstance(expected_type, list) else [expected_type]
        if not expected or any(not isinstance(item, str) for item in expected):
            return [(path, "invalidTypeSchema")]
        if not any(_type_matches(instance, item) for item in expected):
            return [(path, "type")]

    if "const" in schema and not _json_equal(instance, schema["const"]):
        errors.append((path, "const"))
    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, list) or not any(_json_equal(instance, item) for item in enum):
            errors.append((path, "enum"))

    if isinstance(instance, dict):
        required = schema.get("required", [])
        if required is not None:
            if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
                errors.append((path, "invalidRequiredSchema"))
            else:
                errors.extend((path + (item,), "required") for item in required if item not in instance)
        properties = schema.get("properties", {})
        if properties is not None:
            if not isinstance(properties, dict):
                errors.append((path, "invalidPropertiesSchema"))
            else:
                for key, subschema in properties.items():
                    if key in instance:
                        errors.extend(_profile_errors(instance[key], subschema, path + (key,)))
                extras = set(instance) - set(properties)
                additional = schema.get("additionalProperties", True)
                if additional is False:
                    errors.extend((path + (key,), "additionalProperties") for key in sorted(extras))
                elif isinstance(additional, dict):
                    for key in sorted(extras):
                        errors.extend(_profile_errors(instance[key], additional, path + (key,)))
                elif additional is not True:
                    errors.append((path, "invalidAdditionalPropertiesSchema"))

    if isinstance(instance, list):
        minimum_items = schema.get("minItems")
        if minimum_items is not None:
            if type(minimum_items) is not int or minimum_items < 0:
                errors.append((path, "invalidMinItemsSchema"))
            elif len(instance) < minimum_items:
                errors.append((path, "minItems"))
        if schema.get("uniqueItems") is True:
            seen: set[str] = set()
            for item in instance:
                marker = json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                if marker in seen:
                    errors.append((path, "uniqueItems"))
                    break
                seen.add(marker)
        if "items" in schema:
            for index, item in enumerate(instance):
                errors.extend(_profile_errors(item, schema["items"], path + (index,)))

    if isinstance(instance, str):
        minimum_length = schema.get("minLength")
        if minimum_length is not None:
            if type(minimum_length) is not int or minimum_length < 0:
                errors.append((path, "invalidMinLengthSchema"))
            elif len(instance) < minimum_length:
                errors.append((path, "minLength"))
        pattern = schema.get("pattern")
        if pattern is not None:
            try:
                if not isinstance(pattern, str) or re.search(pattern, instance) is None:
                    errors.append((path, "pattern"))
            except re.error:
                errors.append((path, "invalidPatternSchema"))
        format_name = schema.get("format")
        if format_name is not None:
            if format_name != "date-time":
                errors.append((path, f"unsupportedFormat:{format_name}"))
            elif not _valid_datetime(instance):
                errors.append((path, "format"))

    if (type(instance) is int or type(instance) is float) and "minimum" in schema:
        minimum = schema["minimum"]
        if (type(minimum) is not int and type(minimum) is not float) or instance < minimum:
            errors.append((path, "minimum"))

    for subschema in schema.get("allOf", []):
        errors.extend(_profile_errors(instance, subschema, path))
    if "oneOf" in schema:
        branches = schema["oneOf"]
        if not isinstance(branches, list) or sum(not _profile_errors(instance, branch, path) for branch in branches) != 1:
            errors.append((path, "oneOf"))
    if "if" in schema and not _profile_errors(instance, schema["if"], path):
        if "then" in schema:
            errors.extend(_profile_errors(instance, schema["then"], path))
    elif "else" in schema:
        errors.extend(_profile_errors(instance, schema["else"], path))
    return errors


def _schema_backend() -> str:
    force_builtin = os.environ.get("NF_FORCE_BUILTIN_SCHEMA_VALIDATOR") == "1"
    if not force_builtin and Draft202012Validator is not None and FormatChecker is not None:
        return "jsonschema-draft2020-12"
    if BUILTIN_SCHEMA_PROFILE_AVAILABLE:
        return "builtin-closed-schema-profile"
    return "unavailable"


def _schema_diagnostics(instance: Any, schema_path: Path, prefix: str) -> List[str]:
    try:
        schema = load_json(schema_path)
        backend = _schema_backend()
        if backend == "jsonschema-draft2020-12":
            validator = Draft202012Validator(schema, format_checker=FormatChecker())
            errors = sorted(validator.iter_errors(instance), key=lambda item: tuple(str(part) for part in item.absolute_path))
            return [
                f"{prefix}_schema:{'/'.join(str(part) for part in error.absolute_path) or '$'}:{error.validator}"
                for error in errors
            ]
        if backend == "builtin-closed-schema-profile":
            return [
                f"{prefix}_schema:{'/'.join(str(part) for part in path) or '$'}:{validator}"
                for path, validator in _profile_errors(instance, schema)
            ]
        return ["schema_validator_unavailable"]
    except Exception as exc:
        return [f"{prefix}_schema_load_error:{type(exc).__name__}"]


def _unique_strings(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(value for value in values if value))


def policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures = _schema_diagnostics(payload, POLICY_SCHEMA, "policy")
    # Manual semantic checks assume the schema-valid shapes declared below.
    # Any schema or schema-loader failure must stop here so malformed policy
    # values cannot reach set membership or iteration operations and raise.
    if failures:
        return failures
    policy = _policy(payload)
    if payload.get("apiVersion") != POLICY_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if payload.get("id") != "trusted-trigger-source-core":
        failures.append("policy_id_invalid")
    if str(payload.get("status") or "") not in VALID_STATUSES:
        failures.append("policy_status_invalid")
    if policy.get("required_requested_authority") != "create_work_item":
        failures.append("policy_required_requested_authority_invalid")
    if policy.get("enforcement_mode") not in {"shadow", "enforce"}:
        failures.append("policy_enforcement_mode_invalid")
    if policy.get("live_connector_integration_state") not in {"not_run", "pass"}:
        failures.append("policy_live_connector_integration_state_invalid")
    if not _strict_int(policy.get("max_verification_age_seconds")):
        failures.append("policy_max_verification_age_seconds_invalid")
    if type(policy.get("max_future_skew_seconds")) is not int or policy.get("max_future_skew_seconds") < 0:
        failures.append("policy_max_future_skew_seconds_invalid")

    controls = _dict(policy.get("controls"))
    for key in sorted(REQUIRED_CONTROLS):
        if controls.get(key) is not True:
            failures.append(f"policy_control_{key}_not_true")

    declared_codes = set(_strings(policy.get("reason_codes")))
    for code in sorted(RUNTIME_REASON_CODES - declared_codes):
        failures.append(f"policy_reason_code_missing:{code}")
    for code in sorted(declared_codes - RUNTIME_REASON_CODES):
        failures.append(f"policy_reason_code_unknown:{code}")

    refs = set(_strings(payload.get("refs")))
    for ref in sorted(REQUIRED_REFS - refs):
        failures.append(f"policy_ref_missing:{ref}")

    verifier_ids: set[str] = set()
    for item in policy.get("trusted_verifiers", []):
        if not isinstance(item, dict):
            continue
        verifier_id = str(item.get("verifier_id") or "")
        if verifier_id in verifier_ids:
            failures.append(f"policy_verifier_duplicate:{verifier_id}")
        verifier_ids.add(verifier_id)

    app_ids: set[int] = set()
    for item in policy.get("github_apps", []):
        if not isinstance(item, dict):
            continue
        app_id = item.get("app_id")
        if not _strict_int(app_id):
            failures.append("policy_github_app_id_invalid")
            continue
        if app_id in app_ids:
            failures.append(f"policy_github_app_duplicate:{app_id}")
        app_ids.add(app_id)
        installations = item.get("installation_ids")
        if not isinstance(installations, list) or not installations or any(not _strict_int(value) for value in installations):
            failures.append(f"policy_github_installations_invalid:{app_id}")
        elif len(set(installations)) != len(installations):
            failures.append(f"policy_github_installations_duplicate:{app_id}")
        event_types = _strings(item.get("allowed_event_types"))
        if not event_types:
            failures.append(f"policy_github_event_types_empty:{app_id}")
        elif len(set(event_types)) != len(event_types):
            failures.append(f"policy_github_event_types_duplicate:{app_id}")
    return _unique_strings(failures)


def _strict_nullable_integer_diagnostics(
    container: Dict[str, Any], keys: Iterable[str], prefix: str
) -> List[str]:
    failures: List[str] = []
    for key in keys:
        value = container.get(key)
        if value is not None and not _strict_int(value):
            failures.append(f"{prefix}:{key}:strictInteger")
    return failures


def envelope_failures(envelope: Dict[str, Any]) -> List[str]:
    failures = _schema_diagnostics(envelope, ENVELOPE_SCHEMA, "envelope")
    failures.extend(
        _strict_nullable_integer_diagnostics(
            _dict(envelope.get("actor")),
            ("app_id", "installation_id"),
            "envelope_schema:actor",
        )
    )
    return _unique_strings(failures)


def verification_context_failures(context: Dict[str, Any]) -> List[str]:
    failures = _schema_diagnostics(
        context, VERIFICATION_SCHEMA, "verification_context"
    )
    failures.extend(
        _strict_nullable_integer_diagnostics(
            _dict(context.get("bindings")),
            ("app_id", "installation_id"),
            "verification_context_schema:bindings",
        )
    )
    return _unique_strings(failures)


def decision_failures(decision: Dict[str, Any]) -> List[str]:
    return _schema_diagnostics(decision, DECISION_SCHEMA, "decision")


def _base_decision(envelope: Dict[str, Any], payload: Dict[str, Any], evaluated_at: datetime) -> Dict[str, Any]:
    actor = _dict(envelope.get("actor"))
    provenance = _dict(envelope.get("provenance"))
    policy = _policy(payload)
    return {
        "apiVersion": DECISION_VERSION,
        "kind": DECISION_KIND,
        "source_id": str(provenance.get("source_id") or ""),
        "evaluated_at": _format_datetime(evaluated_at),
        "policy": {
            "id": str(payload.get("id") or ""),
            "version": str(payload.get("version") or ""),
            "status": str(payload.get("status") or ""),
            "enforcement_mode": str(policy.get("enforcement_mode") or ""),
            "live_connector_integration_state": str(policy.get("live_connector_integration_state") or ""),
            "sha256": _canonical_sha256(payload),
        },
        "envelope_sha256": _canonical_sha256(envelope),
        "verification_context_sha256": None,
        "allowed": False,
        "trigger_authorized": False,
        "approval_authorized": False,
        "reason_codes": ["envelope_invalid"],
        "diagnostics": [],
        "actor_type": str(actor.get("type") or ""),
        "principal_id": str(actor.get("principal_id") or ""),
        "requested_authority": str(envelope.get("requested_authority") or ""),
        "verification": None,
    }


def _deny(decision: Dict[str, Any], reason: str, diagnostics: Iterable[str] = ()) -> Dict[str, Any]:
    decision["allowed"] = False
    decision["trigger_authorized"] = False
    decision["approval_authorized"] = False
    decision["reason_codes"] = [reason]
    decision["diagnostics"] = _unique_strings(diagnostics)
    return decision


def _verification_record(context: Dict[str, Any]) -> Dict[str, str]:
    verifier = _dict(context.get("verifier"))
    return {
        "verifier_id": str(verifier.get("id") or ""),
        "verifier_class": str(verifier.get("class") or ""),
        "evidence_id": str(verifier.get("evidence_id") or ""),
        "evidence_sha256": str(verifier.get("evidence_sha256") or ""),
        "verified_at": str(context.get("verified_at") or ""),
    }


def _binding_mismatches(envelope: Dict[str, Any], context: Dict[str, Any]) -> List[str]:
    actor = _dict(envelope.get("actor"))
    event = _dict(envelope.get("event"))
    provenance = _dict(envelope.get("provenance"))
    bindings = _dict(context.get("bindings"))
    comparisons = {
        "source_class": (context.get("source_class"), envelope.get("source_class")),
        "actor_principal_id": (bindings.get("actor_principal_id"), actor.get("principal_id")),
        "repository": (bindings.get("repository"), envelope.get("repository")),
        "event_type": (bindings.get("event_type"), event.get("type")),
        "delivery_id": (bindings.get("delivery_id"), event.get("delivery_id")),
        "provenance_source_id": (bindings.get("provenance_source_id"), provenance.get("source_id")),
        "message_id": (bindings.get("message_id"), provenance.get("message_id")),
        "app_id": (bindings.get("app_id"), actor.get("app_id")),
        "installation_id": (bindings.get("installation_id"), actor.get("installation_id")),
    }
    return [
        f"binding_mismatch:{name}"
        for name, (verified, claimed) in comparisons.items()
        if type(verified) is not type(claimed) or verified != claimed
    ]


def _find_verifier(policy: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    verifier = _dict(context.get("verifier"))
    verifier_id = verifier.get("id")
    verifier_class = verifier.get("class")
    for entry in policy.get("trusted_verifiers", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("verifier_id") == verifier_id and entry.get("verifier_class") == verifier_class:
            return entry
    return None


def _evaluate_trigger_at(
    payload: Dict[str, Any],
    envelope: Dict[str, Any],
    verification_context: Optional[Dict[str, Any]],
    *,
    evaluated_at: datetime,
) -> Dict[str, Any]:
    """Deterministic contract-test evaluator. Live callers must use evaluate_trigger()."""
    payload_obj = payload if isinstance(payload, dict) else {}
    envelope_obj = envelope if isinstance(envelope, dict) else {}
    now = _as_utc(evaluated_at)
    decision = _base_decision(envelope_obj, payload_obj, now)

    policy_errors = policy_failures(payload_obj)
    if policy_errors:
        reason = "schema_validator_unavailable" if "schema_validator_unavailable" in policy_errors else "policy_invalid"
        return _deny(decision, reason, policy_errors)

    policy = _policy(payload_obj)
    active = (
        payload_obj.get("status") == "stable"
        and policy.get("enforcement_mode") == "enforce"
        and policy.get("live_connector_integration_state") == "pass"
    )
    if not active:
        return _deny(
            decision,
            "policy_not_active",
            [
                f"policy_status:{payload_obj.get('status')}",
                f"enforcement_mode:{policy.get('enforcement_mode')}",
                f"live_connector_integration_state:{policy.get('live_connector_integration_state')}",
            ],
        )

    envelope_errors = envelope_failures(envelope_obj)
    if envelope_errors:
        return _deny(decision, "envelope_invalid", envelope_errors)

    actor = _dict(envelope_obj.get("actor"))
    event = _dict(envelope_obj.get("event"))
    provenance = _dict(envelope_obj.get("provenance"))

    if envelope_obj.get("requested_authority") != policy.get("required_requested_authority"):
        return _deny(decision, "requested_authority_not_trigger")
    if envelope_obj.get("content_origin") in set(_strings(policy.get("untrusted_content_origins"))):
        return _deny(decision, "content_origin_untrusted")
    if envelope_obj.get("repository") not in set(_strings(policy.get("repositories"))):
        return _deny(decision, "repository_not_allowlisted")
    if provenance.get("copied_text_claims_owner_authority") is True:
        return _deny(decision, "metadata_contradiction", ["copied_text_claims_owner_authority"])

    if verification_context is None:
        return _deny(decision, "verification_context_missing")
    context_obj = verification_context if isinstance(verification_context, dict) else {}
    context_errors = verification_context_failures(context_obj)
    if context_errors:
        return _deny(decision, "verification_context_invalid", context_errors)
    decision["verification_context_sha256"] = _canonical_sha256(context_obj)
    decision["verification"] = _verification_record(context_obj)
    verifier = _dict(context_obj.get("verifier"))

    try:
        verified_at = _parse_datetime(str(context_obj.get("verified_at") or ""))
    except ValueError:
        return _deny(
            decision,
            "verification_context_invalid",
            ["verification_context_datetime_parse_error"],
        )
    future_skew = int(policy.get("max_future_skew_seconds"))
    max_age = int(policy.get("max_verification_age_seconds"))
    delta_seconds = (now - verified_at).total_seconds()
    if delta_seconds < -future_skew:
        return _deny(decision, "verification_from_future", [f"age_seconds:{delta_seconds:.3f}"])
    if delta_seconds > max_age:
        return _deny(decision, "verification_stale", [f"age_seconds:{delta_seconds:.3f}"])

    verifier_entry = _find_verifier(policy, context_obj)
    if verifier_entry is None:
        return _deny(decision, "verifier_not_allowlisted")
    if envelope_obj.get("source_class") not in set(_strings(verifier_entry.get("allowed_source_classes"))):
        return _deny(decision, "verifier_not_allowlisted", ["source_class_not_allowed_for_verifier"])
    if envelope_obj.get("repository") not in set(_strings(verifier_entry.get("allowed_repositories"))):
        return _deny(decision, "verifier_not_allowlisted", ["repository_not_allowed_for_verifier"])

    mismatches = _binding_mismatches(envelope_obj, context_obj)
    if mismatches:
        return _deny(decision, "verification_binding_mismatch", mismatches)

    actor_type = actor.get("type")
    verifier_class = verifier.get("class")
    if actor_type == "owner":
        expected = (
            envelope_obj.get("source_class") == "explicit_owner_message"
            and envelope_obj.get("content_origin") == "explicit_owner_message"
            and event.get("type") == "owner_message"
            and event.get("delivery_id") is None
            and provenance.get("channel") == "conversation"
            and provenance.get("artifact_class") == "direct_request"
            and actor.get("app_id") is None
            and actor.get("installation_id") is None
            and verifier_class == "trusted_conversation_identity"
        )
        if not expected:
            return _deny(decision, "metadata_contradiction")
        if str(actor.get("principal_id")) not in set(_strings(policy.get("owner_principal_ids"))):
            return _deny(decision, "owner_principal_not_allowlisted")
        if not isinstance(provenance.get("message_id"), str) or not provenance.get("message_id"):
            return _deny(decision, "owner_message_metadata_missing")
        decision.update(
            allowed=True,
            trigger_authorized=True,
            approval_authorized=False,
            reason_codes=["allowed_explicit_owner_message"],
            diagnostics=[],
        )
        return decision

    if actor_type == "github_app":
        app_id = actor.get("app_id")
        installation_id = actor.get("installation_id")
        delivery_id = event.get("delivery_id")
        expected_channel = {
            "github_connector": "github_connector",
            "github_webhook_signature": "github_webhook",
        }.get(verifier_class)
        if expected_channel is None:
            return _deny(decision, "metadata_contradiction", ["verifier_class_not_github_event_verifier"])
        if provenance.get("channel") != expected_channel:
            return _deny(decision, "metadata_contradiction", ["verifier_channel_mismatch"])
        expected = (
            envelope_obj.get("source_class") == "github_app_event"
            and envelope_obj.get("content_origin") == "verified_github_event"
            and provenance.get("artifact_class") == "metadata"
        )
        if not expected:
            return _deny(decision, "metadata_contradiction")
        if not _strict_int(app_id) or not _strict_int(installation_id) or not isinstance(delivery_id, str) or not delivery_id:
            return _deny(decision, "github_app_metadata_missing")
        if actor.get("principal_id") != f"github-app:{app_id}":
            return _deny(decision, "verification_binding_mismatch", ["app_principal_id_not_canonical"])
        app_entry = next(
            (
                item
                for item in policy.get("github_apps", [])
                if isinstance(item, dict) and type(item.get("app_id")) is int and item.get("app_id") == app_id
            ),
            None,
        )
        if app_entry is None or installation_id not in app_entry.get("installation_ids", []):
            return _deny(decision, "github_app_not_allowlisted")
        if str(event.get("type")) not in set(_strings(app_entry.get("allowed_event_types"))):
            return _deny(decision, "event_type_not_allowlisted")
        decision.update(
            allowed=True,
            trigger_authorized=True,
            approval_authorized=False,
            reason_codes=["allowed_verified_github_app_event"],
            diagnostics=[],
        )
        return decision

    return _deny(decision, "actor_type_unsupported")


def evaluate_trigger(
    payload: Dict[str, Any],
    envelope: Dict[str, Any],
    verification_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate with the runtime-owned UTC clock. Callers cannot override time."""
    return _evaluate_trigger_at(
        payload,
        envelope,
        verification_context,
        evaluated_at=_utc_now(),
    )


def validate_policy_and_examples(payload: Dict[str, Any], examples: Dict[str, Any]) -> Dict[str, Any]:
    failures = policy_failures(payload)
    activation = _dict(examples.get("contract_test_activation"))
    test_payload = copy.deepcopy(payload)
    if activation != {
        "status": "stable",
        "enforcement_mode": "enforce",
        "live_connector_integration_state": "pass",
    }:
        failures.append("examples_contract_test_activation_invalid")
    else:
        test_payload["status"] = activation["status"]
        test_policy = _policy(test_payload)
        test_policy["enforcement_mode"] = activation["enforcement_mode"]
        test_policy["live_connector_integration_state"] = activation["live_connector_integration_state"]
    if examples.get("apiVersion") != EXAMPLE_VERSION:
        failures.append("examples_api_version_invalid")
    if examples.get("kind") != EXAMPLE_KIND:
        failures.append("examples_kind_invalid")
    raw_examples = examples.get("examples")
    if not isinstance(raw_examples, list) or not raw_examples:
        failures.append("examples_empty")
        raw_examples = []

    reports: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in raw_examples:
        if not isinstance(item, dict):
            failures.append("example_invalid")
            continue
        item_id = str(item.get("id") or "")
        if not item_id or item_id in seen_ids:
            failures.append("example_id_invalid_or_duplicate")
        seen_ids.add(item_id)
        envelope = item.get("envelope")
        context = item.get("verification_context")
        if not isinstance(envelope, dict):
            failures.append(f"example_envelope_invalid:{item_id}")
            continue
        try:
            item_evaluated_at = _parse_datetime(str(item.get("evaluated_at") or ""))
        except ValueError:
            failures.append(f"example_evaluated_at_invalid:{item_id}")
            continue
        decision = _evaluate_trigger_at(
            test_payload,
            envelope,
            context if isinstance(context, dict) else None,
            evaluated_at=item_evaluated_at,
        )
        decision_schema_errors = decision_failures(decision)
        if decision_schema_errors:
            failures.extend(f"example_decision_invalid:{item_id}:{error}" for error in decision_schema_errors)
        expected_allowed = item.get("expected_allowed") is True
        expected_reason = str(item.get("expected_reason") or "")
        ok = decision.get("allowed") is expected_allowed and expected_reason in decision.get("reason_codes", [])
        if not ok:
            failures.append(f"example_mismatch:{item_id}")
        reports.append({"id": item_id, "ok": ok, "decision": decision})

    return {
        "ok": not failures,
        "failures": _unique_strings(failures),
        "example_reports": reports,
        "summary": {
            "trigger_and_approval_separated": _dict(_policy(payload).get("controls")).get("trigger_authority_does_not_grant_approval") is True,
            "login_is_not_authority": _dict(_policy(payload).get("controls")).get("login_is_not_authority") is True,
            "verification_context_required": _dict(_policy(payload).get("controls")).get("verification_context_required") is True,
            "example_count": len(reports),
            "schema_backend": _schema_backend(),
            "default_policy_active": (
                payload.get("status") == "stable"
                and _policy(payload).get("enforcement_mode") == "enforce"
                and _policy(payload).get("live_connector_integration_state") == "pass"
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--examples", type=Path, default=DEFAULT_EXAMPLES)
    parser.add_argument("--event", type=Path)
    parser.add_argument("--verification-context", type=Path)
    args = parser.parse_args()
    payload = load_policy(args.policy)
    if args.event:
        context = load_json(args.verification_context) if args.verification_context else None
        report = evaluate_trigger(payload, load_json(args.event), context)
    else:
        report = validate_policy_and_examples(payload, load_examples(args.examples))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok", report.get("allowed", False)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
