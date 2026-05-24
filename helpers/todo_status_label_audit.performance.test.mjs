import test from "node:test";
import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { validateTodoStatusLabels } from "./todo_status_label_audit.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("TODO status-label audit stays bounded", () => {
  const started = performance.now();
  for (let index = 0; index < 300; index += 1) {
    const report = validateTodoStatusLabels(projectRoot);
    assert.equal(report.ok, true, report.failures.join("\n"));
  }
  const elapsedMs = performance.now() - started;
  assert.ok(elapsedMs < 1500, `TODO status-label audit took ${elapsedMs}ms`);
});
