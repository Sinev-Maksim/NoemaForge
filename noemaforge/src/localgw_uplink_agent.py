#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/localgw_uplink_agent.py
Zone: release/package
Version: 0.31.13.alpha-patched1
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
# File: src/localgw_uplink_agent.py
# Purpose: Provide the module 'localgw_uplink_agent'.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - run_octoprint_upload
#   - main
# Inputs:
#   - --kind
#   - --base-url
#   - --api-key-file
#   - --file
#   - --dest
#   - --select
#   - --print
#   - --out
#   - Common path inputs: application/octet-stream, application/json
#   - Imports: __future__, argparse, hashlib, json, os, sys, urllib.request, urllib.error
# Output formats / side effects:
#   - JSON files
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""localgw_uplink_agent.py (v0.16.0)

One-shot "uplink glove" agent for LocalGateway.

This is **not** an LLM. It is a deterministic helper used to perform
high-risk network actions (uploads) inside a disposable sandbox.

Currently implemented:
- OctoPrint GCODE upload (multipart POST /api/files/local)

Security principles
-------------------
- Reads API key from a file path (mounted read-only into the sandbox).
- Never prints the API key.
- Writes a small JSON report to --out (mounted RW).
- Meant to run in podman slirp or microVM when available.

CLI
---
  python3 localgw_uplink_agent.py \
    --kind octoprint.upload_gcode \
    --base-url http://192.168.1.50 \
    --api-key-file /var/lib/noemaforge/.sys/localgw_secrets/octo1.txt \
    --file /workspace/job.gcode \
    --dest job.gcode \
    --out /tmp/uplink_result.json
"""


import argparse
import hashlib
import json
import os
import sys
import urllib.request
import urllib.error
from typing import Any, Dict, Tuple


# === NoemaForge Autodoc Function Header ===
# Function: _sha256_file(path: str)
# Purpose: Implement the routine ' sha256 file'.
# Inputs:
#   - path: str
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/casebase.py
#   - src/doctor.py
#   - src/glove_agent.py
#   - src/model_registry.py
#   - src/pipelines/finance_budget.py
#   - src/prestart.py
# Calls:
#   - sha256, hexdigest, open, iter, update, read
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - chunk, f, h
# === End NoemaForge Autodoc Function Header ===
def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _read_first_line(path: str)
# Purpose: Implement the routine ' read first line'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, strip, readline
# Returns / emits: str
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _read_first_line(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return (f.readline() or "").strip()
    except Exception:
        return ""


# === NoemaForge Autodoc Function Header ===
# Function: _multipart_form(fields: Dict[str, str], file_field: str, file_path: str, file_name: str)
# Purpose: Implement the routine ' multipart form'.
# Inputs:
#   - fields: Dict[str, str]
#   - file_field: str
#   - file_path: str
#   - file_name: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - bytearray, items, add, encode, open, read, bytes, hexdigest, str, sha256, urandom
# Returns / emits: Tuple[bytes, str]
# Side effects:
#   - reads or writes files
# Key locals:
#   - body, boundary, content_type, f, mime
# === End NoemaForge Autodoc Function Header ===
def _multipart_form(fields: Dict[str, str], file_field: str, file_path: str, file_name: str) -> Tuple[bytes, str]:
    boundary = "----noemaforge-uplink-boundary-" + hashlib.sha256(os.urandom(16)).hexdigest()[:16]

    # === NoemaForge Autodoc Function Header ===
    # Function: add(s: str)
    # Purpose: Implement the routine 'add'.
    # Inputs:
    #   - s: str
    # Called by:
    #   - src/bootdoctor.py
    #   - src/brainctl.py
    #   - src/noemaforge_core.py
    #   - src/flow_catalog.py
    #   - src/glove_agent.py
    #   - src/incidents.py
    #   - src/installer_plan.py
    #   - src/localgateway.py
    # Calls:
    #   - encode
    # Returns / emits: bytes
    # === End NoemaForge Autodoc Function Header ===
    def add(s: str) -> bytes:
        return s.encode("utf-8")

    body = bytearray()
    for k, v in (fields or {}).items():
        body += add(f"--{boundary}\r\n")
        body += add(f'Content-Disposition: form-data; name="{k}"\r\n\r\n')
        body += add(str(v))
        body += add("\r\n")

    # file part
    mime = "application/octet-stream"
    body += add(f"--{boundary}\r\n")
    body += add(f'Content-Disposition: form-data; name="{file_field}"; filename="{file_name}"\r\n')
    body += add(f"Content-Type: {mime}\r\n\r\n")
    with open(file_path, "rb") as f:
        body += f.read()
    body += add("\r\n")

    body += add(f"--{boundary}--\r\n")
    content_type = f"multipart/form-data; boundary={boundary}"
    return bytes(body), content_type


# === NoemaForge Autodoc Function Header ===
# Function: _http_json(method: str, url: str, headers: Dict[str, str], body: bytes)
# Purpose: Implement the routine ' http json'.
# Inputs:
#   - method: str
#   - url: str
#   - headers: Dict[str, str]
#   - body: bytes
# Called by:
#   - src/localgw_connectors/octoprint.py
# Calls:
#   - Request, items, add_header, upper, urlopen, read, loads, isinstance, decode, str, int, repr
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Side effects:
#   - reads or writes files
# Key locals:
#   - msg, obj, raw, req, resp
# === End NoemaForge Autodoc Function Header ===
def _http_json(method: str, url: str, headers: Dict[str, str], body: bytes) -> Tuple[bool, Dict[str, Any], str]:
    req = urllib.request.Request(url, data=body, method=method.upper())
    for k, v in (headers or {}).items():
        req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read() or b"{}"
            try:
                obj = json.loads(raw.decode("utf-8", errors="replace"))
            except Exception:
                obj = {"raw": raw[:4000].decode("utf-8", errors="replace")}
            if not isinstance(obj, dict):
                obj = {"data": obj}
            return True, obj, "ok"
    except urllib.error.HTTPError as e:
        try:
            raw = e.read() or b"{}"
            msg = raw.decode("utf-8", errors="replace")[:4000]
        except Exception:
            msg = str(e)
        return False, {"ok": False, "http": int(getattr(e, "code", 0) or 0), "error": msg}, "http_error"
    except Exception as e:
        return False, {"ok": False, "error": repr(e)}, "fetch_failed"


# === NoemaForge Autodoc Function Header ===
# Function: run_octoprint_upload(base_url: str, api_key: str, file_path: str, dest_name: str, select: bool, do_print: bool)
# Purpose: Implement the routine 'run octoprint upload'.
# Inputs:
#   - base_url: str
#   - api_key: str
#   - file_path: str
#   - dest_name: str
#   - select: bool
#   - do_print: bool
# Called by:
#   - src/localgw_connectors/octoprint.py
# Calls:
#   - _multipart_form, _http_json, rstrip
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Key locals:
#   - fields, headers, url
# === End NoemaForge Autodoc Function Header ===
def run_octoprint_upload(*, base_url: str, api_key: str, file_path: str, dest_name: str, select: bool, do_print: bool) -> Tuple[bool, Dict[str, Any], str]:
    url = base_url.rstrip("/") + "/api/files/local"

    fields = {
        "select": "true" if select else "false",
        "print": "true" if do_print else "false",
    }

    body, ctype = _multipart_form(fields, "file", file_path, dest_name)
    headers = {
        "X-Api-Key": api_key,
        "Content-Type": ctype,
        "Accept": "application/json",
    }

    return _http_json("POST", url, headers, body)


# === NoemaForge Autodoc Function Header ===
# Function: main()
# Purpose: Implement the routine 'main'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - bootstrap/microvm/noemaforge-microvm-run.py
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/noemaforge_core.py
#   - src/brainui.py
#   - src/canary_runner.py
#   - src/doctor.py
#   - src/dream_cycle.py
# Calls:
#   - ArgumentParser, add_argument, parse_args, strip, rstrip, _read_first_line, int, basename, exists, dump, getsize, _sha256_file
# Returns / emits: int
# Side effects:
#   - serializes structured data
# Key locals:
#   - ap, api_key, api_key_file, args, base_url, dest, f, file_path, kind, report, size
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--api-key-file", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--dest", default="")
    ap.add_argument("--select", action="store_true")
    ap.add_argument("--print", dest="do_print", action="store_true")
    ap.add_argument("--out", required=True)

    args = ap.parse_args()

    kind = str(args.kind or "").strip()
    base_url = str(args.base_url or "").strip().rstrip("/")
    api_key_file = str(args.api_key_file or "").strip()
    file_path = str(args.file or "").strip()

    dest = str(args.dest or "").strip()
    if not dest:
        dest = os.path.basename(file_path)

    report: Dict[str, Any] = {
        "ok": False,
        "kind": kind,
        "base_url": base_url,
        "file": os.path.basename(file_path),
        "dest": dest,
    }

    if not os.path.exists(file_path):
        report["reason"] = "file_not_found"
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return 2

    api_key = _read_first_line(api_key_file)
    if not api_key:
        report["reason"] = "api_key_missing"
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return 3

    try:
        size = os.path.getsize(file_path)
    except Exception:
        size = 0

    report["file_size"] = int(size)
    try:
        report["file_sha256"] = _sha256_file(file_path)
    except Exception:
        report["file_sha256"] = ""

    if kind == "octoprint.upload_gcode":
        ok, res, rr = run_octoprint_upload(
            base_url=base_url,
            api_key=api_key,
            file_path=file_path,
            dest_name=dest,
            select=bool(args.select),
            do_print=bool(args.do_print),
        )
        report["ok"] = bool(ok)
        report["reason"] = rr
        report["response"] = res
    else:
        report["reason"] = "unknown_kind"

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return 0 if report.get("ok") else 4


if __name__ == "__main__":
    sys.exit(main())
