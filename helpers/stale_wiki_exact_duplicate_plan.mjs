import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { buildStaleWikiTopicCrosswalk } from "./stale_wiki_topic_crosswalk.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEFAULT_PROJECT_ROOT = path.resolve(__dirname, "..");
const DEFAULT_CONFIG_PATH = "noemaforge/configs/stale-wiki-exact-duplicate-plan.json";

function readJson(projectRoot, relativePath) {
  return JSON.parse(fs.readFileSync(path.join(projectRoot, relativePath), "utf8"));
}

function normalizedHash(projectRoot, relativePath) {
  const text = fs.readFileSync(path.join(projectRoot, relativePath), "utf8").replace(/\r\n/g, "\n").trim();
  return crypto.createHash("sha256").update(text).digest("hex");
}

export function buildStaleWikiExactDuplicatePlan(projectRoot = DEFAULT_PROJECT_ROOT) {
  const crosswalk = buildStaleWikiTopicCrosswalk(projectRoot);
  const byCanonical = new Map();
  for (const row of crosswalk.rows) {
    if (!byCanonical.has(row.canonical_topic)) {
      byCanonical.set(row.canonical_topic, []);
    }
    byCanonical.get(row.canonical_topic).push(row.source);
  }

  const exactGroups = [];
  for (const [canonicalTopic, sources] of byCanonical) {
    if (sources.length < 2) {
      continue;
    }
    const byHash = new Map();
    for (const source of sources) {
      const hash = normalizedHash(projectRoot, source);
      if (!byHash.has(hash)) {
        byHash.set(hash, []);
      }
      byHash.get(hash).push(source);
    }
    for (const [hash, members] of byHash) {
      if (members.length > 1) {
        const retainedSource = members.find((source) => source.includes("patched1")) || members[0];
        exactGroups.push({
          canonical_topic: canonicalTopic,
          normalized_sha256: hash,
          retained_source: retainedSource,
          duplicate_sources: members.filter((source) => source !== retainedSource),
          status: "needs-review-before-trash",
        });
      }
    }
  }

  return {
    exactGroups,
    metrics: {
      exact_duplicate_groups: exactGroups.length,
      duplicate_sources: exactGroups.reduce((total, group) => total + group.duplicate_sources.length, 0),
      retained_sources: exactGroups.length,
    },
  };
}

export function renderStaleWikiExactDuplicatePlan(projectRoot = DEFAULT_PROJECT_ROOT) {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const plan = buildStaleWikiExactDuplicatePlan(projectRoot);
  const lines = [
    "# Stale Wiki Exact Duplicate Plan 0.32.1",
    "",
    "This machine-generated plan identifies versioned wiki pages whose normalized text is exactly identical within the same proposed canonical topic. It does not move files. Each duplicate still needs review, canonical copy confirmation, and an explicit project-trash move step before the stale wiki cleanup TODO can close.",
    "",
    "```json",
    JSON.stringify(
      {
        kind: "StaleWikiExactDuplicatePlan",
        contract: "stale-wiki-exact-duplicate-plan-core",
        source_crosswalk: gate.policy?.source_crosswalk,
        exact_duplicate_groups: plan.metrics.exact_duplicate_groups,
        duplicate_sources: plan.metrics.duplicate_sources,
        auto_move_allowed: gate.policy?.auto_move_allowed,
        trash_move_requires_explicit_review: gate.policy?.trash_move_requires_explicit_review,
      },
      null,
      2,
    ),
    "```",
    "",
    "| canonical_topic | retained_source | duplicate_sources | status |",
    "| --- | --- | --- | --- |",
    ...plan.exactGroups.map((group) => `| \`${group.canonical_topic}\` | \`${group.retained_source}\` | ${group.duplicate_sources.map((source) => `\`${source}\``).join("<br>")} | ${group.status} |`),
    "",
  ];
  return lines.join("\n");
}

export function writeStaleWikiExactDuplicatePlan(projectRoot = DEFAULT_PROJECT_ROOT) {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const reportPath = path.join(projectRoot, gate.policy?.duplicate_plan_report || "noemaforge/docs/quality/STALE_WIKI_EXACT_DUPLICATE_PLAN_0.32.1.md");
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, renderStaleWikiExactDuplicatePlan(projectRoot), "utf8");
  return reportPath;
}

export function validateStaleWikiExactDuplicatePlan(projectRoot = DEFAULT_PROJECT_ROOT) {
  const failures = [];
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const plan = buildStaleWikiExactDuplicatePlan(projectRoot);
  const reportRelative = gate.policy?.duplicate_plan_report || "noemaforge/docs/quality/STALE_WIKI_EXACT_DUPLICATE_PLAN_0.32.1.md";
  const reportPath = path.join(projectRoot, reportRelative);

  if (gate.kind !== "StaleWikiExactDuplicatePlan") {
    failures.push("kind_invalid");
  }
  if (gate.id !== "stale-wiki-exact-duplicate-plan-core") {
    failures.push("id_invalid");
  }
  if (gate.policy?.auto_move_allowed !== false) {
    failures.push("auto_move_policy_unsafe");
  }
  if (gate.policy?.trash_move_requires_explicit_review !== true) {
    failures.push("trash_review_guard_missing");
  }
  if (!fs.existsSync(reportPath)) {
    failures.push("duplicate_plan_report_missing");
  } else {
    const report = fs.readFileSync(reportPath, "utf8");
    const rowCount = (report.match(/^\| `noemaforge\/docs\/wiki\//gm) || []).length;
    if (rowCount !== plan.metrics.exact_duplicate_groups) {
      failures.push(`duplicate_plan_row_count_mismatch:${rowCount}:${plan.metrics.exact_duplicate_groups}`);
    }
    if (plan.metrics.exact_duplicate_groups > 0 && !report.includes("needs-review-before-trash")) {
      failures.push("review_status_missing");
    }
    if (plan.metrics.exact_duplicate_groups === 0 && !report.includes('"exact_duplicate_groups": 0')) {
      failures.push("zero_duplicate_completion_missing");
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
    process.stdout.write(`${writeStaleWikiExactDuplicatePlan(projectRoot)}\n`);
  } else {
    const report = validateStaleWikiExactDuplicatePlan(projectRoot);
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    if (!report.ok) {
      process.exitCode = 1;
    }
  }
}
