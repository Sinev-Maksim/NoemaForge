#!/usr/bin/env python3
from __future__ import annotations
# === NoemaForge File Header ===
# File: src/noemaforge_json_tools.py
# Zone: operator/ux
# Purpose: Normalize LLM text into validated JSON objects for chat/interpret/eval flows.
# Safety: parsing only; never executes commands.
# === End NoemaForge File Header ===

import argparse
import json
import re
import sys
from typing import Any, Iterable

FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.I | re.S)


def strip_markdown_fences(text: str) -> str:
    text = (text or "").strip()
    m = FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text


def extract_json_text(text: str) -> str:
    """Return first JSON object/array from a string, tolerant of markdown fences."""
    text = strip_markdown_fences(text)
    starts = [(text.find("{"), "{"), (text.find("["), "[")]
    starts = [(idx, ch) for idx, ch in starts if idx >= 0]
    if not starts:
        raise ValueError("no JSON object/array start found")
    start, opening = min(starts, key=lambda x: x[0])
    closing = "}" if opening == "{" else "]"

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    # Fallback for simple model output where last closing brace is still useful.
    end = text.rfind(closing)
    if end > start:
        return text[start:end + 1]
    raise ValueError("unterminated JSON object/array")


def loads_llm_json(text: str) -> Any:
    return json.loads(extract_json_text(text))


def validate_required(obj: Any, required: Iterable[str]) -> list[str]:
    if not isinstance(obj, dict):
        return ["root_not_object"]
    missing = []
    for key in required:
        if key not in obj:
            missing.append(key)
    return missing


def normalize_classification(obj: dict[str, Any]) -> dict[str, Any]:
    """Small deterministic corrections for command interpretation output."""
    commands = obj.get("commands") or []
    if isinstance(commands, str):
        commands = [commands]
    text = "\n".join(str(x) for x in commands).lower()
    classification = str(obj.get("classification") or "").strip() or "unknown"

    destructive = [
        "rm -rf", "mkfs", "dd if=", "> /dev/", "shutdown", "reboot", "poweroff",
        "systemctl stop", "systemctl disable", "wipefs", "parted", "fdisk", "cryptsetup",
    ]
    read_only = [
        "status", "smoke", "journalctl", "systemctl --failed", "systemctl status",
        "systemctl show", "systemctl list-", "findmnt", "ls ", "cat ", "jq ", "free", "nvidia-smi", "uptime",
    ]
    privileged_ro = ["sudo noemaforge manager status", "sudo noemaforge runtime-safety check", "sudo cat", "sudo journalctl"]

    if any(x in text for x in destructive):
        classification = "dangerous"
        obj.setdefault("next_step", "refuse_or_require_explicit_recovery_context")
    elif any(x in text for x in privileged_ro):
        classification = "read_only_privileged"
    elif any(x in text for x in read_only):
        classification = "read_only"

    obj["classification"] = classification
    if "risks" not in obj:
        obj["risks"] = []
    if "commands" not in obj:
        obj["commands"] = commands
    if "next_step" not in obj:
        obj["next_step"] = "inspect_output"
    return obj


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Extract and validate JSON from LLM text.")
    ap.add_argument("--require", action="append", default=[], help="Required top-level key. Repeatable.")
    ap.add_argument("--normalize-command", action="store_true", help="Apply NoemaForge command classification normalization.")
    ap.add_argument("--compact", action="store_true")
    ap.add_argument("file", nargs="?", help="Input file; stdin if omitted.")
    ns = ap.parse_args(argv)
    text = open(ns.file, encoding="utf-8").read() if ns.file else sys.stdin.read()
    try:
        obj = loads_llm_json(text)
        if ns.normalize_command and isinstance(obj, dict):
            obj = normalize_classification(obj)
        missing = validate_required(obj, ns.require)
        if missing:
            print(json.dumps({"ok": False, "error": "schema_missing_keys", "missing": missing, "object": obj}, ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
        print(json.dumps(obj, ensure_ascii=False, separators=(",", ":") if ns.compact else None, indent=None if ns.compact else 2))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": "json_extract_failed", "reason": str(e), "raw_preview": text[:800]}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
