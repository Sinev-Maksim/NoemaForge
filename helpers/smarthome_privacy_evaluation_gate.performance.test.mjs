import test from "node:test";
import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { validateSmartHomePrivacyGate } from "./smarthome_privacy_evaluation_gate.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("SmartHome privacy evaluation gate stays bounded on repeated small-fixture checks", () => {
  const started = performance.now();
  for (let index = 0; index < 300; index += 1) {
    const report = validateSmartHomePrivacyGate(projectRoot);
    assert.equal(report.ok, true, report.failures.join("\n"));
  }
  const elapsedMs = performance.now() - started;
  assert.ok(elapsedMs < 1500, `privacy gate validation took ${elapsedMs}ms`);
});
