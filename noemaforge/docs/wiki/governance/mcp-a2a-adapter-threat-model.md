# MCP/A2A Adapter Threat Model

MCP and A2A are treated as extension boundaries, not as implicit permission to expand NoemaForge autonomy. Before any live adapter is enabled, it must pass a zero-trust threat model that proves the adapter has a narrow purpose, explicit scopes, review evidence, auditability, and a rollback path.

The adapter manifest starts disabled. Tool exposure is deny-by-default and must use an explicit allowlist rather than wildcard capabilities. Each adapter declares per-adapter capability scopes so an exchange peer, local tool server, or helper process cannot inherit broad runtime permissions from another adapter.

Network access is denied by default. Mutating actions either stay denied or require explicit approval. Secrets must not be embedded in the manifest, and every reviewed adapter needs SR/SSR evidence, an audit trail, and a rollback plan that can revoke capability bindings and quarantine artifacts.

The executable contract is `mcp-a2a-adapter-threat-model-core` in `noemaforge/configs/mcp-a2a-adapter-threat-model.json`. The local validator in `helpers/mcp_a2a_adapter_threat_model.mjs` checks allow-shadow examples and a denied wildcard adapter case without starting live adapters, opening network connections, or granting tool access.
