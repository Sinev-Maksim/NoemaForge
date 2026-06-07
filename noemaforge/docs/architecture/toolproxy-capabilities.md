# ToolProxy & Capabilities

**ToolProxy** is NoemaForge's tool-access boundary. Agents and roles do not call tools directly;
every tool invocation is mediated by ToolProxy under a **capability token** that is scoped,
time-bound, and pinned to a contract epoch. This makes the extension/security surface explicit and
machine-checkable rather than an internal detail.

## Model

- **Deny-by-default.** A tool call is rejected unless a valid capability token authorizes exactly
  this tool + scope, for the active contract epoch, within its expiry, with an audit reason.
- **Issue / verify.** ToolProxy issues capability tokens and verifies them at call time (analogous
  to a sign/verify handshake); tokens are revocable.
- **Gateway-fronted egress.** Tool/provider access is fronted by the single gateway process
  (Unix-domain sockets under `/run/noemaforge/`), so egress and capability enforcement share one
  chokepoint (see the 0.33.0 gateway-adapter note).

## Capability token (shape)

A capability token carries at least: `tool`, `scope`, `contract_epoch`, `exp` (expiry), `reason`,
and a signature/validity marker. The published schema lives at
`noemaforge/schemas/capability-token.schema.json` (added in the 0.32.2 doc layer), and a
deny-by-default policy at `noemaforge/policies/toolproxy.rego` (validated by `noema policy test`
in 0.33.0). Sketch of the rule:

```rego
package noemaforge.toolproxy
default allow = false
allow if {
  input.cap.token_valid
  input.cap.tool == input.request.tool
  input.cap.scope == input.request.scope
  input.cap.contract_epoch == input.runtime.contract_epoch
  input.cap.exp_ns > time.now_ns()
  data.epochs[input.runtime.contract_epoch].tools[input.request.tool].enabled
}
```

## Boundary

ToolProxy sits between the control plane's planned actions and the execution plane. It cannot
broaden what the active **contract epoch** permits; it only enforces per-call authorization within
that epoch. Denied calls are recorded with a reason in the audit trail.

## Why it matters

A reviewer can confirm, without reading internal code, that a tool is reachable only via a scoped,
epoch-bound, expiring token through a single audited proxy — not "from the agent directly".
