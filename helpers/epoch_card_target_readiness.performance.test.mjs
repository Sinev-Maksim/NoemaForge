import test from "node:test";
import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { validateEpochCardTargetReadiness } from "./epoch_card_target_readiness.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("Epoch Card target readiness validation stays bounded", () => {
  const started = performance.now();
  for (let index = 0; index < 300; index += 1) {
    const report = validateEpochCardTargetReadiness(projectRoot);
    assert.equal(report.ok, true, report.failures.join("\n"));
  }
  const elapsedMs = performance.now() - started;
  assert.ok(elapsedMs < 1500, `epoch card readiness validation took ${elapsedMs}ms`);
});
