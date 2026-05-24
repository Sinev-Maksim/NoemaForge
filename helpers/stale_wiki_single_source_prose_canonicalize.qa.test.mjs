import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  buildSingleSourceProseCanonicalizeBatch,
  renderSingleSourceProseCanonicalizeReport,
  validateSingleSourceProseCanonicalize,
} from "./stale_wiki_single_source_prose_canonicalize.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("single-source prose canonicalize report validates applied canonical copies", () => {
  const report = validateSingleSourceProseCanonicalize(projectRoot);
  assert.equal(report.ok, true, report.failures.join("\n"));
});

test("single-source prose canonicalize keeps bounded offline contract", () => {
  const batch = buildSingleSourceProseCanonicalizeBatch(projectRoot);
  const markdown = renderSingleSourceProseCanonicalizeReport(projectRoot, { applied: [], metrics: batch.metrics });
  assert.ok(batch.metrics.batch_limit <= 3);
  assert.ok(markdown.includes('"active_todo_must_remain_open": true'));
  assert.ok(markdown.includes("The stale wiki cleanup TODO remains open"));
});
