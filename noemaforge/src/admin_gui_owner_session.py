#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/admin_gui_owner_session.py
Zone: gui/control-plane
Version: 0.33.0
Created: 2026-07-24
Modified: 2026-07-24
Purpose: Enforce one central owner-session boundary before every inventoried Admin GUI POST dispatch.
Inputs: Machine-readable mutation policy plus observed request path, headers, client address and active GUI session.
Outputs: Allow/deny decision and safe JSON denial response.
Side effects: Appends security audit records without cookies, bootstrap tokens or request bodies.
Tests: noemaforge/tests/test_trusted_trigger_integration.py
Notes: The guarded HTTP-server base is installed before AdminGuiServer is defined, covering exact and inline/prefix POST branches.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import functools
import hashlib
import http.server
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence
from urllib.parse import urlparse

from trusted_trigger_integration import (
    _client_is_loopback,
    _header,
    _host_header_is_loopback,
    _origin_is_loopback_or_absent,
)

POLICY_FILENAME = "admin-gui-mutation-policy.json"
BOOTSTRAP_ROUTE = "/api/session/owner-bootstrap"
_AUDIT_LOCK = threading.Lock()
_SERVER_BASE_LOCK = threading.Lock()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _headers(handler: Any) -> Dict[str, str]:
    raw = getattr(handler, "headers", None)
    if raw is None:
        return {}
    try:
        return {str(key): str(value) for key, value in raw.items()}
    except Exception:
        return {}


def _active_session_id(server: Any) -> str:
    try:
        return str(server._active_session_id())
    except Exception:
        return str(getattr(server, "current_session_id", "") or "unknown")


def _session_id_sha256(session_id: str) -> str:
    return hashlib.sha256(str(session_id).encode("utf-8")).hexdigest()


class AdminGuiMutationPolicy:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.document: Dict[str, Any] = {}
        self.policy_sha256 = ""
        self.valid = False
        self.error = ""
        self.unauthenticated_exact: frozenset[str] = frozenset()
        self.owner_required_exact: frozenset[str] = frozenset()
        self.owner_required_prefix: tuple[tuple[str, str], ...] = ()
        self._load()

    def _load(self) -> None:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise ValueError("policy root must be an object")
            if document.get("apiVersion") != "noemaforge.admin-gui-mutation-policy/v1":
                raise ValueError("unsupported apiVersion")
            if document.get("kind") != "AdminGuiMutationPolicy":
                raise ValueError("unsupported kind")
            inner = document.get("policy")
            if not isinstance(inner, dict):
                raise ValueError("policy must be an object")
            if inner.get("default_post_action") != "deny_unlisted":
                raise ValueError("default_post_action must be deny_unlisted")
            unauth = inner.get("unauthenticated_exact_routes")
            owner = inner.get("owner_required_exact_routes")
            prefixes = inner.get("owner_required_prefix_routes")
            if not isinstance(unauth, list) or not all(isinstance(item, str) and item.startswith("/") for item in unauth):
                raise ValueError("unauthenticated_exact_routes is invalid")
            if not isinstance(owner, list) or not all(isinstance(item, str) and item.startswith("/") for item in owner):
                raise ValueError("owner_required_exact_routes is invalid")
            parsed_prefixes = []
            if not isinstance(prefixes, list):
                raise ValueError("owner_required_prefix_routes is invalid")
            for item in prefixes:
                if not isinstance(item, dict):
                    raise ValueError("prefix route entry must be an object")
                prefix = str(item.get("prefix") or "")
                suffix = str(item.get("suffix") or "")
                if not prefix.startswith("/") or not suffix.startswith("/"):
                    raise ValueError("prefix route entry is invalid")
                parsed_prefixes.append((prefix, suffix))
            unauth_set = frozenset(unauth)
            owner_set = frozenset(owner)
            if BOOTSTRAP_ROUTE not in unauth_set:
                raise ValueError("owner bootstrap route must be unauthenticated")
            if unauth_set.intersection(owner_set):
                raise ValueError("route cannot be both unauthenticated and owner-required")
            self.document = document
            self.policy_sha256 = _canonical_sha256(document)
            self.unauthenticated_exact = unauth_set
            self.owner_required_exact = owner_set
            self.owner_required_prefix = tuple(parsed_prefixes)
            self.valid = True
        except Exception as exc:
            self.error = str(exc)
            self.valid = False

    def classify(self, path: str) -> str:
        if path in self.unauthenticated_exact:
            return "unauthenticated_exact"
        if path in self.owner_required_exact:
            return "owner_required_exact"
        for prefix, suffix in self.owner_required_prefix:
            if path.startswith(prefix) and path.endswith(suffix) and len(path) > len(prefix) + len(suffix):
                return "owner_required_prefix"
        return "unlisted"


class AdminGuiOwnerSessionGuard:
    def __init__(self, *, root: Path | str, data_root: Path | str):
        self.root = Path(root)
        self.data_root = Path(data_root)
        self.policy = AdminGuiMutationPolicy(self.root / "configs" / POLICY_FILENAME)
        self.audit_path = self.data_root / "admin-gui-owner-session" / "audit.jsonl"

    def _integration(self, handler: Any) -> Optional[Any]:
        try:
            from admin_gui_routes import session_routes

            return session_routes._trusted_trigger_integration(handler)  # noqa: SLF001
        except Exception:
            return None

    def _audit(self, report: Mapping[str, Any]) -> None:
        record = {
            "apiVersion": report.get("apiVersion"),
            "kind": report.get("kind"),
            "allowed": report.get("allowed"),
            "route": report.get("route"),
            "route_class": report.get("route_class"),
            "reason_codes": report.get("reason_codes"),
            "policy_sha256": report.get("policy_sha256"),
            "session_id_sha256": report.get("session_id_sha256"),
        }
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        with _AUDIT_LOCK:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())

    def evaluate(self, handler: Any, path: str) -> Dict[str, Any]:
        route = str(path or "")
        route_class = self.policy.classify(route) if self.policy.valid else "policy_unavailable"
        session_id = _active_session_id(handler.server)
        report: Dict[str, Any] = {
            "apiVersion": "noemaforge.admin-gui-owner-session-decision/v1",
            "kind": "AdminGuiOwnerSessionDecision",
            "allowed": False,
            "route": route,
            "route_class": route_class,
            "reason_codes": [],
            "policy_sha256": self.policy.policy_sha256 or None,
            "session_id_sha256": _session_id_sha256(session_id),
        }
        if not self.policy.valid:
            report["reason_codes"] = ["mutation_policy_unavailable"]
            self._audit(report)
            return report
        if route_class == "unauthenticated_exact":
            report["allowed"] = True
            report["reason_codes"] = ["owner_bootstrap_route"]
            self._audit(report)
            return report
        if route_class == "unlisted":
            report["reason_codes"] = ["mutation_route_not_inventoried"]
            self._audit(report)
            return report

        headers = _headers(handler)
        integration = self._integration(handler)
        checks = {
            "client_loopback": _client_is_loopback(getattr(handler, "client_address", ()) or ()),
            "host_loopback": _host_header_is_loopback(_header(headers, "Host")),
            "origin_loopback_or_absent": _origin_is_loopback_or_absent(_header(headers, "Origin")),
            "session_capability": bool(
                integration is not None
                and integration._owner_session_capability_valid(headers, session_id)  # noqa: SLF001
            ),
        }
        reasons = []
        if not checks["client_loopback"]:
            reasons.append("owner_client_not_loopback")
        if not checks["host_loopback"]:
            reasons.append("owner_host_not_loopback")
        if not checks["origin_loopback_or_absent"]:
            reasons.append("owner_origin_not_loopback")
        if not checks["session_capability"]:
            reasons.append("owner_session_capability_invalid")
        report["allowed"] = not reasons
        report["reason_codes"] = reasons or ["owner_session_authorized"]
        self._audit(report)
        return report


def _guard_for_handler(handler: Any) -> AdminGuiOwnerSessionGuard:
    server = handler.server
    current = getattr(server, "_admin_gui_owner_session_guard", None)
    if isinstance(current, AdminGuiOwnerSessionGuard):
        return current
    guard = AdminGuiOwnerSessionGuard(root=server.root, data_root=server.data_root)
    setattr(server, "_admin_gui_owner_session_guard", guard)
    return guard


def guard_post_request(handler: Any) -> bool:
    path = urlparse(str(getattr(handler, "path", ""))).path
    decision = _guard_for_handler(handler).evaluate(handler, path)
    if decision.get("allowed"):
        return True
    status = 503 if "mutation_policy_unavailable" in decision.get("reason_codes", []) else 403
    handler._send_json(
        {
            "ok": False,
            "error": "Admin GUI owner session required",
            "error_class": "admin_gui_owner_session_denied",
            "owner_session": decision,
        },
        status=status,
    )
    return False


def install_handler_guard(handler_class: type) -> None:
    if getattr(handler_class, "_noemaforge_owner_guard_installed", False):
        return
    original = handler_class.do_POST

    @functools.wraps(original)
    def guarded_do_post(self: Any) -> None:
        if not guard_post_request(self):
            return
        original(self)

    handler_class.do_POST = guarded_do_post
    handler_class._noemaforge_owner_guard_installed = True
    handler_class._noemaforge_owner_guard_original_do_post = original


def install_guarded_server_base() -> None:
    """Install a narrow server base before AdminGuiServer class construction.

    admin_gui_server imports admin_gui_routes after importing ThreadingHTTPServer
    but before defining AdminGuiServer. We replace both the stdlib symbol for
    future imports and the partially initialized module-local symbol. Other HTTP
    servers are unaffected because handler wrapping is enabled only for servers
    exposing the NoemaForge root/data_root boundary.
    """
    with _SERVER_BASE_LOCK:
        current = http.server.ThreadingHTTPServer
        if getattr(current, "_noemaforge_owner_guarded_base", False):
            guarded = current
        else:
            original = current

            class GuardedThreadingHTTPServer(original):
                _noemaforge_owner_guarded_base = True

                def __init__(self, *args: Any, **kwargs: Any):
                    super().__init__(*args, **kwargs)
                    if hasattr(self, "root") and hasattr(self, "data_root"):
                        install_handler_guard(self.RequestHandlerClass)

            GuardedThreadingHTTPServer.__name__ = "GuardedThreadingHTTPServer"
            guarded = GuardedThreadingHTTPServer
            http.server.ThreadingHTTPServer = guarded

        for module in list(sys.modules.values()):
            try:
                filename = str(getattr(module, "__file__", "") or "")
                local = getattr(module, "ThreadingHTTPServer", None)
            except Exception:
                continue
            if filename.endswith("admin_gui_server.py") and not getattr(local, "_noemaforge_owner_guarded_base", False):
                setattr(module, "ThreadingHTTPServer", guarded)
