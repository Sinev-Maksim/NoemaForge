import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEFAULT_PROJECT_ROOT = path.resolve(__dirname, "..");
const DEFAULT_CONFIG_PATH = "noemaforge/configs/mcp-a2a-adapter-threat-model.json";

function readJson(projectRoot, relativePath) {
  return JSON.parse(fs.readFileSync(path.join(projectRoot, relativePath), "utf8"));
}

export function evaluateAdapterThreatModel(policy, adapter) {
  const failures = [];
  const requiredFields = [
    "adapter_id",
    "protocol",
    "enabled",
    "capability_scopes",
    "tool_exposure",
    "network_access",
    "mutating_actions",
    "sr_ssr_review",
    "audit_trail",
    "rollback_plan",
  ];

  for (const field of requiredFields) {
    if (!(field in adapter)) {
      failures.push(`missing_field:${field}`);
    }
  }
  if (!["mcp", "a2a"].includes(adapter.protocol)) {
    failures.push("protocol_not_supported");
  }
  if (policy.live_adapters_enabled_by_default === false && adapter.enabled === true) {
    failures.push("live_adapter_enabled");
  }
  if (!Array.isArray(adapter.capability_scopes) || adapter.capability_scopes.length === 0) {
    failures.push("capability_scopes_required");
  }
  if (policy.deny_by_default_tool_exposure && adapter.tool_exposure !== "explicit_allowlist") {
    failures.push("wildcard_tool_exposure_denied");
  }
  if (policy.network_access_default === "deny" && adapter.network_access !== "deny") {
    failures.push("network_access_not_denied");
  }
  if (policy.mutating_actions_require_approval && !["deny", "approval_required"].includes(adapter.mutating_actions)) {
    failures.push("mutating_actions_not_guarded");
  }
  if (policy.sr_ssr_review_required && adapter.sr_ssr_review !== true) {
    failures.push("sr_ssr_review_required");
  }
  if (policy.audit_trail_required && adapter.audit_trail !== true) {
    failures.push("audit_trail_required");
  }
  if (policy.rollback_plan_required && typeof adapter.rollback_plan !== "string") {
    failures.push("rollback_plan_required");
  } else if (policy.rollback_plan_required && adapter.rollback_plan.trim().length < 16) {
    failures.push("rollback_plan_too_short");
  }

  return {
    ok: failures.length === 0,
    decision: failures.length === 0 ? "allow_shadow" : "deny",
    failures,
  };
}

export function validateMcpA2aAdapterThreatModel(projectRoot = DEFAULT_PROJECT_ROOT) {
  const failures = [];
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const policy = gate.policy || {};

  if (gate.kind !== "McpA2aAdapterThreatModel") {
    failures.push("kind_invalid");
  }
  if (gate.id !== "mcp-a2a-adapter-threat-model-core") {
    failures.push("id_invalid");
  }
  if (policy.live_adapters_enabled_by_default !== false) {
    failures.push("live_adapters_not_disabled_by_default");
  }
  if (policy.zero_trust_adapter_manifest_required !== true) {
    failures.push("zero_trust_manifest_missing");
  }
  if (policy.deny_by_default_tool_exposure !== true) {
    failures.push("deny_by_default_missing");
  }
  if (policy.per_adapter_capability_scopes_required !== true) {
    failures.push("capability_scope_policy_missing");
  }
  if (policy.sr_ssr_review_required !== true) {
    failures.push("sr_ssr_policy_missing");
  }

  const caseResults = [];
  for (const adapter of gate.example_adapters || []) {
    const result = evaluateAdapterThreatModel(policy, adapter);
    caseResults.push({ adapter_id: adapter.adapter_id, ...result });
    if (result.decision !== adapter.expected) {
      failures.push(`unexpected_adapter_decision:${adapter.adapter_id}`);
    }
    for (const expectedFailure of adapter.expected_failures || []) {
      if (!result.failures.includes(expectedFailure)) {
        failures.push(`missing_adapter_failure:${adapter.adapter_id}:${expectedFailure}`);
      }
    }
  }
  if (caseResults.length < 3) {
    failures.push("insufficient_example_adapters");
  }
  if (!caseResults.some((result) => result.decision === "deny")) {
    failures.push("missing_denied_adapter_case");
  }

  return {
    ok: failures.length === 0,
    failures,
    metrics: {
      example_adapters: caseResults.length,
      allowed_shadow_adapters: caseResults.filter((result) => result.decision === "allow_shadow").length,
      denied_adapters: caseResults.filter((result) => result.decision === "deny").length,
    },
    caseResults,
  };
}

if (typeof process !== "undefined" && process.argv[1] === __filename) {
  const report = validateMcpA2aAdapterThreatModel(process.argv[2] || DEFAULT_PROJECT_ROOT);
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.ok) {
    process.exitCode = 1;
  }
}
