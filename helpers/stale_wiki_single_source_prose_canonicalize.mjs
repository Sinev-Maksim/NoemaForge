import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { buildStaleWikiProseMergePlan } from "./stale_wiki_prose_merge_plan.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEFAULT_PROJECT_ROOT = path.resolve(__dirname, "..");
const DEFAULT_CONFIG_PATH = "noemaforge/configs/stale-wiki-single-source-prose-canonicalize.json";

function readJson(projectRoot, relativePath) {
  return JSON.parse(fs.readFileSync(path.join(projectRoot, relativePath), "utf8"));
}

function normalizeRelative(relativePath) {
  return relativePath.replaceAll("\\", "/").replace(/^\/+/, "");
}

function assertInside(basePath, targetPath, label) {
  const resolvedBase = path.resolve(basePath);
  const resolvedTarget = path.resolve(targetPath);
  const relative = path.relative(resolvedBase, resolvedTarget);
  if (relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative))) {
    return resolvedTarget;
  }
  throw new Error(`${label}_outside_allowed_root:${resolvedTarget}`);
}

function sha256(text) {
  return crypto.createHash("sha256").update(text).digest("hex");
}

function wordCount(text) {
  const words = text.replace(/\s+/g, " ").trim().match(/[A-Za-z0-9А-Яа-яЁё_-]+/g);
  return words ? words.length : 0;
}

export function buildSingleSourceProseCanonicalizeBatch(projectRoot = DEFAULT_PROJECT_ROOT) {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const plan = buildStaleWikiProseMergePlan(projectRoot);
  const limit = Number(gate.policy?.batch_limit || 3);
  const rows = plan.rows
    .filter((row) => row.source_count === 1 && row.canonical_exists === false)
    .slice(0, limit)
    .map((row) => ({
      canonical_topic: normalizeRelative(row.canonical_topic),
      source: normalizeRelative(row.sources[0].source),
      words: row.sources[0].words,
      normalized_sha256: row.sources[0].normalized_sha256,
      status: "ready-for-canonical-copy",
    }));

  return {
    rows,
    metrics: {
      candidate_groups: plan.rows.filter((row) => row.source_count === 1 && row.canonical_exists === false).length,
      selected_groups: rows.length,
      batch_limit: limit,
    },
  };
}

export function applySingleSourceProseCanonicalizeBatch(projectRoot = DEFAULT_PROJECT_ROOT, today = "20260522") {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const batch = buildSingleSourceProseCanonicalizeBatch(projectRoot);
  const trashRoot = assertInside(projectRoot, path.join(projectRoot, "trash"), "trash_root");
  const trashBatchRoot = assertInside(trashRoot, path.join(trashRoot, `${gate.policy?.trash_subdir_prefix || "stale-wiki-single-source-prose"}-${today}`), "trash_batch_root");
  const applied = [];

  for (const row of batch.rows) {
    const sourcePath = assertInside(path.join(projectRoot, "noemaforge/docs/wiki"), path.join(projectRoot, row.source), "source");
    const canonicalPath = assertInside(path.join(projectRoot, "noemaforge/docs/wiki"), path.join(projectRoot, row.canonical_topic), "canonical");
    const trashPath = assertInside(trashBatchRoot, path.join(trashBatchRoot, row.source), "trash_target");

    if (!fs.existsSync(sourcePath)) {
      throw new Error(`source_missing:${row.source}`);
    }
    if (fs.existsSync(canonicalPath)) {
      throw new Error(`canonical_already_exists:${row.canonical_topic}`);
    }

    const text = fs.readFileSync(sourcePath, "utf8");
    fs.mkdirSync(path.dirname(canonicalPath), { recursive: true });
    fs.writeFileSync(canonicalPath, text, "utf8");
    const sourceHash = sha256(text);
    const canonicalHash = sha256(fs.readFileSync(canonicalPath, "utf8"));
    if (sourceHash !== canonicalHash) {
      throw new Error(`canonical_hash_mismatch:${row.canonical_topic}`);
    }

    fs.mkdirSync(path.dirname(trashPath), { recursive: true });
    fs.renameSync(sourcePath, trashPath);
    applied.push({
      canonical_topic: row.canonical_topic,
      source: row.source,
      trash_target: normalizeRelative(path.relative(projectRoot, trashPath)),
      words: wordCount(text),
      sha256: canonicalHash,
      status: "canonicalized-and-quarantined",
    });
  }

  return {
    applied,
    metrics: {
      selected_groups: batch.metrics.selected_groups,
      canonicalized_sources: applied.length,
      trash_batch_root: normalizeRelative(path.relative(projectRoot, trashBatchRoot)),
    },
  };
}

export function renderSingleSourceProseCanonicalizeReport(projectRoot = DEFAULT_PROJECT_ROOT, result = null) {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const currentBatch = buildSingleSourceProseCanonicalizeBatch(projectRoot);
  const applied = result?.applied || [];
  const metrics = {
    kind: gate.kind,
    contract: gate.id,
    source_prose_merge_plan: gate.policy?.source_prose_merge_plan,
    batch_limit: gate.policy?.batch_limit,
    selected_groups_before_apply: result?.metrics?.selected_groups ?? currentBatch.metrics.selected_groups,
    canonicalized_sources: applied.length,
    active_todo_must_remain_open: gate.policy?.active_todo_must_remain_open,
  };

  const lines = [
    "# Stale Wiki Single Source Prose Canonicalize 0.32.1",
    "",
    "This machine-generated report records a bounded cleanup batch for versioned wiki pages whose canonical topic was missing and whose prose source group contained exactly one page. Each applied row was copied byte-for-byte to the canonical topic, hash-checked, and then moved into project trash. The stale wiki cleanup TODO remains open because multi-source and canonical-existing prose review groups still require manual merge decisions.",
    "",
    "```json",
    JSON.stringify(metrics, null, 2),
    "```",
    "",
    "| canonical_topic | source | trash_target | words | sha256 | status |",
    "| --- | --- | --- | ---: | --- | --- |",
  ];
  for (const row of applied) {
    lines.push(`| \`${row.canonical_topic}\` | \`${row.source}\` | \`${row.trash_target}\` | ${row.words} | \`${row.sha256}\` | ${row.status} |`);
  }
  if (applied.length === 0) {
    lines.push("| none | none | none | 0 | none | no-op |");
  }
  lines.push("");
  return lines.join("\n");
}

export function writeSingleSourceProseCanonicalizeReport(projectRoot = DEFAULT_PROJECT_ROOT, result = null) {
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const reportPath = path.join(projectRoot, gate.policy?.canonicalize_report || "noemaforge/docs/quality/STALE_WIKI_SINGLE_SOURCE_PROSE_CANONICALIZE_0.32.1.md");
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, renderSingleSourceProseCanonicalizeReport(projectRoot, result), "utf8");
  return reportPath;
}

export function validateSingleSourceProseCanonicalize(projectRoot = DEFAULT_PROJECT_ROOT) {
  const failures = [];
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const reportRelative = gate.policy?.canonicalize_report || "noemaforge/docs/quality/STALE_WIKI_SINGLE_SOURCE_PROSE_CANONICALIZE_0.32.1.md";
  const reportPath = path.join(projectRoot, reportRelative);

  if (gate.kind !== "StaleWikiSingleSourceProseCanonicalize") {
    failures.push("kind_invalid");
  }
  if (gate.id !== "stale-wiki-single-source-prose-canonicalize-core") {
    failures.push("id_invalid");
  }
  if (gate.policy?.move_source_to_project_trash !== true) {
    failures.push("trash_move_policy_missing");
  }
  if (gate.policy?.active_todo_must_remain_open !== true) {
    failures.push("todo_completion_guard_missing");
  }
  if (!fs.existsSync(reportPath)) {
    failures.push("canonicalize_report_missing");
  } else {
    const report = fs.readFileSync(reportPath, "utf8");
    if (!report.includes("canonicalized-and-quarantined")) {
      failures.push("canonicalized_row_missing");
    }
    const rowPattern = /^\| `([^`]+)` \| `([^`]+)` \| `([^`]+)` \| [0-9]+ \| `([a-f0-9]{64})` \| canonicalized-and-quarantined \|$/gm;
    let match;
    let rows = 0;
    while ((match = rowPattern.exec(report)) !== null) {
      rows += 1;
      const canonicalTopic = match[1];
      const source = match[2];
      const trashTarget = match[3];
      const canonicalPath = path.join(projectRoot, canonicalTopic);
      const sourcePath = path.join(projectRoot, source);
      const trashPath = path.join(projectRoot, trashTarget);
      if (!fs.existsSync(canonicalPath)) failures.push(`canonical_missing:${canonicalTopic}`);
      if (fs.existsSync(sourcePath)) failures.push(`source_still_active:${source}`);
      if (!fs.existsSync(trashPath)) failures.push(`trash_target_missing:${trashTarget}`);
      if (fs.existsSync(canonicalPath)) {
        const canonicalHash = sha256(fs.readFileSync(canonicalPath, "utf8"));
        if (canonicalHash !== match[4]) failures.push(`canonical_hash_mismatch:${canonicalTopic}`);
      }
    }
    if (rows === 0) {
      failures.push("canonicalized_rows_unparseable");
    }
  }

  const shortTodo = fs.readFileSync(path.join(projectRoot, "noemaforge/docs/TODO.md"), "utf8");
  if (!shortTodo.includes("[docs-open] Rename or archive stale versioned wiki files")) {
    failures.push("active_todo_not_open");
  }

  return {
    ok: failures.length === 0,
    failures,
    metrics: buildSingleSourceProseCanonicalizeBatch(projectRoot).metrics,
  };
}

if (typeof process !== "undefined" && process.argv[1] === __filename) {
  const command = process.argv[2] || "validate";
  const projectRoot = process.argv[3] || DEFAULT_PROJECT_ROOT;
  if (command === "apply") {
    const result = applySingleSourceProseCanonicalizeBatch(projectRoot);
    const reportPath = writeSingleSourceProseCanonicalizeReport(projectRoot, result);
    process.stdout.write(`${JSON.stringify({ reportPath, ...result }, null, 2)}\n`);
  } else if (command === "write") {
    process.stdout.write(`${writeSingleSourceProseCanonicalizeReport(projectRoot)}\n`);
  } else {
    const report = validateSingleSourceProseCanonicalize(projectRoot);
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    if (!report.ok) {
      process.exitCode = 1;
    }
  }
}
