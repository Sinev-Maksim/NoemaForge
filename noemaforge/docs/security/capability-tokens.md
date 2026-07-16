# Capability Tokens

Capability tokens are how NoemaForge authorizes tool access. They make the security boundary
**machine-checkable**: a tool runs only when a valid token authorizes exactly that tool and scope,
for the active contract epoch, before expiry — enforced by ToolProxy, deny-by-default.

## Contract

The token shape is published as a JSON schema:
[`noemaforge/schemas/capability-token.schema.json`](../../schemas/capability-token.schema.json).
Required fields: `tool`, `scope`, `contract_epoch`, `issued_at`, `expires_at`, `reason`. Optional:
`token_id`, `subject`, `revoked`, `signature`.

## Lifecycle

1. **Issue** — ToolProxy issues a token scoped to a tool + scope, pinned to the active
   `contract_epoch`, with an expiry and an audit `reason`.
2. **Verify** — at call time ToolProxy verifies the token: tool/scope match the request, epoch
   matches the runtime, not expired, not revoked, signature valid (if present).
3. **Audit** — the authorized or denied call is recorded with its reason.
4. **Revoke / expire** — tokens are revocable and always expire; an expired or revoked token is
   denied regardless of other fields.

## Enforcement

Deny-by-default: absent a valid token, the call is rejected. The policy intent (validated by
`noema policy test` in 0.33.0) lives at `noemaforge/policies/toolproxy.rego`. See
[`../architecture/toolproxy-capabilities.md`](../architecture/toolproxy-capabilities.md) for the
proxy boundary and the rule sketch, and [`../architecture/contract-epochs.md`](../architecture/contract-epochs.md)
for how epochs scope what a token may authorize.

For native ToolProxy JSON-over-socket calls, the token is a top-level `token`
field. The caller identity is not read from top-level `actor` or `role`; it is
read from `meta.role`, `meta.project_id`, `meta.run_id`, and
`meta.stream_id`. These `meta` fields are part of the capability binding and
must match the token's `issued_to` record. See the canonical envelope in
[`../architecture/toolproxy-capabilities.md`](../architecture/toolproxy-capabilities.md#native-request-envelope).

## Why it matters

A reviewer can confirm tools are not callable "from the agent directly" — only via a scoped,
epoch-bound, expiring, audited token — by reading one schema and one policy file.
