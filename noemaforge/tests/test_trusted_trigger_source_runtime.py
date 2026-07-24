#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_trusted_trigger_source_runtime.py
Zone: release/package
Version: 0.33.0
Created: 2026-07-21
Modified: 2026-07-23
Purpose: Unit-test trusted trigger-source decisions, verifier binding, schema enforcement, and authority separation.
Inputs: Trusted trigger-source policy, schemas and example fixtures.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import trusted_trigger_source_runtime as tts


class TrustedTriggerSourceRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_policy = tts.load_policy()
        self.policy = copy.deepcopy(self.base_policy)
        self.policy["status"] = "stable"
        self.policy["policy"]["enforcement_mode"] = "enforce"
        self.policy["policy"]["live_connector_integration_state"] = "pass"
        self.examples = tts.load_examples()
        self.owner_item = copy.deepcopy(self.examples["examples"][0])
        self.owner = self.owner_item["envelope"]
        self.owner_context = self.owner_item["verification_context"]
        self.evaluated_at = tts._parse_datetime(self.owner_item["evaluated_at"])
        self.app_item = copy.deepcopy(self.examples["examples"][3])

    def allow_app(self) -> dict:
        policy = copy.deepcopy(self.policy)
        policy["policy"]["github_apps"] = [
            {"app_id": 1234, "installation_ids": [99], "allowed_event_types": ["issues"]}
        ]
        return policy

    def evaluate(self, policy: dict, envelope: dict, context: dict | None = None, *, evaluated_at=None) -> dict:
        return tts._evaluate_trigger_at(
            policy, envelope, context, evaluated_at=evaluated_at or self.evaluated_at
        )

    def test_policy_and_all_contract_schemas_are_explicit(self) -> None:
        for path in [tts.POLICY_SCHEMA, tts.ENVELOPE_SCHEMA, tts.VERIFICATION_SCHEMA, tts.DECISION_SCHEMA]:
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
            self.assertFalse(schema["additionalProperties"])
        self.assertTrue(tts.REQUIRED_REFS.issubset(set(self.policy["refs"])))

    def test_policy_and_examples_validate(self) -> None:
        report = tts.validate_policy_and_examples(self.base_policy, self.examples)
        self.assertTrue(report["ok"], report["failures"])
        self.assertTrue(report["summary"]["verification_context_required"])
        self.assertTrue(report["summary"]["trigger_and_approval_separated"])
        self.assertTrue(report["summary"]["login_is_not_authority"])
        self.assertFalse(report["summary"]["default_policy_active"])

    def test_owner_trigger_never_grants_approval(self) -> None:
        decision = self.evaluate(self.policy, self.owner, self.owner_context)
        self.assertTrue(decision["allowed"], decision)
        self.assertTrue(decision["trigger_authorized"])
        self.assertFalse(decision["approval_authorized"])
        self.assertFalse(tts.decision_failures(decision))

    def test_raw_envelope_without_verification_context_is_denied(self) -> None:
        decision = self.evaluate(self.policy, self.owner)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["verification_context_missing"], decision["reason_codes"])

    def test_unallowlisted_verifier_is_denied(self) -> None:
        context = copy.deepcopy(self.owner_context)
        context["verifier"]["id"] = "attacker-verifier"
        decision = self.evaluate(self.policy, self.owner, context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["verifier_not_allowlisted"], decision["reason_codes"])

    def test_spoofed_owner_login_without_principal_is_denied(self) -> None:
        envelope = copy.deepcopy(self.owner)
        envelope["actor"]["login"] = "Sinev-Maksim"
        envelope["actor"]["principal_id"] = "attacker:copied-login"
        decision = self.evaluate(self.policy, envelope, self.owner_context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["verification_binding_mismatch"], decision["reason_codes"])

    def test_owner_login_is_not_used_as_authority(self) -> None:
        envelope = copy.deepcopy(self.owner)
        envelope["actor"]["login"] = "display-name-changed"
        decision = self.evaluate(self.policy, envelope, self.owner_context)
        self.assertTrue(decision["allowed"], decision)

    def test_owner_principal_not_allowlisted_is_denied_after_consistent_binding(self) -> None:
        envelope = copy.deepcopy(self.owner)
        context = copy.deepcopy(self.owner_context)
        envelope["actor"]["principal_id"] = "nf-owner:other"
        context["bindings"]["actor_principal_id"] = "nf-owner:other"
        decision = self.evaluate(self.policy, envelope, context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["owner_principal_not_allowlisted"], decision["reason_codes"])

    def test_owner_message_binding_mismatch_is_denied(self) -> None:
        context = copy.deepcopy(self.owner_context)
        context["bindings"]["message_id"] = "msg-other"
        decision = self.evaluate(self.policy, self.owner, context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["verification_binding_mismatch"], decision["reason_codes"])
        self.assertIn("binding_mismatch:message_id", decision["diagnostics"])

    def test_owner_source_binding_mismatch_is_denied(self) -> None:
        context = copy.deepcopy(self.owner_context)
        context["bindings"]["provenance_source_id"] = "conversation:owner:other"
        decision = self.evaluate(self.policy, self.owner, context)
        self.assertFalse(decision["allowed"])
        self.assertIn("binding_mismatch:provenance_source_id", decision["diagnostics"])

    def test_repository_binding_mismatch_is_denied(self) -> None:
        context = copy.deepcopy(self.owner_context)
        context["bindings"]["repository"] = "Other/Repo"
        decision = self.evaluate(self.policy, self.owner, context)
        self.assertFalse(decision["allowed"])
        self.assertIn("binding_mismatch:repository", decision["diagnostics"])

    def test_unknown_envelope_property_is_rejected_by_schema(self) -> None:
        envelope = copy.deepcopy(self.owner)
        envelope["unexpected"] = "x"
        decision = self.evaluate(self.policy, envelope, self.owner_context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["envelope_invalid"], decision["reason_codes"])

    def test_unknown_actor_property_is_rejected_by_schema(self) -> None:
        envelope = copy.deepcopy(self.owner)
        envelope["actor"]["unexpected"] = "x"
        decision = self.evaluate(self.policy, envelope, self.owner_context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["envelope_invalid"], decision["reason_codes"])

    def test_missing_provenance_fails_closed(self) -> None:
        envelope = copy.deepcopy(self.owner)
        envelope["provenance"]["source_id"] = ""
        decision = self.evaluate(self.policy, envelope, self.owner_context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["envelope_invalid"], decision["reason_codes"])

    def test_non_owner_human_cannot_reuse_owner_text(self) -> None:
        item = copy.deepcopy(self.examples["examples"][1])
        decision = self.evaluate(self.policy, item["envelope"], item.get("verification_context"))
        self.assertFalse(decision["allowed"])
        self.assertEqual(["content_origin_untrusted"], decision["reason_codes"])

    def test_repository_content_is_data_not_authority(self) -> None:
        envelope = copy.deepcopy(self.owner)
        envelope["source_class"] = "content_only"
        envelope["content_origin"] = "repository_content"
        envelope["actor"]["type"] = "system"
        envelope["provenance"]["artifact_class"] = "data"
        decision = self.evaluate(self.policy, envelope)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["content_origin_untrusted"], decision["reason_codes"])

    def test_approval_request_is_not_trigger_authority(self) -> None:
        item = copy.deepcopy(self.examples["examples"][2])
        decision = self.evaluate(self.policy, item["envelope"], item["verification_context"])
        self.assertFalse(decision["allowed"])
        self.assertEqual(["requested_authority_not_trigger"], decision["reason_codes"])

    def test_verified_allowlisted_github_app_can_trigger(self) -> None:
        decision = self.evaluate(
            self.allow_app(), self.app_item["envelope"], self.app_item["verification_context"]
        )
        self.assertTrue(decision["allowed"], decision)
        self.assertFalse(decision["approval_authorized"])

    def test_connector_verifier_cannot_claim_webhook_channel(self) -> None:
        policy = self.allow_app()
        envelope = copy.deepcopy(self.app_item["envelope"])
        context = copy.deepcopy(self.app_item["verification_context"])
        envelope["provenance"]["channel"] = "github_webhook"
        decision = self.evaluate(policy, envelope, context)
        self.assertFalse(decision["allowed"], decision)
        self.assertEqual(["metadata_contradiction"], decision["reason_codes"])
        self.assertIn("verifier_channel_mismatch", decision["diagnostics"])

    def test_webhook_verifier_cannot_claim_connector_channel(self) -> None:
        policy = self.allow_app()
        policy["policy"]["trusted_verifiers"].append({
            "verifier_id": "nf-github-webhook-verifier",
            "verifier_class": "github_webhook_signature",
            "allowed_source_classes": ["github_app_event"],
            "allowed_repositories": ["Sinev-Maksim/NoemaForge"],
        })
        envelope = copy.deepcopy(self.app_item["envelope"])
        context = copy.deepcopy(self.app_item["verification_context"])
        context["verifier"]["id"] = "nf-github-webhook-verifier"
        context["verifier"]["class"] = "github_webhook_signature"
        decision = self.evaluate(policy, envelope, context)
        self.assertFalse(decision["allowed"], decision)
        self.assertEqual(["metadata_contradiction"], decision["reason_codes"])
        self.assertIn("verifier_channel_mismatch", decision["diagnostics"])

    def test_matching_webhook_verifier_and_channel_can_trigger(self) -> None:
        policy = self.allow_app()
        policy["policy"]["trusted_verifiers"].append({
            "verifier_id": "nf-github-webhook-verifier",
            "verifier_class": "github_webhook_signature",
            "allowed_source_classes": ["github_app_event"],
            "allowed_repositories": ["Sinev-Maksim/NoemaForge"],
        })
        envelope = copy.deepcopy(self.app_item["envelope"])
        context = copy.deepcopy(self.app_item["verification_context"])
        envelope["provenance"]["channel"] = "github_webhook"
        context["verifier"]["id"] = "nf-github-webhook-verifier"
        context["verifier"]["class"] = "github_webhook_signature"
        decision = self.evaluate(policy, envelope, context)
        self.assertTrue(decision["allowed"], decision)
        self.assertEqual(["allowed_verified_github_app_event"], decision["reason_codes"])
        self.assertFalse(tts.decision_failures(decision), decision)

    def test_bool_app_ids_are_rejected(self) -> None:
        policy = self.allow_app()
        envelope = copy.deepcopy(self.app_item["envelope"])
        context = copy.deepcopy(self.app_item["verification_context"])
        policy["policy"]["github_apps"][0]["app_id"] = True
        envelope["actor"]["app_id"] = True
        context["bindings"]["app_id"] = True
        decision = self.evaluate(policy, envelope, context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["policy_invalid"], decision["reason_codes"])

    def test_app_principal_must_match_app_id(self) -> None:
        envelope = copy.deepcopy(self.app_item["envelope"])
        context = copy.deepcopy(self.app_item["verification_context"])
        envelope["actor"]["principal_id"] = "github-app:9999"
        context["bindings"]["actor_principal_id"] = "github-app:9999"
        decision = self.evaluate(self.allow_app(), envelope, context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["verification_binding_mismatch"], decision["reason_codes"])
        self.assertIn("app_principal_id_not_canonical", decision["diagnostics"])

    def test_app_delivery_binding_mismatch_is_denied(self) -> None:
        context = copy.deepcopy(self.app_item["verification_context"])
        context["bindings"]["delivery_id"] = "delivery-other"
        decision = self.evaluate(self.allow_app(), self.app_item["envelope"], context)
        self.assertFalse(decision["allowed"])
        self.assertIn("binding_mismatch:delivery_id", decision["diagnostics"])

    def test_missing_github_installation_id_fails_schema(self) -> None:
        envelope = copy.deepcopy(self.app_item["envelope"])
        envelope["actor"]["installation_id"] = None
        decision = self.evaluate(self.allow_app(), envelope, self.app_item["verification_context"])
        self.assertFalse(decision["allowed"])
        self.assertEqual(["envelope_invalid"], decision["reason_codes"])

    def test_unallowlisted_github_event_type_fails_closed(self) -> None:
        envelope = copy.deepcopy(self.app_item["envelope"])
        context = copy.deepcopy(self.app_item["verification_context"])
        envelope["event"]["type"] = "workflow_run"
        context["bindings"]["event_type"] = "workflow_run"
        decision = self.evaluate(self.allow_app(), envelope, context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["event_type_not_allowlisted"], decision["reason_codes"])

    def test_invalid_policy_still_emits_schema_valid_denial(self) -> None:
        policy = copy.deepcopy(self.policy)
        policy["status"] = "not-a-status"
        decision = self.evaluate(policy, self.owner, self.owner_context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["policy_invalid"], decision["reason_codes"])
        self.assertFalse(tts.decision_failures(decision), decision)

    def test_policy_diagnostics_do_not_escape_into_reason_codes(self) -> None:
        policy = copy.deepcopy(self.policy)
        policy["policy"]["repositories"] = []
        decision = self.evaluate(policy, self.owner, self.owner_context)
        self.assertEqual(["policy_invalid"], decision["reason_codes"])
        self.assertTrue(decision["diagnostics"])
        self.assertTrue(set(decision["reason_codes"]).issubset(set(self.policy["policy"]["reason_codes"])))

    def test_schema_invalid_policy_shapes_fail_closed_without_exception(self) -> None:
        cases = [
            (("policy", "enforcement_mode"), []),
            (("policy", "live_connector_integration_state"), {}),
            (("policy", "trusted_verifiers"), None),
            (("policy", "github_apps"), 1),
        ]
        for path, value in cases:
            with self.subTest(path=path, value=value):
                policy = copy.deepcopy(self.policy)
                target = policy
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                decision = self.evaluate(policy, self.owner, self.owner_context)
                self.assertFalse(decision["allowed"])
                self.assertEqual(["policy_invalid"], decision["reason_codes"])
                self.assertTrue(decision["diagnostics"])
                self.assertFalse(tts.decision_failures(decision), decision)

    def test_builtin_schema_profile_is_used_when_jsonschema_is_unavailable(self) -> None:
        with mock.patch.object(tts, "Draft202012Validator", None), mock.patch.object(tts, "FormatChecker", None):
            decision = self.evaluate(self.policy, self.owner, self.owner_context)
            report = tts.validate_policy_and_examples(self.policy, self.examples)
        self.assertTrue(decision["allowed"], decision)
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("builtin-closed-schema-profile", report["summary"]["schema_backend"])

    def test_builtin_profile_rejects_boolean_integer_and_unknown_property(self) -> None:
        policy = self.allow_app()
        envelope = copy.deepcopy(self.app_item["envelope"])
        context = copy.deepcopy(self.app_item["verification_context"])
        policy["policy"]["github_apps"][0]["app_id"] = True
        envelope["unexpected"] = "x"
        with mock.patch.object(tts, "Draft202012Validator", None), mock.patch.object(tts, "FormatChecker", None):
            decision = self.evaluate(policy, envelope, context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["policy_invalid"], decision["reason_codes"])

    def test_all_schema_backends_unavailable_fails_closed(self) -> None:
        with mock.patch.object(tts, "Draft202012Validator", None), mock.patch.object(tts, "FormatChecker", None), mock.patch.object(tts, "BUILTIN_SCHEMA_PROFILE_AVAILABLE", False):
            decision = self.evaluate(self.policy, self.owner, self.owner_context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["schema_validator_unavailable"], decision["reason_codes"])

    def test_builtin_profile_rejects_unsupported_schema_keyword(self) -> None:
        errors = tts._profile_errors({}, {"type": "object", "$ref": "other.json"})
        self.assertEqual([(( ), "unsupportedKeyword:$ref")], errors)

    def test_default_draft_shadow_policy_cannot_authorize(self) -> None:
        decision = self.evaluate(self.base_policy, self.owner, self.owner_context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["policy_not_active"], decision["reason_codes"])

    def test_retired_policy_cannot_authorize(self) -> None:
        policy = copy.deepcopy(self.policy)
        policy["status"] = "retired"
        decision = self.evaluate(policy, self.owner, self.owner_context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["policy_not_active"], decision["reason_codes"])

    def test_unpassed_connector_integration_cannot_authorize(self) -> None:
        policy = copy.deepcopy(self.policy)
        policy["policy"]["live_connector_integration_state"] = "not_run"
        decision = self.evaluate(policy, self.owner, self.owner_context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["policy_not_active"], decision["reason_codes"])

    def test_stale_verification_is_denied(self) -> None:
        evaluated_at = tts._parse_datetime("2026-07-22T06:00:01Z")
        decision = self.evaluate(
            self.policy, self.owner, self.owner_context, evaluated_at=evaluated_at
        )
        self.assertFalse(decision["allowed"])
        self.assertEqual(["verification_stale"], decision["reason_codes"])

    def test_future_verification_is_denied(self) -> None:
        context = copy.deepcopy(self.owner_context)
        context["verified_at"] = "2026-07-22T05:52:00Z"
        decision = self.evaluate(self.policy, self.owner, context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["verification_from_future"], decision["reason_codes"])

    def test_decision_binds_policy_envelope_and_evidence(self) -> None:
        decision = self.evaluate(self.policy, self.owner, self.owner_context)
        self.assertTrue(decision["allowed"], decision)
        self.assertEqual(tts._canonical_sha256(self.policy), decision["policy"]["sha256"])
        self.assertEqual(tts._canonical_sha256(self.owner), decision["envelope_sha256"])
        self.assertEqual(
            tts._canonical_sha256(self.owner_context),
            decision["verification_context_sha256"],
        )
        self.assertEqual(
            self.owner_context["verifier"]["evidence_sha256"],
            decision["verification"]["evidence_sha256"],
        )
        self.assertEqual(
            self.owner_context["verified_at"], decision["verification"]["verified_at"]
        )
        self.assertFalse(tts.decision_failures(decision))

    def test_duplicate_json_keys_are_rejected(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"kind":"one","kind":"two"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                tts.load_json(path)

    def test_public_evaluator_does_not_accept_caller_clock(self) -> None:
        import inspect

        self.assertNotIn("evaluated_at", inspect.signature(tts.evaluate_trigger).parameters)
        with self.assertRaises(TypeError):
            tts.evaluate_trigger(
                self.policy,
                self.owner,
                self.owner_context,
                evaluated_at=self.evaluated_at,
            )

    def test_lowercase_rfc3339_is_backend_consistent(self) -> None:
        context = copy.deepcopy(self.owner_context)
        context["verified_at"] = "2026-07-22t05:50:00z"
        decision = self.evaluate(self.policy, self.owner, context)
        self.assertTrue(decision["allowed"], decision)
        self.assertFalse(tts.decision_failures(decision))

    def test_datetime_parse_failure_denies_instead_of_raising(self) -> None:
        with mock.patch.object(tts, "verification_context_failures", return_value=[]), mock.patch.object(
            tts, "_parse_datetime", side_effect=ValueError("clock parse")
        ):
            decision = self.evaluate(self.policy, self.owner, self.owner_context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["verification_context_invalid"], decision["reason_codes"])
        self.assertIn("verification_context_datetime_parse_error", decision["diagnostics"])
        self.assertIsNotNone(decision["verification"])
        self.assertFalse(tts.decision_failures(decision))

    def test_stale_denial_retains_verification_audit(self) -> None:
        evaluated_at = tts._parse_datetime("2026-07-22T06:00:01Z")
        decision = self.evaluate(
            self.policy, self.owner, self.owner_context, evaluated_at=evaluated_at
        )
        self.assertFalse(decision["allowed"])
        self.assertEqual(["verification_stale"], decision["reason_codes"])
        self.assertEqual(
            self.owner_context["verifier"]["evidence_sha256"],
            decision["verification"]["evidence_sha256"],
        )
        self.assertEqual(
            self.owner_context["verified_at"], decision["verification"]["verified_at"]
        )
        self.assertFalse(tts.decision_failures(decision))

    def test_binding_denial_retains_verification_audit(self) -> None:
        context = copy.deepcopy(self.owner_context)
        context["bindings"]["message_id"] = "different-message"
        decision = self.evaluate(self.policy, self.owner, context)
        self.assertFalse(decision["allowed"])
        self.assertEqual(["verification_binding_mismatch"], decision["reason_codes"])
        self.assertEqual(
            context["verifier"]["evidence_id"], decision["verification"]["evidence_id"]
        )
        self.assertFalse(tts.decision_failures(decision))


    def test_integral_float_app_bindings_are_denied_by_all_backends(self) -> None:
        policy = self.allow_app()
        for field, value in (("app_id", 1234.0), ("installation_id", 99.0)):
            with self.subTest(field=field):
                context = copy.deepcopy(self.app_item["verification_context"])
                context["bindings"][field] = value
                external = self.evaluate(
                    policy, self.app_item["envelope"], context
                )
                with mock.patch.object(
                    tts, "Draft202012Validator", None
                ), mock.patch.object(tts, "FormatChecker", None):
                    builtin = self.evaluate(
                        policy, self.app_item["envelope"], context
                    )
                for decision in (external, builtin):
                    self.assertFalse(decision["allowed"], decision)
                    self.assertEqual(
                        ["verification_context_invalid"],
                        decision["reason_codes"],
                    )

    def test_integral_float_actor_ids_are_denied_by_all_backends(self) -> None:
        policy = self.allow_app()
        for field, value in (("app_id", 1234.0), ("installation_id", 99.0)):
            with self.subTest(field=field):
                envelope = copy.deepcopy(self.app_item["envelope"])
                envelope["actor"][field] = value
                external = self.evaluate(
                    policy, envelope, self.app_item["verification_context"]
                )
                with mock.patch.object(
                    tts, "Draft202012Validator", None
                ), mock.patch.object(tts, "FormatChecker", None):
                    builtin = self.evaluate(
                        policy, envelope, self.app_item["verification_context"]
                    )
                for decision in (external, builtin):
                    self.assertFalse(decision["allowed"], decision)
                    self.assertEqual(["envelope_invalid"], decision["reason_codes"])

    def test_binding_comparison_is_json_type_strict(self) -> None:
        context = copy.deepcopy(self.app_item["verification_context"])
        context["bindings"]["app_id"] = 1234.0
        mismatches = tts._binding_mismatches(
            self.app_item["envelope"], context
        )
        self.assertIn("binding_mismatch:app_id", mismatches)

    def test_integral_float_policy_ids_remain_policy_invalid(self) -> None:
        policy = self.allow_app()
        policy["policy"]["github_apps"][0]["app_id"] = 1234.0
        external = self.evaluate(
            policy,
            self.app_item["envelope"],
            self.app_item["verification_context"],
        )
        with mock.patch.object(
            tts, "Draft202012Validator", None
        ), mock.patch.object(tts, "FormatChecker", None):
            builtin = self.evaluate(
                policy,
                self.app_item["envelope"],
                self.app_item["verification_context"],
            )
        for decision in (external, builtin):
            self.assertFalse(decision["allowed"], decision)
            self.assertEqual(["policy_invalid"], decision["reason_codes"])

    def test_empty_examples_do_not_validate(self) -> None:
        empty = {"apiVersion": tts.EXAMPLE_VERSION, "kind": tts.EXAMPLE_KIND, "examples": []}
        report = tts.validate_policy_and_examples(self.policy, empty)
        self.assertFalse(report["ok"])
        self.assertIn("examples_empty", report["failures"])


if __name__ == "__main__":
    unittest.main()
