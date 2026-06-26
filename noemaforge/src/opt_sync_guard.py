#!/usr/bin/env python3
"""Guarded /opt sync planning for machine-local NoemaForge backend binaries."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence


PROTECTED_BINARIES = (
    "bin/llama-server",
    "bin/noemaforge-llama-start",
    "bin/llama-server-cpu",
    "bin/llama-server-cuda",
)
REQUIRED_EXECUTABLES = (
    "bin/noemaforge",
    "bin/noemaforge-llama-start",
    "bin/llama-server",
)
REAL_BACKEND_EXECUTABLES = (
    "bin/llama-server-cpu",
    "bin/llama-server-cuda",
)


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def validate_safe_sync(source: Path, target: Path) -> Dict[str, Any]:
    source = source.resolve()
    target = target.resolve()
    errors: List[str] = []
    protected: List[str] = []
    for rel in PROTECTED_BINARIES:
        target_path = target / rel
        if target_path.exists():
            protected.append(rel)
            if not _is_executable(target_path):
                errors.append(f"protected_binary_not_executable:{target_path}")
    for rel in REQUIRED_EXECUTABLES:
        target_path = target / rel
        source_path = source / rel
        if rel in PROTECTED_BINARIES:
            candidate = target_path
        elif target_path.exists():
            candidate = target_path
        else:
            candidate = source_path
        if not _is_executable(candidate):
            errors.append(f"required_executable_missing_or_not_executable:{rel}")
    real_backend_candidates: List[str] = []
    for rel in REAL_BACKEND_EXECUTABLES:
        target_path = target / rel
        if _is_executable(target_path):
            real_backend_candidates.append(rel)
    if not real_backend_candidates:
        errors.append("real_backend_missing_or_not_executable:bin/llama-server-cpu|bin/llama-server-cuda")
    return {
        "ok": not errors,
        "source": str(source),
        "target": str(target),
        "protected_binaries": protected,
        "required_executables": list(REQUIRED_EXECUTABLES),
        "real_backend_executables": list(REAL_BACKEND_EXECUTABLES),
        "available_real_backends": real_backend_candidates,
        "errors": errors,
    }


def rsync_command(source: Path, target: Path) -> List[str]:
    return [
        "rsync",
        "-aH",
        "--delete",
        "--exclude",
        "/bin/llama-server",
        "--exclude",
        "/bin/noemaforge-llama-start",
        "--exclude",
        "/bin/llama-server-cpu",
        "--exclude",
        "/bin/llama-server-cuda",
        f"{source.resolve()}/",
        f"{target.resolve()}/",
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely sync NoemaForge into /opt without deleting machine-local backends.")
    parser.add_argument("--source", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--target", default="/opt/noemaforge")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--restart-services", action="store_true")
    args = parser.parse_args(argv)

    source = Path(args.source)
    target = Path(args.target)
    report = validate_safe_sync(source, target)
    report["rsync_command"] = rsync_command(source, target)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if not report["ok"]:
        if not args.json:
            for error in report["errors"]:
                print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if args.dry_run:
        return 0
    if shutil.which("rsync") is None:
        print("ERROR: rsync is required for safe sync", file=sys.stderr)
        return 2
    subprocess.check_call(report["rsync_command"])
    post = validate_safe_sync(source, target)
    if not post["ok"]:
        for error in post["errors"]:
            print(f"ERROR after sync: {error}", file=sys.stderr)
        return 2
    if args.restart_services:
        subprocess.check_call(["systemctl", "restart", "noemaforge-llama@main.service", "noemaforge-llm-gateway.service"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
