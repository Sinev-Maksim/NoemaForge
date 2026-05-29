#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/pipeline_stage_validator_smoke_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate offline pipeline stage validators and smoke tests.
Inputs: Stage-validator policy, examples, pipeline runtime and unified registry.
Outputs: JSON validation summaries and unittest-callable helpers.
Side effects: Temporary files only during smoke validation.
Tests: noemaforge/tests/test_pipeline_stage_validator_smoke_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pipeline_runtime as prt
import unified_registry_runtime as urr
from noemaforge_version import RUNTIME_VERSION

API_VERSION = "noemaforge.pipeline-stage-validator-smoke/v1"
POLICY_KIND = "PipelineStageValidatorSmokePolicy"
PACK_ID = "pipeline-stage-validator-smoke-core"
VERSION = RUNTIME_VERSION
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "pipeline-stage-validator-smoke-policy.json"
DEFAULT_EXAMPLES = PROJECT_ROOT / "prelaunch" / "governance" / "pipeline_stage_validator_smoke.example.json"
DEFAULT_REGISTRY = PACKAGE_ROOT / "configs" / "unified-registry.json"
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,220}$")
REQUIRED_CONTROLS = [
    "offline_only",
    "sidecar_checksum_required",
    "contract_artifact_gate_required",
    "toolproxy_binding_smoke_required",
    "strict_mode_blocks_unready_stage",
    "smoke_uses_temp_state",
    "no_live_host_required",
    "no_llm_autostart",
]
REQUIRED_COMMANDS = ["stage-validate", "stage-smoke", "context-lint", "executor-step"]
REQUIRED_OUTPUTS = [
    "typed_sidecar_valid",
    "typed_sidecar_checksum",
    "output_non_placeholder",
    "contract_artifact_registered",
    "toolproxy_binding_present",
    "no_live_host_required",
    "no_llm_autostart",
]
REQUIRED_RUNTIME_TOKENS = [
    "validate_stage_artifacts",
    "stage_validate_cmd",
    "stage_smoke_cmd",
    "stage-validate",
    "stage-smoke",
]


def _json_dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_policy(path: Path = DEFAULT_POLICY) -> Dict[str, Any]:
    return load_json(path)


def load_example_set(path: Path = DEFAULT_EXAMPLES) -> Dict[str, Any]:
    return load_json(path)


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float))]


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("policy") if isinstance(payload.get("policy"), dict) else {}


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


def _call_pipeline(argv: List[str]) -> tuple[int, Dict[str, Any]]:
    stdout = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(stdout):
        try:
            prt.main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    raw = stdout.getvalue().strip()
    payload = json.loads(raw) if raw else {}
    return code, payload


def _policy_failures(payload: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    policy = _policy_dict(payload)
    if payload.get("apiVersion") != API_VERSION:
        failures.append("policy_api_version_invalid")
    if payload.get("kind") != POLICY_KIND:
        failures.append("policy_kind_invalid")
    if payload.get("id") != PACK_ID:
        failures.append("policy_id_invalid")
    if payload.get("version") != VERSION:
        failures.append("policy_version_invalid")
    if str(policy.get("mode") or "") != "offline_contract":
        failures.append("policy_mode_not_offline_contract")
    if str(policy.get("activation_state") or "") != "stage_validator_and_smoke_commands":
        failures.append("policy_activation_state_invalid")
    for key in [
        "require_registry_attachment",
        "require_docs_and_changelog_refs",
        "require_policy_schema_runtime_tests",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    for command in REQUIRED_COMMANDS:
        if command not in _as_string_list(policy.get("required_pipeline_commands")):
            failures.append(f"policy_required_command_missing:{command}")
    for output in REQUIRED_OUTPUTS:
        if output not in _as_string_list(policy.get("required_outputs")):
            failures.append(f"policy_required_output_missing:{output}")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"control_{key}_not_true")
    for token in REQUIRED_RUNTIME_TOKENS:
        if token not in _as_string_list(policy.get("required_runtime_tokens")):
            failures.append(f"policy_required_runtime_token_missing:{token}")
    if not str(policy.get("required_pipeline_ref") or "").startswith("pipeline:"):
        failures.append("policy_required_pipeline_ref_invalid")
    if not _as_string_list(policy.get("required_docs")):
        failures.append("policy_required_docs_empty")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _runtime_token_failures(package_root: Path) -> List[str]:
    text = (package_root / "src" / "pipeline_runtime.py").read_text(encoding="utf-8")
    return [f"runtime_token_missing:{token}" for token in REQUIRED_RUNTIME_TOKENS if token not in text]


def _docs_failures(policy_payload: Dict[str, Any], *, project_root: Path) -> List[str]:
    failures: List[str] = []
    for rel in _as_string_list(_policy_dict(policy_payload).get("required_docs")):
        path = project_root / rel
        if not path.exists():
            failures.append(f"doc_missing:{rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if PACK_ID not in text:
            failures.append(f"doc_pack_id_missing:{rel}")
    return failures


def _example_failures(example_set: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    examples = example_set.get("examples")
    if not isinstance(examples, list) or not examples:
        return ["examples_empty"]
    for example in examples:
        if not isinstance(example, dict):
            failures.append("example_not_object")
            continue
        example_id = str(example.get("id") or "<missing>")
        if not SAFE_ID_RE.match(example_id):
            failures.append(f"example_id_invalid:{example_id}")
        if str(example.get("pipeline_id") or "") not in prt.DEFAULT_PIPELINES:
            failures.append(f"example_pipeline_unknown:{example_id}")
        if not str(example.get("stage") or "").strip():
            failures.append(f"example_stage_missing:{example_id}")
    return failures


def _smoke_failures(package_root: Path) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="noemaforge_stage_validator_runtime_") as raw:
        code, smoke = _call_pipeline(["--root", str(package_root), "stage-smoke"])
    failures: List[str] = []
    if code != 0:
        failures.append(f"stage_smoke_exit_code:{code}")
    if smoke.get("ok") is not True:
        failures.append("stage_smoke_not_ok")
    cases = {str(item.get("id")): item.get("ok") for item in smoke.get("smoke_cases") or [] if isinstance(item, dict)}
    for case_id in [
        "unready_stage_is_not_advanceable",
        "ready_stage_is_advanceable",
        "typed_sidecar_smoke_valid",
        "contract_artifact_smoke_registered",
        "offline_only",
    ]:
        if cases.get(case_id) is not True:
            failures.append(f"stage_smoke_case_failed:{case_id}")
    return {"failures": failures, "smoke": smoke}


def _registry_failures(policy_payload: Dict[str, Any], *, project_root: Path, package_root: Path, registry_path: Path) -> Dict[str, Any]:
    registry = urr.load_registry(registry_path)
    report = urr.validate_unified_registry(registry, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures = [f"registry_invalid:{item}" for item in report.get("failures", [])]
    entries = {
        _registry_ref(entry): entry
        for entry in report.get("normalized_registry", {}).get("entries", [])
        if isinstance(entry, dict)
    }
    raw_entries = {
        _registry_ref(entry): entry
        for entry in registry.get("entries", [])
        if isinstance(entry, dict)
    }
    eval_ref = f"eval-pack:{PACK_ID}:{policy_payload.get('version')}"
    eval_entry = entries.get(eval_ref)
    required_eval_refs = {
        "configs/pipeline-stage-validator-smoke-policy.json",
        "contracts/pipeline_stage_validator_smoke.schema.json",
        "src/pipeline_runtime.py",
        "src/pipeline_stage_validator_smoke_runtime.py",
        "tests/test_pipeline_stage_validator_smoke_runtime.py",
        "tests/test_pipeline_stage_validator_smoke_qa.py",
        "tests/test_pipeline_stage_validator_smoke_performance.py",
        "prelaunch/governance/pipeline_stage_validator_smoke.example.json",
    }
    if not eval_entry:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    else:
        refs = set(_as_string_list(eval_entry.get("refs")))
        for ref in required_eval_refs:
            if ref not in refs:
                failures.append(f"registry_eval_pack_ref_missing:{eval_ref}:{ref}")

    pipeline_ref = str(_policy_dict(policy_payload).get("required_pipeline_ref") or "")
    pipeline = raw_entries.get(pipeline_ref) or entries.get(pipeline_ref)
    if not pipeline:
        failures.append(f"registry_pipeline_missing:{pipeline_ref}")
        pipeline_refs: List[str] = []
        pipeline_eval_refs: List[str] = []
    else:
        pipeline_refs = _as_string_list(pipeline.get("refs"))
        pipeline_eval_refs = _as_string_list(pipeline.get("eval_pack_refs"))
    if eval_ref not in pipeline_eval_refs:
        failures.append(f"registry_pipeline_eval_pack_missing:{eval_ref}")
    for ref in [
        "configs/pipeline-stage-validator-smoke-policy.json",
        "contracts/pipeline_stage_validator_smoke.schema.json",
        "src/pipeline_stage_validator_smoke_runtime.py",
        "prelaunch/governance/pipeline_stage_validator_smoke.example.json",
    ]:
        if ref not in pipeline_refs:
            failures.append(f"registry_pipeline_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report}


def validate_pipeline_stage_validator_smoke_policy(
    policy_payload: Dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    package_root: Path = PACKAGE_ROOT,
    registry_path: Path = DEFAULT_REGISTRY,
    example_path: Path = DEFAULT_EXAMPLES,
) -> Dict[str, Any]:
    failures: List[str] = []
    failures.extend(_policy_failures(policy_payload))
    failures.extend(_runtime_token_failures(package_root))
    failures.extend(_docs_failures(policy_payload, project_root=project_root))
    examples = load_example_set(example_path)
    failures.extend(_example_failures(examples))
    smoke = _smoke_failures(package_root)
    failures.extend(smoke["failures"])
    registry = _registry_failures(policy_payload, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures.extend(registry["failures"])
    summary = {
        "control_count": len(REQUIRED_CONTROLS),
        "runtime_token_count": len(REQUIRED_RUNTIME_TOKENS),
        "example_count": len(examples.get("examples") or []),
        "smoke_case_count": len(smoke["smoke"].get("smoke_cases") or []),
        "offline_only": smoke["smoke"].get("ok") is True,
        "ready_stage_guard": bool((smoke["smoke"].get("ready") or {}).get("ready_to_advance")),
        "unready_stage_guard": not bool((smoke["smoke"].get("unready") or {}).get("ready_to_advance")),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": "PipelineStageValidatorSmokeSummary",
        "id": PACK_ID,
        "ok": not failures,
        "failures": failures,
        "summary": summary,
        "registry_metrics": registry["registry_report"].get("metrics", {}),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate pipeline stage-validator smoke policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--examples", default=str(DEFAULT_EXAMPLES))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_pipeline_stage_validator_smoke_policy(
        load_policy(Path(args.policy)),
        project_root=PROJECT_ROOT,
        package_root=PACKAGE_ROOT,
        registry_path=Path(args.registry),
        example_path=Path(args.examples),
    )
    print(_json_dumps(report if args.summary else {"ok": report["ok"], "failures": report["failures"]}))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
