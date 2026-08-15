#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re

FORBIDDEN_TEXT_PATTERNS = {
    "prompt_in_argv": re.compile(r"\$arguments\s*\+=\s*\$prompt", re.I),
    "host_default_stdin_text": re.compile(r"\.StandardInput\.Write\s*\(", re.I),
    "start_process_argumentlist": re.compile(r"\bStart-Process\b[^\n]*-ArgumentList", re.I),
    "global_execution_policy": re.compile(r"\bSet-ExecutionPolicy\b", re.I),
    "git_push_literal": re.compile(r"\bgit\s+push\b", re.I),
    "gcloud_literal": re.compile(r"\bgcloud\s+", re.I),
    "inline_parenthesized_if": re.compile(r"\(\s*\n\s*if\s*\(", re.I),
    "duplicated_agent_mode_validateset": re.compile(
        r"\[ValidateSet\([^]]*(?:implementer|proposal|diagnostic|reviewer|transport)",
        re.I,
    ),
    "review_stdout_stderr_concat": re.compile(
        r"\$reviewer\.stdout\s*\+\s*[^\n]*\$reviewer\.stderr", re.I
    ),
}

REQUIRED_MARKERS = (
    "STAGNATION_LIMIT_PER_TASK",
    "TRAVERSAL_DEPTH_LIMIT",
    "READY_SIGNAL",
)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=pathlib.Path)
    args = parser.parse_args()
    root = args.root.resolve()

    errors: list[str] = []
    scripts: dict[pathlib.Path, str] = {}

    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".ps1", ".cmd"}:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            errors.append(f"NON_UTF8_FILE {path.relative_to(root)}")
            continue
        scripts[path] = text
        for name, pattern in FORBIDDEN_TEXT_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{name} {path.relative_to(root)}")
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.rstrip(" \t") != line:
                errors.append(f"TRAILING_WHITESPACE {path.relative_to(root)}:{lineno}")

    joined = "\n".join(scripts.values())

    for marker in REQUIRED_MARKERS:
        if marker not in joined:
            errors.append(f"MISSING_MARKER {marker}")

    if re.search(r"fresh\s+independent\s+Codex\s+review", joined, re.I):
        errors.append("FALSE_INDEPENDENCE_LABEL fresh independent Codex review")

    if "AGENT_PROMPT_TRANSPORT=stdin" in joined:
        byte_safe = (
            ".StandardInput.BaseStream" in joined
            and ".Write($promptBytes" in joined
            and "GetBytes($Prompt)" in joined
        )
        if not byte_safe:
            errors.append("STDIN_NOT_BYTE_EXPLICIT")

    controller = root / "RUN_AGENT_SELF_HEAL.ps1"
    if controller.exists():
        protocol_path = root / "AGENT_PROTOCOL.json"
        requirements_path = root / "PACKAGE_REQUIREMENTS.json"

        if not protocol_path.is_file():
            errors.append("MISSING_AGENT_PROTOCOL")
            allowed_modes: set[str] = set()
        else:
            try:
                protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"INVALID_AGENT_PROTOCOL {exc}")
                protocol = {}
            if protocol.get("apiVersion") != "noemaforge.agent-protocol/v1":
                errors.append("BAD_AGENT_PROTOCOL_API_VERSION")
            raw_modes = protocol.get("modes", [])
            if not isinstance(raw_modes, list) or not all(isinstance(x, str) for x in raw_modes):
                errors.append("BAD_AGENT_PROTOCOL_MODES")
                allowed_modes = set()
            else:
                allowed_modes = set(raw_modes)
                if len(allowed_modes) != len(raw_modes):
                    errors.append("DUPLICATE_AGENT_PROTOCOL_MODE")

        controller_text = controller.read_text(encoding="utf-8-sig")
        callsite_modes = set(re.findall(r'-Mode\s+"([^"]+)"', controller_text))
        unknown = sorted(callsite_modes - allowed_modes)
        if unknown:
            errors.append("AGENT_MODE_CALLSITE_OUTSIDE_CONTRACT " + ",".join(unknown))

        if not requirements_path.is_file():
            errors.append("MISSING_PACKAGE_REQUIREMENTS")
        else:
            try:
                requirements = json.loads(requirements_path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"INVALID_PACKAGE_REQUIREMENTS {exc}")
                requirements = {}
            if requirements.get("apiVersion") != "noemaforge.package-requirements/v1":
                errors.append("BAD_PACKAGE_REQUIREMENTS_API_VERSION")
            for item in requirements.get("requiredFiles", []):
                rel = item.get("path")
                expected = item.get("sha256")
                if not isinstance(rel, str) or not rel:
                    errors.append("BAD_REQUIRED_FILE_PATH")
                    continue
                target = root / pathlib.PurePosixPath(rel)
                if not target.is_file():
                    errors.append(f"MISSING_REQUIRED_FILE {rel}")
                    continue
                if expected:
                    actual = sha256(target)
                    if actual.lower() != str(expected).lower():
                        errors.append(
                            f"REQUIRED_FILE_SHA_MISMATCH {rel} expected={expected} actual={actual}"
                        )

        if "PACKAGE_CLOSURE_PREFLIGHT" not in controller_text:
            errors.append("MISSING_PACKAGE_CLOSURE_PREFLIGHT")
        if "AGENT_PROTOCOL_PARITY_PREFLIGHT" not in controller_text:
            errors.append("MISSING_AGENT_PROTOCOL_PARITY_PREFLIGHT")
        if controller_text.find("PACKAGE_CLOSURE_PREFLIGHT") > controller_text.find("Test-AgentProtocolTransport `"):
            errors.append("PACKAGE_PREFLIGHT_AFTER_AGENT_CALL")

        if "Parse-LocalReviewResult" not in controller_text:
            errors.append("MISSING_LOCAL_REVIEW_RESULT_PARSER")
        if "-MachineOutput $reviewer.stdout" not in controller_text:
            errors.append("LOCAL_REVIEW_NOT_DESIGNATED_CHANNEL_ONLY")
        if "review_evidence_sha_mismatch" not in controller_text:
            errors.append("MISSING_LOCAL_REVIEW_EVIDENCE_SHA_BINDING")
        if "CONTROL_PLANE_RETRY_EXHAUSTED" not in controller_text:
            errors.append("MISSING_CONTROL_PLANE_RETRY_BOUNDARY")
        if "Get-ProposalNewlineStyle" not in controller_text:
            errors.append("MISSING_PROPOSAL_EOL_NORMALIZATION")

    if errors:
        print("NOEMAFORGE_GUARDRAILS=FAIL")
        for error in errors:
            print(error)
        return 1

    print("NOEMAFORGE_GUARDRAILS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
