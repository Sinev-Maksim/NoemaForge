# Night Watch review routing contract

Status: local UAT implementation candidate
Classification: **UAT request findings resolution**

## Purpose

Night Watch must not equate installation, provider availability, a successful
request, or a green external status with an independent review vote. The review
router therefore records provider state along independent dimensions and decides
vote eligibility only at dispatch time for an exact candidate SHA.

API: `noemaforge.night-watch-routing/v1`

Accepted change scopes are strictly `code`, `config`, `infra`, and `markdown`. Unknown or differently cased scopes fail closed; they never downgrade CodeRabbit requirements.

This contract is additive to `noemaforge.evolution-execution/v1`; it does not
change the strict canonical Evolution execution documents introduced earlier.

## Reviewer/provider state

Each provider is evaluated across these independent facts:

- `provider_availability`: provider/account/runtime availability;
- `surface_readiness`: whether the required automated review surface is usable;
- `quality_calibration`: whether that surface demonstrated the semantic review
  capability required for the gate;
- `vote_eligibility`: derived, never accepted as a successful request proxy;
- `metadata_side_effects`: explicit observation of PR/issue metadata mutation;
- `review_observed`: evidence that a review actually occurred;
- `bound_candidate_sha`: the exact candidate reviewed;
- `independence_key`: engine/model/session identity used to prevent duplicate or
  self review votes.

`metadata_side_effects=observed` does not by itself invalidate a candidate SHA,
but it is retained as evidence and must not be silently treated as read-only
behavior.

## Persona boundary

A persona is configuration, not a provider and not an independent vote. Persona/provider documents are strict JSON-compatible records: malformed types, unknown fields, duplicate/unsorted capability lists, and invalid provider mappings fail closed with typed routing errors.

QA, Security, Architect, UX, and Editor remain configured when one or more model
providers are unavailable. Their provider candidates are late-bound at dispatch.

A missing eligible provider yields a typed blocker; it does not mutate persona
configuration.

## Vote eligibility

A provider vote is eligible only when all of the following are true:

1. provider availability is `available`;
2. automated surface readiness is `ready`;
3. quality calibration is `calibrated` or explicitly `not_required` for a
   deterministic surface;
4. review evidence was actually observed;
5. the review is bound to the exact candidate SHA;
6. its `independence_key` is distinct from the implementer and from every other
   counted reviewer.

A successful review-request API call is not review evidence. This is the rule
that prevents an unobserved Copilot request from becoming a vote.

## CodeRabbit rule

CodeRabbit remains required for `code`, `config`, and `infra` changes.

For Markdown-only changes, CodeRabbit is required only when an affected previous
review/finding came from CodeRabbit. Otherwise one independent co-check is still
required, but CodeRabbit is not mandatory.

A CodeRabbit surface can therefore be simultaneously:

- available;
- exact-SHA aware;
- successful as a provider surface;
- but ineligible for a semantic gate when the relevant quality calibration has
  failed or remains unproven.

## Self-validating route envelope

The serialized route envelope carries enough deterministic context to revalidate its own review-gate semantics: persona configuration/capabilities/provider candidates, the review-policy switches, affected prior reviewers, and provider capabilities. The validator recomputes contextual vote eligibility, CodeRabbit requirement (including the Markdown-history case), required Git-helper and independent-persona presence, blocker/route consistency, and downstream release. Unknown blocker/notice codes fail closed.

The envelope is still evidence, not authentication or authority: the NF caller must bind it to the trusted work item/policy/evidence lineage. But a contradictory envelope cannot become valid merely by asserting `review_gate_pass=true`.

## Review-gate short circuit

A failed review gate cannot start the reproducer, cost estimator, budget route,
or GCP execution.

A passed review gate releases only the **reproducer stage**. Cost estimation is
still false until a later stage proves base FAIL / candidate PASS / negative
control. Budget routing and GCP are later gates.

Typed blockers include:

- `BLOCKED_ENGINE_CAPABILITY`;
- `BLOCKED_REVIEW_QUALITY_CAPABILITY`;
- `WAITING_FOR_LIVE_PR_REVIEW`;
- `WAITING_FOR_REVIEW_EVIDENCE`;
- `STALE_REVIEW_CANDIDATE`;
- `IMPLEMENTER_SELF_REVIEW_REJECTED`;
- `DUPLICATE_INDEPENDENCE_KEY_REJECTED`.

Optional Copilot absence/unverified state is a notice, not a blocker.

## PR #349 calibration evidence

The local unit fixture models the observed PR #349 state without calling GitHub:

- Claude: provider blocked externally;
- Antigravity: interactive-only, automated review surface unavailable;
- CodeRabbit: surface observed on the exact SHA, metadata side effect observed,
  but mutable-state quality calibration failed;
- Copilot: request attempted but no review evidence observed.

Expected result:

- `BLOCKED_ENGINE_CAPABILITY`;
- `BLOCKED_REVIEW_QUALITY_CAPABILITY`;
- `OPTIONAL_COPILOT_UNVERIFIED`;
- no reproducer/cost/budget/GCP start.

The live PR remains an external calibration fixture and is not modified by the
local contract tests.
