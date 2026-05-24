import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEFAULT_PROJECT_ROOT = path.resolve(__dirname, "..");
const DEFAULT_CONFIG_PATH = "noemaforge/configs/todo-status-label-audit.json";

function readJson(projectRoot, relativePath) {
  return JSON.parse(fs.readFileSync(path.join(projectRoot, relativePath), "utf8"));
}

function readText(projectRoot, relativePath) {
  return fs.readFileSync(path.join(projectRoot, relativePath), "utf8");
}

export function evaluateTodoStatusLine(policy, line) {
  const failures = [];
  const checkedMatch = line.match(/^\s*-\s+\[(x|X| )\]\s*(?:\[([^\]]+)\])?/);
  if (!checkedMatch) {
    return { ok: true, decision: "ignore", failures };
  }

  const isChecked = checkedMatch[1].toLowerCase() === "x";
  const statusLabel = checkedMatch[2] || "";
  const allowedLabels = new Set(policy.allowed_status_labels || []);
  if (!statusLabel || !allowedLabels.has(statusLabel)) {
    failures.push(isChecked ? "checked_task_missing_done_label" : "open_task_missing_status_label");
  }
  if (isChecked && !["done-contract", "done-runtime"].includes(statusLabel)) {
    failures.push("checked_task_requires_done_status");
  }
  if (!isChecked && ["done-contract", "done-runtime"].includes(statusLabel)) {
    failures.push("open_task_has_done_status");
  }

  return {
    ok: failures.length === 0,
    decision: failures.length === 0 ? "allow" : "deny",
    failures,
  };
}

export function validateTodoStatusLabels(projectRoot = DEFAULT_PROJECT_ROOT) {
  const failures = [];
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const policy = gate.policy || {};
  const fileResults = [];

  if (gate.kind !== "TodoStatusLabelAudit") {
    failures.push("kind_invalid");
  }
  if (gate.id !== "todo-status-label-audit-core") {
    failures.push("id_invalid");
  }
  for (const label of ["done-contract", "done-runtime", "target-open", "roadmap", "blocked", "docs-open"]) {
    if (!policy.allowed_status_labels?.includes(label)) {
      failures.push(`missing_allowed_label:${label}`);
    }
  }

  for (const example of gate.example_lines || []) {
    const result = evaluateTodoStatusLine(policy, example.line);
    if (result.decision !== example.expected) {
      failures.push(`unexpected_example_decision:${example.line}`);
    }
    for (const expectedFailure of example.expected_failures || []) {
      if (!result.failures.includes(expectedFailure)) {
        failures.push(`missing_example_failure:${expectedFailure}`);
      }
    }
  }

  for (const relativePath of policy.active_todo_files || []) {
    const text = readText(projectRoot, relativePath);
    const fileFailures = [];
    const lines = text.split(/\r?\n/);
    for (const [index, line] of lines.entries()) {
      const result = evaluateTodoStatusLine(policy, line);
      if (!result.ok) {
        fileFailures.push(`${relativePath}:${index + 1}:${result.failures.join(",")}`);
      }
    }
    fileResults.push({
      path: relativePath,
      task_lines: lines.filter((line) => /^\s*-\s+\[(x|X| )\]/.test(line)).length,
      failures: fileFailures.length,
    });
    failures.push(...fileFailures);
  }

  return {
    ok: failures.length === 0,
    failures,
    metrics: {
      active_files: fileResults.length,
      task_lines: fileResults.reduce((total, result) => total + result.task_lines, 0),
      file_failures: fileResults.reduce((total, result) => total + result.failures, 0),
    },
    fileResults,
  };
}

if (typeof process !== "undefined" && process.argv[1] === __filename) {
  const report = validateTodoStatusLabels(process.argv[2] || DEFAULT_PROJECT_ROOT);
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.ok) {
    process.exitCode = 1;
  }
}
