import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { performance } from "node:perf_hooks";
import { fileURLToPath } from "node:url";
import { buildStaleWikiProseMergePlan } from "./stale_wiki_prose_merge_plan.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("stale wiki prose merge planning stays bounded", () => {
  const started = performance.now();
  const plan = buildStaleWikiProseMergePlan(projectRoot);
  const elapsedMs = performance.now() - started;
  assert.ok(plan.metrics.prose_review_groups > 0);
  assert.ok(elapsedMs < 1500, `prose merge planning took ${elapsedMs.toFixed(1)}ms`);
});
