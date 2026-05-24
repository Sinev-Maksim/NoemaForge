import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { validateTodoDocs } from "./todo_docs_structure_check.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("normalized TODO documentation structure is valid", () => {
  const report = validateTodoDocs(projectRoot);
  assert.equal(report.ok, true, report.failures.join("\n"));
  assert.ok(report.metrics.short_todo_lines <= 120);
  assert.ok(report.metrics.current_target_open >= 15);
  assert.ok(report.metrics.current_done_contract >= 3);
  assert.ok(report.metrics.archive_bytes > 100000);
});

