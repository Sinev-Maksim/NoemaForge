import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { performance } from "node:perf_hooks";
import { fileURLToPath } from "node:url";
import { buildSingleSourceProseCanonicalizeBatch } from "./stale_wiki_single_source_prose_canonicalize.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("single-source prose canonicalize batch selection stays bounded", () => {
  const started = performance.now();
  const batch = buildSingleSourceProseCanonicalizeBatch(projectRoot);
  const elapsedMs = performance.now() - started;
  assert.ok(batch.metrics.batch_limit <= 3);
  assert.ok(batch.rows.length <= batch.metrics.batch_limit);
  assert.ok(elapsedMs < 1500, `batch selection took ${elapsedMs.toFixed(3)}ms`);
});
