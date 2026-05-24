import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  buildStaleWikiExactDuplicatePlan,
  renderStaleWikiExactDuplicatePlan,
  validateStaleWikiExactDuplicatePlan,
} from "./stale_wiki_exact_duplicate_plan.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("stale wiki exact duplicate plan identifies reviewable duplicate groups", () => {
  const report = validateStaleWikiExactDuplicatePlan(projectRoot);
  assert.equal(report.ok, true, report.failures.join("\n"));
  assert.ok(report.metrics.exact_duplicate_groups >= 0);
  assert.ok(report.metrics.duplicate_sources >= 0);
});

test("rendered exact duplicate plan does not authorize automatic moves", () => {
  const plan = buildStaleWikiExactDuplicatePlan(projectRoot);
  const markdown = renderStaleWikiExactDuplicatePlan(projectRoot);
  assert.ok(markdown.includes("auto_move_allowed"));
  if (plan.metrics.exact_duplicate_groups > 0) {
    assert.ok(markdown.includes("needs-review-before-trash"));
  } else {
    assert.ok(markdown.includes('"exact_duplicate_groups": 0'));
  }
  assert.equal((markdown.match(/^\| `noemaforge\/docs\/wiki\//gm) || []).length, plan.metrics.exact_duplicate_groups);
});
