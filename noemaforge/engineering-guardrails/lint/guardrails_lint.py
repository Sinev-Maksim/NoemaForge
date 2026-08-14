#!/usr/bin/env python3
from __future__ import annotations
import argparse
import pathlib
import re
import sys

FORBIDDEN_TEXT_PATTERNS = {
    "prompt_in_argv": re.compile(r"\$arguments\s*\+=\s*\$prompt", re.I),
    "host_default_stdin_text": re.compile(r"\.StandardInput\.Write\s*\(", re.I),
    "start_process_argumentlist": re.compile(r"\bStart-Process\b[^\n]*-ArgumentList", re.I),
    "global_execution_policy": re.compile(r"\bSet-ExecutionPolicy\b", re.I),
    "git_push_literal": re.compile(r"\bgit\s+push\b", re.I),
    "gcloud_literal": re.compile(r"\bgcloud\s+", re.I),
    "inline_parenthesized_if": re.compile(r"\(\s*\n\s*if\s*\(", re.I),
}

REQUIRED_MARKERS = (
    "STAGNATION_LIMIT_PER_TASK",
    "TRAVERSAL_DEPTH_LIMIT",
    "READY_SIGNAL",
)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=pathlib.Path)
    args = parser.parse_args()
    root = args.root.resolve()

    errors: list[str] = []
    all_text = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".ps1", ".cmd"}:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            errors.append(f"NON_UTF8_FILE {path.relative_to(root)}")
            continue
        all_text.append(text)
        for name, pattern in FORBIDDEN_TEXT_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{name} {path.relative_to(root)}")
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.rstrip(" \t") != line:
                errors.append(f"TRAILING_WHITESPACE {path.relative_to(root)}:{lineno}")

    joined = "\n".join(all_text)
    for marker in REQUIRED_MARKERS:
        if marker not in joined:
            errors.append(f"MISSING_MARKER {marker}")

    # Same-provider local Codex review must not be described as independent.
    if re.search(r"fresh\s+independent\s+Codex\s+review", joined, re.I):
        errors.append("FALSE_INDEPENDENCE_LABEL fresh independent Codex review")

    # Byte-safe stdin must be represented by BaseStream.Write or an explicit file pipe.
    if "AGENT_PROMPT_TRANSPORT=stdin" in joined:
        byte_safe = (
            ".StandardInput.BaseStream" in joined
            and ".Write($promptBytes" in joined
            and "GetBytes($Prompt)" in joined
        )
        if not byte_safe:
            errors.append("STDIN_NOT_BYTE_EXPLICIT")

    if errors:
        print("NOEMAFORGE_GUARDRAILS=FAIL")
        for error in errors:
            print(error)
        return 1

    print("NOEMAFORGE_GUARDRAILS=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
