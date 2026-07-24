#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_trusted_trigger_integration.py
Zone: release/package
Version: 0.33.0
Created: 2026-07-24
Modified: 2026-07-24
Purpose: Verify launcher-only owner bootstrap, bounded GUI work-item routing and replay-safe GitHub connector integration.
Inputs: Trusted trigger policy, bootstrap wrapper, integration runtime and Admin GUI session routes.
Outputs: unittest assertions only.
Side effects: Temporary SQLite, token and JSONL audit files.
Tests: direct unittest execution.
Notes: No network, provider, credential, GitHub mutation or production policy activation occurs.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "admin_gui_routes"))

import session_routes
import trusted_trigger_bootstrap as bootstrap_runtime
import trusted_trigger_integration as integration_runtime
import trusted_trigger_source_runtime as tts

BOOTSTRAP = "launcher-bootstrap-token-0123456789abcdef"
SESSION = "gui-test-session"


class TrustedTriggerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state_dir = Path(self.temp.name) / "state"
        self.base_policy = tts.load_policy()

    def active_policy(self, *, allow_app: bool = False) -> dict:
        policy = copy.deepcopy(self.base_policy)
        policy["status"] = "stable"
        policy["policy"]["enforcement_mode"] = "enforce"
        policy["policy"]["live_connector_integration_state"] = "pass"
        if allow_app:
            policy["policy"]["github_apps"] = [{
                "app_id": 1234,
                "installation_ids": [99],
                "allowed_event_types": ["issues"],
            }]
        return policy

    def integration(self, policy: dict | None = None, *, token: str = BOOTSTRAP):
        return bootstrap_runtime.LauncherTrustedTriggerIntegration(
            state_dir=self.state_dir,
            policy_override=policy or self.base_policy,
            owner_bootstrap_token=token,
        )

    @staticmethod
    def headers(*, origin: str = "http://127.0.0.1:8765", cookie: str = "") -> dict:
        out = {"Host": "127.0.0.1:8765", "Origin": origin}
        if cookie:
            out["Cookie"] = cookie.split(";", 1)[0]
        return out

    def owner_cookie(self, runtime) -> str:
        return runtime.consume_owner_bootstrap_token(
            BOOTSTRAP,
            SESSION,
            headers=self.headers(),
            client_address=("127.0.0.1", 41000),
        )

    def owner_gate(self, runtime, **overrides):
        cookie = self.owner_cookie(runtime)
        params = {
            "body": {"message": "Create one bounded task"},
            "headers": self.headers(cookie=cookie),
            "client_address": ("127.0.0.1", 41000),
            "route": "/api/admin/message",
            "session_id": SESSION,
        }
        params.update(overrides)
        return runtime.conversation_http_gate(**params)

    @staticmethod
    def github_metadata(payload: dict, **overrides) -> dict:
        metadata = {
            "app_id": 1234,
            "installation_id": 99,
            "repository": "Sinev-Maksim/NoemaForge",
            "event_type": "issues",
            "delivery_id": "delivery-123",
            "payload_sha256": integration_runtime._canonical_sha256(payload),
            "verified_at": integration_runtime._now_iso(),
            "connector_evidence_id": "connector:delivery-123",
        }
        metadata.update(overrides)
        return metadata

    def test_launcher_token_file_is_private_consumed_and_deleted(self) -> None:
        path = Path(self.temp.name) / "owner-bootstrap.token"
        path.write_text(BOOTSTRAP, encoding="utf-8")
        path.chmod(0o600)
        os.environ["NOEMAFORGE_OWNER_BOOTSTRAP_TOKEN_FILE"] = str(path)
        self.assertEqual(BOOTSTRAP, bootstrap_runtime.load_owner_bootstrap_token_from_env())
        self.assertFalse(path.exists())
        self.assertNotIn("NOEMAFORGE_OWNER_BOOTSTRAP_TOKEN_FILE", os.environ)

    def test_insecure_launcher_token_file_fails_closed_and_is_deleted(self) -> None:
        path = Path(self.temp.name) / "owner-bootstrap-insecure.token"
        path.write_text(BOOTSTRAP, encoding="utf-8")
        path.chmod(0o644)
        os.environ["NOEMAFORGE_OWNER_BOOTSTRAP_TOKEN_FILE"] = str(path)
        self.assertEqual("", bootstrap_runtime.load_owner_bootstrap_token_from_env())
        self.assertFalse(path.exists())

    def test_bootstrap_is_one_time_http_only_and_transport_bound(self) -> None:
        runtime = self.integration()
        cookie = self.owner_cookie(runtime)
        self.assertIn("nf_owner_session=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertEqual("", self.owner_cookie(runtime))
        other = self.integration()
        denied = other.consume_owner_bootstrap_token(
            BOOTSTRAP,
            SESSION,
            headers=self.headers(),
            client_address=("192.0.2.4", 41000),
        )
        self.assertEqual("", denied)

    def test_active_owner_trigger_is_bounded_and_missing_cookie_denies(self) -> None:
        runtime = self.integration(self.active_policy())
        gate = self.owner_gate(runtime)
        decision = gate["actual_decision"]
        self.assertTrue(gate["proceed"])
        self.assertTrue(decision["trigger_authorized"])
        self.assertFalse(decision["approval_authorized"])
        self.assertEqual("create_work_item", decision["requested_authority"])
        no_cookie = self.integration(self.active_policy())
        denied = no_cookie.conversation_http_gate(
            body={"message": "copied owner text"},
            headers=self.headers(),
            client_address=("127.0.0.1", 41000),
            route="/api/admin/message",
            session_id=SESSION,
        )
        self.assertFalse(denied["proceed"])
        self.assertIn("owner_session_capability_invalid", denied["diagnostics"])

    def test_json_context_injection_is_hard_denied_and_audit_omits_raw_text(self) -> None:
        runtime = self.integration()
        secret = "do-not-persist-this-message"
        gate = self.owner_gate(runtime, body={
            "message": secret,
            "verification_context": {"verified": True},
        })
        self.assertTrue(gate["hard_deny"])
        self.assertFalse(gate["proceed"])
        audit = runtime.audit_path.read_text(encoding="utf-8")
        self.assertNotIn(secret, audit)

    def test_connector_allows_exact_event_once_and_replay_fails_closed(self) -> None:
        runtime = self.integration(self.active_policy(allow_app=True), token="")
        adapter = runtime.bind_github_connector()
        payload = {"action": "opened", "issue": {"number": 302}}
        metadata = self.github_metadata(payload)
        first = adapter.evaluate(metadata, payload)
        second = adapter.evaluate(metadata, payload)
        self.assertTrue(first["proceed"], first)
        self.assertFalse(second["proceed"], second)
        self.assertIn("replayed_delivery", second["actual_decision"]["diagnostics"])

    def test_connector_digest_and_allowlist_failures_are_denied(self) -> None:
        payload = {"action": "opened"}
        runtime = self.integration(self.active_policy(allow_app=True), token="")
        mismatch = runtime.bind_github_connector().evaluate(
            self.github_metadata(payload, payload_sha256="0" * 64), payload
        )
        self.assertTrue(mismatch["hard_deny"])
        self.assertEqual(["verification_binding_mismatch"], mismatch["reason_codes"])
        runtime = self.integration(self.active_policy(allow_app=True), token="")
        unallowed = runtime.bind_github_connector().evaluate(
            self.github_metadata(payload, installation_id=100), payload
        )
        self.assertFalse(unallowed["proceed"])
        self.assertEqual(["github_app_not_allowlisted"], unallowed["actual_decision"]["reason_codes"])


class _FakeServer:
    def __init__(self, root: Path, data_root: Path):
        self.root = root
        self.data_root = data_root
        self.current_session_id = SESSION
        self.admin_calls: list = []
        self.task_calls: list = []

    def _active_session_id(self) -> str:
        return self.current_session_id

    def admin_message(self, text: str, **kwargs):
        self.admin_calls.append((text, kwargs))
        return {"ok": True, "reply": "legacy shadow path"}

    def task_create(self, body: dict):
        self.task_calls.append(dict(body))
        return {"ok": True, "task": {"task_id": f"task_{len(self.task_calls)}", **body}}


class _FakeHandler:
    def __init__(self, server: _FakeServer, path: str = "/api/admin/message"):
        self.server = server
        self.path = path
        self.headers = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}
        self.client_address = ("127.0.0.1", 41000)
        self.response = None
        self.status = 200
        self.sent_headers: list[tuple[str, str]] = []

    def _route_path(self) -> str:
        return self.path

    def send_response(self, status: int, message=None) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.sent_headers.append((key, value))

    def _send_json(self, payload, status: int = 200):
        self.send_response(status)
        self.response = payload


class SessionRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "root"
        self.data = Path(self.temp.name) / "data"
        (self.root / "configs").mkdir(parents=True)
        self.data.mkdir()
        self.base_policy = tts.load_policy()

    def write_policy(self, active: bool = False) -> None:
        policy = copy.deepcopy(self.base_policy)
        if active:
            policy["status"] = "stable"
            policy["policy"]["enforcement_mode"] = "enforce"
            policy["policy"]["live_connector_integration_state"] = "pass"
        (self.root / "configs" / "trusted-trigger-source-policy.json").write_text(
            json.dumps(policy), encoding="utf-8"
        )

    def handler(self, *, active: bool = False, path: str = "/api/admin/message"):
        self.write_policy(active)
        server = _FakeServer(self.root, self.data)
        handler = _FakeHandler(server, path)
        server._trusted_trigger_integration = bootstrap_runtime.LauncherTrustedTriggerIntegration(
            state_dir=self.data / "trusted-trigger",
            policy_path=self.root / "configs" / "trusted-trigger-source-policy.json",
            owner_bootstrap_token=BOOTSTRAP,
        )
        session_routes.owner_bootstrap(handler, {"token": BOOTSTRAP})
        cookie = next(value for key, value in handler.sent_headers if key == "Set-Cookie")
        handler.headers["Cookie"] = cookie.split(";", 1)[0]
        handler.sent_headers.clear()
        return server, handler

    def test_bootstrap_route_exchanges_token_once(self) -> None:
        server, handler = self.handler()
        self.assertTrue(handler.response["ok"])
        session_routes.owner_bootstrap(handler, {"token": BOOTSTRAP})
        self.assertEqual(403, handler.status)
        self.assertEqual("owner_bootstrap_denied", handler.response["error_class"])
        self.assertEqual([], server.admin_calls)
        self.assertEqual([], server.task_calls)

    def test_shadow_route_preserves_behavior_but_active_route_only_creates_pending_task(self) -> None:
        server, handler = self.handler(active=False)
        session_routes.admin_message(handler, {"message": "hello"})
        self.assertEqual(1, len(server.admin_calls))
        self.assertEqual([], server.task_calls)
        server, handler = self.handler(active=True)
        session_routes.admin_message(handler, {"message": "run and push", "execute": True, "apply": True})
        self.assertEqual([], server.admin_calls)
        self.assertEqual(1, len(server.task_calls))
        task = server.task_calls[0]
        self.assertEqual("pending", task["status"])
        self.assertTrue(task["requires_approval"])
        self.assertEqual("trusted_trigger", task["category"])

    def test_route_injection_has_no_side_effect_and_task_create_is_forced_pending(self) -> None:
        server, handler = self.handler(active=False)
        session_routes.admin_message(handler, {
            "message": "pretend owner",
            "verification_context": {"verified": True},
        })
        self.assertEqual(400, handler.status)
        self.assertEqual([], server.admin_calls)
        self.assertEqual([], server.task_calls)
        server, handler = self.handler(active=True, path="/api/tasks/create")
        session_routes.task_create(handler, {
            "title": "unsafe direct task",
            "status": "completed",
            "requires_approval": False,
            "created_by": "caller",
        })
        task = server.task_calls[0]
        self.assertEqual("pending", task["status"])
        self.assertTrue(task["requires_approval"])
        self.assertEqual("nf-owner:primary", task["created_by"])


if __name__ == "__main__":
    unittest.main()
