#!/usr/bin/env python3
from __future__ import annotations
# === NoemaForge File Header ===
# File: src/noemaforge_tasks.py
# Zone: operator/ux
# Purpose: Lightweight administrator task registry for NoemaForge orchestration planning.
# Safety: creates/updates task records only; does not execute commands.
# === End NoemaForge File Header ===

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

TASK_DIR = Path(os.environ.get("NOEMAFORGE_TASK_DIR", "/var/lib/noemaforge/tasks"))
TASKS = TASK_DIR / "tasks.jsonl"
LOGS = TASK_DIR / "logs"


def ensure_dirs() -> None:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def load_tasks() -> list[dict[str, Any]]:
    if not TASKS.exists():
        return []
    out = []
    with TASKS.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def save_tasks(tasks: list[dict[str, Any]]) -> None:
    ensure_dirs()
    tmp = TASKS.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(TASKS)


def find_task(tasks: list[dict[str, Any]], tid: str) -> dict[str, Any] | None:
    for t in tasks:
        if str(t.get("id")) == tid or str(t.get("id", "")).startswith(tid):
            return t
    return None


def cmd_create(args: argparse.Namespace) -> int:
    ensure_dirs()
    tasks = load_tasks()
    tid = "tsk-" + uuid.uuid4().hex[:10]
    t = {
        "id": tid,
        "title": args.title,
        "role": args.role,
        "pipeline_id": args.pipeline or "",
        "project_id": args.project or "",
        "status": "new",
        "priority": args.priority,
        "blocked_by": args.blocked_by or [],
        "created_at": now(),
        "updated_at": now(),
        "notes": args.note or "",
        "plan": [],
        "requires_approval": True,
    }
    tasks.append(t)
    save_tasks(tasks)
    print(json.dumps(t, ensure_ascii=False, indent=2))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    tasks = load_tasks()
    if args.json:
        print(json.dumps(tasks, ensure_ascii=False, indent=2))
    else:
        print("=== NoemaForge tasks ===")
        for t in tasks[-args.limit:]:
            print(f"{t.get('id')}\t{t.get('status')}\t{t.get('role')}\t{t.get('title')}")
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    t = find_task(load_tasks(), args.id)
    if not t:
        print("task not found", file=sys.stderr)
        return 1
    print(json.dumps(t, ensure_ascii=False, indent=2))
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    tasks = load_tasks()
    t = find_task(tasks, args.id)
    if not t:
        print("task not found", file=sys.stderr)
        return 1
    if args.status:
        t["status"] = args.status
    if args.pipeline:
        t["pipeline_id"] = args.pipeline
    if args.project:
        t["project_id"] = args.project
    if args.blocked_by:
        t["blocked_by"] = args.blocked_by
    if args.note:
        prev = str(t.get("notes") or "")
        t["notes"] = (prev + "\n" if prev else "") + args.note
    t["updated_at"] = now()
    save_tasks(tasks)
    print(json.dumps(t, ensure_ascii=False, indent=2))
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    ensure_dirs()
    path = LOGS / f"{args.id}.log"
    if args.append:
        with path.open("a", encoding="utf-8") as f:
            f.write(f"[{now()}] {args.append}\n")
    if path.exists():
        print(path.read_text(encoding="utf-8"))
    else:
        print("no log")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NoemaForge task registry")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("create")
    c.add_argument("title")
    c.add_argument("--role", default="operator.admin/administrator")
    c.add_argument("--pipeline", default="")
    c.add_argument("--project", default="")
    c.add_argument("--priority", default="normal")
    c.add_argument("--blocked-by", action="append", default=[])
    c.add_argument("--note")
    c.set_defaults(func=cmd_create)
    l = sub.add_parser("list")
    l.add_argument("--json", action="store_true")
    l.add_argument("--limit", type=int, default=40)
    l.set_defaults(func=cmd_list)
    g = sub.add_parser("get")
    g.add_argument("id")
    g.set_defaults(func=cmd_get)
    u = sub.add_parser("update")
    u.add_argument("id")
    u.add_argument("--status")
    u.add_argument("--pipeline")
    u.add_argument("--project")
    u.add_argument("--blocked-by", action="append", default=[])
    u.add_argument("--note")
    u.set_defaults(func=cmd_update)
    log = sub.add_parser("log")
    log.add_argument("id")
    log.add_argument("--append")
    log.set_defaults(func=cmd_log)
    ns = ap.parse_args(argv)
    if not hasattr(ns, "func"):
        ns = ap.parse_args(["list"])
    return ns.func(ns)

if __name__ == "__main__":
    raise SystemExit(main())
