import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEFAULT_PROJECT_ROOT = path.resolve(__dirname, "..");
const DEFAULT_CONFIG_PATH = "noemaforge/configs/stale-wiki-version-audit.json";

function readJson(projectRoot, relativePath) {
  return JSON.parse(fs.readFileSync(path.join(projectRoot, relativePath), "utf8"));
}

function walkFiles(rootDirectory) {
  const files = [];
  for (const entry of fs.readdirSync(rootDirectory, { withFileTypes: true })) {
    const fullPath = path.join(rootDirectory, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkFiles(fullPath));
    } else if (entry.isFile()) {
      files.push(fullPath);
    }
  }
  return files;
}

function toProjectRelative(projectRoot, fullPath) {
  return path.relative(projectRoot, fullPath).replaceAll(path.sep, "/");
}

export function inventoryStaleWikiPages(projectRoot = DEFAULT_PROJECT_ROOT) {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const policy = gate.policy || {};
  const wikiRoot = path.join(projectRoot, policy.wiki_root || "noemaforge/docs/wiki");
  const patterns = policy.stale_filename_patterns || [];
  const markdownFiles = walkFiles(wikiRoot).filter((fullPath) => fullPath.endsWith(".md"));
  const stalePages = markdownFiles
    .filter((fullPath) => patterns.some((pattern) => path.basename(fullPath).includes(pattern)))
    .map((fullPath) => toProjectRelative(projectRoot, fullPath))
    .sort();

  const byDirectory = {};
  for (const relativePath of stalePages) {
    const directory = path.dirname(relativePath).replaceAll(path.sep, "/");
    byDirectory[directory] = (byDirectory[directory] || 0) + 1;
  }

  return {
    stalePages,
    byDirectory,
    totalMarkdown: markdownFiles.length,
  };
}

export function validateStaleWikiVersionAudit(projectRoot = DEFAULT_PROJECT_ROOT) {
  const failures = [];
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const policy = gate.policy || {};

  if (gate.kind !== "StaleWikiVersionAudit") {
    failures.push("kind_invalid");
  }
  if (gate.id !== "stale-wiki-version-audit-core") {
    failures.push("id_invalid");
  }
  if (policy.archive_without_crosswalk_allowed !== false) {
    failures.push("unsafe_archive_policy");
  }
  if (policy.active_todo_must_remain_open_until_moves_complete !== true) {
    failures.push("todo_completion_guard_missing");
  }
  for (const action of ["inventory_versioned_pages", "map_to_canonical_topic", "merge_unique_prose", "move_obsolete_source_to_trash_after_integration", "preserve_redirect_or_crosswalk"]) {
    if (!policy.required_next_actions?.includes(action)) {
      failures.push(`missing_next_action:${action}`);
    }
  }

  const inventory = inventoryStaleWikiPages(projectRoot);
  if (inventory.totalMarkdown === 0) {
    failures.push("wiki_markdown_inventory_empty");
  }
  if (gate.expected_report?.stale_pages_may_exist && inventory.stalePages.length === 0) {
    failures.push("expected_stale_pages_not_found");
  }

  const shortTodo = fs.readFileSync(path.join(projectRoot, "noemaforge/docs/TODO.md"), "utf8");
  if (!shortTodo.includes("[docs-open] Rename or archive stale versioned wiki files")) {
    failures.push("active_todo_not_open");
  }

  return {
    ok: failures.length === 0,
    failures,
    metrics: {
      total_markdown: inventory.totalMarkdown,
      stale_pages: inventory.stalePages.length,
      directories_with_stale_pages: Object.keys(inventory.byDirectory).length,
    },
    sample: inventory.stalePages.slice(0, 10),
    byDirectory: inventory.byDirectory,
  };
}

if (typeof process !== "undefined" && process.argv[1] === __filename) {
  const report = validateStaleWikiVersionAudit(process.argv[2] || DEFAULT_PROJECT_ROOT);
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.ok) {
    process.exitCode = 1;
  }
}
