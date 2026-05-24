import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  buildStaleWikiProseMergePlan,
  renderStaleWikiProseMergePlan,
  validateStaleWikiProseMergePlan,
} from "./stale_wiki_prose_merge_plan.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("stale wiki prose merge plan identifies review-only source groups", () => {
  const report = validateStaleWikiProseMergePlan(projectRoot);
  assert.equal(report.ok, true, report.failures.join("\n"));
  assert.ok(report.metrics.prose_review_groups > 0);
  assert.ok(report.metrics.sources_requiring_review > 0);
});

test("rendered prose merge plan never authorizes trash moves", () => {
  const plan = buildStaleWikiProseMergePlan(projectRoot);
  const markdown = renderStaleWikiProseMergePlan(projectRoot);
  assert.ok(markdown.includes('"move_sources_to_trash": false'));
  assert.ok(markdown.includes("needs-prose-review"));
  assert.equal((markdown.match(/^\| `noemaforge\/docs\/wiki\//gm) || []).length, plan.metrics.prose_review_groups);
});
