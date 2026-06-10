# MCP and A2A as zero-trust extension boundaries

> **Status: historical snapshot (0.31.21.alpha era).** Kept as release-evidence history; it is not maintained. For the current state start at the [wiki hub](../WIKI.md).

Version scope: runtime `0.32.1`, documentation reconciliation `0.32.1-docs-integrated`.  
Updated: 2026-05-18T20:33:59Z

## Policy

MCP/A2A are extension and interoperability boundaries, not permission to increase autonomy.

Every adapter must have:

- manifest;
- capability scope;
- local/cloud/privacy classification;
- sandbox policy;
- audit logging;
- SR/SSR review route;
- rollback/removal plan.

## No hidden tool execution

No agent may call a new MCP/A2A tool without:

```text
registry entry -> policy check -> capability token -> trace -> artifact -> review evidence
```

## Executable MCP adapter registry seed

The MCP side now has a local, zero-trust registry seed:

- `noemaforge/configs/mcp-adapter-registry.json`
- `noemaforge/contracts/mcp_adapter_registry.schema.json`
- `noemaforge/src/mcp_adapter_registry_runtime.py`
- `noemaforge/tests/test_mcp_adapter_registry_runtime.py`

The registry is intentionally stricter than the older `mcp-adapters.yaml` local
catalog. It treats adapters as disabled by default, denies network egress,
allows only local transports (`stdio`, `unix_socket`), requires capability
scopes, requires trace IDs and capability tokens, and keeps SR/SSR review plus a
rollback plan on every adapter record.

The existing local `mcp_router.py` catalog loader also has a stdlib fallback for
the small shipped `mcp-adapters.yaml` shape, so offline smoke tests do not depend
on installing PyYAML.

Local validation:

```bash
python noemaforge/src/mcp_adapter_registry_runtime.py --project-root . --summary
```

This validator is the acceptance gate before an adapter can move from a local
catalog entry into shadow/canary/enabled exposure.

## Executable A2A interoperability seed

The A2A side now has a matching optional interop registry:

- `noemaforge/configs/a2a-interop-registry.json`
- `noemaforge/contracts/a2a_interop_registry.schema.json`
- `noemaforge/src/a2a_interop_registry_runtime.py`
- `noemaforge/tests/test_a2a_interop_registry_runtime.py`

The registry models A2A as reviewed envelope exchange, not remote delegation.
Seed peers are disabled by default, use offline manifest transport only, deny
network egress, require trace IDs and capability tokens, forbid autonomy
increase, require human review, and require release evidence before any
shadow/canary/enabled state.

Local validation:

```bash
python noemaforge/src/a2a_interop_registry_runtime.py --project-root . --summary
```

This keeps A2A as an optional interoperability boundary until a specific peer
has registry evidence, SR/SSR review, release evidence and rollback coverage.
