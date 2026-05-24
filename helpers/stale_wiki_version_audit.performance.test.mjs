import test from "node:test";
import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { validateStaleWikiVersionAudit } from "./stale_wiki_version_audit.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("stale wiki version audit stays bounded", () => {
  const started = performance.now();
  for (let index = 0; index < 50; index += 1) {
    const report = validateStaleWikiVersionAudit(projectRoot);
    assert.equal(report.ok, true, report.failures.join("\n"));
  }
  const elapsedMs = performance.now() - started;
  assert.ok(elapsedMs < 1500, `stale wiki audit took ${elapsedMs}ms`);
});
