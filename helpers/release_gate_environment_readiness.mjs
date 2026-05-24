import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEFAULT_PROJECT_ROOT = path.resolve(__dirname, "..");
const DEFAULT_POLICY = path.join(
  DEFAULT_PROJECT_ROOT,
  "noemaforge",
  "configs",
  "release-gate-environment-readiness.json",
);

function loadJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function defaultRunCommand(command, args, timeoutMs) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    shell: false,
    timeout: timeoutMs,
    windowsHide: true,
  });
  return {
    command,
    args,
    status: result.status,
    signal: result.signal,
    error: result.error ? result.error.message : "",
    stdout: result.stdout || "",
    stderr: result.stderr || "",
  };
}

function commandSucceeded(result) {
  return result && result.status === 0 && !result.error;
}

export function evaluateReadiness(policy, options = {}) {
  const runCommand = options.runCommand || defaultRunCommand;
  const timeoutMs = options.timeoutMs || 2000;
  const requiredChecks = policy?.policy?.required_checks || [];
  const checks = requiredChecks.map((check) => {
    const attempts = (check.commands || []).map((commandSpec) =>
      runCommand(commandSpec.cmd, commandSpec.args || [], timeoutMs),
    );
    const passingAttempt = attempts.find(commandSucceeded);
    const ok = Boolean(passingAttempt);
    return {
      id: check.id,
      status: ok ? "pass" : "blocked",
      required_for: check.required_for || [],
      blocker: ok ? "" : check.blocker,
      selected_command: ok ? passingAttempt.command : "",
      attempts: attempts.map((attempt) => ({
        command: attempt.command,
        args: attempt.args,
        status: attempt.status,
        signal: attempt.signal,
        error: attempt.error,
      })),
    };
  });
  const blockers = checks
    .filter((check) => check.status !== "pass")
    .map((check) => ({
      id: check.id,
      required_for: check.required_for,
      blocker: check.blocker,
    }));
  return {
    apiVersion: "noemaforge.release-gate-environment-readiness.report/v1",
    kind: "ReleaseGateEnvironmentReadinessReport",
    policy_id: policy.id || "",
    policy_version: policy.version || "",
    ok: blockers.length === 0,
    checks,
    blockers,
    network_allowed: Boolean(policy?.policy?.report_contract?.network_allowed),
    hardware_required: Boolean(policy?.policy?.report_contract?.hardware_required),
  };
}

function parseArgs(argv) {
  const args = {
    policy: DEFAULT_POLICY,
    failOnBlockers: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--policy") {
      args.policy = path.resolve(argv[index + 1]);
      index += 1;
    } else if (value === "--fail-on-blockers") {
      args.failOnBlockers = true;
    }
  }
  return args;
}

export function main(argv = typeof process !== "undefined" ? process.argv.slice(2) : []) {
  const args = parseArgs(argv);
  const policy = loadJson(args.policy);
  const report = evaluateReadiness(policy);
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (args.failOnBlockers && !report.ok) {
    process.exitCode = 1;
  }
}

if (typeof process !== "undefined" && process.argv[1] === __filename) {
  main();
}
