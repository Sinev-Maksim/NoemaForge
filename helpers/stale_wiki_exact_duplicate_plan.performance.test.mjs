import test from "node:test";
import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildStaleWikiExactDuplicatePlan } from "./stale_wiki_exact_duplicate_plan.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("stale wiki exact duplicate planning stays bounded", () => {
  const started = performance.now();
  for (let index = 0; index < 30; index += 1) {
    const plan = buildStaleWikiExactDuplicatePlan(projectRoot);
    assert.ok(plan.metrics.exact_duplicate_groups > 0);
  }
  const elapsedMs = performance.now() - started;
  assert.ok(elapsedMs < 1500, `stale wiki exact duplicate plan took ${elapsedMs}ms`);
});
