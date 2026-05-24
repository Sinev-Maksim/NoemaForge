import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  evaluateSmartHomePrivacyCase,
  validateSmartHomePrivacyGate,
} from "./smarthome_privacy_evaluation_gate.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");

test("SmartHome privacy evaluation gate validates required local-first controls", () => {
  const report = validateSmartHomePrivacyGate(projectRoot);
  assert.equal(report.ok, true, report.failures.join("\n"));
  assert.equal(report.metrics.example_cases, 3);
  assert.equal(report.metrics.allowed_cases, 2);
  assert.equal(report.metrics.denied_cases, 1);
});

test("SmartHome privacy evaluator rejects cloud camera defaults and missing pause", () => {
  const gate = {
    policy: {
      allowed_device_sources: ["trusted", "simulated", "unverified"],
      camera_policy: {
        local_only_required: true,
        visible_privacy_state_required: true,
        hidden_capture_allowed: false,
      },
      cloud_policy: {
        upload_default_allowed: false,
      },
      automation_policy: {
        audit_trail_required: true,
        trace_id_required: true,
        human_override_required: true,
        emergency_all_automation_pause_required: true,
      },
    },
  };
  const result = evaluateSmartHomePrivacyCase(gate, {
    device_source: "trusted",
    camera: {
      present: true,
      local_only: false,
      visible_privacy_state: false,
      hidden_capture: true,
    },
    cloud_upload_default: true,
    audit_trail: true,
    trace_id: "trace-smarthome-privacy-negative",
    human_override: true,
    emergency_all_automation_pause: false,
  });
  assert.equal(result.decision, "deny");
  assert.ok(result.failures.includes("camera_local_only_required"));
  assert.ok(result.failures.includes("cloud_upload_default_must_be_false"));
  assert.ok(result.failures.includes("emergency_all_automation_pause_required"));
});
