import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  buildStaleWikiCanonicalCopyPlan,
  renderStaleWikiCanonicalCopyPlan,
  validateStaleWikiCanonicalCopyPlan,
} from "./stale_wiki_canonical_copy_plan.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("stale wiki canonical copy plan records bounded safe trash moves", () => {
  const report = validateStaleWikiCanonicalCopyPlan(projectRoot);
  assert.equal(report.ok, true, report.failures.join("\n"));
});

test("rendered canonical copy plan keeps retained review sources active", () => {
  const plan = buildStaleWikiCanonicalCopyPlan(projectRoot);
  const markdown = renderStaleWikiCanonicalCopyPlan(plan, projectRoot);
  assert.ok(plan.metrics.selected_groups <= 3);
  assert.ok(markdown.includes("active_todo_must_remain_open"));
  assert.ok(markdown.includes("trash/"));
});
