#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/dev_team_runtime.py
Zone: release/package
Version: 0.31.13.alpha
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

Existing module notes:
NoemaForge Dev Team runtime.

Provides auditable code-improvement operations that can either produce a patch
proposal or apply direct file changes under an explicit --apply flag.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

RUNTIME_VERSION = "0.31.13.alpha"
DEFAULT_ROOT = Path(os.environ.get("NOEMAFORGE_ROOT", "/opt/noemaforge"))
DEFAULT_STATE = Path(os.environ.get("NOEMAFORGE_DEV_TEAM_STATE", "/var/lib/noemaforge/dev-team"))
DEFAULT_PIPELINE_STATE = Path(os.environ.get("NOEMAFORGE_PIPELINE_STATE", "/var/lib/noemaforge/pipelines"))
SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def safe_id(value: str, limit: int = 96) -> str:
    out = SAFE_ID_RE.sub("_", str(value or "").strip()).strip("_") or "dev_team"
    return out[:limit].strip("_") or "dev_team"


def resolve_project_file(project: Path, rel: str) -> Path:
    project = project.resolve()
    path = (project / rel).resolve()
    if path != project and project not in path.parents:
        raise SystemExit(f"refusing path outside project: {rel}")
    return path


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(obj) + "\n", encoding="utf-8")


def unified_diff(old: str, new: str, fromfile: str, tofile: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile=fromfile, tofile=tofile))


def run_dir(state: Path, op: str) -> Path:
    rid = safe_id(f"{op}_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    path = state / "runs" / rid
    path.mkdir(parents=True, exist_ok=True)
    return path


def command_json(cmd: List[str]) -> Dict[str, Any]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out: Any = proc.stdout.strip()
    if out:
        try:
            out = json.loads(out)
        except Exception:
            pass
    return {"ok": proc.returncode == 0, "returncode": proc.returncode, "cmd": cmd, "stdout": out, "stderr": proc.stderr.strip()}


def write_context_artifacts(rd: Path, *, project: str, request: str, changed_files: List[str], mode: str) -> Dict[str, str]:
    artifacts = {
        "NoemaForge-context": rd / "NoemaForge-context.md",
        "NoemaForge-architecture": rd / "NoemaForge-architecture.md",
        "NoemaForge-qa": rd / "NoemaForge-qa.md",
        "changed-files": rd / "changed-files.json",
    }
    artifacts["NoemaForge-context"].write_text(
        "# NoemaForge Context\n\n"
        f"- created_at: {nowz()}\n"
        f"- mode: {mode}\n"
        f"- project: {project or 'not provided'}\n"
        f"- request: {request}\n\n"
        "This context packet summarizes the Admin → Dev Team handoff and must be reviewed before merge.\n",
        encoding="utf-8",
    )
    artifacts["NoemaForge-architecture"].write_text(
        "# NoemaForge Architecture Notes\n\n"
        "- Keep Admin as the control-plane owner.\n"
        "- Dev Team may propose or apply code changes only through explicit artifacts and apply gates.\n"
        "- QA must remain separate from Developer responsibilities.\n",
        encoding="utf-8",
    )
    artifacts["NoemaForge-qa"].write_text(
        "# NoemaForge QA Notes\n\n"
        "- Validate changed files.\n"
        "- Run syntax/audit checks relevant to the change.\n"
        "- Confirm rollback or backup exists before applying.\n",
        encoding="utf-8",
    )
    write_json(artifacts["changed-files"], {"created_at": nowz(), "mode": mode, "project": project, "changed_files": changed_files})
    return {k: str(v) for k, v in artifacts.items()}


def cmd_run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    state = Path(args.pipeline_state).resolve() if args.pipeline_state else DEFAULT_PIPELINE_STATE
    dev_state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    request = args.request or " ".join(args.text or []) or "development task"
    cmd = [
        sys.executable,
        str(root / "src" / "pipeline_runtime.py"),
        "--root",
        str(root),
        "--state",
        str(state),
        "run",
        args.pipeline,
        "--task-id",
        safe_id(f"dev_{request[:48]}"),
        "--request",
        request,
    ]
    if args.allow_degraded:
        cmd.append("--allow-degraded")
    result = command_json(cmd)
    rd = run_dir(dev_state, "dev_team_run")
    artifacts = write_context_artifacts(rd, project="", request=request, changed_files=[], mode="dev_team_pipeline")
    budget = {"max_steps": int(getattr(args, "max_steps", 0) or 0), "time_budget_minutes": int(getattr(args, "time_budget_minutes", 0) or 0), "until_stop": bool(getattr(args, "until_stop", False))}
    budget["active"] = bool(budget["max_steps"] or budget["time_budget_minutes"] or budget["until_stop"])
    doc = {"ok": result["ok"], "version": RUNTIME_VERSION, "mode": "dev_team_pipeline", "pipeline": args.pipeline, "result": result, "run_dir": str(rd), "artifacts": artifacts, "improvement_budget": budget}
    print(json_dumps(doc) if args.json else json_dumps(doc))
    return 0 if result["ok"] else 1


def cmd_replace(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    path = resolve_project_file(project, args.path)
    if not path.exists():
        raise SystemExit(f"file not found: {path}")
    old_text = path.read_text(encoding=args.encoding, errors="replace")
    if args.old not in old_text:
        raise SystemExit("old text not found; refusing partial/ambiguous replacement")
    new_text = old_text.replace(args.old, args.new, 1 if args.once else -1)
    diff = unified_diff(old_text, new_text, str(path), str(path))
    rd = run_dir(state, "replace")
    diff_path = rd / "patch.diff"
    diff_path.write_text(diff, encoding="utf-8")
    backup_path = None
    if args.apply:
        backup_path = path.with_suffix(path.suffix + f".bak.{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
        shutil.copy2(path, backup_path)
        path.write_text(new_text, encoding=args.encoding)
    manifest = {
        "ok": True,
        "version": RUNTIME_VERSION,
        "mode": "replace",
        "applied": bool(args.apply),
        "project": str(project),
        "path": str(path),
        "diff": str(diff_path),
        "backup": str(backup_path) if backup_path else None,
        "changed": old_text != new_text,
        "created_at": nowz(),
    }
    manifest["artifacts"] = write_context_artifacts(rd, project=str(project), request=f"replace {args.path}", changed_files=[str(path)], mode="replace")
    write_json(rd / "manifest.json", manifest)
    print(json_dumps(manifest) if args.json else str(diff_path))
    return 0


def cmd_write_file(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    path = resolve_project_file(project, args.path)
    old_text = path.read_text(encoding=args.encoding, errors="replace") if path.exists() else ""
    new_text = args.content if args.content is not None else Path(args.content_file).read_text(encoding=args.encoding)
    diff = unified_diff(old_text, new_text, str(path), str(path))
    rd = run_dir(state, "write_file")
    diff_path = rd / "patch.diff"
    diff_path.write_text(diff, encoding="utf-8")
    backup_path = None
    if args.apply:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            backup_path = path.with_suffix(path.suffix + f".bak.{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
            shutil.copy2(path, backup_path)
        path.write_text(new_text, encoding=args.encoding)
    manifest = {"ok": True, "version": RUNTIME_VERSION, "mode": "write_file", "applied": bool(args.apply), "project": str(project), "path": str(path), "diff": str(diff_path), "backup": str(backup_path) if backup_path else None, "created_at": nowz()}
    manifest["artifacts"] = write_context_artifacts(rd, project=str(project), request=f"write-file {args.path}", changed_files=[str(path)], mode="write_file")
    write_json(rd / "manifest.json", manifest)
    print(json_dumps(manifest) if args.json else str(diff_path))
    return 0


def _replace_regex(path: Path, pattern: str, repl: str) -> bool:
    if not path.exists() or path.is_dir():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    new = re.sub(pattern, repl, text)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def cmd_set_version(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    version = args.version
    candidates = [project / "VERSION", project / "noemaforge" / "VERSION", project / "release.json"]
    for cfg in (project / "noemaforge" / "configs").glob("*.json") if (project / "noemaforge" / "configs").exists() else []:
        candidates.append(cfg)
    if (project / "noemaforge" / "src").exists():
        candidates.extend((project / "noemaforge" / "src").glob("*.py"))
    candidates.append(project / "noemaforge" / "bin" / "noemaforge")
    rd = run_dir(state, "set_version")
    changes: List[Dict[str, Any]] = []
    for path in sorted(set(candidates)):
        if not path.exists() or path.is_dir():
            continue
        old = path.read_text(encoding="utf-8", errors="replace")
        new = old
        if path.name == "VERSION":
            new = version + "\n"
        elif path.suffix == ".json":
            try:
                obj = json.loads(old)
                if isinstance(obj, dict) and "version" in obj:
                    obj["version"] = version
                    if path.name == "release.json":
                        obj["package"] = f"noemaforge_{version}_release_candidate_prelaunch"
                    new = json_dumps(obj) + "\n"
            except Exception:
                pass
        else:
            new = re.sub(r'RUNTIME_VERSION\s*=\s*"0\.31\.\d+(?:\.pre-alpha(?:-patched\d*)?)?"', ''.join(['RUNTIME_VERSION', ' = ']) + json.dumps(version), new)
            new = re.sub(r'VERSION\s*=\s*"0\.31\.\d+(?:\.pre-alpha(?:-patched\d*)?)?"', ''.join(['VERSION', ' = ']) + json.dumps(version), new)
            new = re.sub(r'echo "0\.31\.\d+(?:\.pre-alpha(?:-patched\d*)?)?"', 'echo ' + json.dumps(version), new)
        if new != old:
            diff = unified_diff(old, new, str(path), str(path))
            changes.append({"path": str(path), "diff": diff})
            if args.apply:
                shutil.copy2(path, path.with_suffix(path.suffix + f".bak.{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"))
                path.write_text(new, encoding="utf-8")
    patch = "\n".join(c["diff"] for c in changes)
    (rd / "version.patch").write_text(patch, encoding="utf-8")
    manifest = {"ok": True, "version": RUNTIME_VERSION, "mode": "set_version", "target_version": version, "applied": bool(args.apply), "changed_files": [c["path"] for c in changes], "patch": str(rd / "version.patch")}
    manifest["artifacts"] = write_context_artifacts(rd, project=str(project), request=f"set-version {version}", changed_files=[c["path"] for c in changes], mode="set_version")
    write_json(rd / "manifest.json", manifest)
    print(json_dumps(manifest))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noemaforge dev-team")
    parser.add_argument("--root")
    parser.add_argument("--state")
    parser.add_argument("--pipeline-state")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run")
    run.add_argument("text", nargs="*")
    run.add_argument("--state")
    run.add_argument("--pipeline-state")
    run.add_argument("--request")
    run.add_argument("--pipeline", default="dev_pipeline_member_cells")
    run.add_argument("--allow-degraded", action="store_true")
    run.add_argument("--max-steps", type=int, default=0)
    run.add_argument("--time-budget-minutes", type=int, default=0)
    run.add_argument("--until-stop", action="store_true")
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=cmd_run)

    rep = sub.add_parser("replace")
    rep.add_argument("--state")
    rep.add_argument("--project", required=True)
    rep.add_argument("--path", required=True)
    rep.add_argument("--old", required=True)
    rep.add_argument("--new", required=True)
    rep.add_argument("--once", action="store_true")
    rep.add_argument("--apply", action="store_true")
    rep.add_argument("--encoding", default="utf-8")
    rep.add_argument("--json", action="store_true")
    rep.set_defaults(func=cmd_replace)

    wr = sub.add_parser("write-file")
    wr.add_argument("--project", required=True)
    wr.add_argument("--path", required=True)
    wr.add_argument("--content")
    wr.add_argument("--content-file")
    wr.add_argument("--apply", action="store_true")
    wr.add_argument("--encoding", default="utf-8")
    wr.add_argument("--json", action="store_true")
    wr.set_defaults(func=cmd_write_file)

    sv = sub.add_parser("set-version")
    sv.add_argument("--state")
    sv.add_argument("--project", required=True)
    sv.add_argument("--version", required=True)
    sv.add_argument("--apply", action="store_true")
    sv.add_argument("--json", action="store_true")
    sv.set_defaults(func=cmd_set_version)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "cmd", "") == "write-file" and not args.content and not args.content_file:
        parser.error("write-file requires --content or --content-file")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
