import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEFAULT_PROJECT_ROOT = path.resolve(__dirname, "..");
const DEFAULT_CONFIG_PATH = "noemaforge/configs/smarthome-privacy-evaluation-gate.json";

function readJson(projectRoot, relativePath) {
  return JSON.parse(fs.readFileSync(path.join(projectRoot, relativePath), "utf8"));
}

function requireBoolean(value, failure, failures) {
  if (value !== true) {
    failures.push(failure);
  }
}

export function evaluateSmartHomePrivacyCase(gate, sample) {
  const failures = [];
  const policy = gate.policy || {};
  const cameraPolicy = policy.camera_policy || {};
  const cloudPolicy = policy.cloud_policy || {};
  const automationPolicy = policy.automation_policy || {};
  const allowedSources = new Set(policy.allowed_device_sources || []);

  if (!allowedSources.has(sample.device_source)) {
    failures.push("device_source_not_allowed");
  }
  if (cloudPolicy.upload_default_allowed === false && sample.cloud_upload_default !== false) {
    failures.push("cloud_upload_default_must_be_false");
  }
  if (automationPolicy.audit_trail_required) {
    requireBoolean(sample.audit_trail, "audit_trail_required", failures);
  }
  if (automationPolicy.trace_id_required && typeof sample.trace_id !== "string") {
    failures.push("trace_id_required");
  }
  if (automationPolicy.human_override_required) {
    requireBoolean(sample.human_override, "human_override_required", failures);
  }
  if (automationPolicy.emergency_all_automation_pause_required) {
    requireBoolean(sample.emergency_all_automation_pause, "emergency_all_automation_pause_required", failures);
  }

  const camera = sample.camera || {};
  if (camera.present) {
    if (cameraPolicy.local_only_required && camera.local_only !== true) {
      failures.push("camera_local_only_required");
    }
    if (cameraPolicy.visible_privacy_state_required && camera.visible_privacy_state !== true) {
      failures.push("camera_visible_privacy_state_required");
    }
    if (cameraPolicy.hidden_capture_allowed === false && camera.hidden_capture === true) {
      failures.push("hidden_camera_capture_denied");
    }
  }

  return {
    ok: failures.length === 0,
    decision: failures.length === 0 ? "allow" : "deny",
    failures,
  };
}

export function validateSmartHomePrivacyGate(projectRoot = DEFAULT_PROJECT_ROOT) {
  const failures = [];
  const gate = readJson(projectRoot, DEFAULT_CONFIG_PATH);

  if (gate.kind !== "SmartHomePrivacyEvaluationGate") {
    failures.push("kind_invalid");
  }
  if (gate.id !== "smarthome-privacy-evaluation-gate-core") {
    failures.push("id_invalid");
  }
  if (gate.policy?.evaluation_policy?.local_only !== true) {
    failures.push("evaluation_not_local_only");
  }
  for (const source of ["trusted", "simulated", "unverified"]) {
    if (!gate.policy?.allowed_device_sources?.includes(source)) {
      failures.push(`missing_source:${source}`);
    }
  }
  if (gate.policy?.camera_policy?.local_only_required !== true) {
    failures.push("camera_local_only_policy_missing");
  }
  if (gate.policy?.cloud_policy?.upload_default_allowed !== false) {
    failures.push("cloud_upload_default_not_disabled");
  }
  if (gate.policy?.automation_policy?.audit_trail_required !== true) {
    failures.push("audit_trail_policy_missing");
  }
  if (gate.policy?.automation_policy?.emergency_all_automation_pause_required !== true) {
    failures.push("emergency_pause_policy_missing");
  }

  const caseResults = [];
  for (const sample of gate.example_cases || []) {
    const result = evaluateSmartHomePrivacyCase(gate, sample);
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
  if (caseResults.length < 3) {
    failures.push("insufficient_example_cases");
  }
  if (!caseResults.some((result) => result.decision === "deny")) {
    failures.push("missing_denied_example_case");
  }

  return {
    ok: failures.length === 0,
    failures,
    metrics: {
      example_cases: caseResults.length,
      allowed_cases: caseResults.filter((result) => result.decision === "allow").length,
      denied_cases: caseResults.filter((result) => result.decision === "deny").length,
    },
    caseResults,
  };
}

if (typeof process !== "undefined" && process.argv[1] === __filename) {
  const report = validateSmartHomePrivacyGate(process.argv[2] || DEFAULT_PROJECT_ROOT);
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.ok) {
    process.exitCode = 1;
  }
}
