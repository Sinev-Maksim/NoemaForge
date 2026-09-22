#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_night_watch_routing_runtime.py
Zone: release/package
Version: 0.33.0
Created: 2026-08-13
Modified: 2026-08-13
Purpose: Prove strict Night Watch reviewer/provider routing semantics.
Inputs: Deterministic in-memory provider/persona fixtures only.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest or pytest execution.
Notes: UAT request findings resolution; covers NW-UAT-GH-031..036 semantics.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from typing import Optional


ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import night_watch_routing_runtime as routing


BASE = "a" * 40
CANDIDATE = "8e41329f353b0161c54e47795ea45d636639dd70"
OTHER = "b" * 40


def provider(
    provider_id: str,
    *,
    availability: str = "available",
    surface: str = "ready",
    quality: str = "calibrated",
    metadata: str = "none_observed",
    key: Optional[str] = None,
    capabilities=(),
    requested: bool = True,
    observed: bool = True,
    sha: Optional[str] = CANDIDATE,
    optional: bool = False,
):
    return routing.make_provider_state(
        provider_id=provider_id,
        provider_availability=availability,
        surface_readiness=surface,
        quality_calibration=quality,
        metadata_side_effects=metadata,
        independence_key=key or provider_id,
        capabilities=capabilities,
        request_attempted=requested,
        review_observed=observed,
        bound_candidate_sha=sha,
        optional=optional,
    )


def persona(name="architect", candidates=("claude", "antigravity")):
    return routing.make_persona_state(
        persona_id=name,
        capabilities=(name, "independent_review"),
        provider_candidates=candidates,
        configured=True,
    )


def baseline_providers():
    return {
        "codex": provider(
            "codex",
            quality="not_required",
            capabilities=("implementation",),
        ),
        "git_helper": provider(
            "git_helper",
            quality="not_required",
            capabilities=("git_integrity",),
        ),
        "claude": provider(
            "claude",
            capabilities=("independent_review", "architecture"),
        ),
        "antigravity": provider(
            "antigravity",
            capabilities=("independent_review", "architecture"),
        ),
        "coderabbit": provider(
            "coderabbit",
            capabilities=("code_review", "config_review", "markdown_review"),
        ),
        "copilot": provider(
            "copilot",
            capabilities=("code_review",),
            optional=True,
        ),
    }


class NightWatchRoutingRuntimeTests(unittest.TestCase):
    def test_persona_configuration_is_provider_independent(self):
        state = persona("security", ("claude", "antigravity"))
        self.assertTrue(state["configured"])
        self.assertEqual(["antigravity", "claude"], state["provider_candidates"])

    def test_surface_ready_without_quality_is_not_vote_eligible(self):
        state = provider(
            "coderabbit",
            quality="failed",
            capabilities=("code_review",),
        )
        self.assertEqual("ready", state["surface_readiness"])
        self.assertEqual("ineligible", state["vote_eligibility"])

    def test_copilot_request_attempt_is_not_review_evidence(self):
        state = provider(
            "copilot",
            capabilities=("code_review",),
            requested=True,
            observed=False,
            sha=None,
            optional=True,
        )
        self.assertTrue(state["request_attempted"])
        self.assertFalse(state["review_observed"])
        self.assertEqual("ineligible", state["vote_eligibility"])

    def test_metadata_side_effect_is_explicit_but_does_not_change_candidate_binding(self):
        state = provider(
            "coderabbit",
            metadata="observed",
            capabilities=("code_review",),
        )
        self.assertEqual("observed", state["metadata_side_effects"])
        self.assertEqual(CANDIDATE, state["bound_candidate_sha"])
        self.assertEqual("eligible", state["vote_eligibility"])

    def test_code_config_infra_require_coderabbit(self):
        for scope in ("code", "config", "infra"):
            self.assertTrue(routing.coderabbit_required(scope, ()))

    def test_markdown_requires_coderabbit_only_when_affected(self):
        self.assertFalse(routing.coderabbit_required("markdown", ("claude",)))
        self.assertTrue(routing.coderabbit_required("markdown", ("coderabbit",)))

    def test_exact_candidate_mismatch_cannot_vote(self):
        providers = baseline_providers()
        providers["coderabbit"] = provider(
            "coderabbit", capabilities=("code_review",), sha=OTHER
        )
        envelope = routing.evaluate_review_gate(
            candidate_sha=CANDIDATE,
            change_scope="code",
            persona=persona(),
            implementer_provider="codex",
            providers=providers,
        )
        self.assertFalse(envelope["review_gate_pass"])
        self.assertIn("STALE_REVIEW_CANDIDATE", envelope["blockers"])

    def test_coderabbit_quality_failure_is_typed_blocker(self):
        providers = baseline_providers()
        providers["coderabbit"] = provider(
            "coderabbit",
            quality="failed",
            metadata="observed",
            capabilities=("code_review",),
        )
        envelope = routing.evaluate_review_gate(
            candidate_sha=CANDIDATE,
            change_scope="code",
            persona=persona(),
            implementer_provider="codex",
            providers=providers,
        )
        self.assertFalse(envelope["review_gate_pass"])
        self.assertIn("BLOCKED_REVIEW_QUALITY_CAPABILITY", envelope["blockers"])
        self.assertEqual("YIELD_BLOCKED_REVIEW_QUALITY", envelope["route"])

    def test_live_pr_review_wait_is_distinct_from_quality_failure(self):
        providers = baseline_providers()
        providers["coderabbit"] = provider(
            "coderabbit",
            surface="unverified",
            quality="unproven",
            capabilities=("code_review",),
            requested=True,
            observed=False,
            sha=None,
        )
        envelope = routing.evaluate_review_gate(
            candidate_sha=CANDIDATE,
            change_scope="code",
            persona=persona(),
            implementer_provider="codex",
            providers=providers,
        )
        # A known failed/unproven quality state is stronger than mere waiting.
        self.assertIn("BLOCKED_REVIEW_QUALITY_CAPABILITY", envelope["blockers"])

    def test_coderabbit_calibrated_surface_waits_for_observed_review(self):
        providers = baseline_providers()
        providers["coderabbit"] = provider(
            "coderabbit",
            surface="ready",
            quality="calibrated",
            capabilities=("code_review",),
            requested=True,
            observed=False,
            sha=None,
        )
        envelope = routing.evaluate_review_gate(
            candidate_sha=CANDIDATE,
            change_scope="code",
            persona=persona(),
            implementer_provider="codex",
            providers=providers,
        )
        self.assertIn("WAITING_FOR_LIVE_PR_REVIEW", envelope["blockers"])
        self.assertNotIn("BLOCKED_REVIEW_QUALITY_CAPABILITY", envelope["blockers"])

    def test_late_binding_uses_eligible_persona_provider(self):
        providers = baseline_providers()
        providers["claude"] = provider(
            "claude",
            availability="blocked_external",
            surface="unavailable",
            quality="unproven",
            capabilities=("independent_review", "architecture"),
            requested=False,
            observed=False,
            sha=None,
        )
        envelope = routing.evaluate_review_gate(
            candidate_sha=CANDIDATE,
            change_scope="markdown",
            persona=persona(),
            implementer_provider="codex",
            providers=providers,
            affected_prior_reviewers=("claude",),
        )
        self.assertTrue(envelope["review_gate_pass"])
        self.assertIn("antigravity", envelope["selected_reviewers"])
        self.assertNotIn("claude", envelope["selected_reviewers"])

    def test_degraded_pr349_state_blocks_engine_and_quality(self):
        providers = baseline_providers()
        providers["claude"] = provider(
            "claude",
            availability="blocked_external",
            surface="unavailable",
            quality="unproven",
            capabilities=("independent_review", "architecture"),
            requested=True,
            observed=False,
            sha=None,
        )
        providers["antigravity"] = provider(
            "antigravity",
            availability="available",
            surface="interactive_only",
            quality="unproven",
            capabilities=("independent_review", "architecture"),
            requested=True,
            observed=False,
            sha=None,
        )
        providers["coderabbit"] = provider(
            "coderabbit",
            quality="failed",
            metadata="observed",
            capabilities=("code_review",),
        )
        providers["copilot"] = provider(
            "copilot",
            capabilities=("code_review",),
            requested=True,
            observed=False,
            sha=None,
            optional=True,
        )
        envelope = routing.evaluate_review_gate(
            candidate_sha=CANDIDATE,
            change_scope="code",
            persona=persona(),
            implementer_provider="codex",
            providers=providers,
        )
        self.assertFalse(envelope["review_gate_pass"])
        self.assertIn("BLOCKED_ENGINE_CAPABILITY", envelope["blockers"])
        self.assertIn("BLOCKED_REVIEW_QUALITY_CAPABILITY", envelope["blockers"])
        self.assertIn("OPTIONAL_COPILOT_UNVERIFIED", envelope["notices"])
        self.assertFalse(envelope["downstream"]["build_reproducer"])
        self.assertFalse(envelope["downstream"]["call_cost_estimator"])
        self.assertFalse(envelope["downstream"]["route_budget"])
        self.assertFalse(envelope["downstream"]["start_gcp"])

    def test_blocked_gate_short_circuits_all_downstream_work(self):
        providers = baseline_providers()
        providers["claude"] = provider(
            "claude", availability="unavailable", surface="unavailable",
            quality="unproven", capabilities=("independent_review",),
            requested=False, observed=False, sha=None,
        )
        providers["antigravity"] = provider(
            "antigravity", availability="unavailable", surface="unavailable",
            quality="unproven", capabilities=("independent_review",),
            requested=False, observed=False, sha=None,
        )
        envelope = routing.evaluate_review_gate(
            candidate_sha=CANDIDATE,
            change_scope="markdown",
            persona=persona(),
            implementer_provider="codex",
            providers=providers,
            affected_prior_reviewers=("claude",),
        )
        self.assertFalse(envelope["review_gate_pass"])
        self.assertEqual(
            {
                "build_reproducer": False,
                "call_cost_estimator": False,
                "route_budget": False,
                "start_gcp": False,
            },
            envelope["downstream"],
        )

    def test_review_gate_pass_only_releases_reproducer_stage(self):
        providers = baseline_providers()
        envelope = routing.evaluate_review_gate(
            candidate_sha=CANDIDATE,
            change_scope="code",
            persona=persona(),
            implementer_provider="codex",
            providers=providers,
        )
        self.assertTrue(envelope["review_gate_pass"])
        self.assertTrue(envelope["downstream"]["build_reproducer"])
        self.assertFalse(envelope["downstream"]["call_cost_estimator"])
        self.assertFalse(envelope["downstream"]["route_budget"])
        self.assertFalse(envelope["downstream"]["start_gcp"])

    def test_self_review_is_rejected_by_independence_key(self):
        providers = baseline_providers()
        providers["codex_reviewer"] = provider(
            "codex_reviewer",
            key=providers["codex"]["independence_key"],
            capabilities=("independent_review",),
        )
        envelope = routing.evaluate_review_gate(
            candidate_sha=CANDIDATE,
            change_scope="markdown",
            persona=persona(candidates=("codex_reviewer",)),
            implementer_provider="codex",
            providers=providers,
            require_git_helper=False,
        )
        self.assertFalse(envelope["review_gate_pass"])
        self.assertIn("IMPLEMENTER_SELF_REVIEW_REJECTED", envelope["blockers"])

    def test_duplicate_independence_key_is_rejected(self):
        providers = baseline_providers()
        providers["coderabbit"]["independence_key"] = providers["claude"]["independence_key"]
        envelope = routing.evaluate_review_gate(
            candidate_sha=CANDIDATE,
            change_scope="code",
            persona=persona(candidates=("claude",)),
            implementer_provider="codex",
            providers=providers,
            require_git_helper=False,
        )
        self.assertFalse(envelope["review_gate_pass"])
        self.assertIn("DUPLICATE_INDEPENDENCE_KEY_REJECTED", envelope["blockers"])

    def test_strict_provider_contract_rejects_extra_fields(self):
        state = provider("claude", capabilities=("independent_review",))
        state["surprise"] = True
        with self.assertRaises(routing.NightWatchRoutingError):
            routing.validate_provider_state(state)

    def test_strict_route_contract_rejects_extra_fields(self):
        providers = baseline_providers()
        envelope = routing.evaluate_review_gate(
            candidate_sha=CANDIDATE,
            change_scope="code",
            persona=persona(),
            implementer_provider="codex",
            providers=providers,
        )
        envelope["surprise"] = True
        with self.assertRaises(routing.NightWatchRoutingError):
            routing.validate_route_envelope(envelope)

    def test_vote_eligibility_cannot_be_forged(self):
        state = provider(
            "copilot", capabilities=("code_review",), requested=True,
            observed=False, sha=None, optional=True
        )
        state["vote_eligibility"] = "eligible"
        with self.assertRaises(routing.NightWatchRoutingError):
            routing.validate_provider_state(state)

    def test_schema_is_strict_and_carries_readiness_dimensions(self):
        schema_path = ROOT / "contracts" / "night_watch_routing.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        observation = schema["$defs"]["providerObservation"]
        self.assertFalse(observation["additionalProperties"])
        for field in (
            "provider_availability",
            "surface_readiness",
            "quality_calibration",
            "vote_eligibility",
            "metadata_side_effects",
            "review_observed",
            "bound_candidate_sha",
        ):
            self.assertIn(field, observation["required"])

    def test_output_is_deterministic_for_same_inputs(self):
        providers = baseline_providers()
        kwargs = dict(
            candidate_sha=CANDIDATE,
            change_scope="code",
            persona=persona(),
            implementer_provider="codex",
            providers=providers,
        )
        first = routing.evaluate_review_gate(**kwargs)
        second = routing.evaluate_review_gate(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual(
            json.dumps(first, sort_keys=True, separators=(",", ":")),
            json.dumps(second, sort_keys=True, separators=(",", ":")),
        )

    def test_unknown_change_scope_fails_closed(self):
        providers = baseline_providers()
        for scope in ("python", "CODE", "security", ""):
            with self.subTest(scope=scope):
                with self.assertRaises(routing.NightWatchRoutingError):
                    routing.evaluate_review_gate(
                        candidate_sha=CANDIDATE,
                        change_scope=scope,
                        persona=persona(),
                        implementer_provider="codex",
                        providers=providers,
                    )

    def test_strict_provider_contract_rejects_malformed_field_types(self):
        mutations = {
            "provider_id": 123,
            "independence_key": {},
            "capabilities": "independent_review",
            "request_attempted": "yes",
            "optional": "false",
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                state = provider("claude", capabilities=("independent_review",))
                state[field] = value
                with self.assertRaises(routing.NightWatchRoutingError):
                    routing.validate_provider_state(state)

    def test_strict_persona_contract_rejects_malformed_field_types(self):
        mutations = {
            "persona_id": 123,
            "configured": "true",
            "capabilities": "independent_review",
            "provider_candidates": 123,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                state = persona()
                state[field] = value
                with self.assertRaises(routing.NightWatchRoutingError):
                    routing.validate_persona_state(state)

    def test_persona_without_independent_review_capability_cannot_vote(self):
        providers = baseline_providers()
        state = routing.make_persona_state(
            persona_id="artist",
            capabilities=("visual_review",),
            provider_candidates=("claude",),
            configured=True,
        )
        envelope = routing.evaluate_review_gate(
            candidate_sha=CANDIDATE,
            change_scope="markdown",
            persona=state,
            implementer_provider="codex",
            providers=providers,
            require_git_helper=False,
        )
        self.assertFalse(envelope["review_gate_pass"])
        self.assertIn("PERSONA_CAPABILITY_MISSING", envelope["blockers"])

    def test_route_validator_rejects_forged_pass_semantics(self):
        providers = baseline_providers()
        envelope = routing.evaluate_review_gate(
            candidate_sha=CANDIDATE,
            change_scope="code",
            persona=persona(),
            implementer_provider="codex",
            providers=providers,
        )
        forged = []

        item = json.loads(json.dumps(envelope))
        item["blockers"] = ["SYNTHETIC_BLOCKER"]
        forged.append(item)

        item = json.loads(json.dumps(envelope))
        item["selected_reviewers"] = ["claude", "git_helper"]
        forged.append(item)

        item = json.loads(json.dumps(envelope))
        item["downstream"]["build_reproducer"] = False
        forged.append(item)

        item = json.loads(json.dumps(envelope))
        item["coderabbit_required"] = False
        forged.append(item)

        for item in forged:
            with self.subTest(item=item):
                with self.assertRaises(routing.NightWatchRoutingError):
                    routing.validate_route_envelope(item)


if __name__ == "__main__":
    unittest.main()
