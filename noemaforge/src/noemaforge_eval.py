#!/usr/bin/env python3
from __future__ import annotations
# === NoemaForge File Header ===
# File: src/noemaforge_eval.py
# Zone: operator/ux
# Purpose: Lightweight role smoke tests for NoemaForge roles through gateway.
# Safety: LLM-only evaluation; no command execution.
# === End NoemaForge File Header ===

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:
    yaml = None

from noemaforge_llm_client import gateway_chat, content_from_chat_response
from noemaforge_json_tools import loads_llm_json

DEFAULT_PACK = "/opt/noemaforge/configs/role-light-eval-029.yaml"


def load_pack(path: str) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    if yaml:
        return yaml.safe_load(text) or {}
    raise RuntimeError("python3-yaml is required")


def run_role(role: str, tests: list[dict[str, Any]], model: str) -> dict[str, Any]:
    results = []
    for t in tests:
        prompt = t["prompt"]
        system = "Return only valid JSON. You are being smoke-tested for role capability."
        started = time.time()
        ok = False
        content = ""
        obj = None
        err = ""
        try:
            resp = gateway_chat([
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ], model=model, max_tokens=512, temperature=0)
            content = content_from_chat_response(resp)
            obj = loads_llm_json(content)
            hay = json.dumps(obj, ensure_ascii=False).lower()
            ok = all(str(x).lower() in hay for x in (t.get("expect_contains") or []))
        except Exception as e:
            err = str(e)
        results.append({"name": t.get("name"), "ok": ok, "latency_ms": int((time.time() - started) * 1000), "error": err, "content": obj if obj is not None else content[:500]})
    passed = sum(1 for r in results if r["ok"])
    return {"role": role, "model": model, "passed": passed, "total": len(results), "pass_rate": passed / max(1, len(results)), "results": results}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NoemaForge light role evals")
    ap.add_argument("run", nargs="?", default="run")
    ap.add_argument("--role", action="append", help="Role to run; repeatable. Default all roles in pack.")
    ap.add_argument("--model", default="main")
    ap.add_argument("--pack", default=DEFAULT_PACK)
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args(argv)
    pack = load_pack(ns.pack)
    roles = pack.get("roles") or {}
    selected = ns.role or sorted(roles)
    out = {"updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "pack": ns.pack, "model": ns.model, "roles": {}}
    for role in selected:
        if role not in roles:
            print(f"unknown role in pack: {role}", file=sys.stderr)
            continue
        out["roles"][role] = run_role(role, roles[role], ns.model)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("=== NoemaForge role light eval ===")
        for role, res in out["roles"].items():
            print(f"{role}: {res['passed']}/{res['total']} pass_rate={res['pass_rate']:.2f}")
            for r in res["results"]:
                print(f"  - {r['name']}: {'ok' if r['ok'] else 'fail'} latency_ms={r['latency_ms']} {r['error']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
