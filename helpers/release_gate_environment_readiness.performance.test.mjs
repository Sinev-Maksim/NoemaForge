import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { performance } from "node:perf_hooks";
import { fileURLToPath } from "node:url";
import { evaluateReadiness } from "./release_gate_environment_readiness.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");
const policyPath = path.join(projectRoot, "noemaforge", "configs", "release-gate-environment-readiness.json");
const policy = JSON.parse(fs.readFileSync(policyPath, "utf8"));

test("release-gate environment readiness scan stays bounded", () => {
  const started = performance.now();
  for (let index = 0; index < 250; index += 1) {
    const report = evaluateReadiness(policy, {
      runCommand: (command) => ({
        command,
        args: [],
        status: 0,
        signal: null,
        error: "",
        stdout: "",
        stderr: "",
      }),
    });
    assert.equal(report.ok, true);
  }
  const elapsedMs = performance.now() - started;
  assert.ok(elapsedMs < 250, `readiness scan took ${elapsedMs}ms`);
});
