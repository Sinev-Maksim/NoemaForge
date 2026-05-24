import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { buildStaleWikiExactDuplicatePlan } from "./stale_wiki_exact_duplicate_plan.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEFAULT_PROJECT_ROOT = path.resolve(__dirname, "..");
const DEFAULT_CONFIG_PATH = "noemaforge/configs/stale-wiki-canonical-copy-plan.json";

function readJson(projectRoot, relativePath) {
  return JSON.parse(fs.readFileSync(path.join(projectRoot, relativePath), "utf8"));
}

function toPosix(relativePath) {
  return relativePath.replaceAll(path.sep, "/");
}

function resolveInside(base, relativePath) {
  const resolved = path.resolve(base, relativePath);
  const relative = path.relative(base, resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`unsafe_path:${relativePath}`);
  }
  return resolved;
}

function normalizedHash(filePath) {
  const text = fs.readFileSync(filePath, "utf8").replace(/\r\n/g, "\n").trim();
  return crypto.createHash("sha256").update(text).digest("hex");
}

function currentBatchName(gate) {
  const date = new Date().toISOString().slice(0, 10).replaceAll("-", "");
  return `${gate.policy?.trash_batch_prefix || "stale-wiki-exact-duplicates"}-${date}`;
}

export function buildStaleWikiCanonicalCopyPlan(projectRoot = DEFAULT_PROJECT_ROOT) {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const exactPlan = buildStaleWikiExactDuplicatePlan(projectRoot);
  const maxGroups = Number(gate.policy?.max_groups_per_pulse || 3);
  const selectedGroups = exactPlan.exactGroups.slice(0, maxGroups);
  const trashBatch = currentBatchName(gate);
  const rows = selectedGroups.map((group) => {
    const canonicalPath = resolveInside(projectRoot, group.canonical_topic);
    const retainedPath = resolveInside(projectRoot, group.retained_source);
    const retainedHash = normalizedHash(retainedPath);
    const canonicalExists = fs.existsSync(canonicalPath);
    const canonicalHash = canonicalExists ? normalizedHash(canonicalPath) : retainedHash;
    const canonicalStatus = canonicalExists
      ? canonicalHash === retainedHash
        ? "canonical-already-matches"
        : "blocked-canonical-mismatch"
      : "copy-canonical-from-retained-source";
    const duplicateMoves = group.duplicate_sources.map((source) => {
      const trashRelative = toPosix(path.join(trashBatch, source));
      return {
        source,
        trash_target: `trash/${trashRelative}`,
        status: canonicalStatus === "blocked-canonical-mismatch" ? "blocked-canonical-mismatch" : "planned-trash-move",
      };
    });
    return {
      canonical_topic: group.canonical_topic,
      retained_source: group.retained_source,
      canonical_status: canonicalStatus,
      retained_hash: retainedHash,
      duplicate_moves: duplicateMoves,
      status: canonicalStatus === "blocked-canonical-mismatch" ? "blocked" : "ready",
    };
  });

  return {
    rows,
    metrics: {
      selected_groups: rows.length,
      planned_duplicate_moves: rows.reduce((total, row) => total + row.duplicate_moves.length, 0),
      blocked_groups: rows.filter((row) => row.status === "blocked").length,
      remaining_exact_duplicate_groups_before_apply: exactPlan.metrics.exact_duplicate_groups,
    },
    trashBatch,
  };
}

export function applyStaleWikiCanonicalCopyPlan(projectRoot = DEFAULT_PROJECT_ROOT) {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const trashRoot = resolveInside(projectRoot, "trash");
  const plan = buildStaleWikiCanonicalCopyPlan(projectRoot);
  const appliedRows = [];

  for (const row of plan.rows) {
    const canonicalPath = resolveInside(projectRoot, row.canonical_topic);
    const retainedPath = resolveInside(projectRoot, row.retained_source);
    const appliedMoves = [];
    let canonicalStatus = row.canonical_status;

    if (canonicalStatus === "copy-canonical-from-retained-source") {
      fs.mkdirSync(path.dirname(canonicalPath), { recursive: true });
      fs.copyFileSync(retainedPath, canonicalPath);
      canonicalStatus = "canonical-copied";
    }

    const canonicalReady = normalizedHash(canonicalPath) === normalizedHash(retainedPath);
    for (const move of row.duplicate_moves) {
      const sourcePath = resolveInside(projectRoot, move.source);
      const trashTarget = resolveInside(projectRoot, move.trash_target);
      const activeRelative = toPosix(path.relative(projectRoot, sourcePath));
      if (!activeRelative.startsWith("noemaforge/docs/wiki/")) {
        appliedMoves.push({ ...move, status: "skipped-source-outside-wiki" });
        continue;
      }
      if (!canonicalReady) {
        appliedMoves.push({ ...move, status: "skipped-canonical-not-ready" });
        continue;
      }
      if (!fs.existsSync(sourcePath)) {
        appliedMoves.push({ ...move, status: "skipped-source-missing" });
        continue;
      }
      if (fs.existsSync(trashTarget)) {
        appliedMoves.push({ ...move, status: "skipped-trash-target-exists" });
        continue;
      }
      fs.mkdirSync(path.dirname(trashTarget), { recursive: true });
      fs.renameSync(sourcePath, trashTarget);
      appliedMoves.push({ ...move, status: "moved-to-trash" });
    }

    appliedRows.push({
      ...row,
      canonical_status: canonicalStatus,
      duplicate_moves: appliedMoves,
      status: appliedMoves.every((move) => move.status === "moved-to-trash") ? "applied" : "partial",
    });
  }

  return {
    rows: appliedRows,
    metrics: {
      selected_groups: appliedRows.length,
      moved_duplicate_sources: appliedRows.reduce(
        (total, row) => total + row.duplicate_moves.filter((move) => move.status === "moved-to-trash").length,
        0,
      ),
      canonical_copies: appliedRows.filter((row) => row.canonical_status === "canonical-copied").length,
      blocked_or_skipped_moves: appliedRows.reduce(
        (total, row) => total + row.duplicate_moves.filter((move) => move.status !== "moved-to-trash").length,
        0,
      ),
    },
    trashBatch: plan.trashBatch,
    policy: gate.policy,
  };
}

export function renderStaleWikiCanonicalCopyPlan(result, projectRoot = DEFAULT_PROJECT_ROOT) {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const plan = result || buildStaleWikiCanonicalCopyPlan(projectRoot);
  const metrics = plan.metrics;
  const lines = [
    "# Stale Wiki Canonical Copy Plan 0.32.1",
    "",
    "This machine-generated report records the bounded exact-duplicate consolidation pulse. It copies a retained versioned wiki page into the canonical topic when needed, keeps the retained source active for review, and moves only exact duplicate sources into project trash after verifying every trash target is inside the project trash root.",
    "",
    "```json",
    JSON.stringify(
      {
        kind: "StaleWikiCanonicalCopyPlan",
        contract: gate.id,
        selected_groups: metrics.selected_groups,
        moved_duplicate_sources: metrics.moved_duplicate_sources || 0,
        canonical_copies: metrics.canonical_copies || 0,
        blocked_or_skipped_moves: metrics.blocked_or_skipped_moves || 0,
        trash_batch: plan.trashBatch,
        active_todo_must_remain_open: gate.policy?.active_todo_must_remain_open,
      },
      null,
      2,
    ),
    "```",
    "",
    "| canonical_topic | retained_source | canonical_status | duplicate_source | trash_target | status |",
    "| --- | --- | --- | --- | --- | --- |",
  ];
  for (const row of plan.rows) {
    for (const move of row.duplicate_moves) {
      lines.push(
        `| \`${row.canonical_topic}\` | \`${row.retained_source}\` | ${row.canonical_status} | \`${move.source}\` | \`${move.trash_target}\` | ${move.status} |`,
      );
    }
  }
  lines.push("");
  return lines.join("\n");
}

export function writeStaleWikiCanonicalCopyPlan(result, projectRoot = DEFAULT_PROJECT_ROOT) {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const reportPath = resolveInside(projectRoot, gate.policy?.canonical_copy_report || "noemaforge/docs/quality/STALE_WIKI_CANONICAL_COPY_PLAN_0.32.1.md");
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, renderStaleWikiCanonicalCopyPlan(result, projectRoot), "utf8");
  return reportPath;
}

export function validateStaleWikiCanonicalCopyPlan(projectRoot = DEFAULT_PROJECT_ROOT) {
  const failures = [];
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const reportRelative = gate.policy?.canonical_copy_report || "noemaforge/docs/quality/STALE_WIKI_CANONICAL_COPY_PLAN_0.32.1.md";
  const reportPath = resolveInside(projectRoot, reportRelative);

  if (gate.kind !== "StaleWikiCanonicalCopyPlan") {
    failures.push("kind_invalid");
  }
  if (gate.id !== "stale-wiki-canonical-copy-plan-core") {
    failures.push("id_invalid");
  }
  if (gate.policy?.retain_review_source_active !== true) {
    failures.push("retained_source_guard_missing");
  }
  if (gate.policy?.active_todo_must_remain_open !== true) {
    failures.push("todo_completion_guard_missing");
  }
  if (!fs.existsSync(reportPath)) {
    failures.push("canonical_copy_report_missing");
  } else {
    const report = fs.readFileSync(reportPath, "utf8");
    const movedRows = [...report.matchAll(/\| `([^`]+)` \| `([^`]+)` \| ([^|]+) \| `([^`]+)` \| `([^`]+)` \| moved-to-trash \|/g)];
    if (movedRows.length === 0) {
      failures.push("moved_rows_missing");
    }
    for (const match of movedRows) {
      const canonicalTopic = match[1];
      const retainedSource = match[2];
      const duplicateSource = match[4];
      const trashTarget = match[5];
      if (!fs.existsSync(resolveInside(projectRoot, canonicalTopic))) {
        failures.push(`canonical_missing:${canonicalTopic}`);
      }
      if (!fs.existsSync(resolveInside(projectRoot, retainedSource))) {
        failures.push(`retained_source_missing:${retainedSource}`);
      }
      if (fs.existsSync(resolveInside(projectRoot, duplicateSource))) {
        failures.push(`duplicate_source_still_active:${duplicateSource}`);
      }
      if (!trashTarget.startsWith("trash/") || !fs.existsSync(resolveInside(projectRoot, trashTarget))) {
        failures.push(`trash_target_missing:${trashTarget}`);
      }
    }
  }

  const shortTodo = fs.readFileSync(path.join(projectRoot, "noemaforge/docs/TODO.md"), "utf8");
  if (!shortTodo.includes("[docs-open] Rename or archive stale versioned wiki files")) {
    failures.push("active_todo_not_open");
  }

  return {
    ok: failures.length === 0,
    failures,
  };
}

if (typeof process !== "undefined" && process.argv[1] === __filename) {
  const command = process.argv[2] || "validate";
  const projectRoot = process.argv[3] || DEFAULT_PROJECT_ROOT;
  if (command === "apply") {
    const result = applyStaleWikiCanonicalCopyPlan(projectRoot);
    const reportPath = writeStaleWikiCanonicalCopyPlan(result, projectRoot);
    process.stdout.write(`${reportPath}\n`);
  } else if (command === "write") {
    process.stdout.write(`${writeStaleWikiCanonicalCopyPlan(undefined, projectRoot)}\n`);
  } else {
    const report = validateStaleWikiCanonicalCopyPlan(projectRoot);
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    if (!report.ok) {
      process.exitCode = 1;
    }
  }
}
