import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  evaluateEpochCardInput,
  validateEpochCardTargetReadiness,
} from "./epoch_card_target_readiness.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("Epoch Card target readiness validates required evidence fields", () => {
  const report = validateEpochCardTargetReadiness(projectRoot);
  assert.equal(report.ok, true, report.failures.join("\n"));
  assert.equal(report.metrics.example_cases, 2);
  assert.equal(report.metrics.ready_cases, 1);
  assert.equal(report.metrics.blocked_cases, 1);
});

test("Epoch Card target readiness blocks generation without target evidence", () => {
  const result = evaluateEpochCardInput(
    { target_model_selection_required: true },
    {
      target_model_selection_evidence: false,
      selected_model: {},
      role_map: {},
      staffing_state: {},
      scorecards: [],
      rollback_plan: {},
      approval_evidence: null,
    },
  );
  assert.equal(result.decision, "blocked");
  assert.ok(result.failures.includes("target_model_selection_evidence_required"));
  assert.ok(result.failures.includes("selected_model_required"));
  assert.ok(result.failures.includes("approval_evidence_required"));
});
