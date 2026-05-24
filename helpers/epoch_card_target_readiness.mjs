import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEFAULT_PROJECT_ROOT = path.resolve(__dirname, "..");
const DEFAULT_CONFIG_PATH = "noemaforge/configs/epoch-card-target-readiness.json";
const SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/;

function readJson(projectRoot, relativePath) {
  return JSON.parse(fs.readFileSync(path.join(projectRoot, relativePath), "utf8"));
}

function objectHasContent(value) {
  return value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length > 0;
}

export function evaluateEpochCardInput(policy, sample) {
  const failures = [];

  if (policy.target_model_selection_required && sample.target_model_selection_evidence !== true) {
    failures.push("target_model_selection_evidence_required");
  }
  if (!objectHasContent(sample.selected_model)) {
    failures.push("selected_model_required");
  } else if (!SHA256_PATTERN.test(sample.selected_model.artifact_hash || "")) {
    failures.push("selected_model_hash_required");
  }
  if (!objectHasContent(sample.role_map)) {
    failures.push("role_map_required");
  }
  if (!objectHasContent(sample.staffing_state)) {
    failures.push("staffing_state_required");
  }
  if (!Array.isArray(sample.scorecards) || sample.scorecards.length === 0) {
    failures.push("scorecards_required");
  } else {
    for (const scorecard of sample.scorecards) {
      if (!SHA256_PATTERN.test(scorecard.hash || "")) {
        failures.push("scorecard_hash_required");
        break;
      }
    }
  }
  if (!objectHasContent(sample.rollback_plan)) {
    failures.push("rollback_plan_required");
  }
  if (!objectHasContent(sample.approval_evidence)) {
    failures.push("approval_evidence_required");
  } else if (!SHA256_PATTERN.test(sample.approval_evidence.approval_hash || "")) {
    failures.push("approval_hash_required");
  }

  return {
    ok: failures.length === 0,
    decision: failures.length === 0 ? "ready" : "blocked",
    failures,
  };
}

export function validateEpochCardTargetReadiness(projectRoot = DEFAULT_PROJECT_ROOT) {
  const failures = [];
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);
  const policy = gate.policy || {};

  if (gate.kind !== "EpochCardTargetReadiness") {
    failures.push("kind_invalid");
  }
  if (gate.id !== "epoch-card-target-readiness-core") {
    failures.push("id_invalid");
  }
  if (policy.target_model_selection_required !== true) {
    failures.push("target_model_selection_policy_missing");
  }
  if (policy.generate_card_without_target_evidence !== false) {
    failures.push("unsafe_generation_policy");
  }
  for (const field of ["selected_model", "role_map", "staffing_state", "scorecards", "rollback_plan", "approval_evidence"]) {
    if (!policy.required_fields?.includes(field)) {
      failures.push(`missing_required_field:${field}`);
    }
  }

  const caseResults = [];
  for (const sample of gate.example_cases || []) {
    const result = evaluateEpochCardInput(policy, sample);
    caseResults.push({ name: sample.name, ...result });
    if (result.decision !== sample.expected) {
      failures.push(`unexpected_case_decision:${sample.name}`);
    }
    for (const expectedFailure of sample.expected_failures || []) {
      if (!result.failures.includes(expectedFailure)) {
        failures.push(`missing_case_failure:${sample.name}:${expectedFailure}`);
      }
    }
  }
  if (caseResults.length < 2) {
    failures.push("insufficient_example_cases");
  }
  if (!caseResults.some((result) => result.decision === "blocked")) {
    failures.push("missing_blocked_example_case");
  }

  return {
    ok: failures.length === 0,
    failures,
    metrics: {
      example_cases: caseResults.length,
      ready_cases: caseResults.filter((result) => result.decision === "ready").length,
      blocked_cases: caseResults.filter((result) => result.decision === "blocked").length,
    },
    caseResults,
  };
}

if (typeof process !== "undefined" && process.argv[1] === __filename) {
  const report = validateEpochCardTargetReadiness(process.argv[2] || DEFAULT_PROJECT_ROOT);
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.ok) {
    process.exitCode = 1;
  }
}
