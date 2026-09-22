# Night Watch candidate 38882b — independent code review

**Classification:** `UAT request findings resolution`  
**Review date:** 2026-09-22  
**Original candidate patch SHA-256:** `38882b33058de4f2ce3b16bdcbe293b8bf6c8c541090882c2a4e3b54fd59a020`  
**Canonical base:** `a3c172f5d60113876f0c103010de411fc30b8c38`  
**Original Night Watch terminal state:** `IMPLEMENTATION_COMPLETE_INDEPENDENT_REVIEW_PENDING`

## Handoff integrity

The recovered cumulative handoff is internally consistent:

- handoff ZIP SHA-256: `ef5ca29f1a7fb92cfca46cad2706267791788f98e99aec0a87332ebd7e55af80`;
- `OBJECTS.nwpack` SHA-256: `c7033cd6234b14197e4780673360e0a81237149b28404515f2613cb4ca95a46d`;
- content-addressed object count: `1196`;
- history run count: `12`;
- every packed object verified against its SHA-256 filename;
- current candidate patch bytes reproduce SHA-256 `38882b...a020` exactly.

The original candidate was therefore recovered without ambiguity.

## Original candidate verification

The original candidate's focused routing suite was rerun independently:

`21 / 21 PASS`

The prior target-host evidence also recorded the read-only-adapter/evolution-contract/syntax gates as PASS.

A green focused suite was **not** sufficient for acceptance. Adversarial review found fail-open behavior not covered by the original tests.

## Blocking finding A — unknown change scope can bypass CodeRabbit policy

The original routing schema accepted any non-empty `change_scope`, while runtime policy recognized only selected strings when deciding whether CodeRabbit was mandatory.

As a result, malformed/unrecognized values such as `python`, `CODE`, or another non-empty scope could be treated as not requiring CodeRabbit and still reach a passing review route.

This is fail-open review-policy behavior.

**Required invariant:** the scope domain is closed and validated before routing. Unknown or differently cased values fail closed.

## Blocking finding B — provider/persona records are not actually strict

The original validator rejected unknown fields but did not consistently validate field types and collection semantics.

Observed examples included malformed provider/persona fields being accepted, and malformed `independence_key` data reaching set/mapping logic where a raw Python `TypeError` could escape instead of a typed routing failure.

**Required invariant:** provider/persona records must validate scalar types, booleans, sorted duplicate-free list fields, mapping structure, and reviewer capability before any routing/review decision.

## Blocking finding C — route-envelope semantic contradictions can validate

The original `validate_route_envelope()` validated shape more strongly than meaning. A syntactically valid envelope could claim a passing review state while contradicting the routing invariants, for example:

- `review_gate_pass=true` together with blockers;
- code route with CodeRabbit required but no CodeRabbit reviewer selected;
- passing gate while downstream reproducer remained disabled;
- review selections that were not independently eligible/exact-candidate-bound.

If a serialized route envelope crosses a trust boundary, shape-only validation is insufficient.

**Required invariant:** the envelope validator must recompute/verify security- and acceptance-relevant semantics, not trust self-asserted booleans.

## Corrective WIP

A corrected WIP iteration was produced without modifying the original recovered candidate bytes.

Changes include:

- closed `change_scope` enum: `code|config|infra|markdown`;
- closed route enum;
- unknown scope fails closed;
- strict provider record types and sorted/unique capabilities;
- strict persona record types and sorted/unique capabilities/provider candidates;
- persona requires `independent_review` capability to supply an independent vote;
- strict affected-reviewer collection validation;
- stronger `evaluate_review_gate()` input validation;
- semantic `validate_route_envelope()` invariants for blocker/pass consistency, CodeRabbit presence, downstream release, candidate binding, reviewer independence and unique independence keys;
- new regression tests for all three findings.

Corrected file SHA-256 values:

- `noemaforge/src/night_watch_routing_runtime.py`: `28a538e8d3b83db10600a75b8a835e0dbdf86176ce5c26e9e1271166d00ca9f7`;
- `noemaforge/tests/test_night_watch_routing_runtime.py`: `856c1d02fd6afa62924bfe8829ecf9515e78c9c62516dd7881f5abe7d72f7623`;
- `noemaforge/contracts/night_watch_routing.schema.json`: `9b4999db2650a693b53681a809a53cf6352ee506d4ff85b15667ef81b95107a8`;
- `noemaforge/docs/architecture/night-watch-routing-contract.md`: `b28ceb2c0cb00f23f62f9c7c996aff488aef7214011dca3430e32330354ddfa8`.

Normalized review-fix patch SHA-256:

`14abf5506d4e6aae0e72fccb23e7dd00aa16976a8c5fb20a9afa072e0328555d`

## Corrected focused validation

Fresh local validation of the corrected WIP:

- routing unit tests: `26 / 26 PASS`;
- Python compile: `PASS`;
- routing schema JSON parse: `PASS`.

These checks validate the reviewed routing surface. They do not replace the full repository regression suite, CodeRabbit where required, remote exact-candidate independent review, or human release authority.

## Review verdict

```text
ORIGINAL_CANDIDATE_38882b=REQUEST_CHANGES
HANDOFF_INTEGRITY=PASS
ORIGINAL_FOCUSED_TESTS=PASS
ADVERSARIAL_REVIEW=BLOCKING_FINDINGS_FOUND
CORRECTED_WIP_FOCUSED_TESTS=PASS_26_OF_26
EXTERNAL_INDEPENDENT_ACCEPTANCE=PENDING
CODERABBIT=PENDING
HUMAN_RELEASE_GO=NOT_GRANTED
```

The original candidate SHA `38882b...a020` must not be represented as accepted. The corrected WIP is a new candidate iteration and requires the remaining canonical gates.
