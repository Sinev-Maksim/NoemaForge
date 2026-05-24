import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  evaluateTodoStatusLine,
  validateTodoStatusLabels,
} from "./todo_status_label_audit.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("active TODO status labels are explicit", () => {
  const report = validateTodoStatusLabels(projectRoot);
  assert.equal(report.ok, true, report.failures.join("\n"));
  assert.equal(report.metrics.active_files, 3);
  assert.ok(report.metrics.task_lines >= 20);
});

test("status-line evaluator rejects ambiguous checked tasks", () => {
  const policy = {
    allowed_status_labels: ["done-contract", "done-runtime", "target-open", "roadmap", "blocked", "docs-open"],
  };
  const ambiguous = evaluateTodoStatusLine(policy, "- [x] Closed without status.");
  assert.equal(ambiguous.decision, "deny");
  assert.ok(ambiguous.failures.includes("checked_task_missing_done_label"));
  const explicit = evaluateTodoStatusLine(policy, "- [x] [done-contract] Closed with contract evidence.");
  assert.equal(explicit.decision, "allow");
});
