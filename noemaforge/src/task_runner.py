#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/task_runner.py
Zone: release/package
Version: 0.31.13.alpha
Created: 2026-05-14
Modified: 2026-05-14
Purpose: Manage NoemaForge task queue and task execution surfaces.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations


# === NoemaForge Autodoc File Header ===
# File: src/task_runner.py
# Purpose: Provide the module 'task_runner'.
# Invoked by / imported from:
#   - src/maintenance.py
# Public API / entry functions:
#   - run_task
# Inputs:
#   - Common path inputs: /opt/noemaforge/src/noemaforge_core.py, /opt/noemaforge/configs
#   - Imports: __future__, os, re, subprocess, json, typing, seclog, incidents
# Output formats / side effects:
#   - JSON files
#   - YAML files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""task_runner.py (v0.11.8)

Executes a claimed TaskQueue task.

This is intentionally conservative:
- No network.
- Prefer modules that already exist as deterministic spine tools.
- Capture limited stdout/stderr for diagnostics.
"""


import os
import re
import subprocess
import json
from typing import Any, Dict

from seclog import append as sel_append

try:
    import incidents
except Exception:  # pragma: no cover
    incidents = None  # type: ignore

try:
    import epoch
except Exception:  # pragma: no cover
    epoch = None  # type: ignore

try:
    import taskqueue
except Exception:  # pragma: no cover
    taskqueue = None  # type: ignore

try:
    import invites
except Exception:  # pragma: no cover
    invites = None  # type: ignore

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

try:
    from fixture_autogen import fixture_from_incident, canonical_fixture_digest
except Exception:  # pragma: no cover
    fixture_from_incident = None  # type: ignore
    canonical_fixture_digest = None  # type: ignore

try:
    import fixture_bundle
except Exception:  # pragma: no cover
    fixture_bundle = None  # type: ignore


SAFE_MODULE_RE = re.compile(r"^[a-zA-Z0-9_]+$")


# === NoemaForge Autodoc Function Header ===
# Function: _script_for_module(module: str)
# Purpose: Implement the routine ' script for module'.
# Inputs:
#   - module: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - strip, ValueError, match
# Returns / emits: str
# Key locals:
#   - m
# === End NoemaForge Autodoc Function Header ===
def _script_for_module(module: str) -> str:
    m = (module or "").strip()
    if not m or not SAFE_MODULE_RE.match(m):
        raise ValueError("unsafe_module")
    return f"/opt/noemaforge/src/{m}.py"


# === NoemaForge Autodoc Function Header ===
# Function: run_task(task: Dict[str, Any])
# Purpose: Run a task.
# Inputs:
#   - task: Dict[str, Any]
# Called by:
#   - src/maintenance.py
# Calls:
#   - str, strip, upper, get, isinstance, startswith, PermissionError, _script_for_module, run, update, sel_append, bool
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses or workers
#   - appends to logs or files
# Key locals:
#   - action, cfg, check_id, comment, digest, domain, e_dir, emitted, err, fid, fx, fxm
# === End NoemaForge Autodoc Function Header ===
def run_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """Run a task.

    Returns a structured dict (ok, rc, stdout_tail, stderr_tail).
    """

    tid = str(task.get("task_id") or "")
    kind = str(task.get("kind") or "").strip()
    domain = str(task.get("domain") or "").strip().upper()

    res: Dict[str, Any] = {"ok": False, "rc": 1, "task_id": tid, "kind": kind, "domain": domain}

    payload = task.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    # Defense-in-depth: certain tasks are invite-gated (must not run automatically).
    req_inv = str(payload.get("requires_invite") or "").strip()
    if not req_inv and kind.startswith("surgeon.live."):
        req_inv = "surgeon_live"
    if req_inv:
        if invites is None or not bool(invites.is_active(req_inv)):
            raise PermissionError(f"invite_required:{req_inv}")

    try:
        if kind == "module":
            mod = str(task.get("module") or "").strip()
            script = _script_for_module(mod)
            p = subprocess.run(["/usr/bin/python3", script], capture_output=True, text=True)
            out = (p.stdout or "")
            err = (p.stderr or "")
            res.update(
                {
                    "ok": p.returncode == 0,
                    "rc": int(p.returncode),
                    "stdout_tail": out[-2000:],
                    "stderr_tail": err[-2000:],
                    "module": mod,
                }
            )
        elif kind == "core.teamworker_tick":
            # Advance project batons by one step.
            p = subprocess.run(
                ["/usr/bin/python3", "/opt/noemaforge/src/noemaforge_core.py", "teamworker-tick", "--max-steps", "1"],
                capture_output=True,
                text=True,
            )
            res.update(
                {
                    "ok": p.returncode == 0,
                    "rc": int(p.returncode),
                    "stdout_tail": (p.stdout or "")[-2000:],
                    "stderr_tail": (p.stderr or "")[-2000:],
                }
            )
        elif kind == "core.run_recurring":
            # Execute a deterministic recurring pipeline.
            payload = task.get("payload") or {}
            task_id = str(payload.get("task_id") or "").strip()
            if not task_id:
                raise ValueError("missing_payload.task_id")
            p = subprocess.run(
                ["/usr/bin/python3", "/opt/noemaforge/src/noemaforge_core.py", "run-recurring", task_id],
                capture_output=True,
                text=True,
            )
            res.update(
                {
                    "ok": p.returncode == 0,
                    "rc": int(p.returncode),
                    "stdout_tail": (p.stdout or "")[-2000:],
                    "stderr_tail": (p.stderr or "")[-2000:],
                    "recurring_task_id": task_id,
                }
            )
        elif kind == "core.run_audit":
            # Daily compliance audit (verification task).
            payload = task.get("payload") or {}
            check_id = str(payload.get("check_id") or "").strip()
            if not check_id:
                raise ValueError("missing_payload.check_id")
            p = subprocess.run(
                ["/usr/bin/python3", "/opt/noemaforge/src/noemaforge_core.py", "run-audit", check_id],
                capture_output=True,
                text=True,
            )
            res.update(
                {
                    "ok": p.returncode == 0,
                    "rc": int(p.returncode),
                    "stdout_tail": (p.stdout or "")[-2000:],
                    "stderr_tail": (p.stderr or "")[-2000:],
                    "audit_check_id": check_id,
                }
            )
        elif kind == "core.incident_update":
            # Update an incident lifecycle state (ack/close/escalate).
            if not incidents:
                raise RuntimeError("incidents_module_missing")
            payload = task.get("payload") or {}
            iid = str(payload.get("incident_id") or "").strip()
            action = str(payload.get("action") or "").strip().lower()
            comment = str(payload.get("comment") or "").strip()
            if not iid:
                raise ValueError("missing_payload.incident_id")
            if action not in ("ack", "close", "escalate"):
                raise ValueError("invalid_payload.action")
            upd = incidents.update_incident(incident_id=iid, action=action, actor={"subsystem": "task_runner"}, comment=comment)
            res.update({"ok": True, "rc": 0, "stdout_tail": json.dumps(upd, ensure_ascii=False)[:2000], "stderr_tail": "", "incident_id": iid, "incident_action": action})
        elif kind == "security.autogen_fixture":
            # Generate a staged SecurityFixture from a repeated Incident.
            if fixture_bundle is None or fixture_from_incident is None or canonical_fixture_digest is None:
                raise RuntimeError("fixture_modules_missing")
            payload = task.get("payload") or {}
            incident_path = str(payload.get("incident_path") or "").strip()
            incident_id = str(payload.get("incident_id") or "").strip().lower()

            obj: Dict[str, Any] = {}
            if incident_path and os.path.exists(incident_path):
                obj = json.load(open(incident_path, "r", encoding="utf-8"))
                incident_id = str(obj.get("incident_id") or incident_id).strip().lower()
            elif incidents and incident_id:
                obj = incidents.get_incident(incident_id)
            else:
                raise ValueError("missing_incident_reference")

            # Resolve epoch dir for contract reads.
            e_dir = "/opt/noemaforge/configs"
            try:
                if epoch is not None:
                    e_dir = epoch.current_epoch_dir() or e_dir
            except Exception:
                pass

            cfg = fixture_bundle.load_fixture_autogen_cfg(epoch_dir=e_dir)
            if not bool(cfg.get("enabled", True)):
                res.update({"ok": True, "rc": 0, "note": "fixtures_autogen_disabled"})
            else:
                # Load patterns from epoch (optional).
                patt: Dict[str, Any] = {}
                try:
                    ppath = os.path.join(e_dir, "patterns.yaml")
                    if yaml is not None and os.path.exists(ppath):
                        patt = yaml.safe_load(open(ppath, "r", encoding="utf-8")) or {}
                except Exception:
                    patt = {}

                qsample_dir = ""
                try:
                    pol = {}
                    ipath = os.path.join(e_dir, "incident-policy.yaml")
                    if yaml is not None and os.path.exists(ipath):
                        pol = yaml.safe_load(open(ipath, "r", encoding="utf-8")) or {}
                    fx = pol.get("fixtures") if isinstance(pol, dict) else None
                    paths = fx.get("paths") if isinstance(fx, dict) and isinstance(fx.get("paths"), dict) else {}
                    qsample_dir = str(paths.get("quarantine_sample_store_dir") or "").strip()
                except Exception:
                    qsample_dir = ""

                fx = fixture_from_incident(obj, quarantine_sample_store_dir=qsample_dir, pattern_catalog=patt)
                if not fx:
                    res.update({"ok": True, "rc": 0, "note": "fixture_not_generated"})
                else:
                    fid = str(fx.get("id") or "").strip()
                    digest = canonical_fixture_digest(fx)

                    # Skip if already emitted (state remembers digests).
                    st = {}
                    try:
                        st = json.load(open(str(cfg.get("state_path") or ""), "r", encoding="utf-8"))
                    except Exception:
                        st = {}
                    emitted = st.get("emitted") if isinstance(st.get("emitted"), dict) else {}
                    if fid and str(emitted.get(fid) or "") == str(digest):
                        res.update({"ok": True, "rc": 0, "note": "already_emitted", "fixture_id": fid})
                    else:
                        stg = fixture_bundle.stage_fixture(
                            fixture=fx,
                            digest=digest,
                            cfg=cfg,
                            source_incident_id=incident_id,
                            source_incident_path=incident_path,
                        )
                        # Link staging to Incident (best-effort).
                        try:
                            if incidents and incident_id and bool(stg.get("ok")):
                                incidents.attach_artifact(
                                    incident_id=incident_id,
                                    artifact={"kind": "staged_security_fixture", "fixture_id": fid, "digest": digest, "path": str(stg.get("path") or "")},
                                    actor={"subsystem": "task_runner", "role": "scary"},
                                    comment="autogen stage fixture",
                                )
                        except Exception:
                            pass

                        # Enqueue a flush (deduped) so staged fixtures become a draft request.
                        try:
                            if taskqueue is not None:
                                taskqueue.enqueue_task(
                                    domain="SECURITY",
                                    kind="security.flush_fixture_bundle",
                                    priority_class="background",
                                    title="Flush staged security fixture bundle",
                                    description="Bundle staged fixtures into a draft PreStartChangeRequest.",
                                    payload={},
                                    group_key="security.flush_fixture_bundle",
                                )
                        except Exception:
                            pass

                        res.update({"ok": bool(stg.get("ok")), "rc": 0 if bool(stg.get("ok")) else 2, "fixture_id": fid, "staged_path": stg.get("path"), "digest": digest})
        elif kind == "security.flush_fixture_bundle":
            if fixture_bundle is None:
                raise RuntimeError("fixture_bundle_missing")
            # Resolve epoch dir.
            e_dir = "/opt/noemaforge/configs"
            try:
                if epoch is not None:
                    e_dir = epoch.current_epoch_dir() or e_dir
            except Exception:
                pass
            cfg = fixture_bundle.load_fixture_autogen_cfg(epoch_dir=e_dir)
            meta = fixture_bundle.flush_staged_bundle(epoch_dir=e_dir, cfg=cfg, actor={"actor_type": "scary", "actor_id": "task_runner"})
            # Link request to source incidents (best-effort).
            try:
                if incidents and bool(meta.get("emitted")):
                    rid = str(meta.get("request_id") or "")
                    for fxm in (meta.get("fixtures") or []) if isinstance(meta.get("fixtures"), list) else []:
                        if not isinstance(fxm, dict):
                            continue
                        iid = str(fxm.get("source_incident_id") or "").strip().lower()
                        if not iid:
                            continue
                        incidents.attach_artifact(
                            incident_id=iid,
                            artifact={"kind": "security_fixture_request", "request_id": rid, "fixture_id": str(fxm.get("fixture_id") or ""), "queue_path": str(meta.get("queue_path") or "")},
                            actor={"subsystem": "task_runner", "role": "scary"},
                            comment="autogen fixture bundle emitted",
                        )
            except Exception:
                pass
            res.update({"ok": bool(meta.get("ok")), "rc": 0 if bool(meta.get("ok")) else 2, "stdout_tail": json.dumps(meta, ensure_ascii=False)[:2000], "stderr_tail": ""})
        else:
            res.update({"ok": True, "rc": 0, "stdout_tail": "", "stderr_tail": "", "note": "noop"})

    except Exception as e:
        res.update({"ok": False, "rc": 2, "error": repr(e)})

    # SEL
    try:
        if sel_append:
            sel_append(
                {
                    "severity": "info" if res.get("ok") else "warning",
                    "type": "taskqueue_task_run",
                    "task": {"task_id": tid, "domain": domain, "kind": kind, "module": res.get("module")},
                    "result": {"ok": bool(res.get("ok")), "rc": int(res.get("rc")), "error": res.get("error")},
                }
            )
    except Exception:
        pass

    return res
