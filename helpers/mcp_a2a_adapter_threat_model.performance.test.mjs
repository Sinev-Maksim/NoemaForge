import test from "node:test";
import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { validateMcpA2aAdapterThreatModel } from "./mcp_a2a_adapter_threat_model.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("MCP/A2A adapter threat model validation stays bounded", () => {
  const started = performance.now();
  for (let index = 0; index < 300; index += 1) {
    const report = validateMcpA2aAdapterThreatModel(projectRoot);
    assert.equal(report.ok, true, report.failures.join("\n"));
  }
  const elapsedMs = performance.now() - started;
  assert.ok(elapsedMs < 1500, `adapter threat model validation took ${elapsedMs}ms`);
});
