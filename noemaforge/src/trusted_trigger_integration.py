#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/trusted_trigger_integration.py
Zone: release/package
Version: 0.33.0
Created: 2026-07-24
Modified: 2026-07-24
Purpose: Construct trusted trigger verification context only inside trusted ingress adapters and enforce replay-safe bounded work-item authorization.
Inputs: Server-owned conversation metadata or verified GitHub connector metadata plus an untrusted event payload.
Outputs: Integration gate reports containing schema-valid trusted-trigger decisions and audit hashes.
Side effects: Appends audit JSONL and records accepted GitHub delivery IDs in SQLite.
Tests: noemaforge/tests/test_trusted_trigger_integration.py
Notes: Raw request bodies can never provide TrustedTriggerVerificationContext; packaged policy activation remains a separate release gate.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import ipaddress
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence
from urllib.parse import urlparse

import trusted_trigger_source_runtime as tts

TRUSTED_CONTEXT_INJECTION_KEYS = frozenset(
    {
        "verification_context",
        "trusted_verification_context",
        "trusted_trigger_verification_context",
        "trusted_trigger_context",
        "trusted_source_context",
        "verifier_evidence",
    }
)
CONVERSATION_TRIGGER_PATHS = frozenset(
    {
        "/api/admin/message",
        "/api/admin/ask",
        "/api/admin/start",
        "/api/conversation/message",
        "/api/tasks/create",
    }
)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat().replace("+00:00", "Z")


def _strict_positive_int(value: Any) -> bool:
    return type(value) is int and value >= 1


def _string(value: Any) -> str:
    return str(value or "").strip()


def _header(headers: Mapping[str, Any], name: str) -> str:
    target = name.lower()
    for key, value in headers.items():
        if str(key).lower() == target:
            return _string(value)
    return ""


def _hostname_is_loopback(value: str) -> bool:
    host = _string(value).lower().rstrip(".")
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _host_header_is_loopback(value: str) -> bool:
    text = _string(value)
    if not text:
        return False
    try:
        parsed = urlparse("//" + text)
    except ValueError:
        return False
    return _hostname_is_loopback(parsed.hostname or "")


def _origin_is_loopback_or_absent(value: str) -> bool:
    text = _string(value)
    if not text:
        return True
    try:
        parsed = urlparse(text)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and _hostname_is_loopback(
        parsed.hostname or ""
    )


def _client_is_loopback(client_address: Sequence[Any]) -> bool:
    if not client_address:
        return False
    host = _string(client_address[0])
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def _extract_request_text(body: Mapping[str, Any]) -> str:
    for key in ("message", "text", "prompt", "title", "task", "request"):
        value = _string(body.get(key))
        if value:
            return value
    return ""


def _active(policy: Mapping[str, Any]) -> bool:
    inner = policy.get("policy") if isinstance(policy.get("policy"), dict) else {}
    return (
        policy.get("status") == "stable"
        and inner.get("enforcement_mode") == "enforce"
        and inner.get("live_connector_integration_state") == "pass"
    )


def _preview_policy(policy: Mapping[str, Any]) -> Dict[str, Any]:
    preview = copy.deepcopy(dict(policy))
    preview["status"] = "stable"
    inner = preview.get("policy") if isinstance(preview.get("policy"), dict) else {}
    inner["enforcement_mode"] = "enforce"
    inner["live_connector_integration_state"] = "pass"
    preview["policy"] = inner
    return preview


def _deny_existing_decision(
    decision: Mapping[str, Any], reason: str, diagnostics: Sequence[str]
) -> Dict[str, Any]:
    denied = copy.deepcopy(dict(decision))
    denied["allowed"] = False
    denied["trigger_authorized"] = False
    denied["approval_authorized"] = False
    denied["reason_codes"] = [reason]
    denied["diagnostics"] = list(
        dict.fromkeys(_string(item) for item in diagnostics if _string(item))
    )
    return denied


class ReplayStore:
    """Persistent duplicate-delivery guard with an atomic UNIQUE claim."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.path), timeout=10.0, isolation_level=None
        )
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS trusted_github_deliveries (
                    delivery_id TEXT PRIMARY KEY,
                    payload_sha256 TEXT NOT NULL,
                    repository TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    app_id INTEGER NOT NULL,
                    installation_id INTEGER NOT NULL,
                    claimed_at TEXT NOT NULL
                )
                """
            )

    def claim(
        self,
        *,
        delivery_id: str,
        payload_sha256: str,
        repository: str,
        event_type: str,
        app_id: int,
        installation_id: int,
    ) -> bool:
        with self._lock:
            try:
                with self._connect() as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute(
                        """
                        INSERT INTO trusted_github_deliveries (
                            delivery_id, payload_sha256, repository, event_type,
                            app_id, installation_id, claimed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            delivery_id,
                            payload_sha256,
                            repository,
                            event_type,
                            app_id,
                            installation_id,
                            _now_iso(),
                        ),
                    )
                    connection.execute("COMMIT")
                return True
            except sqlite3.IntegrityError:
                return False


class VerifiedGithubConnectorAdapter:
    """Capability-bound adapter returned only to the trusted connector owner."""

    def __init__(
        self, integration: "TrustedTriggerIntegration", capability: object
    ):
        self.__integration = integration
        self.__capability = capability

    def evaluate(
        self, metadata: Mapping[str, Any], payload: Any
    ) -> Dict[str, Any]:
        return self.__integration._github_connector_gate(  # noqa: SLF001
            metadata, payload, capability=self.__capability
        )


class TrustedTriggerIntegration:
    def __init__(
        self,
        *,
        state_dir: Path | str,
        policy_path: Path | str = tts.DEFAULT_POLICY,
        repository: str = "Sinev-Maksim/NoemaForge",
        owner_principal_id: str = "nf-owner:primary",
        policy_override: Optional[Mapping[str, Any]] = None,
    ):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.policy_path = Path(policy_path)
        self.repository = repository
        self.owner_principal_id = owner_principal_id
        self._policy_override = (
            copy.deepcopy(dict(policy_override))
            if policy_override is not None
            else None
        )
        self._connector_capability = object()
        self._audit_lock = threading.Lock()
        self.audit_path = self.state_dir / "trusted-trigger-audit.jsonl"
        self.replay_store = ReplayStore(
            self.state_dir / "github-deliveries.sqlite3"
        )

    def bind_github_connector(self) -> VerifiedGithubConnectorAdapter:
        """Return a capability-bound callable; no HTTP/body field can mint it."""
        return VerifiedGithubConnectorAdapter(self, self._connector_capability)

    def _load_policy(self) -> Dict[str, Any]:
        if self._policy_override is not None:
            return copy.deepcopy(self._policy_override)
        return tts.load_policy(self.policy_path)

    def _append_audit(self, record: Mapping[str, Any]) -> None:
        safe_record = dict(record)
        safe_record.setdefault("recorded_at", _now_iso())
        line = json.dumps(safe_record, ensure_ascii=False, sort_keys=True) + "\n"
        with self._audit_lock:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())

    def _finalize_gate(
        self,
        *,
        source_kind: str,
        policy: Mapping[str, Any],
        envelope: Optional[Mapping[str, Any]],
        context: Optional[Mapping[str, Any]],
        actual_decision: Optional[Mapping[str, Any]],
        preview_decision: Optional[Mapping[str, Any]],
        hard_deny: bool = False,
        integration_reason: str = "",
        diagnostics: Sequence[str] = (),
    ) -> Dict[str, Any]:
        enforcement_active = _active(policy)
        actual_allowed = bool(
            actual_decision and actual_decision.get("allowed") is True
        )
        would_authorize = bool(
            preview_decision and preview_decision.get("allowed") is True
        )
        proceed = actual_allowed if enforcement_active else not hard_deny
        reason_codes = list(
            (actual_decision or preview_decision or {}).get("reason_codes") or []
        )
        if integration_reason:
            reason_codes = [integration_reason]
        report = {
            "apiVersion": "noemaforge.trusted-trigger-integration-gate/v1",
            "kind": "TrustedTriggerIntegrationGate",
            "source_kind": source_kind,
            "recorded_at": _now_iso(),
            "enforcement_active": enforcement_active,
            "proceed": proceed,
            "hard_deny": hard_deny,
            "would_authorize_if_activated": would_authorize,
            "reason_codes": reason_codes,
            "diagnostics": list(
                dict.fromkeys(
                    _string(item) for item in diagnostics if _string(item)
                )
            ),
            "policy_sha256": _canonical_sha256(policy),
            "envelope_sha256": (
                _canonical_sha256(envelope) if envelope is not None else None
            ),
            "verification_context_sha256": (
                _canonical_sha256(context) if context is not None else None
            ),
            "actual_decision": (
                copy.deepcopy(dict(actual_decision))
                if actual_decision is not None
                else None
            ),
            "shadow_preview_decision": (
                copy.deepcopy(dict(preview_decision))
                if preview_decision is not None
                else None
            ),
        }
        self._append_audit(
            {
                key: value
                for key, value in report.items()
                if key not in {"actual_decision", "shadow_preview_decision"}
            }
            | {
                "actual_reason_codes": list(
                    (actual_decision or {}).get("reason_codes") or []
                ),
                "preview_reason_codes": list(
                    (preview_decision or {}).get("reason_codes") or []
                ),
            }
        )
        return report

    def public_summary(self, gate: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            key: copy.deepcopy(gate.get(key))
            for key in (
                "apiVersion",
                "kind",
                "source_kind",
                "recorded_at",
                "enforcement_active",
                "proceed",
                "hard_deny",
                "would_authorize_if_activated",
                "reason_codes",
                "diagnostics",
                "policy_sha256",
                "envelope_sha256",
                "verification_context_sha256",
            )
        }

    def record_work_item(
        self, gate: Mapping[str, Any], task_id: str
    ) -> None:
        self._append_audit(
            {
                "apiVersion": "noemaforge.trusted-trigger-work-item-link/v1",
                "kind": "TrustedTriggerWorkItemLink",
                "task_id": _string(task_id),
                "source_kind": gate.get("source_kind"),
                "policy_sha256": gate.get("policy_sha256"),
                "envelope_sha256": gate.get("envelope_sha256"),
                "verification_context_sha256": gate.get(
                    "verification_context_sha256"
                ),
            }
        )

    def conversation_http_gate(
        self,
        *,
        body: Mapping[str, Any],
        headers: Mapping[str, Any],
        client_address: Sequence[Any],
        route: str,
        session_id: str,
    ) -> Dict[str, Any]:
        policy = self._load_policy()
        injected = sorted(
            TRUSTED_CONTEXT_INJECTION_KEYS.intersection(body.keys())
        )
        if injected:
            return self._finalize_gate(
                source_kind="conversation",
                policy=policy,
                envelope=None,
                context=None,
                actual_decision=None,
                preview_decision=None,
                hard_deny=True,
                integration_reason="metadata_contradiction",
                diagnostics=[
                    f"trusted_context_injection_attempt:{key}"
                    for key in injected
                ],
            )

        request_text = _extract_request_text(body)
        request_id = "msg-" + uuid.uuid4().hex
        source_id = (
            f"conversation:{_string(session_id) or 'unknown'}:{request_id}"
        )
        envelope = {
            "apiVersion": tts.ENVELOPE_VERSION,
            "kind": tts.ENVELOPE_KIND,
            "source_class": "explicit_owner_message",
            "content_origin": "explicit_owner_message",
            "actor": {
                "type": "owner",
                "principal_id": self.owner_principal_id,
                "login": None,
                "app_id": None,
                "installation_id": None,
            },
            "repository": self.repository,
            "event": {"type": "owner_message", "delivery_id": None},
            "provenance": {
                "source_id": source_id,
                "channel": "conversation",
                "artifact_class": "direct_request",
                "message_id": request_id,
                "copied_text_claims_owner_authority": False,
            },
            "requested_authority": "create_work_item",
        }
        route_valid = route in CONVERSATION_TRIGGER_PATHS
        connection_valid = _client_is_loopback(client_address)
        host_valid = _host_header_is_loopback(_header(headers, "Host"))
        origin_valid = _origin_is_loopback_or_absent(
            _header(headers, "Origin")
        )
        identity_valid = bool(
            request_text
            and route_valid
            and connection_valid
            and host_valid
            and origin_valid
        )
        context: Optional[Dict[str, Any]] = None
        diagnostics = []
        if not request_text:
            diagnostics.append("owner_message_empty")
        if not route_valid:
            diagnostics.append("owner_route_not_allowlisted")
        if not connection_valid:
            diagnostics.append("owner_client_not_loopback")
        if not host_valid:
            diagnostics.append("owner_host_not_loopback")
        if not origin_valid:
            diagnostics.append("owner_origin_not_loopback")
        if identity_valid:
            evidence = {
                "session_id_sha256": hashlib.sha256(
                    _string(session_id).encode("utf-8")
                ).hexdigest(),
                "route": route,
                "client": _string(client_address[0]),
                "host": _header(headers, "Host"),
                "origin": _header(headers, "Origin"),
                "request_body_sha256": _canonical_sha256(dict(body)),
                "message_id": request_id,
            }
            context = {
                "apiVersion": tts.VERIFICATION_VERSION,
                "kind": tts.VERIFICATION_KIND,
                "source_class": "explicit_owner_message",
                "verifier": {
                    "id": "nf-conversation-owner-verifier",
                    "class": "trusted_conversation_identity",
                    "verified": True,
                    "evidence_id": (
                        f"gui-session:{evidence['session_id_sha256']}:{request_id}"
                    ),
                    "evidence_sha256": _canonical_sha256(evidence),
                },
                "bindings": {
                    "actor_principal_id": self.owner_principal_id,
                    "repository": self.repository,
                    "event_type": "owner_message",
                    "delivery_id": None,
                    "provenance_source_id": source_id,
                    "message_id": request_id,
                    "app_id": None,
                    "installation_id": None,
                },
                "verified_at": _now_iso(),
            }
        actual = tts.evaluate_trigger(policy, envelope, context)
        preview = tts.evaluate_trigger(_preview_policy(policy), envelope, context)
        return self._finalize_gate(
            source_kind="conversation",
            policy=policy,
            envelope=envelope,
            context=context,
            actual_decision=actual,
            preview_decision=preview,
            hard_deny=False,
            diagnostics=diagnostics,
        )

    def _github_connector_gate(
        self,
        metadata: Mapping[str, Any],
        payload: Any,
        *,
        capability: object,
    ) -> Dict[str, Any]:
        policy = self._load_policy()
        injected = sorted(
            TRUSTED_CONTEXT_INJECTION_KEYS.intersection(metadata.keys())
        )
        if injected:
            return self._finalize_gate(
                source_kind="github_connector",
                policy=policy,
                envelope=None,
                context=None,
                actual_decision=None,
                preview_decision=None,
                hard_deny=True,
                integration_reason="metadata_contradiction",
                diagnostics=[
                    f"trusted_context_injection_attempt:{key}"
                    for key in injected
                ],
            )
        if capability is not self._connector_capability:
            return self._finalize_gate(
                source_kind="github_connector",
                policy=policy,
                envelope=None,
                context=None,
                actual_decision=None,
                preview_decision=None,
                hard_deny=True,
                integration_reason="verifier_not_allowlisted",
                diagnostics=["connector_capability_invalid"],
            )

        app_id = metadata.get("app_id")
        installation_id = metadata.get("installation_id")
        repository = _string(metadata.get("repository"))
        event_type = _string(metadata.get("event_type"))
        delivery_id = _string(metadata.get("delivery_id"))
        verified_at = _string(metadata.get("verified_at")) or _now_iso()
        claimed_payload_sha256 = _string(
            metadata.get("payload_sha256")
        ).lower()
        actual_payload_sha256 = _canonical_sha256(payload)
        malformed = []
        if not _strict_positive_int(app_id):
            malformed.append("github_app_id_invalid")
        if not _strict_positive_int(installation_id):
            malformed.append("github_installation_id_invalid")
        if not repository:
            malformed.append("github_repository_missing")
        if not event_type:
            malformed.append("github_event_type_missing")
        if not delivery_id:
            malformed.append("github_delivery_id_missing")
        if len(claimed_payload_sha256) != 64 or any(
            ch not in "0123456789abcdef"
            for ch in claimed_payload_sha256
        ):
            malformed.append("github_payload_digest_invalid")
        if malformed:
            return self._finalize_gate(
                source_kind="github_connector",
                policy=policy,
                envelope=None,
                context=None,
                actual_decision=None,
                preview_decision=None,
                hard_deny=True,
                integration_reason="github_app_metadata_missing",
                diagnostics=malformed,
            )
        if not hmac.compare_digest(
            claimed_payload_sha256, actual_payload_sha256
        ):
            return self._finalize_gate(
                source_kind="github_connector",
                policy=policy,
                envelope=None,
                context=None,
                actual_decision=None,
                preview_decision=None,
                hard_deny=True,
                integration_reason="verification_binding_mismatch",
                diagnostics=["payload_digest_mismatch"],
            )

        principal_id = f"github-app:{app_id}"
        source_id = f"github:delivery:{delivery_id}"
        envelope = {
            "apiVersion": tts.ENVELOPE_VERSION,
            "kind": tts.ENVELOPE_KIND,
            "source_class": "github_app_event",
            "content_origin": "verified_github_event",
            "actor": {
                "type": "github_app",
                "principal_id": principal_id,
                "login": _string(metadata.get("app_login")) or None,
                "app_id": app_id,
                "installation_id": installation_id,
            },
            "repository": repository,
            "event": {"type": event_type, "delivery_id": delivery_id},
            "provenance": {
                "source_id": source_id,
                "channel": "github_connector",
                "artifact_class": "metadata",
                "message_id": None,
                "copied_text_claims_owner_authority": False,
            },
            "requested_authority": "create_work_item",
        }
        evidence = {
            "app_id": app_id,
            "installation_id": installation_id,
            "repository": repository,
            "event_type": event_type,
            "delivery_id": delivery_id,
            "payload_sha256": actual_payload_sha256,
            "verified_at": verified_at,
            "connector_evidence_id": (
                _string(metadata.get("connector_evidence_id"))
                or f"github-delivery:{delivery_id}"
            ),
        }
        context = {
            "apiVersion": tts.VERIFICATION_VERSION,
            "kind": tts.VERIFICATION_KIND,
            "source_class": "github_app_event",
            "verifier": {
                "id": "nf-github-connector-verifier",
                "class": "github_connector",
                "verified": True,
                "evidence_id": evidence["connector_evidence_id"],
                "evidence_sha256": _canonical_sha256(evidence),
            },
            "bindings": {
                "actor_principal_id": principal_id,
                "repository": repository,
                "event_type": event_type,
                "delivery_id": delivery_id,
                "provenance_source_id": source_id,
                "message_id": None,
                "app_id": app_id,
                "installation_id": installation_id,
            },
            "verified_at": verified_at,
        }
        actual = tts.evaluate_trigger(policy, envelope, context)
        preview = tts.evaluate_trigger(_preview_policy(policy), envelope, context)
        if _active(policy) and actual.get("allowed") is True:
            claimed = self.replay_store.claim(
                delivery_id=delivery_id,
                payload_sha256=actual_payload_sha256,
                repository=repository,
                event_type=event_type,
                app_id=app_id,
                installation_id=installation_id,
            )
            if not claimed:
                actual = _deny_existing_decision(
                    actual,
                    "metadata_contradiction",
                    ["replayed_delivery"],
                )
        return self._finalize_gate(
            source_kind="github_connector",
            policy=policy,
            envelope=envelope,
            context=context,
            actual_decision=actual,
            preview_decision=preview,
            diagnostics=[],
        )
