import test from "node:test";
import assert from "node:assert/strict";
import { performance } from "node:perf_hooks";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildStaleWikiTopicCrosswalk } from "./stale_wiki_topic_crosswalk.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("stale wiki topic crosswalk generation stays bounded", () => {
  const started = performance.now();
  for (let index = 0; index < 50; index += 1) {
    const crosswalk = buildStaleWikiTopicCrosswalk(projectRoot);
    assert.ok(crosswalk.metrics.stale_pages > 0);
  }
  const elapsedMs = performance.now() - started;
  assert.ok(elapsedMs < 1500, `stale wiki topic crosswalk took ${elapsedMs}ms`);
});
