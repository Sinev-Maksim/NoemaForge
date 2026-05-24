import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  inventoryStaleWikiPages,
  validateStaleWikiVersionAudit,
} from "./stale_wiki_version_audit.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("stale wiki version audit inventories versioned pages without archiving", () => {
  const report = validateStaleWikiVersionAudit(projectRoot);
  assert.equal(report.ok, true, report.failures.join("\n"));
  assert.ok(report.metrics.total_markdown > 0);
  assert.ok(report.metrics.stale_pages > 0);
  assert.ok(report.metrics.directories_with_stale_pages > 0);
});

test("stale wiki inventory reports project-relative markdown paths", () => {
  const inventory = inventoryStaleWikiPages(projectRoot);
  assert.ok(inventory.stalePages.every((relativePath) => relativePath.startsWith("noemaforge/docs/wiki/")));
  assert.ok(inventory.stalePages.every((relativePath) => relativePath.endsWith(".md")));
});
