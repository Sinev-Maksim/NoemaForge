import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  evaluateAdapterThreatModel,
  validateMcpA2aAdapterThreatModel,
} from "./mcp_a2a_adapter_threat_model.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("MCP/A2A adapter threat model validates zero-trust defaults", () => {
  const report = validateMcpA2aAdapterThreatModel(projectRoot);
  assert.equal(report.ok, true, report.failures.join("\n"));
  assert.equal(report.metrics.example_adapters, 3);
  assert.equal(report.metrics.allowed_shadow_adapters, 2);
  assert.equal(report.metrics.denied_adapters, 1);
});

test("MCP/A2A adapter threat evaluator rejects wildcard live adapters", () => {
  const policy = {
    live_adapters_enabled_by_default: false,
    deny_by_default_tool_exposure: true,
    network_access_default: "deny",
    mutating_actions_require_approval: true,
    sr_ssr_review_required: true,
    audit_trail_required: true,
    rollback_plan_required: true,
  };
  const result = evaluateAdapterThreatModel(policy, {
    adapter_id: "mcp.bad",
    protocol: "mcp",
    enabled: true,
    capability_scopes: ["exec.run"],
    tool_exposure: "wildcard",
    network_access: "allow",
    mutating_actions: "allow",
    sr_ssr_review: false,
    audit_trail: false,
    rollback_plan: "",
  });
  assert.equal(result.decision, "deny");
  assert.ok(result.failures.includes("live_adapter_enabled"));
  assert.ok(result.failures.includes("wildcard_tool_exposure_denied"));
  assert.ok(result.failures.includes("network_access_not_denied"));
  assert.ok(result.failures.includes("sr_ssr_review_required"));
});
