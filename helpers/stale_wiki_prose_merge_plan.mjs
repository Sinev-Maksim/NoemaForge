import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { buildStaleWikiTopicCrosswalk } from "./stale_wiki_topic_crosswalk.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEFAULT_PROJECT_ROOT = path.resolve(__dirname, "..");
const DEFAULT_CONFIG_PATH = "noemaforge/configs/stale-wiki-prose-merge-plan.json";

function readJson(projectRoot, relativePath) {
  return JSON.parse(fs.readFileSync(path.join(projectRoot, relativePath), "utf8"));
}

function readText(projectRoot, relativePath) {
  return fs.readFileSync(path.join(projectRoot, relativePath), "utf8").replace(/\r\n/g, "\n");
}

function normalizedText(text) {
  return text.replace(/\s+/g, " ").trim();
}

function normalizedHash(text) {
  return crypto.createHash("sha256").update(normalizedText(text)).digest("hex");
}

function wordCount(text) {
  const words = normalizedText(text).match(/[A-Za-z0-9А-Яа-яЁё_-]+/g);
  return words ? words.length : 0;
}

function groupRows(rows) {
  const byCanonical = new Map();
  for (const row of rows) {
    if (!byCanonical.has(row.canonical_topic)) {
      byCanonical.set(row.canonical_topic, []);
    }
    byCanonical.get(row.canonical_topic).push(row.source);
  }
  return byCanonical;
}

export function buildStaleWikiProseMergePlan(projectRoot = DEFAULT_PROJECT_ROOT) {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const crosswalk = buildStaleWikiTopicCrosswalk(projectRoot);
  const rows = [];
  for (const [canonicalTopic, sources] of groupRows(crosswalk.rows)) {
    const sourceDetails = sources.map((source) => {
      const text = readText(projectRoot, source);
      return {
        source,
        normalized_sha256: normalizedHash(text),
        words: wordCount(text),
      };
    });
    const distinctHashes = new Set(sourceDetails.map((detail) => detail.normalized_sha256));
    const canonicalExists = fs.existsSync(path.join(projectRoot, canonicalTopic));
    if (sources.length === 1 || distinctHashes.size > 1) {
      rows.push({
        canonical_topic: canonicalTopic,
        source_count: sources.length,
        distinct_versions: distinctHashes.size,
        canonical_exists: canonicalExists,
        action: gate.policy?.default_action || "merge-unique-prose-before-trash",
        status: gate.policy?.required_status || "needs-prose-review",
        sources: sourceDetails,
      });
    }
  }

  return {
    rows,
    metrics: {
      prose_review_groups: rows.length,
      sources_requiring_review: rows.reduce((total, row) => total + row.source_count, 0),
      canonical_topics_missing: rows.filter((row) => !row.canonical_exists).length,
      single_source_groups: rows.filter((row) => row.source_count === 1).length,
      multi_source_non_identical_groups: rows.filter((row) => row.source_count > 1).length,
    },
  };
}

export function renderStaleWikiProseMergePlan(projectRoot = DEFAULT_PROJECT_ROOT) {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const plan = buildStaleWikiProseMergePlan(projectRoot);
  const lines = [
    "# Stale Wiki Prose Merge Plan 0.32.1",
    "",
    "This machine-generated plan starts the non-identical stale wiki cleanup phase. It does not move files. Each row identifies a canonical topic whose versioned source pages still need prose review, unique-content merge decisions, and only then project-trash quarantine.",
    "",
    "```json",
    JSON.stringify(
      {
        kind: gate.kind,
        contract: gate.id,
        source_crosswalk: gate.policy?.source_crosswalk,
        source_exact_duplicate_plan: gate.policy?.source_exact_duplicate_plan,
        prose_review_groups: plan.metrics.prose_review_groups,
        sources_requiring_review: plan.metrics.sources_requiring_review,
        canonical_topics_missing: plan.metrics.canonical_topics_missing,
        move_sources_to_trash: gate.policy?.move_sources_to_trash,
      },
      null,
      2,
    ),
    "```",
    "",
    "| canonical_topic | sources | distinct_versions | canonical_exists | action | status |",
    "| --- | ---: | ---: | --- | --- | --- |",
    ...plan.rows.map((row) => `| \`${row.canonical_topic}\` | ${row.source_count} | ${row.distinct_versions} | ${row.canonical_exists ? "yes" : "no"} | ${row.action} | ${row.status} |`),
    "",
    "## Source Details",
    "",
  ];
  for (const row of plan.rows) {
    lines.push(`### ${row.canonical_topic}`, "");
    for (const source of row.sources) {
      lines.push(`- \`${source.source}\` - words: ${source.words}; normalized_sha256: \`${source.normalized_sha256}\``);
    }
    lines.push("");
  }
  return lines.join("\n");
}

export function writeStaleWikiProseMergePlan(projectRoot = DEFAULT_PROJECT_ROOT) {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const reportPath = path.join(projectRoot, gate.policy?.prose_merge_report || "noemaforge/docs/quality/STALE_WIKI_PROSE_MERGE_PLAN_0.32.1.md");
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, renderStaleWikiProseMergePlan(projectRoot), "utf8");
  return reportPath;
}

export function validateStaleWikiProseMergePlan(projectRoot = DEFAULT_PROJECT_ROOT) {
  const failures = [];
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const plan = buildStaleWikiProseMergePlan(projectRoot);
  const reportRelative = gate.policy?.prose_merge_report || "noemaforge/docs/quality/STALE_WIKI_PROSE_MERGE_PLAN_0.32.1.md";
  const reportPath = path.join(projectRoot, reportRelative);

  if (gate.kind !== "StaleWikiProseMergePlan") {
    failures.push("kind_invalid");
  }
  if (gate.id !== "stale-wiki-prose-merge-plan-core") {
    failures.push("id_invalid");
  }
  if (gate.policy?.move_sources_to_trash !== false) {
    failures.push("trash_move_policy_unsafe");
  }
  if (gate.policy?.active_todo_must_remain_open !== true) {
    failures.push("todo_completion_guard_missing");
  }
  if (plan.metrics.prose_review_groups === 0) {
    failures.push("prose_review_groups_missing");
  }
  if (!fs.existsSync(reportPath)) {
    failures.push("prose_merge_report_missing");
  } else {
    const report = fs.readFileSync(reportPath, "utf8");
    const rowCount = (report.match(/^\| `noemaforge\/docs\/wiki\//gm) || []).length;
    if (rowCount !== plan.metrics.prose_review_groups) {
      failures.push(`prose_merge_row_count_mismatch:${rowCount}:${plan.metrics.prose_review_groups}`);
    }
    if (!report.includes("needs-prose-review") || !report.includes('"move_sources_to_trash": false')) {
      failures.push("prose_merge_guard_missing");
    }
  }

  const shortTodo = fs.readFileSync(path.join(projectRoot, "noemaforge/docs/TODO.md"), "utf8");
  if (!shortTodo.includes("[docs-open] Rename or archive stale versioned wiki files")) {
    failures.push("active_todo_not_open");
  }

  return {
    ok: failures.length === 0,
    failures,
    metrics: plan.metrics,
  };
}

if (typeof process !== "undefined" && process.argv[1] === __filename) {
  const command = process.argv[2] || "validate";
  const projectRoot = process.argv[3] || DEFAULT_PROJECT_ROOT;
  if (command === "write") {
    process.stdout.write(`${writeStaleWikiProseMergePlan(projectRoot)}\n`);
  } else {
    const report = validateStaleWikiProseMergePlan(projectRoot);
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    if (!report.ok) {
      process.exitCode = 1;
    }
  }
}
