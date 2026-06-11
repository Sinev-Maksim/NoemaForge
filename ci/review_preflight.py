#!/usr/bin/env python3
"""Pre-flight validation digest for the model review prompt.

The Codex review step runs with an enforced read-only sandbox, so it cannot
execute local commands. This script runs the standard read-only validations
on its behalf — in a separate, non-model step — and emits a compact digest
that is embedded into the review prompt as trusted CI output.

Checks (changed files only, parsed from the diff): py_compile for *.py,
json.loads for *.json, yaml.safe_load for *.yaml/yml (skipped if PyYAML is
missing), plus the SoT version line.

Usage:
    python ci/review_preflight.py <diff-file> <worktree-root> <digest-out>
"""
from __future__ import annotations

import json
import py_compile
import re
import sys
from pathlib import Path

DIFF_PATH_RE = re.compile(r"^diff --git a/(?:[^ ]+) b/([^ \n]+)", re.M)


def main() -> int:
    diff_file, root_arg, out_file = sys.argv[1:4]
    root = Path(root_arg)
    raw = Path(diff_file).read_text(encoding="utf-8", errors="replace")
    changed = sorted(set(DIFF_PATH_RE.findall(raw)))

    lines: list[str] = []
    counts = {"py": 0, "json": 0, "yaml": 0}
    failures = 0

    sys.path.insert(0, str(root / "noemaforge" / "src"))
    try:
        from noemaforge_version import RUNTIME_VERSION  # type: ignore
        lines.append(f"version SoT: RUNTIME_VERSION={RUNTIME_VERSION}")
    except Exception as exc:  # pragma: no cover - environment-dependent
        lines.append(f"version SoT: unavailable ({exc})")

    try:
        import yaml  # type: ignore
    except Exception:
        yaml = None
        lines.append("yaml parse: PyYAML unavailable on runner — skipped")

    for rel in changed:
        path = root / rel
        if not path.exists():
            continue
        try:
            if rel.endswith(".py"):
                counts["py"] += 1
                py_compile.compile(str(path), doraise=True)
            elif rel.endswith(".json"):
                counts["json"] += 1
                json.loads(path.read_text(encoding="utf-8-sig"))
            elif rel.endswith((".yaml", ".yml")) and yaml is not None:
                counts["yaml"] += 1
                yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            failures += 1
            lines.append(f"FAIL {rel}: {type(exc).__name__}: {exc}")

    lines.insert(0, (
        f"pre-flight over {len(changed)} changed files: "
        f"py_compile={counts['py']} json={counts['json']} yaml={counts['yaml']} "
        f"failures={failures}"
    ))
    Path(out_file).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))
    return 0  # informational: the model weighs failures in its verdict


if __name__ == "__main__":
    sys.exit(main())
