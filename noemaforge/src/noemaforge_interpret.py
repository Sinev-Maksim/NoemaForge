#!/usr/bin/env python3
from __future__ import annotations
# === NoemaForge File Header ===
# File: src/noemaforge_interpret.py
# Zone: operator/ux
# Purpose: Interpret admin/user commands into safe JSON plans without executing them.
# Safety: LLM interpretation only. No shell command execution.
# === End NoemaForge File Header ===

import argparse
import json
import sys
from pathlib import Path

from noemaforge_json_tools import loads_llm_json, normalize_classification, validate_required
from noemaforge_llm_client import gateway_chat, content_from_chat_response

SYSTEM = (
    "You are NoemaForge command interpreter. Return ONLY valid compact JSON, no markdown. "
    "Do not execute commands. Classify Linux/admin commands into: "
    "read_only, read_only_privileged, safe_action, needs_confirmation, dangerous. "
    "Required keys: intent, classification, commands, risks, next_step. "
    "Destructive commands, deletion, reboot/shutdown, service stop/disable, disk writes, modelstore deletion, "
    "or privilege-changing actions are dangerous or needs_confirmation. "
    "Read-only sudo status commands are read_only_privileged."
)


def interpret(text: str, model: str = "main", max_tokens: int = 512) -> dict:
    resp = gateway_chat([
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": text},
    ], model=model, max_tokens=max_tokens, temperature=0)
    content = content_from_chat_response(resp)
    try:
        obj = loads_llm_json(content)
    except Exception:
        # Retry once with stronger correction instruction.
        resp2 = gateway_chat([
            {"role": "system", "content": SYSTEM + " Your previous answer must be repaired to JSON only."},
            {"role": "user", "content": text},
            {"role": "assistant", "content": content},
            {"role": "user", "content": "Repair the answer. Return JSON only."},
        ], model=model, max_tokens=max_tokens, temperature=0)
        content = content_from_chat_response(resp2)
        obj = loads_llm_json(content)
    if not isinstance(obj, dict):
        raise ValueError("interpreter output is not an object")
    obj = normalize_classification(obj)
    missing = validate_required(obj, ["intent", "classification", "commands", "risks", "next_step"])
    if missing:
        raise ValueError(f"schema missing keys: {missing}")
    return obj


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Interpret commands/tasks safely through NoemaForge LLM gateway.")
    ap.add_argument("text", nargs="*", help="Task/command text. Reads stdin if omitted.")
    ap.add_argument("--json", action="store_true", help="JSON output; default is readable JSON too.")
    ap.add_argument("--model", default="main")
    ap.add_argument("--max-tokens", type=int, default=512)
    ns = ap.parse_args(argv)
    text = " ".join(ns.text).strip() if ns.text else sys.stdin.read().strip()
    if not text:
        print("Usage: noemaforge interpret 'команда или задача'", file=sys.stderr)
        return 2
    try:
        obj = interpret(text, model=ns.model, max_tokens=ns.max_tokens)
        print(json.dumps(obj, ensure_ascii=False, indent=None if ns.json else 2, separators=(",", ":") if ns.json else None))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": "interpret_failed", "reason": str(e)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
