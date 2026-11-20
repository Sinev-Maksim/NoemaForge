# Trusted trigger live integration

Status: implementation candidate for `0.33.0` UAT request findings resolution.

This integration connects the trusted trigger-source contract to the localhost Admin GUI ingress and exposes a capability-bound adapter for verified GitHub connector events. It does not activate the packaged policy and does not claim target-host UAT.

## Conversation ingress

The protected conversation paths are:

- `/api/admin/message`;
- `/api/admin/ask`;
- `/api/admin/start`;
- `/api/conversation/message`;
- `/api/tasks/create`.

`TrustedTriggerVerificationContext` is created inside the route adapter from server-owned session metadata and observed HTTP connection metadata. Login text, message text and request-body identity claims are not authority. Any request containing a verification-context field is rejected before `save_message`, task creation, pipeline routing or another side effect.

Loopback addressing is necessary but is not treated as owner identity. The dashboard launcher creates a cryptographically random one-time bootstrap token in the operator state directory with mode `0600` and prints an owner bootstrap URL. The token is placed only in the URL fragment, so it is not sent in the HTTP request line, server logs or referrer. `owner-bootstrap.html` removes the fragment from browser history and sends the token once in a same-origin POST body.

`/api/session/owner-bootstrap` accepts the token only from a loopback client with a loopback Host and loopback-or-absent Origin. The route adapter securely reads and removes the launcher token file, performs a constant-time one-time comparison, and exchanges it for a process-local `nf_owner_session` capability as an `HttpOnly`, `SameSite=Strict` cookie bound to the active GUI session. Ordinary GET routes cannot issue authority cookies. The random bootstrap/session values are never accepted as identity fields inside a work request and are represented in evidence only by SHA-256 where correlation is needed.

While the packaged policy remains `draft / shadow / not_run`, valid requests continue through the existing GUI behavior and receive a non-authorizing shadow audit. Requests without the owner-session capability are visible as shadow denials and cannot pass after activation. The audit records hashes and reason codes but does not persist raw conversation text or capability tokens.

After a separately reviewed activation changes the policy to `stable / enforce / pass`, the same endpoints no longer execute an external message as a command. A successful trigger creates exactly one pending task with `requires_approval=true`; execute/apply fields cannot expand that authority. A denied trigger produces no message, task, pipeline, apply, push, merge or release side effect.

The bootstrap is a launcher-to-browser capability, not proof of a human biometric or cryptographic OS identity. Its security boundary is the operator account, the mode-`0600` state directory, the local terminal/journal that displays the fragment URL, browser same-origin enforcement and the loopback-only server. Target-host UAT must verify those assumptions, capability rotation on restart, and denial from unrelated local origins/users.

## GitHub connector ingress

`TrustedTriggerIntegration.bind_github_connector()` returns a capability-bound adapter. The adapter accepts metadata only from its trusted connector owner and constructs the verification context internally. There is no HTTP or JSON field that can mint the adapter capability.

The connector metadata binds:

- GitHub App ID and installation ID;
- repository;
- event type;
- delivery ID;
- canonical normalized payload SHA-256;
- connector evidence ID;
- verification timestamp.

The event is evaluated against the same contract as conversation triggers. An active, allowlisted event atomically claims its delivery ID in SQLite before it may proceed. SQLite connections are explicitly closed and a failed duplicate claim rolls its transaction back. A repeated delivery fails closed with `metadata_contradiction` and the stable diagnostic `replayed_delivery`. Payload digest mismatch fails before a replay claim is written.

The packaged `github_apps` allowlist remains empty. No GitHub App event can authorize production work until exact App and installation identifiers are configured through the separate activation gate.

## Audit and state

Integration state is stored under the platform-aware data root:

- `trusted-trigger/trusted-trigger-audit.jsonl` — append-only hash/reason audit;
- `trusted-trigger/github-deliveries.sqlite3` — persistent duplicate-delivery guard;
- `owner-bootstrap.token` — launcher-created mode-`0600` one-time token, removed when loaded by the integration boundary.

Raw message text, bootstrap/session capability values and raw GitHub payloads are not written to the audit log. Decisions retain policy, envelope and verification-context hashes for correlation with the contract evaluator.

## Remaining target-host gate

This implementation is not sufficient to mark issue `#302` complete. The production target must still prove, from the exact PR head:

1. a real launcher bootstrap establishes one owner browser session without putting the token in request logs/history;
2. a real Admin GUI owner message with the issued session capability creates one bounded pending work item after activation in an isolated UAT policy;
3. copied owner text, missing/invalid/replayed bootstrap or session capabilities, cross-origin bootstrap and injected verification context are denied without mutation;
4. a real allowlisted GitHub connector event binds the observed App, installation, repository, event, delivery and payload digest;
5. duplicate, stale, future-dated, malformed and contradictory connector events fail closed;
6. before/after target-host evidence shows no unrelated task, job, repository, provider, credential or runtime mutation;
7. the packaged policy remains non-authorizing until that evidence is independently reviewed.

Policy activation must be a separate exact-head change after this gate passes.
