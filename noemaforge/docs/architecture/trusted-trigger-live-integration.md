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

While the packaged policy remains `draft / shadow / not_run`, valid requests continue through the existing GUI behavior and receive a non-authorizing shadow audit. The audit records hashes and reason codes but does not persist raw conversation text.

After a separately reviewed activation changes the policy to `stable / enforce / pass`, the same endpoints no longer execute an external message as a command. A successful trigger creates exactly one pending task with `requires_approval=true`; execute/apply fields cannot expand that authority. A denied trigger produces no message, task, pipeline, apply, push, merge or release side effect.

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

The event is evaluated against the same contract as conversation triggers. An active, allowlisted event atomically claims its delivery ID in SQLite before it may proceed. A repeated delivery fails closed with `metadata_contradiction` and the stable diagnostic `replayed_delivery`. Payload digest mismatch fails before a replay claim is written.

The packaged `github_apps` allowlist remains empty. No GitHub App event can authorize production work until exact App and installation identifiers are configured through the separate activation gate.

## Audit and state

Integration state is stored under the platform-aware data root:

- `trusted-trigger/trusted-trigger-audit.jsonl` — append-only hash/reason audit;
- `trusted-trigger/github-deliveries.sqlite3` — persistent duplicate-delivery guard.

Raw message text and raw GitHub payloads are not written to the audit log. Decisions retain policy, envelope and verification-context hashes for correlation with the contract evaluator.

## Remaining target-host gate

This implementation is not sufficient to mark issue `#302` complete. The production target must still prove, from the exact PR head:

1. a real Admin GUI owner message creates one bounded pending work item after activation in an isolated UAT policy;
2. copied owner text and injected verification context are denied without mutation;
3. a real allowlisted GitHub connector event binds the observed App, installation, repository, event, delivery and payload digest;
4. duplicate, stale, future-dated, malformed and contradictory events fail closed;
5. before/after target-host evidence shows no unrelated task, job, repository, provider, credential or runtime mutation;
6. the packaged policy remains non-authorizing until that evidence is independently reviewed.

Policy activation must be a separate exact-head change after this gate passes.
