# Trusted trigger-source boundary

Status: draft contract for `0.33.0` UAT request findings resolution.

The trigger envelope is untrusted data. Fields such as an actor login, principal ID,
application ID, installation ID, repository, event type, delivery ID, and provenance
reference do not become trusted merely because they are present in JSON.

Authorization requires a separate `TrustedTriggerVerificationContext` produced by an
allowlisted adapter or verifier. The pure evaluator performs schema validation,
checks that the verifier is allowed by policy, and binds every verified field to the
corresponding envelope field. A mismatch fails closed.

The evaluator does not verify a GitHub webhook signature or a conversation identity
by itself. That evidence must be produced by the connector/integration boundary and
must not be constructible from repository content, model output, issue text, logs,
diffs, files, or generated artifacts. Integration of a trusted verifier remains a
separate runtime gate.

A successful trigger decision authorizes only creation of a bounded work item. It
never grants approval, apply, push, merge, release-marker, credential, provider
purchase, or manual-evidence authority.

A policy document is not active merely because it is syntactically valid. Authorization
requires all three activation conditions: policy status `stable`, enforcement mode
`enforce`, and live connector integration state `pass`. The packaged contract remains
`draft`/`shadow` with integration `not_run`, so it cannot authorize work before target
integration evidence exists.

Verification evidence is time-bounded. The evaluator rejects evidence older than the
policy maximum age and evidence dated beyond the allowed future clock skew. Every
decision binds the canonical policy, envelope, and verification-context hashes together
with the verifier evidence hash and verification timestamp. Duplicate JSON object keys
are rejected at file-loading boundaries to avoid parser ambiguity.

## Runtime clock and denial audit

The public `evaluate_trigger` entry point owns the current UTC clock and has no
caller-controlled evaluation-time parameter. Deterministic timestamps are accepted only
by the private contract-test evaluator used by fixtures and unit tests; the live connector
boundary must call the public entry point.

Both schema backends accept the same RFC 3339 forms, including lowercase `t`/`z`, and
normalize them through one parser. A schema/parser discrepancy produces a deny decision
rather than an uncaught exception.

After a verification context passes schema validation, its verifier ID, evidence ID/hash,
and verification timestamp remain in denial decisions for audit. Their presence records a
validated claim; it does not imply that the verifier was allowlisted, the bindings matched,
the evidence was fresh, or trigger authority was granted.

## Verifier-to-channel binding

The trusted verifier class and the normalized provenance channel are a strict pair:
`github_connector` may attest only `github_connector`, while
`github_webhook_signature` may attest only `github_webhook`. A valid context cannot be
reused with the alternate channel; such a contradiction fails closed before app allowlist
evaluation. Conversation owner verification remains bound to the `conversation` channel.
