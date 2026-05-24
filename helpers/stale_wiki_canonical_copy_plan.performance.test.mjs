import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { performance } from "node:perf_hooks";
import { fileURLToPath } from "node:url";
import { buildStaleWikiCanonicalCopyPlan } from "./stale_wiki_canonical_copy_plan.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("stale wiki canonical copy planning stays bounded", () => {
  const started = performance.now();
  const plan = buildStaleWikiCanonicalCopyPlan(projectRoot);
  const elapsedMs = performance.now() - started;
  assert.ok(plan.metrics.selected_groups <= 3);
  assert.ok(elapsedMs < 1500, `canonical copy planning took ${elapsedMs.toFixed(1)}ms`);
});
