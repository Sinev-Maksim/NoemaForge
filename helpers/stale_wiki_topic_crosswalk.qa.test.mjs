import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  buildStaleWikiTopicCrosswalk,
  renderStaleWikiTopicCrosswalk,
  validateStaleWikiTopicCrosswalk,
} from "./stale_wiki_topic_crosswalk.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("stale wiki topic crosswalk maps each stale page to a canonical topic", () => {
  const report = validateStaleWikiTopicCrosswalk(projectRoot);
  assert.equal(report.ok, true, report.failures.join("\n"));
  assert.ok(report.metrics.stale_pages > 0);
  assert.ok(report.metrics.canonical_topics > 0);
});

test("rendered stale wiki topic crosswalk keeps review status explicit", () => {
  const crosswalk = buildStaleWikiTopicCrosswalk(projectRoot);
  const markdown = renderStaleWikiTopicCrosswalk(projectRoot);
  assert.ok(markdown.includes("needs-review"));
  assert.ok(markdown.includes("merge-unique-prose"));
  assert.ok(markdown.includes("completion_blocker"));
  assert.equal((markdown.match(/^\| `noemaforge\/docs\/wiki\//gm) || []).length, crosswalk.metrics.stale_pages);
});
