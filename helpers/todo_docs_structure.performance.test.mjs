import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { performance } from "node:perf_hooks";
import { fileURLToPath } from "node:url";
import { validateTodoDocs } from "./todo_docs_structure_check.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("TODO documentation validation remains bounded", () => {
  const started = performance.now();
  for (let index = 0; index < 50; index += 1) {
    const report = validateTodoDocs(projectRoot);
    assert.equal(report.ok, true, report.failures.join("\n"));
  }
  const elapsedMs = performance.now() - started;
  assert.ok(elapsedMs < 500, `TODO docs validation took ${elapsedMs}ms`);
});

