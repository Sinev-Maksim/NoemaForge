import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { evaluateReadiness } from "./release_gate_environment_readiness.mjs";

const __filename = fileURLToPath(import.meta.url);
const projectRoot = path.resolve(path.dirname(__filename), "..");
const policyPath = path.join(projectRoot, "noemaforge", "configs", "release-gate-environment-readiness.json");
const policy = JSON.parse(fs.readFileSync(policyPath, "utf8"));

test("release-gate environment readiness reports all required checks", () => {
  const report = evaluateReadiness(policy, {
    runCommand: (command) => ({
      command,
      args: [],
      status: command === "python" || command === "bash" ? 0 : 1,
      signal: null,
      error: "",
      stdout: "",
      stderr: "",
    }),
  });

  assert.equal(report.kind, "ReleaseGateEnvironmentReadinessReport");
  assert.equal(report.ok, true);
  assert.deepEqual(
    report.checks.map((check) => check.id),
    ["python_ast_and_pytest_runner", "yaml_semantic_parser", "bash_syntax_runner"],
  );
  assert.equal(report.network_allowed, false);
  assert.equal(report.hardware_required, false);
});

test("missing tools remain blockers instead of being treated as success", () => {
  const report = evaluateReadiness(policy, {
    runCommand: (command, args) => ({
      command,
      args,
      status: 1,
      signal: null,
      error: "not found",
      stdout: "",
      stderr: "",
    }),
  });

  assert.equal(report.ok, false);
  assert.equal(report.blockers.length, 3);
  assert.ok(report.blockers.some((blocker) => blocker.id === "python_ast_and_pytest_runner"));
  assert.ok(report.blockers.some((blocker) => blocker.required_for.includes("yaml_parse")));
  assert.ok(report.blockers.every((blocker) => blocker.blocker.length > 20));
});

test("canonical docs record the preflight contract", () => {
  const todo = fs.readFileSync(path.join(projectRoot, "noemaforge", "docs", "TODO.md"), "utf8");
  const context = fs.readFileSync(
    path.join(projectRoot, "noemaforge", "docs", "reference", "PROJECT_CONTEXT.md"),
    "utf8",
  );

  assert.match(todo, /release-gate-environment-readiness-core/);
  assert.match(context, /Release-gate environment readiness/);
});
