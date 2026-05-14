#!/usr/bin/env python3
from __future__ import annotations
# === NoemaForge File Header ===
# File: src/noemaforge_chat.py
# Zone: operator/ux
# Purpose: Human chat shell for NoemaForge through gateway, without curl/json wrappers.
# Safety: Chat only; slash commands are local read-only status helpers except /exit, /reset.
# === End NoemaForge File Header ===

import argparse
import os
import subprocess
import sys
from typing import Any

from noemaforge_llm_client import gateway_chat, content_from_chat_response

ROLE_PROMPTS = {
    "admin": "You are NoemaForge administrator assistant. Be precise, operational, and cautious. Do not claim to execute commands.",
    "dev": "You are NoemaForge developer assistant. Help with code, debugging, tests, and patch plans. Prefer concise actionable steps.",
    "sr": "You are NoemaForge senior reviewer. Focus on risks, regressions, invariants, and acceptance criteria.",
    "surgeon": "You are NoemaForge surgeon role. Diagnose high-impact failures, propose reversible steps, and avoid destructive actions without confirmation.",
    "music": "You are NoemaForge music assistant. Help with music analysis, composition, audio workflows, and safe tooling assumptions.",
    "writer": "You are NoemaForge writing assistant. Help with story, style, structure, and consistency.",
}


def run_readonly(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=False)
    except Exception as e:
        print(f"[noemaforge-chat] command failed: {e}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Interactive NoemaForge chat over the local gateway.")
    ap.add_argument("--role", default="admin", choices=sorted(ROLE_PROMPTS))
    ap.add_argument("--model", default="main")
    ap.add_argument("--once", help="Send one message and exit.")
    ap.add_argument("--max-tokens", type=int, default=768)
    ap.add_argument("--temperature", type=float, default=0.2)
    ns = ap.parse_args(argv)

    system = ROLE_PROMPTS[ns.role] + " You are running inside NoemaForge. If asked to execute commands, provide a plan unless an explicit tool layer is used."
    history: list[dict[str, str]] = [{"role": "system", "content": system}]

    def ask(text: str) -> int:
        history.append({"role": "user", "content": text})
        try:
            resp = gateway_chat(history, model=ns.model, max_tokens=ns.max_tokens, temperature=ns.temperature)
            content = content_from_chat_response(resp).strip()
        except Exception as e:
            print(f"[noemaforge-chat][ERROR] {e}", file=sys.stderr)
            return 1
        history.append({"role": "assistant", "content": content})
        print(content)
        return 0

    if ns.once:
        return ask(ns.once)

    print(f"NoemaForge chat role={ns.role} model={ns.model}. Commands: /exit /reset /role NAME /status /smoke /manager")
    while True:
        try:
            line = input("noemaforge> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("/exit", "/quit"):
            return 0
        if line == "/reset":
            history = [{"role": "system", "content": system}]
            print("[noemaforge-chat] history reset")
            continue
        if line.startswith("/role "):
            role = line.split(None, 1)[1].strip()
            if role not in ROLE_PROMPTS:
                print("roles:", ", ".join(sorted(ROLE_PROMPTS)))
                continue
            ns.role = role
            system = ROLE_PROMPTS[role] + " You are running inside NoemaForge. If asked to execute commands, provide a plan unless an explicit tool layer is used."
            history = [{"role": "system", "content": system}]
            print(f"[noemaforge-chat] role={role}")
            continue
        if line == "/status":
            run_readonly(["noemaforge", "status"])
            continue
        if line == "/smoke":
            run_readonly(["noemaforge", "smoke", "--debug"])
            continue
        if line == "/manager":
            run_readonly(["sudo", "noemaforge", "manager", "status"])
            continue
        rc = ask(line)
        if rc:
            return rc

if __name__ == "__main__":
    raise SystemExit(main())
