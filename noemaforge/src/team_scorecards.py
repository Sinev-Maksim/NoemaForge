#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/team_scorecards.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations


# === NoemaForge Autodoc File Header ===
# File: src/team_scorecards.py
# Purpose: Provide the module 'team_scorecards'.
# Invoked by / imported from:
#   - src/surgeon_auto.py
# Public API / entry functions:
#   - class UnixHTTPConnection
#   - load_flow_eval_suite
#   - load_role_affirmations
#   - run_team_scorecard
# Inputs:
#   - Environment: NOEMAFORGE_TEAM_SCORECARDS, NOEMAFORGE_LLM_GATEWAY_SOCKET
#   - Common path inputs: /var/lib/noemaforge/team_scorecards, /run/noemaforge/llm/gateway.sock, application/json
#   - Imports: __future__, datetime, hashlib, json, os, time, typing, yaml
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""team_scorecards.py (v0.11.6)

End-to-end "team" evaluation.

This is NOT a canary.
It produces measurements (scorecards) that Surgeon can use to propose
pre-start policy changes.

Key idea
--------
Per-role "best" models do not necessarily yield best final outcome.
We therefore evaluate *combinations* (team configs) for a flow.

Implementation in MVP
---------------------
- Deterministic, cheap, sequential.
- One flow case = a short synthetic goal.
- We simulate the pipeline by calling gateway for each role step.
- Final output is judged by a judge model and produces overall score.
"""


import datetime as dt
import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import yaml

# Unix socket HTTP client (same approach as model_scorecards)
import http.client
import socket


DEFAULT_TEAM_SCORECARDS_DIR = os.environ.get("NOEMAFORGE_TEAM_SCORECARDS", "/var/lib/noemaforge/team_scorecards")
DEFAULT_GATEWAY_SOCKET = os.environ.get("NOEMAFORGE_LLM_GATEWAY_SOCKET", "/run/noemaforge/llm/gateway.sock")


class UnixHTTPConnection(http.client.HTTPConnection):
    # === NoemaForge Autodoc Function Header ===
    # Function: __init__(self, unix_socket_path: str, timeout: float = 30.0)
    # Purpose: Implement the routine '  init  '.
    # Inputs:
    #   - self
    #   - unix_socket_path: str
    #   - timeout: float = 30.0
    # Called by:
    #   - src/model_scorecards.py
    #   - src/toolproxy.py
    # Calls:
    #   - __init__, super
    # Returns / emits: unspecified Python value
    # === End NoemaForge Autodoc Function Header ===
    def __init__(self, unix_socket_path: str, timeout: float = 30.0):
        super().__init__("localhost", timeout=timeout)
        self.unix_socket_path = unix_socket_path

    # === NoemaForge Autodoc Function Header ===
    # Function: connect(self)
    # Purpose: Implement the routine 'connect'.
    # Inputs:
    #   - self
    # Called by:
    #   - src/casebase.py
    #   - src/dream_cycle.py
    #   - src/flow_metrics.py
    #   - src/incident_metrics.py
    #   - src/incidents.py
    #   - src/knowledge/gatekeeper.py
    #   - src/knowledge/retrieval.py
    #   - src/knowledge/store.py
    # Calls:
    #   - socket, settimeout, connect
    # Returns / emits: unspecified Python value
    # Side effects:
    #   - opens a database or socket connection
    # === End NoemaForge Autodoc Function Header ===
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.unix_socket_path)


# === NoemaForge Autodoc Function Header ===
# Function: _nowz()
# Purpose: Implement the routine ' nowz'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/bundles.py
#   - src/caps.py
#   - src/casebase.py
#   - src/coordinator_fanout.py
#   - src/dream_cycle.py
#   - src/fixture_bundle.py
# Calls:
#   - isoformat, utcnow
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"


# === NoemaForge Autodoc Function Header ===
# Function: _load_yaml(path: str)
# Purpose: Implement the routine ' load yaml'.
# Inputs:
#   - path: str
# Called by:
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/canary_runner.py
#   - src/daily_scheduler.py
#   - src/fixture_bundle.py
#   - src/flow_metrics.py
#   - src/incidents.py
#   - src/knowledge/policy.py
# Calls:
#   - open, safe_load
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# === NoemaForge Autodoc Function Header ===
# Function: _save_json(path: str, obj)
# Purpose: Implement the routine ' save json'.
# Inputs:
#   - path: str
#   - obj
# Called by:
#   - src/audit_remediation.py
#   - src/noemaforge_core.py
#   - src/fixture_bundle.py
#   - src/model_registry.py
#   - src/model_scorecards.py
#   - src/prestart.py
#   - src/roles/role_entry.py
#   - src/scary_sweep.py
# Calls:
#   - makedirs, replace, dirname, open, dump
# Returns / emits: None
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f, tmp
# === End NoemaForge Autodoc Function Header ===
def _save_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# === NoemaForge Autodoc Function Header ===
# Function: _gateway_chat(sock: str, model: str, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 256, timeout_sec: float = 90.0)
# Purpose: Implement the routine ' gateway chat'.
# Inputs:
#   - sock: str
#   - model: str
#   - messages: List[Dict[str, str]]
#   - temperature: float = 0.2
#   - max_tokens: int = 256
#   - timeout_sec: float = 90.0
# Called by:
#   - src/model_scorecards.py
# Calls:
#   - encode, time, exists, UnixHTTPConnection, request, getresponse, read, close, dumps, loads, decode
# Returns / emits: Tuple[bool, Dict[str, Any], str, float]
# Side effects:
#   - serializes structured data
# Key locals:
#   - body, conn, data, ms, resp, t0
# === End NoemaForge Autodoc Function Header ===
def _gateway_chat(
    *,
    sock: str,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 256,
    timeout_sec: float = 90.0,
) -> Tuple[bool, Dict[str, Any], str, float]:
    if not os.path.exists(sock):
        return False, {}, "gateway_socket_missing", 0.0

    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    t0 = time.time()
    try:
        conn = UnixHTTPConnection(sock, timeout=timeout_sec)
        conn.request("POST", "/v1/chat/completions", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        ms = (time.time() - t0) * 1000.0
        if resp.status >= 300:
            return False, {"status": resp.status, "body": data.decode("utf-8", "replace")}, "gateway_error", ms
        try:
            return True, json.loads(data.decode("utf-8")), "ok", ms
        except Exception:
            return True, {"raw": data.decode("utf-8", "replace")}, "ok_nonjson", ms
    except Exception as e:
        ms = (time.time() - t0) * 1000.0
        return False, {}, f"gateway_unreachable:{e!r}", ms


# === NoemaForge Autodoc Function Header ===
# Function: _extract_text(resp: Dict[str, Any])
# Purpose: Implement the routine ' extract text'.
# Inputs:
#   - resp: Dict[str, Any]
# Called by:
#   - src/model_scorecards.py
# Calls:
#   - str
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _extract_text(resp: Dict[str, Any]) -> str:
    try:
        return str(resp["choices"][0]["message"]["content"])
    except Exception:
        return ""


# === NoemaForge Autodoc Function Header ===
# Function: _variance(values: List[float])
# Purpose: Compute a simple population variance for score aggregation.
# Inputs:
#   - values: List[float]
# Called by:
#   - _quality_metrics
# Returns / emits: float
# === End NoemaForge Autodoc Function Header ===
def _variance(values: List[float]) -> float:
    vals = [float(v) for v in (values or [])]
    if not vals:
        return 0.0
    mean = float(sum(vals) / len(vals))
    return float(sum((float(v) - mean) ** 2 for v in vals) / len(vals))


# === NoemaForge Autodoc Function Header ===
# Function: _quality_metrics(results: List[Dict[str, Any]], scores: List[float])
# Purpose: Derive stability and safety-facing metrics from team scorecard results.
# Inputs:
#   - results: List[Dict[str, Any]]
#   - scores: List[float]
# Called by:
#   - run_team_scorecard
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def _quality_metrics(results: List[Dict[str, Any]], scores: List[float]) -> Dict[str, Any]:
    vals = [float(v) for v in (scores or [])]
    case_count = len(results or [])
    variance = _variance(vals)
    missing_total = 0
    judge_failures = 0
    step_total = 0
    step_failures = 0
    nonjson_steps = 0
    hallucination_markers = 0

    for case in results or []:
        judge = case.get('judge') or {}
        raw = judge.get('raw') if isinstance(judge, dict) else {}
        if not bool(judge.get('ok')):
            judge_failures += 1
        if isinstance(raw, dict):
            missing = raw.get('missing') or []
            if isinstance(missing, list):
                missing_total += len(missing)
            notes = raw.get('notes') or []
            if isinstance(notes, list):
                note_blob = ' '.join(str(x) for x in notes)
                lowered = note_blob.lower()
                hallucination_markers += sum(1 for tok in ['hallucination', 'fabricated', 'unsupported', 'contradiction'] if tok in lowered)
        for step in case.get('steps') or []:
            step_total += 1
            if not bool(step.get('ok')):
                step_failures += 1
            reason = str(step.get('reason') or '')
            if 'nonjson' in reason or 'raw' in reason:
                nonjson_steps += 1

    stability = max(0.0, 1.0 - min(1.0, variance))
    success_rate = 1.0 if step_total == 0 else max(0.0, min(1.0, 1.0 - (step_failures / max(1, step_total))))
    hallucination_risk = min(1.0, (hallucination_markers + missing_total + nonjson_steps) / max(1, case_count * 4))

    return {
        'case_count': case_count,
        'step_count': step_total,
        'step_failures': step_failures,
        'judge_failures': judge_failures,
        'missing_sections_total': missing_total,
        'nonjson_steps': nonjson_steps,
        'score_variance': variance,
        'stability_score': stability,
        'step_success_rate': success_rate,
        'hallucination_markers': hallucination_markers,
        'hallucination_risk': hallucination_risk,
    }


# === NoemaForge Autodoc Function Header ===
# Function: load_flow_eval_suite(epoch_dir: str)
# Purpose: Implement the routine 'load flow eval suite'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, exists, _load_yaml
# Returns / emits: Dict[str, Any]
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def load_flow_eval_suite(epoch_dir: str) -> Dict[str, Any]:
    p = os.path.join(epoch_dir, "flow-eval-suite.yaml")
    if os.path.exists(p):
        try:
            return _load_yaml(p)
        except Exception:
            return {}
    return {}


# === NoemaForge Autodoc Function Header ===
# Function: load_role_affirmations(epoch_dir: str)
# Purpose: Implement the routine 'load role affirmations'.
# Inputs:
#   - epoch_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, exists, _load_yaml
# Returns / emits: Dict[str, Any]
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def load_role_affirmations(epoch_dir: str) -> Dict[str, Any]:
    p = os.path.join(epoch_dir, "role-affirmations.yaml")
    if os.path.exists(p):
        try:
            return _load_yaml(p)
        except Exception:
            return {}
    return {}


# === NoemaForge Autodoc Function Header ===
# Function: _affirmation_text(aff: Dict[str, Any], role: str)
# Purpose: Implement the routine ' affirmation text'.
# Inputs:
#   - aff: Dict[str, Any]
#   - role: str
# Called by:
#   - src/toolproxy.py
# Calls:
#   - strip, append, get, isinstance, split, range, join, str, len
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - affirmation, default, i, it, lines, parts, pr, r, roles, rules, title
# === End NoemaForge Autodoc Function Header ===
def _affirmation_text(aff: Dict[str, Any], role: str) -> str:
    default = aff.get("default") or {}
    roles = aff.get("roles") or {}
    r = roles.get(role) or {}
    if not r and isinstance(role, str) and "." in role:
        parts = role.split(".")
        for i in range(len(parts) - 1, 0, -1):
            pr = ".".join(parts[:i])
            if pr in roles:
                r = roles.get(pr) or {}
                break

    title = str(r.get("title") or default.get("title") or role or "executor").strip()
    affirmation = str(r.get("affirmation") or default.get("affirmation") or "").strip()
    rules = r.get("rules") if isinstance(r.get("rules"), list) else default.get("rules")
    rules = rules if isinstance(rules, list) else []

    lines: List[str] = []
    lines.append(f"Роль: {title} ({role})")
    if affirmation:
        lines.append("")
        lines.append(affirmation)
    if rules:
        lines.append("")
        lines.append("Правила:")
        for it in rules:
            lines.append(f"- {str(it)}")
    return "\n".join(lines).strip() + "\n"


# === NoemaForge Autodoc Function Header ===
# Function: _hash_team_config(flow_id: str, role_models: Dict[str, str], suite: str)
# Purpose: Implement the routine ' hash team config'.
# Inputs:
#   - flow_id: str
#   - role_models: Dict[str, str]
#   - suite: str
# Called by:
#   - src/team_search.py
# Calls:
#   - join, hexdigest, sorted, keys, sha256, encode
# Returns / emits: str
# Key locals:
#   - items, s
# === End NoemaForge Autodoc Function Header ===
def _hash_team_config(flow_id: str, role_models: Dict[str, str], suite: str) -> str:
    # Stable hash: order-independent keys.
    items = [f"{k}={role_models[k]}" for k in sorted(role_models.keys())]
    s = f"flow={flow_id}|suite={suite}|" + "|".join(items)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


# === NoemaForge Autodoc Function Header ===
# Function: _select_cases(doc: Dict[str, Any], suite: str, flow_id: str)
# Purpose: Implement the routine ' select cases'.
# Inputs:
#   - doc: Dict[str, Any]
#   - suite: str
#   - flow_id: str
# Called by:
#   - src/model_scorecards.py
# Calls:
#   - isinstance, get, append, dict
# Returns / emits: List[Dict[str, Any]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - c, cases, out, srec, suites
# === End NoemaForge Autodoc Function Header ===
def _select_cases(doc: Dict[str, Any], suite: str, flow_id: str) -> List[Dict[str, Any]]:
    suites = doc.get("suites") or {}
    srec = suites.get(suite) or {}
    cases = (srec.get("cases") or {}).get(flow_id) or []
    out: List[Dict[str, Any]] = []
    if isinstance(cases, list):
        for c in cases:
            if isinstance(c, dict) and c.get("id") and c.get("goal"):
                out.append(dict(c))
    return out


# === NoemaForge Autodoc Function Header ===
# Function: run_team_scorecard(epoch_dir: str, flow_id: str, nodes: List[Dict[str, Any]], role_models: Dict[str, str], judge_model: str = 'main', suite: str = 'smoke', gateway_socket: str = DEFAULT_GATEWAY_SOCKET, scorecards_dir: str = DEFAULT_TEAM_SCORECARDS_DIR)
# Purpose: Run an end-to-end scorecard for a flow/team configuration.
# Inputs:
#   - epoch_dir: str
#   - flow_id: str
#   - nodes: List[Dict[str, Any]]
#   - role_models: Dict[str, str]
#   - judge_model: str = 'main'
#   - suite: str = 'smoke'
#   - gateway_socket: str = DEFAULT_GATEWAY_SOCKET
#   - scorecards_dir: str = DEFAULT_TEAM_SCORECARDS_DIR
# Called by:
#   - src/surgeon_auto.py
# Calls:
#   - load_flow_eval_suite, load_role_affirmations, _select_cases, float, _hash_team_config, join, _save_json, lower, str, strip, int, dumps
# Returns / emits: Dict[str, Any]
# Side effects:
#   - serializes structured data
# Key locals:
#   - aff, baton, card, case, cases, cid, cons, eval_doc, final_text, goal, h, j_parsed
# === End NoemaForge Autodoc Function Header ===
def run_team_scorecard(
    *,
    epoch_dir: str,
    flow_id: str,
    nodes: List[Dict[str, Any]],
    role_models: Dict[str, str],
    judge_model: str = "main",
    suite: str = "smoke",
    gateway_socket: str = DEFAULT_GATEWAY_SOCKET,
    scorecards_dir: str = DEFAULT_TEAM_SCORECARDS_DIR,
) -> Dict[str, Any]:
    """Run an end-to-end scorecard for a flow/team configuration.

    nodes: list of {id, role, ...}
    role_models: mapping role_id -> model_id
    """
    suite = (suite or "smoke").strip().lower() or "smoke"
    eval_doc = load_flow_eval_suite(epoch_dir)
    aff = load_role_affirmations(epoch_dir)

    cases = _select_cases(eval_doc, suite, flow_id)
    if not cases:
        # Minimal fallback case.
        cases = [{"id": "default", "goal": "Коротко опиши план и дай проверяемый результат.", "rubric": {"required_sections": ["plan"]}}]

    results: List[Dict[str, Any]] = []
    scores: List[float] = []

    for case in cases:
        cid = str(case.get("id") or "")
        goal = str(case.get("goal") or "").strip()
        cons = case.get("constraints") or {}
        max_tokens = int(cons.get("max_tokens_per_step") or 220)
        temperature = float(cons.get("temperature") or 0.2)

        # Pipeline state
        baton = {
            "goal": goal,
            "artifacts": {},
            "notes": [],
        }

        step_traces: List[Dict[str, Any]] = []

        for n in nodes:
            rid = str(n.get("role") or "")
            nid = str(n.get("id") or rid)
            mid = str(role_models.get(rid) or "main")
            sys = _affirmation_text(aff, rid)

            user = (
                f"Цель: {goal}\n\n"
                f"Контекст (baton JSON):\n{json.dumps(baton, ensure_ascii=False, indent=2)}\n\n"
                "Сгенерируй свой вклад кратко и структурированно. "
                "Сохраняй итог как baton['artifacts'][<node_id>].\n"
                "Верни ТОЛЬКО JSON: {\"artifact\": ..., \"handoff\": ... }\n"
            )
            msgs = [{"role": "system", "content": sys}, {"role": "user", "content": user}]

            ok, resp, reason, ms = _gateway_chat(
                sock=gateway_socket,
                model=mid,
                messages=msgs,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            txt = _extract_text(resp) if ok else ""
            parsed: Dict[str, Any] = {}
            try:
                parsed = json.loads(txt)
            except Exception:
                parsed = {"raw": txt}

            baton["artifacts"][nid] = parsed.get("artifact") if isinstance(parsed, dict) else parsed
            baton["notes"].append({"node": nid, "role": rid, "model": mid, "reason": reason, "elapsed_ms": ms})
            step_traces.append({"node": nid, "role": rid, "model": mid, "ok": bool(ok), "reason": reason, "elapsed_ms": ms, "json_ok": isinstance(parsed, dict) and "raw" not in parsed})

        final_text = json.dumps(baton.get("artifacts") or {}, ensure_ascii=False, indent=2)
        rubric = case.get("rubric") or {}
        required = rubric.get("required_sections") or []
        judge_prompt = str(case.get("judge_prompt") or "").strip() or (
            "Верни JSON {\"overall\": <0..1>, \"missing\": [..], \"notes\": [..]} "
            "overall=1 если требования выполнены и результат связный."
        )

        judge_user = (
            f"Требования к секциям: {json.dumps(required, ensure_ascii=False)}\n\n"
            f"Финальный результат (artifacts JSON):\n{final_text}\n\n"
            f"{judge_prompt}\n"
        )
        judge_msgs = [{"role": "system", "content": "Ты строгий, но справедливый ревьюер."}, {"role": "user", "content": judge_user}]
        j_ok, j_resp, j_reason, j_ms = _gateway_chat(
            sock=gateway_socket,
            model=judge_model,
            messages=judge_msgs,
            temperature=0.0,
            max_tokens=220,
        )
        j_txt = _extract_text(j_resp) if j_ok else ""
        j_parsed: Dict[str, Any] = {}
        try:
            j_parsed = json.loads(j_txt)
        except Exception:
            j_parsed = {"raw": j_txt}

        overall = 0.0
        try:
            overall = float(j_parsed.get("overall") or 0.0)
        except Exception:
            overall = 0.0
        if overall < 0.0:
            overall = 0.0
        if overall > 1.0:
            overall = 1.0

        scores.append(overall)
        results.append(
            {
                "case_id": cid,
                "goal": goal,
                "steps": step_traces,
                "judge": {"ok": bool(j_ok), "reason": j_reason, "elapsed_ms": j_ms, "raw": j_parsed},
                "overall": overall,
            }
        )

    overall_score = float(sum(scores) / max(1, len(scores)))
    quality_metrics = _quality_metrics(results, scores)

    h = _hash_team_config(flow_id, role_models, suite)
    out_dir = os.path.join(scorecards_dir, flow_id)
    out_path = os.path.join(out_dir, f"team__{suite}__{h}.json")

    card = {
        "schema_version": "v1",
        "kind": "TeamScorecard",
        "created_at": _nowz(),
        "epoch_dir": epoch_dir,
        "flow_id": flow_id,
        "suite": suite,
        "judge_model": judge_model,
        "role_models": role_models,
        "overall_score": overall_score,
        "quality_metrics": quality_metrics,
        "cases": results,
    }
    _save_json(out_path, card)
    return {"ok": True, "scorecard_path": out_path, "card": card}
