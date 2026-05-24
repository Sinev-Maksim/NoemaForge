import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEFAULT_PROJECT_ROOT = path.resolve(__dirname, "..");

function readText(projectRoot, relativePath) {
  return fs.readFileSync(path.join(projectRoot, relativePath), "utf8");
}

function exists(projectRoot, relativePath) {
  return fs.existsSync(path.join(projectRoot, relativePath));
}

function countMatches(text, expression) {
  return [...text.matchAll(expression)].length;
}

export function validateTodoDocs(projectRoot = DEFAULT_PROJECT_ROOT) {
  const failures = [];
  const files = {
    shortTodo: "noemaforge/docs/TODO.md",
    current: "noemaforge/docs/backlog/CURRENT_0.32.1_TODO.md",
    crosswalk: "noemaforge/docs/backlog/TODO_CROSSWALK.md",
    archive: "noemaforge/docs/backlog/HISTORICAL_TODO_ARCHIVE.md",
    roadmap: "noemaforge/docs/backlog/ROADMAP_AND_TODO.md",
    audit: "noemaforge/docs/quality/TODO_STATUS_RECONCILIATION_0.32.1.md",
  };

  for (const [key, relativePath] of Object.entries(files)) {
    if (!exists(projectRoot, relativePath)) {
      failures.push(`missing:${key}:${relativePath}`);
    }
  }
  if (exists(projectRoot, "noemaforge/TODO.md")) {
    failures.push("legacy_path_active:noemaforge/TODO.md");
  }
  if (exists(projectRoot, "docs/TODO.md")) {
    failures.push("legacy_path_active:docs/TODO.md");
  }
  if (failures.length) {
    return { ok: false, failures, metrics: {} };
  }

  const shortTodo = readText(projectRoot, files.shortTodo);
  const current = readText(projectRoot, files.current);
  const crosswalk = readText(projectRoot, files.crosswalk);
  const archive = readText(projectRoot, files.archive);
  const roadmap = readText(projectRoot, files.roadmap);
  const audit = readText(projectRoot, files.audit);

  if (shortTodo.split(/\r?\n/).length > 120) {
    failures.push("short_todo_too_long");
  }
  for (const heading of [
    "P0 - Boot, Display And Storage Safety",
    "P0 - Admin Chat And Routing",
    "P0 - Stateful GUI Jobs",
    "P0 - Runtime Service Safety",
    "P1 - Documentation And TODO Hygiene",
  ]) {
    if (!current.includes(heading)) {
      failures.push(`missing_current_heading:${heading}`);
    }
  }
  for (const status of ["target-open", "blocked", "docs-open", "done-contract", "roadmap"]) {
    if (!current.includes(`[${status}]`) && !shortTodo.includes(`[${status}]`)) {
      failures.push(`missing_status:${status}`);
    }
  }
  if (!crosswalk.includes("noemaforge/TODO.md") || !crosswalk.includes("docs/TODO.md")) {
    failures.push("crosswalk_missing_legacy_paths");
  }
  if (!archive.includes("NoemaForge consolidated roadmap and TODO backlog")) {
    failures.push("archive_missing_previous_roadmap");
  }
  if (roadmap.includes("## Fragment")) {
    failures.push("roadmap_still_contains_historical_fragments");
  }

  const jsonMatch = audit.match(/```json\s*([\s\S]*?)```/);
  if (!jsonMatch) {
    failures.push("audit_json_block_missing");
  } else {
    const payload = JSON.parse(jsonMatch[1]);
    if (payload.kind !== "TodoStatusReconciliation") {
      failures.push("audit_kind_invalid");
    }
    if (payload.legacy_paths.length !== 2) {
      failures.push("audit_legacy_path_count_invalid");
    }
  }

  const forbiddenTokens = [
    ["BigBro", "-BOS"].join(""),
    ["docs", "public"].join("/"),
    ["noemaforge", "docs", "public"].join("/"),
    ["OUT", "DATED"].join(""),
  ];
  const forbidden = new RegExp(forbiddenTokens.map((token) => token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"));
  for (const [key, text] of Object.entries({ shortTodo, current, crosswalk, archive, roadmap, audit })) {
    if (forbidden.test(text)) {
      failures.push(`forbidden_text:${key}`);
    }
  }

  return {
    ok: failures.length === 0,
    failures,
    metrics: {
      short_todo_lines: shortTodo.split(/\r?\n/).length,
      current_target_open: countMatches(current, /\[target-open\]/g),
      current_done_contract: countMatches(current, /\[done-contract\]/g),
      archive_bytes: Buffer.byteLength(archive, "utf8"),
    },
  };
}

if (typeof process !== "undefined" && process.argv[1] === __filename) {
  const report = validateTodoDocs(process.argv[2] || DEFAULT_PROJECT_ROOT);
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.ok) {
    process.exitCode = 1;
  }
}
