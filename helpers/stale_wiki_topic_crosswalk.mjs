import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { inventoryStaleWikiPages } from "./stale_wiki_version_audit.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEFAULT_PROJECT_ROOT = path.resolve(__dirname, "..");
const DEFAULT_CONFIG_PATH = "noemaforge/configs/stale-wiki-topic-crosswalk.json";

function readJson(projectRoot, relativePath) {
  return JSON.parse(fs.readFileSync(path.join(projectRoot, relativePath), "utf8"));
}

function stripVersionSuffix(fileName) {
  return fileName
    .replace(/-0\.3[0-9](?:\.[0-9]+)?(?:\.alpha)?(?:-patched[0-9]+)?(?=\.md$)/g, "")
    .replace(/-0\.2[0-9](?:\.[0-9]+)?(?:\.alpha)?(?:-patched[0-9]+)?(?=\.md$)/g, "");
}

export function buildStaleWikiTopicCrosswalk(projectRoot = DEFAULT_PROJECT_ROOT) {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const inventory = inventoryStaleWikiPages(projectRoot);
  const canonicalPrefix = gate.policy?.canonical_topic_prefix || "noemaforge/docs/wiki";
  const rows = inventory.stalePages.map((source) => {
    const directory = path.dirname(source).replaceAll(path.sep, "/");
    const fileName = path.basename(source);
    const wikiRelativeDirectory = directory.replace(/^noemaforge\/docs\/wiki\/?/, "");
    const canonicalFile = stripVersionSuffix(fileName);
    const canonicalTopic = [canonicalPrefix, wikiRelativeDirectory, canonicalFile]
      .filter(Boolean)
      .join("/")
      .replaceAll("//", "/");
    return {
      source,
      canonical_topic: canonicalTopic,
      action: gate.policy?.default_action || "merge-unique-prose",
      status: "needs-review",
    };
  });
  return {
    rows,
    metrics: {
      stale_pages: inventory.stalePages.length,
      canonical_topics: new Set(rows.map((row) => row.canonical_topic)).size,
      duplicate_topic_groups: rows.length - new Set(rows.map((row) => row.canonical_topic)).size,
    },
  };
}

export function renderStaleWikiTopicCrosswalk(projectRoot = DEFAULT_PROJECT_ROOT) {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const crosswalk = buildStaleWikiTopicCrosswalk(projectRoot);
  const lines = [
    "# Stale Wiki Topic Crosswalk 0.32.1",
    "",
    "This machine-generated crosswalk maps versioned wiki pages to canonical topic destinations before any archival move. It is intentionally conservative: every row starts as `needs-review`, the default action is `merge-unique-prose`, and the active cleanup TODO remains open until prose integration and project-trash quarantine are complete.",
    "",
    "```json",
    JSON.stringify(
      {
        kind: "StaleWikiTopicCrosswalk",
        contract: "stale-wiki-topic-crosswalk-core",
        source_inventory: gate.policy?.source_inventory,
        stale_pages: crosswalk.metrics.stale_pages,
        canonical_topics: crosswalk.metrics.canonical_topics,
        duplicate_topic_groups: crosswalk.metrics.duplicate_topic_groups,
        completion_blocker: gate.policy?.completion_blocker,
      },
      null,
      2,
    ),
    "```",
    "",
    "| source | canonical_topic | action | status |",
    "| --- | --- | --- | --- |",
    ...crosswalk.rows.map((row) => `| \`${row.source}\` | \`${row.canonical_topic}\` | ${row.action} | ${row.status} |`),
    "",
  ];
  return lines.join("\n");
}

export function writeStaleWikiTopicCrosswalk(projectRoot = DEFAULT_PROJECT_ROOT) {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const reportPath = path.join(projectRoot, gate.policy?.crosswalk_report || "noemaforge/docs/quality/STALE_WIKI_TOPIC_CROSSWALK_0.32.1.md");
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, renderStaleWikiTopicCrosswalk(projectRoot), "utf8");
  return reportPath;
}

export function validateStaleWikiTopicCrosswalk(projectRoot = DEFAULT_PROJECT_ROOT) {
  const failures = [];
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const crosswalk = buildStaleWikiTopicCrosswalk(projectRoot);
  const reportRelative = gate.policy?.crosswalk_report || "noemaforge/docs/quality/STALE_WIKI_TOPIC_CROSSWALK_0.32.1.md";
  const reportPath = path.join(projectRoot, reportRelative);

  if (gate.kind !== "StaleWikiTopicCrosswalk") {
    failures.push("kind_invalid");
  }
  if (gate.id !== "stale-wiki-topic-crosswalk-core") {
    failures.push("id_invalid");
  }
  if (gate.policy?.active_todo_must_remain_open !== true) {
    failures.push("todo_completion_guard_missing");
  }
  if (!fs.existsSync(reportPath)) {
    failures.push("crosswalk_report_missing");
  } else {
    const report = fs.readFileSync(reportPath, "utf8");
    const rowCount = (report.match(/^\| `noemaforge\/docs\/wiki\//gm) || []).length;
    if (rowCount !== crosswalk.metrics.stale_pages) {
      failures.push(`crosswalk_row_count_mismatch:${rowCount}:${crosswalk.metrics.stale_pages}`);
    }
    if (!report.includes("needs-review") || !report.includes("merge-unique-prose")) {
      failures.push("crosswalk_review_status_missing");
    }
  }

  const shortTodo = fs.readFileSync(path.join(projectRoot, "noemaforge/docs/TODO.md"), "utf8");
  if (!shortTodo.includes("[docs-open] Rename or archive stale versioned wiki files")) {
    failures.push("active_todo_not_open");
  }

  return {
    ok: failures.length === 0,
    failures,
    metrics: crosswalk.metrics,
  };
}

if (typeof process !== "undefined" && process.argv[1] === __filename) {
  const command = process.argv[2] || "validate";
  const projectRoot = process.argv[3] || DEFAULT_PROJECT_ROOT;
  if (command === "write") {
    process.stdout.write(`${writeStaleWikiTopicCrosswalk(projectRoot)}\n`);
  } else {
    const report = validateStaleWikiTopicCrosswalk(projectRoot);
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    if (!report.ok) {
      process.exitCode = 1;
    }
  }
}
