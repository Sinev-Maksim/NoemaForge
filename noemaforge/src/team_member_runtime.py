#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/team_member_runtime.py
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
NoemaForge pipeline team-member runtime.

0.32.2 scope:
- every pipeline member can be standalone or a sequentially executed multi-model cell;
- each cell writes proposal logs, consensus artifacts, unique artifacts and a typed handoff;
- code-dev cells include consistency gates: developer auto-tests, QA loop detection,
  analyzer/visualizer architecture diagrams and bottleneck notes;
- no live LLM calls by default. The runtime emits deterministic scaffolds/prompts that
  are compatible with the switchable single-LLM lease model.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from noemaforge_version import RUNTIME_VERSION
from platform_paths import DEFAULT_PATHS as _pp
DEFAULT_ROOT = _pp.root
DEFAULT_STATE = Path(os.environ.get("NOEMAFORGE_MEMBER_STATE", "/var/lib/noemaforge/pipeline-members"))
DEFAULT_PIPELINE_STATE = _pp.pipelines_dir
SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")
CODE_EXTS = {".py", ".sh", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp", ".yaml", ".yml", ".json"}
IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", "dist", "build", ".venv", "venv", ".mypy_cache"}


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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return default


def default_policy() -> Dict[str, Any]:
    return {
        "apiVersion": "noemaforge/v1",
        "kind": "TeamMemberRuntimePolicy",
        "version": RUNTIME_VERSION,
        "invariant": {"llm_mode": "switchable", "max_active_llms": 1, "default_execution": "sequential"},
        "member_cells": {
            "architect": {"mode": "ensemble", "min_models": 2, "artifact_contract": ["architecture_clarification", "risks", "handoff"]},
            "developer": {"mode": "standalone_or_ensemble", "min_models": 1, "artifact_contract": ["implementation_plan", "auto_tests_report", "handoff"], "requires_auto_tests": True},
            "code_analyser_visualiser": {"mode": "ensemble", "min_models": 2, "artifact_contract": ["architecture_diagrams", "bottleneck_report", "call_graph", "handoff"], "requires_diagrams": True},
            "qa": {"mode": "ensemble", "min_models": 2, "artifact_contract": ["qa_report", "recommended_tests", "approval_or_denial", "handoff"], "detect_dev_misunderstanding_loop": True},
            "tester": {"mode": "ensemble", "min_models": 2, "artifact_contract": ["test_plan", "test_results", "handoff"]},
            "integration_tester": {"mode": "ensemble", "min_models": 2, "artifact_contract": ["integration_report", "risk_register", "handoff"]},
            "optimizer": {"mode": "ensemble", "min_models": 2, "artifact_contract": ["performance_note", "memory_note", "operation_count_note", "handoff"]},
            "reviewer": {"mode": "ensemble", "min_models": 2, "artifact_contract": ["review_report", "merge_recommendation", "handoff"]}
        },
        "model_candidates": [
            {"id": "qwen25-coder-14b", "family": "qwen", "local": True, "code_score": 0.88, "test_score": 0.78, "analysis_score": 0.76, "tags": ["python", "linux", "refactor", "pragmatic"]},
            {"id": "deepseek-coder-v2-lite", "family": "deepseek", "local": False, "code_score": 0.90, "test_score": 0.84, "analysis_score": 0.86, "tags": ["algorithms", "tests", "static-analysis", "edge-cases"]},
            {"id": "codestral-22b", "family": "mistral", "local": False, "code_score": 0.86, "test_score": 0.82, "analysis_score": 0.80, "tags": ["typescript", "python", "contracts", "lint"]},
            {"id": "llama31-8b-instruct", "family": "llama", "local": True, "code_score": 0.75, "test_score": 0.71, "analysis_score": 0.78, "tags": ["explainability", "docs", "small-model", "sanity"]},
            {"id": "phi4-mini-instruct", "family": "phi", "local": True, "code_score": 0.72, "test_score": 0.76, "analysis_score": 0.74, "tags": ["compact", "unit-tests", "reasoning", "sanity"]},
            {"id": "gpt-5.5-pro-external", "family": "openai", "local": False, "code_score": 0.95, "test_score": 0.93, "analysis_score": 0.94, "tags": ["architecture", "tests", "security", "performance"]},
            {"id": "claude-sonnet-external", "family": "anthropic", "local": False, "code_score": 0.93, "test_score": 0.91, "analysis_score": 0.92, "tags": ["review", "edge-cases", "readability", "integration"]},
            {"id": "gemini-pro-external", "family": "google", "local": False, "code_score": 0.91, "test_score": 0.89, "analysis_score": 0.95, "tags": ["large-context", "cross-file", "api-contracts", "regression"]}
        ],
        "handoff": {"markdown": True, "json_sidecar": True, "sha256": True},
    }


def load_policy(root: Path) -> Dict[str, Any]:
    return load_json(root / "configs" / "team-member-policy.json", default_policy())


def tag_diversity(a: Iterable[str], b: Iterable[str]) -> float:
    aa, bb = set(a or []), set(b or [])
    if not aa and not bb:
        return 0.5
    return 1.0 - (len(aa & bb) / max(1, len(aa | bb)))


def select_models(policy: Dict[str, Any], member: str, producer: str, count: int, requested: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    candidates = [dict(x) for x in policy.get("model_candidates", [])]
    by_id = {str(c.get("id")): c for c in candidates}
    if requested:
        out = []
        for mid in requested:
            if mid == producer:
                continue
            out.append(by_id.get(mid, {"id": mid, "family": "manual", "code_score": 0.80, "test_score": 0.80, "analysis_score": 0.80, "tags": ["manual"]}))
        return out[:max(1, count)]
    prod_tags = by_id.get(producer, {}).get("tags") or []
    pool = [c for c in candidates if c.get("id") != producer]
    selected: List[Dict[str, Any]] = []
    key_score = "analysis_score" if "analyser" in member or "visual" in member else "test_score" if member in {"qa", "tester", "integration_tester"} else "code_score"
    while pool and len(selected) < max(1, count):
        scored = []
        for c in pool:
            div_prod = tag_diversity(c.get("tags") or [], prod_tags)
            div_sel = 1.0 if not selected else sum(tag_diversity(c.get("tags") or [], s.get("tags") or []) for s in selected) / len(selected)
            score = float(c.get(key_score, 0.0)) * 0.55 + float(c.get("code_score", 0.0)) * 0.15 + div_prod * 0.15 + div_sel * 0.15
            scored.append((score, div_prod, div_sel, c))
        scored.sort(key=lambda x: (x[0], x[1], x[2], str(x[3].get("id"))), reverse=True)
        best = dict(scored[0][3])
        best["selection_score"] = round(scored[0][0], 4)
        best["diversity_from_producer"] = round(scored[0][1], 4)
        best["diversity_from_selected"] = round(scored[0][2], 4)
        selected.append(best)
        pool = [c for c in pool if c.get("id") != best.get("id")]
    return selected


def scan_files(project: Path, limit: int = 220) -> Dict[str, Any]:
    files: List[Dict[str, Any]] = []
    for path in project.rglob("*"):
        if len(files) >= limit:
            break
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.suffix.lower() not in CODE_EXTS:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            loc = len([line for line in lines if line.strip()])
        except Exception:
            text, loc = "", 0
        rel = str(path.relative_to(project))
        files.append({"path": rel, "suffix": path.suffix.lower(), "loc": loc, "is_test": any(h in rel for h in ["/tests/", "test_", "_test.", ".spec.", ".test."]), "sha256": sha256_text(text) if text else ""})
    return {"project": str(project), "file_count": len(files), "source_count": len([f for f in files if not f["is_test"]]), "test_count": len([f for f in files if f["is_test"]]), "files": files, "truncated": len(files) >= limit}


def run_auto_checks(project: Path, scan: Dict[str, Any], max_files: int = 90) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    for f in scan.get("files", [])[:max_files]:
        rel = f.get("path", "")
        p = project / rel
        if f.get("suffix") == ".py":
            cmd = [sys.executable, "-m", "py_compile", str(p)]
        elif f.get("suffix") == ".sh":
            cmd = ["bash", "-n", str(p)]
        else:
            continue
        try:
            cp = subprocess.run(cmd, text=True, capture_output=True, timeout=12)
            checks.append({"path": rel, "command": cmd, "ok": cp.returncode == 0, "exit_code": cp.returncode, "stderr_tail": cp.stderr[-1200:]})
        except Exception as e:
            checks.append({"path": rel, "command": cmd, "ok": False, "exit_code": None, "stderr_tail": str(e)})
    return {"created_at": nowz(), "ok": all(c.get("ok") for c in checks), "check_count": len(checks), "failed_count": len([c for c in checks if not c.get("ok")]), "checks": checks}


class PythonAnalyzer(ast.NodeVisitor):
    def __init__(self, rel: str):
        self.rel = rel
        self.functions: List[Dict[str, Any]] = []
        self.classes: List[Dict[str, Any]] = []
        self.calls: List[Dict[str, Any]] = []
        self.current: List[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self.classes.append({"name": node.name, "file": self.rel, "lineno": node.lineno, "method_count": len([x for x in node.body if isinstance(x, ast.FunctionDef)])})
        self.current.append(node.name)
        self.generic_visit(node)
        self.current.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        qual = ".".join(self.current + [node.name]) if self.current else node.name
        end = getattr(node, "end_lineno", node.lineno)
        self.functions.append({"name": node.name, "qualname": qual, "file": self.rel, "lineno": node.lineno, "loc": max(1, end - node.lineno + 1), "arg_count": len(node.args.args)})
        self.current.append(node.name)
        self.generic_visit(node)
        self.current.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_Call(self, node: ast.Call) -> Any:
        callee = "unknown"
        if isinstance(node.func, ast.Name):
            callee = node.func.id
        elif isinstance(node.func, ast.Attribute):
            callee = node.func.attr
        caller = ".".join(self.current) if self.current else "<module>"
        self.calls.append({"file": self.rel, "lineno": getattr(node, "lineno", 0), "caller": caller, "callee": callee})
        self.generic_visit(node)


def analyze_code(project: Path, scan: Dict[str, Any]) -> Dict[str, Any]:
    classes: List[Dict[str, Any]] = []
    functions: List[Dict[str, Any]] = []
    calls: List[Dict[str, Any]] = []
    for f in scan.get("files", []):
        if f.get("suffix") != ".py":
            continue
        rel = f.get("path", "")
        try:
            tree = ast.parse((project / rel).read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            calls.append({"file": rel, "caller": "parse", "callee": "parse_error", "error": str(e)})
            continue
        visitor = PythonAnalyzer(rel)
        visitor.visit(tree)
        classes.extend(visitor.classes)
        functions.extend(visitor.functions)
        calls.extend(visitor.calls)
    by_callee: Dict[str, int] = {}
    for c in calls:
        by_callee[str(c.get("callee"))] = by_callee.get(str(c.get("callee")), 0) + 1
    repeated = [{"callee": k, "call_count": v} for k, v in sorted(by_callee.items(), key=lambda kv: (-kv[1], kv[0])) if v > 1]
    heavy_functions = [fn for fn in functions if int(fn.get("loc", 0)) >= 50 or int(fn.get("arg_count", 0)) >= 6]
    bottlenecks = []
    for fn in heavy_functions[:50]:
        bottlenecks.append({"id": f"long_or_wide_function:{fn['file']}:{fn['qualname']}", "severity": "medium", "summary": f"{fn['qualname']} is large/wide: loc={fn['loc']} args={fn['arg_count']}"})
    for item in repeated[:50]:
        bottlenecks.append({"id": f"repeated_call:{item['callee']}", "severity": "info", "summary": f"Function/call `{item['callee']}` appears {item['call_count']} times in static call emulation."})
    return {"created_at": nowz(), "project": str(project), "class_count": len(classes), "function_count": len(functions), "call_count": len(calls), "classes": classes, "functions": functions, "calls": calls[:2000], "repeated_calls": repeated[:200], "bottlenecks": bottlenecks[:200]}


def mermaid_overview(analysis: Dict[str, Any], scan: Dict[str, Any]) -> str:
    exts: Dict[str, int] = {}
    for f in scan.get("files", []):
        exts[f.get("suffix", "?")] = exts.get(f.get("suffix", "?"), 0) + 1
    lines = ["flowchart TD", "  Project[Project] --> Files[Files]", f"  Files --> Py[Python functions: {analysis.get('function_count', 0)}]", f"  Files --> Classes[Classes: {analysis.get('class_count', 0)}]", f"  Py --> Calls[Calls: {analysis.get('call_count', 0)}]"]
    for ext, count in sorted(exts.items()):
        node = safe_id(ext or "other")
        lines.append(f"  Files --> {node}[{ext or 'other'}: {count}]")
    if analysis.get("bottlenecks"):
        lines.append("  Calls --> Bottlenecks[Potential bottlenecks]")
    return "\n".join(lines) + "\n"


def mermaid_call_graph(analysis: Dict[str, Any], limit: int = 80) -> str:
    lines = ["flowchart LR"]
    edges = []
    seen = set()
    for c in analysis.get("calls", [])[:limit]:
        a, b = safe_id(str(c.get("caller", "caller")))[:60], safe_id(str(c.get("callee", "callee")))[:60]
        key = (a, b)
        if key in seen:
            continue
        seen.add(key)
        edges.append(f"  {a}[{c.get('caller')}] --> {b}[{c.get('callee')}]")
    return "\n".join(lines + edges) + "\n"


def member_finding_seed(member: str, scan: Dict[str, Any], auto: Dict[str, Any], analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    if scan.get("source_count", 0) > 0 and scan.get("test_count", 0) == 0:
        findings.append({"id": "missing_tests", "severity": "high", "summary": "Source files are present but no obvious tests were found."})
    if auto.get("failed_count", 0):
        findings.append({"id": "auto_checks_failed", "severity": "high", "summary": f"Auto checks failed for {auto.get('failed_count')} files."})
    if analysis.get("bottlenecks"):
        findings.append({"id": "bottleneck_candidates", "severity": "medium", "summary": f"Static analysis found {len(analysis.get('bottlenecks') or [])} bottleneck/repeated-call candidates."})
    if member in {"qa", "tester"}:
        findings.append({"id": "qa_requires_regression_cases", "severity": "medium", "summary": "QA must add regression tests for every consensus finding before approval."})
    if member == "developer":
        findings.append({"id": "developer_must_attach_auto_tests", "severity": "medium", "summary": "Developer handoff must include auto_tests_report and changed-file summary."})
    if member == "code_analyser_visualiser":
        findings.append({"id": "architecture_diagrams_created", "severity": "info", "summary": "Architecture overview and call graph diagrams were generated."})
    return findings


def proposal_for(model: Dict[str, Any], member: str, request: str, scan: Dict[str, Any], auto: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    mid = str(model.get("id"))
    findings = member_finding_seed(member, scan, auto, analysis)
    # Deterministic model-specific angle for consensus/unique artifacts.
    tags = set(model.get("tags") or [])
    if "security" in tags:
        findings.append({"id": "security_review_required", "severity": "medium", "summary": "Security-sensitive changes need capability/token and filesystem-write review."})
    if "performance" in tags or "static-analysis" in tags:
        findings.append({"id": "resource_budget_required", "severity": "medium", "summary": "Change should include CPU/memory/disk budget and before/after measurements."})
    if "edge-cases" in tags:
        findings.append({"id": "edge_case_tests_required", "severity": "medium", "summary": "Tests should cover failure paths, empty inputs and malformed artifacts."})
    return {"model": mid, "family": model.get("family"), "created_at": nowz(), "member": member, "request": request, "execution": "sequential_slot", "findings": findings, "recommended_artifacts": recommended_artifacts(member), "notes": f"Offline scaffold for {member}; execute with switchable LLM lease when live model is available."}


def recommended_artifacts(member: str) -> List[str]:
    table = {
        "developer": ["implementation_plan.md", "auto_tests_report.json", "changed_files.json"],
        "qa": ["qa_report.md", "recommended_tests.md", "approval_or_denial.json"],
        "tester": ["test_plan.md", "test_results.json"],
        "integration_tester": ["integration_report.md", "risk_register.json"],
        "optimizer": ["optimization_report.md", "resource_budget.json"],
        "code_analyser_visualiser": ["architecture_overview.mmd", "call_graph.mmd", "bottleneck_report.json", "helicopter_view.md"],
    }
    return table.get(member, ["member_report.md", "handoff_context.md"])


def merge_consensus(proposals: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_id: Dict[str, List[str]] = {}
    details: Dict[str, Dict[str, Any]] = {}
    for p in proposals:
        model = str(p.get("model"))
        for f in p.get("findings") or []:
            fid = str(f.get("id") or "unknown")
            by_id.setdefault(fid, []).append(model)
            details.setdefault(fid, f)
    consensus = []
    unique = []
    for fid, models in sorted(by_id.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        item = dict(details[fid])
        item["models"] = models
        item["agreement_count"] = len(models)
        if len(models) > 1:
            consensus.append(item)
        else:
            unique.append(item)
    return {"created_at": nowz(), "proposal_count": len(proposals), "consensus_artifacts": consensus, "unique_artifacts": unique, "agreement_ratio": round(sum(1 for x in consensus) / max(1, len(consensus) + len(unique)), 4)}


def find_pipeline_run_dir(pipeline_state: Path, run_id: Optional[str]) -> Optional[Path]:
    if not run_id:
        return None
    db = pipeline_state / "pipeline_registry.sqlite"
    if db.exists():
        try:
            conn = sqlite3.connect(db)
            row = conn.execute("SELECT run_dir FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row:
                return Path(row[0])
        except Exception:
            pass
    candidate = pipeline_state / "runs" / run_id
    return candidate if candidate.exists() else None


def maybe_register_pipeline_artifact(pipeline_state: Path, pipeline_run_id: Optional[str], stage: str, artifact_type: str, path: Path, metadata: Dict[str, Any]) -> None:
    if not pipeline_run_id:
        return
    db = pipeline_state / "pipeline_registry.sqlite"
    if not db.exists():
        return
    try:
        conn = sqlite3.connect(db)
        ts = nowz()
        artifact_id = safe_id(metadata.get("artifact_id") or f"art_{pipeline_run_id}_{stage}_{artifact_type}_{path.stem}")[:180]
        conn.execute("INSERT OR REPLACE INTO artifacts(artifact_id,run_id,stage,artifact_type,path,status,created_at,updated_at,metadata) VALUES(?,?,?,?,?,?,?,?,?)", (artifact_id, pipeline_run_id, stage, artifact_type, str(path), "reviewed", ts, ts, jdump(metadata, pretty=False)))
        conn.execute("INSERT INTO events(run_id,ts,event_type,payload) VALUES(?,?,?,?)", (pipeline_run_id, ts, "member_artifact_registered", jdump({"artifact_id": artifact_id, "stage": stage, "path": str(path), "artifact_type": artifact_type}, pretty=False)))
        conn.commit()
    except Exception:
        return


def misunderstanding_loop_check(member_run_dir: Path, member: str, consensus_doc: Dict[str, Any]) -> Dict[str, Any]:
    if member not in {"qa", "tester", "integration_tester"}:
        return {"checked": False, "loop_risk": False, "reason": "not a QA/tester member"}
    root = member_run_dir.parent.parent if member_run_dir.parent.name == "members" else member_run_dir.parent
    finding_ids: List[str] = []
    for p in root.rglob("consensus.json"):
        if p == member_run_dir / "consensus.json":
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8", errors="replace"))
            for item in (doc.get("consensus_artifacts") or []) + (doc.get("unique_artifacts") or []):
                finding_ids.append(str(item.get("id")))
        except Exception:
            pass
    current = [str(x.get("id")) for x in (consensus_doc.get("consensus_artifacts") or [])]
    repeats = sorted({fid for fid in current if finding_ids.count(fid) >= 2})
    loop_risk = bool(repeats)
    return {"checked": True, "loop_risk": loop_risk, "repeated_finding_ids": repeats, "policy": "If the same ambiguity returns to Dev twice, QA must deny approval and request architect clarification instead of another blind dev loop."}


def validate_artifacts(run_dir: Path, member: str, policy: Dict[str, Any], auto: Dict[str, Any], consensus_doc: Dict[str, Any]) -> Dict[str, Any]:
    cell = (policy.get("member_cells") or {}).get(member, {})
    problems: List[str] = []
    warnings: List[str] = []
    required = ["member_run.json", "consensus.json", "unique_artifacts.json", "next_participant_handoff_context.md", "next_participant_handoff_context.json", "next_participant_handoff_context.json.sha256"]
    if cell.get("requires_auto_tests"):
        required.append("auto_tests_report.json")
        if auto.get("check_count", 0) == 0:
            warnings.append("developer auto-tests produced zero runnable checks; attach manual test evidence before QA approval")
        elif not auto.get("ok"):
            problems.append("developer auto-tests failed")
    if cell.get("requires_diagrams"):
        required.extend(["architecture_overview.mmd", "call_graph.mmd", "bottleneck_report.json", "helicopter_view.md"])
    for name in required:
        if not (run_dir / name).exists():
            problems.append(f"missing required artifact: {name}")
    sidecar = run_dir / "next_participant_handoff_context.json"
    sha = run_dir / "next_participant_handoff_context.json.sha256"
    if sidecar.exists() and sha.exists():
        actual = hashlib.sha256(sidecar.read_bytes()).hexdigest()
        expected = sha.read_text(encoding="utf-8", errors="replace").strip()
        if actual != expected:
            problems.append("handoff JSON checksum mismatch")
    loop = misunderstanding_loop_check(run_dir, member, consensus_doc)
    if loop.get("loop_risk"):
        problems.append("QA loop risk: repeated dev misunderstanding detected; route to architect clarification")
    return {"ok": not problems, "member": member, "checked_at": nowz(), "problems": problems, "warnings": warnings, "loop_check": loop, "required_artifacts": required}


def write_handoff(run_dir: Path, doc: Dict[str, Any]) -> None:
    lines = [f"# Team member handoff — {doc['member']} / {doc['stage']}", "", f"- run_id: `{doc['run_id']}`", f"- pipeline_run_id: `{doc.get('pipeline_run_id') or ''}`", f"- stage: `{doc['stage']}`", f"- member: `{doc['member']}`", f"- execution_mode: `{doc['execution_mode']}`", f"- effective_execution: `sequential_by_single_llm_lease`", f"- created_at: `{doc['created_at']}`", "", "## Models / participants", ""]
    for m in doc.get("models") or []:
        lines.append(f"- `{m.get('id')}` family=`{m.get('family')}` score=`{m.get('selection_score')}` diversity=`{m.get('diversity_from_producer')}`")
    lines += ["", "## Consensus artifacts", ""]
    for item in doc["consensus"].get("consensus_artifacts") or []:
        lines.append(f"- `{item['id']}` agreement={item['agreement_count']} models={', '.join(item['models'])}: {item['summary']}")
    if not doc["consensus"].get("consensus_artifacts"):
        lines.append("- No multi-model consensus artifacts in this offline run.")
    lines += ["", "## Unique artifacts", ""]
    for item in doc["consensus"].get("unique_artifacts") or []:
        lines.append(f"- `{item['id']}` by={', '.join(item['models'])}: {item['summary']}")
    lines += ["", "## Artifact consistency", "", f"- ok: `{doc['artifact_consistency']['ok']}`"]
    for p in doc["artifact_consistency"].get("problems") or []:
        lines.append(f"- problem: {p}")
    for w in doc["artifact_consistency"].get("warnings") or []:
        lines.append(f"- warning: {w}")
    lines += ["", "## Next participant instruction", "", doc.get("next_instruction") or "Use this as the typed input to the next pipeline member. Do not advance unless artifact_consistency.ok=true or admin waives the gate.", ""]
    md = "\n".join(lines)
    atomic_write(run_dir / "next_participant_handoff_context.md", md)
    envelope = {"apiVersion": "noemaforge/v1", "kind": "TeamMemberHandoff", "version": RUNTIME_VERSION, "run_id": doc["run_id"], "pipeline_run_id": doc.get("pipeline_run_id"), "stage": doc["stage"], "member": doc["member"], "created_at": nowz(), "consensus": doc["consensus"], "artifact_consistency": doc["artifact_consistency"], "sha256_markdown": sha256_text(md)}
    json_text = jdump(envelope)
    atomic_write(run_dir / "next_participant_handoff_context.json", json_text)
    atomic_write(run_dir / "next_participant_handoff_context.json.sha256", sha256_bytes(json_text.encode("utf-8")) + "\n")


def connect(state: Path) -> sqlite3.Connection:
    state.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(state / "team_member_registry.sqlite")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, pipeline_run_id TEXT, stage TEXT NOT NULL, member TEXT NOT NULL, project TEXT NOT NULL, result_json TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, ts TEXT NOT NULL, event_type TEXT NOT NULL, payload_json TEXT NOT NULL)")
    conn.commit()
    return conn


def emit(conn: sqlite3.Connection, run_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    conn.execute("INSERT INTO events(run_id,ts,event_type,payload_json) VALUES(?,?,?,?)", (run_id, nowz(), event_type, jdump(payload, pretty=False)))
    conn.commit()


def cmd_team(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    policy = load_policy(root)
    member = args.member
    cell = (policy.get("member_cells") or {}).get(member, {})
    count = args.count or int(cell.get("min_models") or 1)
    models = select_models(policy, member, args.producer, count, args.model)
    out = {"ok": True, "member": member, "producer_model": args.producer, "cell_policy": cell, "effective_execution": "sequential_by_single_llm_lease", "models": models, "invariant": policy.get("invariant")}
    print(jdump(out) if args.json else "\n".join([f"member: {member}"] + [f"model: {m.get('id')} score={m.get('selection_score')} diversity={m.get('diversity_from_producer')}" for m in models]))


def cmd_analyze_code(args: argparse.Namespace) -> None:
    project = Path(args.project or os.getcwd()).resolve()
    scan = scan_files(project)
    analysis = analyze_code(project, scan)
    out_dir = Path(args.out).resolve() if args.out else None
    if out_dir:
        atomic_write(out_dir / "scan.json", jdump(scan))
        atomic_write(out_dir / "code_analysis.json", jdump(analysis))
        atomic_write(out_dir / "architecture_overview.mmd", mermaid_overview(analysis, scan))
        atomic_write(out_dir / "call_graph.mmd", mermaid_call_graph(analysis))
        atomic_write(out_dir / "bottleneck_report.json", jdump({"bottlenecks": analysis.get("bottlenecks"), "repeated_calls": analysis.get("repeated_calls")}))
    doc = {"ok": True, "project": str(project), "scan": {k: v for k, v in scan.items() if k != "files"}, "analysis_summary": {k: analysis.get(k) for k in ["class_count", "function_count", "call_count", "repeated_calls", "bottlenecks"]}, "out": str(out_dir) if out_dir else None}
    print(jdump(doc))


def cmd_run(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    pipeline_state = Path(args.pipeline_state).resolve() if args.pipeline_state else DEFAULT_PIPELINE_STATE
    project = Path(args.project or os.getcwd()).resolve()
    policy = load_policy(root)
    member = safe_id(args.member)
    cell = (policy.get("member_cells") or {}).get(member, {})
    count = args.count or int(cell.get("min_models") or (2 if cell.get("mode") == "ensemble" else 1))
    models = select_models(policy, member, args.producer, count, args.model)
    run_id = safe_id(args.run_id or f"member_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{member}")
    pipeline_run_dir = find_pipeline_run_dir(pipeline_state, args.pipeline_run_id)
    if pipeline_run_dir:
        run_dir = pipeline_run_dir / "members" / safe_id(args.stage) / member / run_id
    else:
        run_dir = state / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    scan = scan_files(project)
    auto = run_auto_checks(project, scan) if not args.skip_auto_tests else {"created_at": nowz(), "ok": True, "check_count": 0, "failed_count": 0, "checks": [], "skipped": True}
    analysis = analyze_code(project, scan)
    atomic_write(run_dir / "scan.json", jdump(scan))
    atomic_write(run_dir / "auto_tests_report.json", jdump(auto))
    atomic_write(run_dir / "code_analysis.json", jdump(analysis))
    if member == "code_analyser_visualiser" or args.write_diagrams:
        atomic_write(run_dir / "architecture_overview.mmd", mermaid_overview(analysis, scan))
        atomic_write(run_dir / "call_graph.mmd", mermaid_call_graph(analysis))
        atomic_write(run_dir / "bottleneck_report.json", jdump({"bottlenecks": analysis.get("bottlenecks"), "repeated_calls": analysis.get("repeated_calls"), "helicopter_view": {"files": scan.get("file_count"), "functions": analysis.get("function_count"), "classes": analysis.get("class_count")}}))
        hv = ["# Code helicopter view", "", f"- files: `{scan.get('file_count')}`", f"- source files: `{scan.get('source_count')}`", f"- test files: `{scan.get('test_count')}`", f"- classes: `{analysis.get('class_count')}`", f"- functions: `{analysis.get('function_count')}`", f"- calls observed by static execution emulation: `{analysis.get('call_count')}`", "", "## Repeated function/call usage", ""]
        for item in analysis.get("repeated_calls", [])[:40]:
            hv.append(f"- `{item['callee']}` used `{item['call_count']}` times")
        atomic_write(run_dir / "helicopter_view.md", "\n".join(hv) + "\n")
    proposals = []
    for index, model in enumerate(models, 1):
        proposal = proposal_for(model, member, args.request, scan, auto, analysis)
        proposal["sequence_index"] = index
        proposals.append(proposal)
        atomic_write(run_dir / "proposals" / f"{index:02d}_{safe_id(str(model.get('id')))}.json", jdump(proposal))
    consensus_doc = merge_consensus(proposals)
    atomic_write(run_dir / "consensus.json", jdump(consensus_doc))
    atomic_write(run_dir / "unique_artifacts.json", jdump({"items": consensus_doc.get("unique_artifacts") or []}))
    consistency = validate_artifacts(run_dir, member, policy, auto, consensus_doc)
    doc = {"ok": consistency["ok"], "apiVersion": "noemaforge/v1", "kind": "PipelineTeamMemberRun", "version": RUNTIME_VERSION, "run_id": run_id, "pipeline_run_id": args.pipeline_run_id, "created_at": nowz(), "updated_at": nowz(), "stage": args.stage, "member": member, "producer_model": args.producer, "execution_mode": args.mode, "effective_execution": "sequential_by_single_llm_lease", "project": str(project), "request": args.request, "models": models, "proposal_count": len(proposals), "consensus": consensus_doc, "artifact_consistency": consistency, "run_dir": str(run_dir), "next_instruction": args.next_instruction or "Pass this handoff to the next pipeline member; if artifact_consistency.ok=false, route back to the responsible member or architect."}
    atomic_write(run_dir / "member_run.json", jdump(doc))
    # Re-validate after member_run.json exists, then write handoff, then validate the full outgoing artifact set.
    consistency = validate_artifacts(run_dir, member, policy, auto, consensus_doc)
    doc["artifact_consistency"] = consistency
    doc["ok"] = bool(consistency.get("ok"))
    atomic_write(run_dir / "member_run.json", jdump(doc))
    write_handoff(run_dir, doc)
    consistency = validate_artifacts(run_dir, member, policy, auto, consensus_doc)
    doc["artifact_consistency"] = consistency
    doc["ok"] = bool(consistency.get("ok"))
    atomic_write(run_dir / "member_run.json", jdump(doc))
    write_handoff(run_dir, doc)
    conn = connect(state)
    conn.execute("INSERT OR REPLACE INTO runs(run_id,created_at,updated_at,pipeline_run_id,stage,member,project,result_json) VALUES(?,?,?,?,?,?,?,?)", (run_id, doc["created_at"], doc["updated_at"], args.pipeline_run_id, args.stage, member, str(project), jdump(doc, pretty=False)))
    conn.commit()
    emit(conn, run_id, "member_run_created", {"pipeline_run_id": args.pipeline_run_id, "stage": args.stage, "member": member, "model_count": len(models), "ok": doc["ok"]})
    maybe_register_pipeline_artifact(pipeline_state, args.pipeline_run_id, args.stage, f"member_{member}_handoff", run_dir / "next_participant_handoff_context.md", {"artifact_id": f"member_{args.pipeline_run_id}_{args.stage}_{member}_{run_id}", "member_run_id": run_id, "consistency_ok": doc["ok"]})
    print(jdump(doc) if args.json else f"ok={str(doc['ok']).lower()} run_id={run_id} run_dir={run_dir}")
    if args.strict and not doc["ok"]:
        raise SystemExit(1)


def cmd_show(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = connect(state)
    row = conn.execute("SELECT result_json FROM runs WHERE run_id=?", (args.run_id,)).fetchone()
    if not row:
        raise SystemExit(f"unknown member run: {args.run_id}")
    print(jdump(json.loads(row[0])))


def cmd_list(args: argparse.Namespace) -> None:
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    conn = connect(state)
    rows = conn.execute("SELECT run_id,created_at,pipeline_run_id,stage,member,project FROM runs ORDER BY updated_at DESC LIMIT ?", (args.limit,)).fetchall()
    print(jdump({"ok": True, "items": [dict(zip(["run_id", "created_at", "pipeline_run_id", "stage", "member", "project"], r)) for r in rows]}))


def cmd_validate(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    policy = load_policy(root)
    problems: List[str] = []
    cells = policy.get("member_cells") or {}
    if not cells:
        problems.append("no member_cells configured")
    if int((policy.get("invariant") or {}).get("max_active_llms") or 0) != 1:
        problems.append("max_active_llms must be 1")
    for required in ["developer", "qa", "code_analyser_visualiser"]:
        if required not in cells:
            problems.append(f"missing required member cell: {required}")
    print(jdump({"ok": not problems, "version": policy.get("version"), "member_count": len(cells), "problems": problems, "invariant": policy.get("invariant")}))
    if problems:
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="noemaforge member")
    p.add_argument("--root")
    p.add_argument("--state")
    p.add_argument("--pipeline-state")
    sub = p.add_subparsers(dest="cmd", required=True)
    team = sub.add_parser("team")
    team.add_argument("--member", default="qa")
    team.add_argument("--producer", default="qwen25-coder-14b")
    team.add_argument("--model", action="append")
    team.add_argument("--count", type=int)
    team.add_argument("--json", action="store_true")
    team.set_defaults(func=cmd_team)
    run = sub.add_parser("run")
    run.add_argument("--pipeline-run-id")
    run.add_argument("--stage", default="development")
    run.add_argument("--member", default="qa")
    run.add_argument("--project", default=os.getcwd())
    run.add_argument("--producer", default="qwen25-coder-14b")
    run.add_argument("--model", action="append")
    run.add_argument("--count", type=int)
    run.add_argument("--mode", choices=["sequential", "parallel_requested_serialized"], default="sequential")
    run.add_argument("--request", default="Pipeline member execution")
    run.add_argument("--run-id")
    run.add_argument("--next-instruction")
    run.add_argument("--skip-auto-tests", action="store_true")
    run.add_argument("--write-diagrams", action="store_true")
    run.add_argument("--strict", action="store_true")
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=cmd_run)
    ana = sub.add_parser("analyze-code")
    ana.add_argument("--project", default=os.getcwd())
    ana.add_argument("--out")
    ana.set_defaults(func=cmd_analyze_code)
    lst = sub.add_parser("list")
    lst.add_argument("--limit", type=int, default=20)
    lst.set_defaults(func=cmd_list)
    show = sub.add_parser("show")
    show.add_argument("run_id")
    show.set_defaults(func=cmd_show)
    val = sub.add_parser("validate")
    val.set_defaults(func=cmd_validate)
    return p


def normalize_global_argv(argv: Optional[List[str]]) -> List[str]:
    items = list(sys.argv[1:] if argv is None else argv)
    global_opts: List[str] = []
    rest: List[str] = []
    i = 0
    while i < len(items):
        if items[i] in {"--root", "--state", "--pipeline-state"} and i + 1 < len(items):
            global_opts.extend([items[i], items[i + 1]])
            i += 2
        else:
            rest.append(items[i])
            i += 1
    return global_opts + rest


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_global_argv(argv))
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


