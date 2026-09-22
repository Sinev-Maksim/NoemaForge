# Night Watch candidate 38882b — independent code review

**Classification:** `UAT request findings resolution`  
**Review date:** 2026-09-22  
**Canonical base:** `a3c172f5d60113876f0c103010de411fc30b8c38`  
**Original candidate patch SHA-256:** `38882b33058de4f2ce3b16bdcbe293b8bf6c8c541090882c2a4e3b54fd59a020`  
**Original Night Watch terminal state:** `IMPLEMENTATION_COMPLETE_INDEPENDENT_REVIEW_PENDING`

## 1. Handoff integrity

The recovered cumulative handoff is internally consistent:

- handoff ZIP SHA-256: `ef5ca29f1a7fb92cfca46cad2706267791788f98e99aec0a87332ebd7e55af80`;
- `OBJECTS.nwpack` SHA-256: `c7033cd6234b14197e4780673360e0a81237149b28404515f2613cb4ca95a46d`;
- content-addressed objects: `1196`;
- history runs: `12`;
- all packed objects match their SHA-256 identities;
- `current/CONTINUATION_CANDIDATE.patch` reproduces `38882b...a020` exactly.

The initial pre-fix patch in the same lineage already contained the new routing test file. Therefore the final candidate's test file was not introduced by a later self-heal attempt that bypassed the immutable-test rule; later attempts to mutate that test were rejected as recorded by the controller.

## 2. Original candidate verification

The original candidate's focused routing suite was rerun independently:

`21 / 21 PASS`

The target-host run had also reported its read-only-adapter/evolution-contract/syntax gates green.

This was not sufficient for acceptance. Adversarial review found multiple fail-open or strictness defects outside the original regression set.

## 3. Blocking findings in original candidate

### NW-REV-001 — unknown change scope can bypass CodeRabbit policy

The original schema accepted arbitrary non-empty `change_scope`. Runtime policy only recognized selected strings when deciding whether CodeRabbit was mandatory. Unknown/differently cased values could therefore downgrade a code-like change to a route where CodeRabbit was not required.

**Fix:** closed scope domain: `code|config|infra|markdown`; unknown scope fails closed.

### NW-REV-002 — provider/persona records were not truly strict

Unknown fields were rejected, but many field types and collection semantics were not. Malformed values could be accepted or leak raw Python exceptions instead of a typed `NightWatchRoutingError`.

**Fix:** strict scalar/boolean/enum/list validation, sorted duplicate-free string collections, mapping-key/provider-id parity, and typed failure normalization.

### NW-REV-003 — route envelope could assert contradictory PASS semantics

The original `validate_route_envelope()` checked structure more strongly than meaning. A syntactically valid document could claim PASS while carrying blockers, omitting required CodeRabbit, or withholding the reproducer transition.

**Fix:** semantic pass/block checks, exact route/blocker consistency, exact-candidate reviewer checks, and fail-closed downstream gating.

## 4. Extrapolation findings after the first correction

A second adversarial cycle deliberately tried neighboring forms of the same root cause. It found additional trust-boundary gaps that the first correction did not yet cover.

### NW-REV-004 — contextual vote eligibility could still be forged

A serialized provider observation could claim `vote_eligibility=eligible` while simultaneously declaring the provider unavailable/unready.

**Fix:** route validation now recomputes contextual vote eligibility from availability, surface readiness, quality calibration, observed review, exact candidate binding, implementer identity and independence key.

### NW-REV-005 — required Git-helper review could be silently removed

A forged PASS envelope could remove `git_helper` from `selected_reviewers` because the original envelope did not carry/revalidate the review-policy switch.

**Fix:** route envelope now carries review requirements and verifies required Git-helper selection plus `git_integrity` capability.

### NW-REV-006 — required independent persona reviewer could be silently removed

A forged PASS envelope could retain only other reviewers and still validate.

**Fix:** the envelope now carries persona configuration/capabilities/provider candidates and verifies that a required independent reviewer is both selected and capability-eligible.

### NW-REV-007 — Markdown CodeRabbit history requirement was not self-validating

For Markdown changes, CodeRabbit is conditional on affected prior review history. That input was missing from the serialized envelope, so a forged envelope could flip `coderabbit_required` to false.

**Fix:** `affected_prior_reviewers` is carried in `review_requirements`; the validator recomputes the CodeRabbit requirement for every scope.

### NW-REV-008 — blocker/route typing was not closed

A blocked envelope could carry an arbitrary blocker code or a route inconsistent with the blocker priority.

**Fix:** blocker/notice code domains are closed and the route is deterministically recomputed from blockers.

### NW-REV-009 — builder collection inputs could degrade into character/key lists

Passing a scalar string or mapping as `capabilities` could be iterated as characters/keys and converted into an apparently valid list. Other non-iterable values leaked raw `TypeError`.

**Fix:** collection builders reject scalar strings/bytes/mappings and normalize non-iterable failures to typed routing errors.

## 5. Corrected WIP behavior

The current WIP now preserves enough deterministic context to revalidate the route envelope's own semantics:

- strict scope and route domains;
- persona configured state, capabilities and provider candidates;
- review-policy switches and affected prior reviewers;
- provider capabilities and exact candidate observations;
- contextual vote-eligibility derivation;
- required Git-helper / independent persona / CodeRabbit checks;
- typed blocker/notice domains;
- blocker -> route derivation;
- pass/block -> downstream derivation;
- typed errors for malformed public validator/builder inputs.

The envelope remains evidence, not authentication or authority. NF must still bind it to the trusted work item/policy/evidence lineage.

## 6. Final focused validation of corrected WIP

Fresh local checks:

- routing unit tests: `35 / 35 PASS`;
- Python syntax/compile: `PASS`;
- routing schema JSON parse: `PASS`;
- Draft 2020-12 JSON Schema validation of a valid PASS envelope: `PASS`;
- schema + runtime validation of representative blocked-route matrix: `PASS`;
- adversarial forged-PASS probes for unavailable reviewer, missing Git helper, missing independent reviewer, Markdown CodeRabbit downgrade and unknown blocker: all `REJECTED`;
- malformed public validator/builder inputs return typed `NightWatchRoutingError` rather than raw exceptions in the tested matrix.

Current corrected file SHA-256 values:

- `noemaforge/src/night_watch_routing_runtime.py`: `750318b30a73bdf1a7864cb6e8845415259635134ef5e43601a69f17c0e8b1c1`;
- `noemaforge/tests/test_night_watch_routing_runtime.py`: `c1698979ac19a88e19774ce44fd34aef1fdb474f29b923531c9b231676ef7a7b`;
- `noemaforge/contracts/night_watch_routing.schema.json`: `ffe19548498836b37f4b07e777a02ac07754b51aec41720e0e3525ce9b6fd2f7`;
- `noemaforge/docs/architecture/night-watch-routing-contract.md`: `fe1cf9d4307a6eabc89780322e4cf95f8a858d8a1a5243fec5da5b1245dc04b3`.

Full final review-fix patch from original candidate -> current corrected WIP:

`afad43c2f4e1a1e8bf4ecddc882cb93ba34db5e868a2dbe4420adc70a389c3cd`

## 7. Review verdict

```text
HANDOFF_INTEGRITY=PASS
ORIGINAL_CANDIDATE_38882b=REQUEST_CHANGES
ORIGINAL_FOCUSED_TESTS=PASS_21_OF_21
ROOT_CAUSE_EXTRAPOLATION=ADDITIONAL_DEFECTS_FOUND_AND_FIXED
CORRECTED_WIP_FOCUSED_TESTS=PASS_35_OF_35
CORRECTED_WIP_ADVERSARIAL_PROBES=PASS
CORRECTED_WIP_REMOTE_PERSISTENCE=PASS
FULL_REPOSITORY_REGRESSION=PENDING
REMOTE_EXACT_CANDIDATE_REVIEW=PENDING
CODERABBIT=PENDING
HUMAN_RELEASE_GO=NOT_GRANTED
```

The original candidate SHA `38882b...a020` is preserved as historical evidence and must not be represented as accepted. The corrected WIP is a new candidate iteration and still requires the remaining canonical external gates.
