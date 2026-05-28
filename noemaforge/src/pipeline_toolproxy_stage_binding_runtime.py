#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/pipeline_toolproxy_stage_binding_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate ToolProxy capability-policy bindings on pipeline stages.
Inputs: Stage-binding policy, examples, pipeline runtime and unified registry.
Outputs: JSON validation summaries and unittest-callable helpers.
Side effects: None.
Tests: noemaforge/tests/test_pipeline_toolproxy_stage_binding_runtime.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pipeline_runtime as pr
import unified_registry_runtime as urr

API_VERSION = "noemaforge.pipeline-toolproxy-stage-binding/v1"
POLICY_KIND = "PipelineToolProxyStageBindingPolicy"
PACK_ID = "pipeline-toolproxy-stage-binding-core"
VERSION = "0.32.1"
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_POLICY = PACKAGE_ROOT / "configs" / "pipeline-toolproxy-stage-binding-policy.json"
DEFAULT_EXAMPLES = PROJECT_ROOT / "prelaunch" / "governance" / "pipeline_toolproxy_stage_binding.example.json"
DEFAULT_REGISTRY = PACKAGE_ROOT / "configs" / "unified-registry.json"
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
REQUIRED_CONTROLS = [
    "deny_by_default",
    "stage_scoped_tokens",
    "network_default_deny",
    "mutating_actions_require_approval",
    "exec_actions_require_sandbox",
    "review_stages_may_record_roadmap",
    "public_mwp_is_readmostly",
]
REQUIRED_BINDING_FIELDS = [
    "policy_ref",
    "capability_schema_ref",
    "pipeline_id",
    "stage",
    "scope",
    "capability_token_required",
    "approval_required",
    "sandbox_required",
    "network_allowed",
    "allowed_actions",
    "mutating_actions",
    "sandboxed_actions",
    "blocked_actions",
]
REQUIRED_RUNTIME_TOKENS = [
    "TOOLPROXY_POLICY_REF",
    "build_toolproxy_stage_binding",
    "toolproxy_stage_binding",
    "toolproxy_stage_bindings",
    "toolproxy-policy",
]


def _json_dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_policy(path: Path = DEFAULT_POLICY) -> Dict[str, Any]:
    return load_json(path)


def load_example_set(path: Path = DEFAULT_EXAMPLES) -> Dict[str, Any]:
    return load_json(path)


def _policy_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    policy = payload.get("policy")
    return policy if isinstance(policy, dict) else {}


def _as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float))]


def _registry_ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('id')}:{entry.get('version')}"


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
    if str(policy.get("required_tool_policy_ref") or "") != pr.TOOLPROXY_POLICY_REF:
        failures.append("policy_required_tool_policy_ref_invalid")
    if str(policy.get("capability_schema_ref") or "") != pr.TOOLPROXY_CAPABILITY_SCHEMA_REF:
        failures.append("policy_capability_schema_ref_invalid")
    for key in [
        "require_capability_token",
        "require_stage_scope",
        "require_run_manifest_binding",
        "require_context_packet_binding",
        "require_policy_schema_runtime_tests",
        "require_docs_and_changelog_refs",
        "require_registry_attachment",
    ]:
        if policy.get(key) is not True:
            failures.append(f"policy_{key}_not_true")
    controls = policy.get("controls") if isinstance(policy.get("controls"), dict) else {}
    for key in REQUIRED_CONTROLS:
        if controls.get(key) is not True:
            failures.append(f"control_{key}_not_true")
    fields = set(_as_string_list(policy.get("required_binding_fields")))
    for field in REQUIRED_BINDING_FIELDS:
        if field not in fields:
            failures.append(f"policy_required_binding_field_missing:{field}")
    runtime_tokens = set(_as_string_list(policy.get("required_runtime_tokens")))
    for token in REQUIRED_RUNTIME_TOKENS:
        if token not in runtime_tokens:
            failures.append(f"policy_required_runtime_token_missing:{token}")
    if not _as_string_list(policy.get("required_docs")):
        failures.append("policy_required_docs_empty")
    if not _as_string_list(policy.get("required_example_sets")):
        failures.append("policy_required_example_sets_empty")
    return failures


def _binding_failures(binding: Dict[str, Any], *, pipeline_id: str, stage: str) -> List[str]:
    failures: List[str] = []
    if binding.get("apiVersion") != "noemaforge.pipeline.toolproxy-stage-binding/v1":
        failures.append(f"binding_api_version_invalid:{pipeline_id}:{stage}")
    if binding.get("policy_ref") != pr.TOOLPROXY_POLICY_REF:
        failures.append(f"binding_policy_ref_invalid:{pipeline_id}:{stage}")
    if binding.get("capability_schema_ref") != pr.TOOLPROXY_CAPABILITY_SCHEMA_REF:
        failures.append(f"binding_capability_schema_ref_invalid:{pipeline_id}:{stage}")
    if binding.get("pipeline_id") != pipeline_id:
        failures.append(f"binding_pipeline_mismatch:{pipeline_id}:{stage}")
    if binding.get("stage") != pr.safe_id(stage):
        failures.append(f"binding_stage_mismatch:{pipeline_id}:{stage}")
    if not str(binding.get("scope") or "").startswith(f"pipeline:{pr.safe_id(pipeline_id)}:stage:{pr.safe_id(stage)}"):
        failures.append(f"binding_scope_invalid:{pipeline_id}:{stage}")
    if binding.get("capability_token_required") is not True:
        failures.append(f"binding_capability_token_not_required:{pipeline_id}:{stage}")
    if binding.get("network_allowed") is not False:
        failures.append(f"binding_network_not_default_denied:{pipeline_id}:{stage}")
    allowed = _as_string_list(binding.get("allowed_actions"))
    blocked = _as_string_list(binding.get("blocked_actions"))
    if len(allowed) != len(set(allowed)):
        failures.append(f"binding_allowed_duplicates:{pipeline_id}:{stage}")
    if len(blocked) != len(set(blocked)):
        failures.append(f"binding_blocked_duplicates:{pipeline_id}:{stage}")
    if "llm.chat" not in allowed or "fs.read" not in allowed:
        failures.append(f"binding_base_actions_missing:{pipeline_id}:{stage}")
    if "db.write" not in blocked or "voice.capture_live" not in blocked:
        failures.append(f"binding_default_blocks_missing:{pipeline_id}:{stage}")
    if "exec.run" in allowed and binding.get("sandbox_required") is not True:
        failures.append(f"binding_exec_without_sandbox:{pipeline_id}:{stage}")
    mutating = set(_as_string_list(binding.get("mutating_actions")))
    if mutating and binding.get("approval_required") is not True:
        failures.append(f"binding_mutation_without_approval:{pipeline_id}:{stage}")
    if not set(allowed).isdisjoint(set(blocked)):
        failures.append(f"binding_allow_block_overlap:{pipeline_id}:{stage}")
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
        pipeline_id = str(example.get("pipeline_id") or "")
        stage = str(example.get("stage") or "")
        permission_mode = str(example.get("permission_mode") or "plan_only")
        if not SAFE_ID_RE.match(pr.safe_id(example_id)):
            failures.append(f"example_id_invalid:{example_id}")
        binding = pr.build_toolproxy_stage_binding(pipeline_id, stage, permission_mode)
        failures.extend(_binding_failures(binding, pipeline_id=pipeline_id, stage=stage))
        allowed = set(_as_string_list(binding.get("allowed_actions")))
        blocked = set(_as_string_list(binding.get("blocked_actions")))
        for action in _as_string_list(example.get("expect_allowed")):
            if action not in allowed:
                failures.append(f"example_allowed_missing:{example_id}:{action}")
        for action in _as_string_list(example.get("expect_forbidden_allowed")):
            if action in allowed:
                failures.append(f"example_forbidden_was_allowed:{example_id}:{action}")
        for action in _as_string_list(example.get("expect_blocked")):
            if action not in blocked:
                failures.append(f"example_blocked_missing:{example_id}:{action}")
        if binding.get("approval_required") is not example.get("expect_approval_required"):
            failures.append(f"example_approval_mismatch:{example_id}")
        if binding.get("sandbox_required") is not example.get("expect_sandbox_required"):
            failures.append(f"example_sandbox_mismatch:{example_id}")
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
        "configs/pipeline-toolproxy-stage-binding-policy.json",
        "contracts/pipeline_toolproxy_stage_binding.schema.json",
        "src/pipeline_runtime.py",
        "src/pipeline_toolproxy_stage_binding_runtime.py",
        "tests/test_pipeline_toolproxy_stage_binding_runtime.py",
        "tests/test_pipeline_toolproxy_stage_binding_qa.py",
        "tests/test_pipeline_toolproxy_stage_binding_performance.py",
        "prelaunch/governance/pipeline_toolproxy_stage_binding.example.json",
    }
    if not eval_entry:
        failures.append(f"registry_eval_pack_missing:{eval_ref}")
    else:
        refs = set(_as_string_list(eval_entry.get("refs")))
        for ref in required_eval_refs:
            if ref not in refs:
                failures.append(f"registry_eval_pack_ref_missing:{eval_ref}:{ref}")

    tool_ref = str(_policy_dict(policy_payload).get("required_tool_policy_ref") or "")
    tool_policy = raw_entries.get(tool_ref) or entries.get(tool_ref)
    if not tool_policy:
        failures.append(f"registry_tool_policy_missing:{tool_ref}")
        tool_refs: List[str] = []
        tool_eval_refs: List[str] = []
    else:
        tool_refs = _as_string_list(tool_policy.get("refs"))
        tool_eval_refs = _as_string_list(tool_policy.get("eval_pack_refs"))
    if eval_ref not in tool_eval_refs:
        failures.append(f"registry_tool_policy_eval_pack_missing:{eval_ref}")
    for ref in [
        "configs/pipeline-toolproxy-stage-binding-policy.json",
        "contracts/pipeline_toolproxy_stage_binding.schema.json",
        "src/pipeline_toolproxy_stage_binding_runtime.py",
    ]:
        if ref not in tool_refs:
            failures.append(f"registry_tool_policy_ref_missing:{ref}")
    return {"failures": failures, "registry_report": report}


def validate_pipeline_toolproxy_stage_binding_policy(
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
    registry = _registry_failures(policy_payload, project_root=project_root, package_root=package_root, registry_path=registry_path)
    failures.extend(registry["failures"])

    sample_bindings = [
        pr.build_toolproxy_stage_binding("evolution", "development", "ask_before_write"),
        pr.build_toolproxy_stage_binding("evolution", "unit_testing", "ask_before_write"),
        pr.build_toolproxy_stage_binding("public_mwp", "status_check", "guided_readmostly"),
    ]
    summary = {
        "control_count": len(REQUIRED_CONTROLS),
        "runtime_token_count": len(REQUIRED_RUNTIME_TOKENS),
        "example_count": len(examples.get("examples") or []),
        "sample_binding_count": len(sample_bindings),
        "capability_token_required": all(item.get("capability_token_required") is True for item in sample_bindings),
        "network_default_deny": all(item.get("network_allowed") is False for item in sample_bindings),
        "exec_sandbox_guard": pr.build_toolproxy_stage_binding("evolution", "unit_testing", "ask_before_write").get("sandbox_required") is True,
        "public_readmostly_guard": "fs.write" not in pr.build_toolproxy_stage_binding("public_mwp", "status_check", "guided_readmostly").get("allowed_actions", []),
    }
    return {
        "apiVersion": API_VERSION,
        "kind": "PipelineToolProxyStageBindingSummary",
        "id": PACK_ID,
        "ok": not failures,
        "failures": failures,
        "summary": summary,
        "registry_metrics": registry["registry_report"].get("metrics", {}),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate pipeline ToolProxy stage-binding policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--examples", default=str(DEFAULT_EXAMPLES))
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = validate_pipeline_toolproxy_stage_binding_policy(
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
