#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/code_qa_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-14
Modified: 2026-05-25
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

Existing module notes:
NoemaForge code-development QA sub-team runtime.

0.32.2 scope:
- sequential-by-default code review/test-gap sub-team for code-dev projects;
- reviewer model selection that avoids the producer model and maximizes diversity;
- audit ledger of what each reviewer proposed, consensus/unique findings, and handoff context;
- no live LLM call by default. It creates deterministic offline scaffolds and prompts for switchable-LLM execution.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from noemaforge_version import RUNTIME_VERSION
DEFAULT_ROOT = Path(os.environ.get("NOEMAFORGE_ROOT", "/opt/noemaforge"))
DEFAULT_STATE = Path(os.environ.get("NOEMAFORGE_QA_STATE", "/var/lib/noemaforge/code-qa"))
CONFIG_REL = Path("configs/code-qa-team.json")
SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")

CODE_EXTS = {".py", ".sh", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp", ".yaml", ".yml", ".json"}
TEST_HINTS = ("test_", "_test.", ".spec.", ".test.", "/tests/", "\\tests\\")


def nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_id(value: str) -> str:
    value = SAFE_ID_RE.sub("_", (value or "").strip()).strip("_")
    return value or "item"


def jdump(data: Any, *, pretty: bool = True) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2 if pretty else None, sort_keys=False)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def default_config() -> Dict[str, Any]:
    return {
        "apiVersion": "noemaforge/v1",
        "kind": "CodeQATeamPolicy",
        "version": RUNTIME_VERSION,
        "invariant": {"llm_mode": "switchable", "max_active_llms": 1, "default_mode": "sequential"},
        "reviewer_count_default": 2,
        "selection_policy": {
            "exclude_producer_model": True,
            "prefer_correct_and_diverse": True,
            "minimum_code_score": 0.70,
            "weights": {"code_score": 0.40, "test_score": 0.25, "diversity_from_producer": 0.20, "diversity_from_selected": 0.15},
        },
        "model_candidates": [
            {"id": "qwen25-coder-14b", "family": "qwen", "local": True, "code_score": 0.88, "test_score": 0.78, "tags": ["python", "linux", "refactor", "pragmatic"]},
            {"id": "deepseek-coder-v2-lite", "family": "deepseek", "local": False, "code_score": 0.90, "test_score": 0.84, "tags": ["algorithms", "tests", "static-analysis", "edge-cases"]},
            {"id": "codestral-22b", "family": "mistral", "local": False, "code_score": 0.86, "test_score": 0.82, "tags": ["typescript", "python", "contracts", "lint"]},
            {"id": "llama31-8b-instruct", "family": "llama", "local": True, "code_score": 0.75, "test_score": 0.71, "tags": ["explainability", "docs", "small-model", "sanity"]},
            {"id": "phi4-mini-instruct", "family": "phi", "local": True, "code_score": 0.72, "test_score": 0.76, "tags": ["compact", "unit-tests", "reasoning", "sanity"]},
            {"id": "gpt-5.5-pro-external", "family": "openai", "local": False, "code_score": 0.95, "test_score": 0.93, "tags": ["architecture", "tests", "security", "performance"]},
            {"id": "claude-sonnet-external", "family": "anthropic", "local": False, "code_score": 0.93, "test_score": 0.91, "tags": ["review", "edge-cases", "readability", "integration"]},
            {"id": "gemini-pro-external", "family": "google", "local": False, "code_score": 0.91, "test_score": 0.89, "tags": ["large-context", "cross-file", "api-contracts", "regression"]},
        ],
        "stages": ["intake", "static_scan", "reviewer_a", "reviewer_b", "consensus_merge", "test_plan", "handoff"],
    }


def load_config(root: Path) -> Dict[str, Any]:
    path = root / CONFIG_REL
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(loaded, dict):
                return loaded
        except Exception:
            pass
    return default_config()


def tag_diversity(a: List[str], b: List[str]) -> float:
    aa, bb = set(a or []), set(b or [])
    if not aa and not bb:
        return 0.5
    return 1.0 - (len(aa & bb) / max(1, len(aa | bb)))


def select_reviewers(config: Dict[str, Any], producer: str, count: int = 2, requested: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    candidates = [dict(x) for x in config.get("model_candidates") or []]
    by_id = {c.get("id"): c for c in candidates}
    if requested:
        picked = []
        for rid in requested:
            if rid == producer:
                continue
            picked.append(by_id.get(rid, {"id": rid, "family": "manual", "code_score": 0.80, "test_score": 0.80, "tags": ["manual"]}))
        return picked[:count]
    producer_tags = by_id.get(producer, {}).get("tags") or []
    weights = (config.get("selection_policy") or {}).get("weights") or {}
    min_score = float((config.get("selection_policy") or {}).get("minimum_code_score", 0.0))
    pool = [c for c in candidates if c.get("id") != producer and float(c.get("code_score", 0.0)) >= min_score]
    selected: List[Dict[str, Any]] = []
    while pool and len(selected) < count:
        scored = []
        for c in pool:
            div_prod = tag_diversity(c.get("tags") or [], producer_tags)
            div_sel = 1.0 if not selected else sum(tag_diversity(c.get("tags") or [], s.get("tags") or []) for s in selected) / len(selected)
            score = (
                float(c.get("code_score", 0.0)) * float(weights.get("code_score", 0.40))
                + float(c.get("test_score", 0.0)) * float(weights.get("test_score", 0.25))
                + div_prod * float(weights.get("diversity_from_producer", 0.20))
                + div_sel * float(weights.get("diversity_from_selected", 0.15))
            )
            scored.append((score, div_prod, div_sel, c))
        scored.sort(key=lambda x: (x[0], x[1], x[2], x[3].get("id", "")), reverse=True)
        best = scored[0][3]
        best["selection_score"] = round(scored[0][0], 4)
        best["diversity_from_producer"] = round(scored[0][1], 4)
        selected.append(best)
        pool = [c for c in pool if c.get("id") != best.get("id")]
    return selected


def connect(state: Path) -> sqlite3.Connection:
    state.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(state / "code_qa_registry.sqlite")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, project TEXT NOT NULL, producer TEXT NOT NULL, mode TEXT NOT NULL, reviewers_json TEXT NOT NULL, result_json TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, ts TEXT NOT NULL, event_type TEXT NOT NULL, payload_json TEXT NOT NULL)")
    conn.commit()
    return conn


def emit(conn: sqlite3.Connection, run_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    conn.execute("INSERT INTO events(run_id,ts,event_type,payload_json) VALUES(?,?,?,?)", (run_id, nowz(), event_type, jdump(payload, pretty=False)))
    conn.commit()


def scan_project(project: Path, limit_files: int = 180) -> Dict[str, Any]:
    files: List[Dict[str, Any]] = []
    ignored = {".git", "node_modules", "__pycache__", ".pytest_cache", "dist", "build", ".venv", "venv"}
    for path in project.rglob("*"):
        if len(files) >= limit_files:
            break
        if any(part in ignored for part in path.parts):
            continue
        if path.is_file() and path.suffix.lower() in CODE_EXTS:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                loc = len([line for line in text.splitlines() if line.strip()])
            except Exception:
                loc = 0
            rel = path.relative_to(project)
            files.append({"path": str(rel), "suffix": path.suffix.lower(), "loc": loc, "is_test": any(h in str(rel) for h in TEST_HINTS)})
    source_files = [f for f in files if not f["is_test"]]
    test_files = [f for f in files if f["is_test"]]
    by_ext: Dict[str, int] = {}
    for f in files:
        by_ext[f["suffix"]] = by_ext.get(f["suffix"], 0) + 1
    return {"project": str(project), "file_count": len(files), "source_count": len(source_files), "test_count": len(test_files), "by_ext": by_ext, "files": files, "truncated": len(files) >= limit_files}


def run_local_checks(project: Path, scan: Dict[str, Any], max_files: int = 60) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for f in scan.get("files", [])[:max_files]:
        rel = f.get("path", "")
        path = project / rel
        if f.get("suffix") == ".py":
            cmd = [sys.executable, "-m", "py_compile", str(path)]
        elif f.get("suffix") == ".sh":
            cmd = ["bash", "-n", str(path)]
        else:
            continue
        try:
            cp = subprocess.run(cmd, text=True, capture_output=True, timeout=10)
            results.append({"path": rel, "command": cmd, "exit_code": cp.returncode, "ok": cp.returncode == 0, "stderr": cp.stderr[-1000:]})
        except Exception as e:
            results.append({"path": rel, "command": cmd, "exit_code": None, "ok": False, "stderr": str(e)})
    return results


def proposal_for(reviewer: Dict[str, Any], scan: Dict[str, Any], local_checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    rid = str(reviewer.get("id"))
    tags = reviewer.get("tags") or []
    findings: List[Dict[str, Any]] = []
    failed_checks = [x for x in local_checks if not x.get("ok")]
    if failed_checks:
        findings.append({"id": "local_syntax_failures", "severity": "high", "summary": f"{len(failed_checks)} local syntax/compile checks failed", "evidence": [x.get("path") for x in failed_checks[:8]]})
    if scan.get("source_count", 0) > 0 and scan.get("test_count", 0) == 0:
        findings.append({"id": "missing_tests", "severity": "high", "summary": "Source files found but no test files detected", "evidence": [x.get("path") for x in (scan.get("files") or [])[:8] if not x.get("is_test")]})
    elif scan.get("source_count", 0) > 0:
        ratio = scan.get("test_count", 0) / max(1, scan.get("source_count", 1))
        if ratio < 0.20:
            findings.append({"id": "low_test_surface", "severity": "medium", "summary": f"Low test/source ratio: {ratio:.2f}", "evidence": []})
    if "security" in tags or "static-analysis" in tags:
        findings.append({"id": "security_static_pass_required", "severity": "medium", "summary": "Run explicit security/static checks before merge", "evidence": ["bandit/semgrep/shellcheck where available"]})
    if "performance" in tags or "regression" in tags:
        findings.append({"id": "resource_regression_budget", "severity": "medium", "summary": "Attach CPU/RSS/disk timing baseline for changed code paths", "evidence": ["noemaforge testbench compare --fail-on-regression"]})
    if "contracts" in tags or "api-contracts" in tags:
        findings.append({"id": "stage_contract_tests", "severity": "medium", "summary": "Add contract tests for CLI JSON shape and stage outputs", "evidence": ["schema validate + pytest json-shape tests"]})
    if not findings:
        findings.append({"id": "no_major_issue_offline", "severity": "low", "summary": "No high-confidence offline issue found; proceed to live reviewer prompt", "evidence": []})
    return {"reviewer": rid, "family": reviewer.get("family"), "tags": tags, "selection_score": reviewer.get("selection_score"), "created_at": nowz(), "findings": findings, "recommended_tests": recommended_tests(scan)}


def recommended_tests(scan: Dict[str, Any]) -> List[str]:
    tests = ["noemaforge schema validate", "noemaforge mvp-smoke --json", "noemaforge testbench run --suite quick --json"]
    exts = scan.get("by_ext") or {}
    if exts.get(".py"):
        tests.append("python3 -m pytest noemaforge/tests -q")
    if exts.get(".sh"):
        tests.append("find . -name '*.sh' -print0 | xargs -0 -r bash -n")
    if exts.get(".js") or exts.get(".ts") or exts.get(".tsx"):
        tests.append("npm test / npm run lint when package.json is present")
    return tests


def consensus(proposals: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_id: Dict[str, List[str]] = {}
    details: Dict[str, Dict[str, Any]] = {}
    for p in proposals:
        reviewer = p.get("reviewer")
        for f in p.get("findings") or []:
            fid = f.get("id") or "unknown"
            by_id.setdefault(fid, []).append(reviewer)
            details.setdefault(fid, f)
    consensus_items = []
    unique_items = []
    for fid, reviewers in sorted(by_id.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        item = dict(details[fid])
        item["reviewers"] = reviewers
        item["agreement_count"] = len(reviewers)
        if len(reviewers) > 1:
            consensus_items.append(item)
        else:
            unique_items.append(item)
    return {"created_at": nowz(), "reviewer_count": len(proposals), "consensus_findings": consensus_items, "unique_findings": unique_items, "all_finding_ids": sorted(by_id)}


def write_handoff(run_dir: Path, run_doc: Dict[str, Any]) -> None:
    c = run_doc["consensus"]
    md = [
        f"# Code QA handoff — {run_doc['run_id']}", "",
        f"- created_at: `{run_doc['created_at']}`",
        f"- producer_model: `{run_doc['producer_model']}`",
        f"- execution_mode: `{run_doc['mode']}`",
        f"- effective_execution: `{run_doc['effective_execution']}`",
        f"- project: `{run_doc['project']}`", "",
        "## Reviewers", "",
    ]
    for r in run_doc["reviewers"]:
        md.append(f"- `{r.get('id')}` family=`{r.get('family')}` score=`{r.get('selection_score')}` diversity_from_producer=`{r.get('diversity_from_producer')}`")
    md += ["", "## Consensus findings", ""]
    for item in c.get("consensus_findings") or []:
        md.append(f"- `{item['id']}` agreement={item['agreement_count']} reviewers={', '.join(item['reviewers'])}: {item['summary']}")
    if not c.get("consensus_findings"):
        md.append("- No multi-reviewer consensus findings in offline scaffold.")
    md += ["", "## Unique findings", ""]
    for item in c.get("unique_findings") or []:
        md.append(f"- `{item['id']}` by={', '.join(item['reviewers'])}: {item['summary']}")
    md += ["", "## Next participant instruction", "", "Use this handoff as the input context for the tester/integration-tester stage. Do not merge code until consensus findings are resolved or explicitly waived.", ""]
    atomic_write(run_dir / "next_participant_handoff_context.md", "\n".join(md))
    envelope = {"apiVersion": "noemaforge/v1", "kind": "CodeQAHandoff", "version": RUNTIME_VERSION, "run_id": run_doc["run_id"], "created_at": nowz(), "producer_model": run_doc["producer_model"], "reviewers": [r.get("id") for r in run_doc["reviewers"]], "consensus": c, "sha256_markdown": sha256_text("\n".join(md))}
    atomic_write(run_dir / "next_participant_handoff_context.json", jdump(envelope))
    atomic_write(run_dir / "next_participant_handoff_context.json.sha256", hashlib.sha256((run_dir / "next_participant_handoff_context.json").read_bytes()).hexdigest()+"\n")


def cmd_team(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    cfg = load_config(root)
    reviewers = select_reviewers(cfg, args.producer, args.count, args.reviewer)
    doc = {"ok": True, "producer_model": args.producer, "mode": args.mode, "effective_execution": "sequential_enforced_by_single_llm", "reviewers": reviewers, "policy": cfg.get("selection_policy"), "invariant": cfg.get("invariant")}
    print(jdump(doc) if args.json else "\n".join([f"producer: {args.producer}"] + [f"reviewer: {r.get('id')} score={r.get('selection_score')} diversity={r.get('diversity_from_producer')}" for r in reviewers]))


def cmd_run(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    project = Path(args.project or os.getcwd()).resolve()
    cfg = load_config(root)
    reviewers = select_reviewers(cfg, args.producer, args.count, args.reviewer)
    run_id = safe_id(args.run_id or f"codeqa_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{safe_id(args.task_id or 'task')}")
    run_dir = state / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(state)
    scan = scan_project(project)
    local_checks = run_local_checks(project, scan) if not args.skip_local_checks else []
    proposals = []
    for r in reviewers:
        prop = proposal_for(r, scan, local_checks)
        proposals.append(prop)
        atomic_write(run_dir / "proposals" / f"{safe_id(str(r.get('id')))}.json", jdump(prop))
        emit(conn, run_id, "reviewer_proposal", {"reviewer": r.get("id"), "finding_ids": [f.get("id") for f in prop.get("findings", [])]})
    cons = consensus(proposals)
    run_doc = {
        "ok": True,
        "apiVersion": "noemaforge/v1",
        "kind": "CodeQAConsensusRun",
        "version": RUNTIME_VERSION,
        "run_id": run_id,
        "created_at": nowz(),
        "updated_at": nowz(),
        "task_id": args.task_id,
        "request": args.request,
        "project": str(project),
        "producer_model": args.producer,
        "mode": args.mode,
        "effective_execution": "sequential_enforced_by_single_llm" if args.mode == "sequential" else "logical_parallel_requested_but_lease_serialized",
        "reviewers": reviewers,
        "scan": scan,
        "local_checks": local_checks,
        "proposals": proposals,
        "consensus": cons,
        "run_dir": str(run_dir),
    }
    atomic_write(run_dir / "scan.json", jdump(scan))
    atomic_write(run_dir / "local_checks.json", jdump(local_checks))
    atomic_write(run_dir / "consensus.json", jdump(cons))
    write_handoff(run_dir, run_doc)
    atomic_write(run_dir / "run.json", jdump(run_doc))
    conn.execute("INSERT OR REPLACE INTO runs(run_id,created_at,updated_at,project,producer,mode,reviewers_json,result_json) VALUES(?,?,?,?,?,?,?,?)", (run_id, run_doc["created_at"], run_doc["updated_at"], str(project), args.producer, args.mode, jdump(reviewers, pretty=False), jdump(run_doc, pretty=False)))
    conn.commit()
    emit(conn, run_id, "code_qa_run_created", {"run_dir": str(run_dir), "reviewers": [r.get("id") for r in reviewers]})
    print(jdump(run_doc) if args.json else f"ok=true run_id={run_id} run_dir={run_dir}")


def cmd_list(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = connect(state)
    rows = conn.execute("SELECT run_id,created_at,updated_at,project,producer,mode,reviewers_json FROM runs ORDER BY updated_at DESC LIMIT ?", (args.limit,)).fetchall()
    items=[]
    for row in rows:
        run_id, created_at, updated_at, project, producer, mode, reviewers_json = row
        try: reviewers=json.loads(reviewers_json)
        except Exception: reviewers=[]
        items.append({"run_id":run_id,"created_at":created_at,"updated_at":updated_at,"project":project,"producer":producer,"mode":mode,"reviewers":[r.get('id') for r in reviewers]})
    print(jdump({"ok": True, "items": items}))


def cmd_show(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = connect(state)
    row = conn.execute("SELECT result_json FROM runs WHERE run_id=?", (args.run_id,)).fetchone()
    if not row:
        raise SystemExit(f"unknown run_id: {args.run_id}")
    print(jdump(json.loads(row[0])))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="noemaforge qa")
    p.add_argument("--root")
    p.add_argument("--state")
    sub = p.add_subparsers(dest="cmd", required=True)
    code = sub.add_parser("code")
    csub = code.add_subparsers(dest="code_cmd", required=True)
    team = csub.add_parser("team")
    team.add_argument("--producer", default="qwen25-coder-14b")
    team.add_argument("--reviewer", action="append")
    team.add_argument("--count", type=int, default=2)
    team.add_argument("--mode", choices=["sequential", "parallel"], default="sequential")
    team.add_argument("--json", action="store_true")
    team.set_defaults(func=cmd_team)
    run = csub.add_parser("run")
    run.add_argument("--project", default=os.getcwd())
    run.add_argument("--producer", default="qwen25-coder-14b")
    run.add_argument("--reviewer", action="append")
    run.add_argument("--count", type=int, default=2)
    run.add_argument("--mode", choices=["sequential", "parallel"], default="sequential")
    run.add_argument("--task-id", default="code_dev")
    run.add_argument("--request", default="Code-dev QA sub-team review")
    run.add_argument("--run-id")
    run.add_argument("--skip-local-checks", action="store_true")
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=cmd_run)
    lst = csub.add_parser("list")
    lst.add_argument("--limit", type=int, default=20)
    lst.set_defaults(func=cmd_list)
    show = csub.add_parser("show")
    show.add_argument("run_id")
    show.set_defaults(func=cmd_show)
    return p


def normalize_global_argv(argv: Optional[List[str]]) -> List[str]:
    items = list(sys.argv[1:] if argv is None else argv)
    global_opts: List[str] = []
    rest: List[str] = []
    i = 0
    while i < len(items):
        item = items[i]
        if item in {"--root", "--state"} and i + 1 < len(items):
            global_opts.extend([item, items[i + 1]])
            i += 2
            continue
        rest.append(item)
        i += 1
    return global_opts + rest


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_global_argv(argv))
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


