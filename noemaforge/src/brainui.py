#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/brainui.py
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
# File: src/brainui.py
# Purpose: Expose a local UI for operator-visible snapshots, incidents, queues, and runtime state.
# Invoked by / imported from:
#   - No inbound Python import detected; treat as library leaf or direct entrypoint.
# Public API / entry functions:
#   - cmd_serve
#   - cmd_snapshot
#   - main
# Inputs:
#   - --state-root
#   - --configs-dir
#   - --host
#   - --port
#   - --out
#   - Common path inputs: image/png, application/octet-stream, noemaforge.ui.snapshot/v1, NoemaForgeUI/0.25.1
#   - Imports: __future__, argparse, json, os, http.server, typing, urllib.parse, ui_snapshot
# Output formats / side effects:
#   - JSON files
#   - HTTP responses
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""brainui.py (v0.25.1)

Local, offline-first dashboard for NoemaForge orchestration.

Goal
----
Provide an "orchestrator view" similar to agent frameworks:
  - what's running now
  - what's next
  - recent traces/events

But with NoemaForge constraints:
  - no external network required
  - safe by default (no prompt leakage)
  - cross-platform (Windows lab usage)

Usage
-----
  python src/brainui.py serve --state-root /var/lib/noemaforge

Windows (lab / offline directory):
  python src/brainui.py serve --state-root C:/Users/<you>/.../noemaforge-lab/data

Then open: http://127.0.0.1:8787
"""


import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import urlparse


try:
    from ui_snapshot import build_snapshot
except Exception as e:  # pragma: no cover
    build_snapshot = None  # type: ignore
    _IMPORT_ERR = str(e)


# === NoemaForge Autodoc Function Header ===
# Function: _assets_dir()
# Purpose: Locate dashboard assets.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - dirname, abspath, isdir, join
# Returns / emits: str
# Key locals:
#   - cand, here
# === End NoemaForge Autodoc Function Header ===
def _assets_dir() -> str:
    """Locate dashboard assets."""
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.abspath(os.path.join(here, "..", "templates", "ui-dashboard"))
    if os.path.isdir(cand):
        return cand
    return os.path.join(here, "ui-dashboard")


# === NoemaForge Autodoc Function Header ===
# Function: _read_file(path: str)
# Purpose: Implement the routine ' read file'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - open, read
# Returns / emits: bytes
# Side effects:
#   - reads or writes files
# Key locals:
#   - f
# === End NoemaForge Autodoc Function Header ===
def _read_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


# === NoemaForge Autodoc Function Header ===
# Function: _guess_type(path: str)
# Purpose: Implement the routine ' guess type'.
# Inputs:
#   - path: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - lower, endswith
# Returns / emits: str
# Key locals:
#   - p
# === End NoemaForge Autodoc Function Header ===
def _guess_type(path: str) -> str:
    p = path.lower()
    if p.endswith(".html"):
        return "text/html; charset=utf-8"
    if p.endswith(".js"):
        return "text/javascript; charset=utf-8"
    if p.endswith(".css"):
        return "text/css; charset=utf-8"
    if p.endswith(".svg"):
        return "image/svg+xml"
    if p.endswith(".png"):
        return "image/png"
    return "application/octet-stream"


class _ServerCtx:
    # === NoemaForge Autodoc Function Header ===
    # Function: __init__(self, state_root: str, configs_dir: str)
    # Purpose: Implement the routine '  init  '.
    # Inputs:
    #   - self
    #   - state_root: str
    #   - configs_dir: str
    # Called by:
    #   - src/model_scorecards.py
    #   - src/team_scorecards.py
    #   - src/toolproxy.py
    # Returns / emits: unspecified Python value
    # === End NoemaForge Autodoc Function Header ===
    def __init__(self, state_root: str, configs_dir: str):
        self.state_root = state_root
        self.configs_dir = configs_dir

    # === NoemaForge Autodoc Function Header ===
    # Function: snapshot(self)
    # Purpose: Implement the routine 'snapshot'.
    # Inputs:
    #   - self
    # Called by:
    #   - src/nids_lite.py
    # Calls:
    #   - build_snapshot
    # Returns / emits: Dict[str, Any]
    # === End NoemaForge Autodoc Function Header ===
    def snapshot(self) -> Dict[str, Any]:
        if build_snapshot is None:
            return {
                "schema_version": "noemaforge.ui.snapshot/v1",
                "generated_at": "",
                "error": "ui_snapshot import failed",
                "details": _IMPORT_ERR,
            }
        return build_snapshot(state_root=self.state_root, configs_dir=self.configs_dir)


# === NoemaForge Autodoc Function Header ===
# Function: _make_handler(ctx: _ServerCtx, assets_dir: str)
# Purpose: Implement the routine ' make handler'.
# Inputs:
#   - ctx: _ServerCtx
#   - assets_dir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - encode, send_response, send_header, end_headers, write, urlparse, startswith, replace, join, str, _json, isfile
# Returns / emits: value from 'Handler', None, result of ._json(), result of ._bytes()
# Side effects:
#   - sends a response or network payload
# Key locals:
#   - full, path, payload, server_version, u
# === End NoemaForge Autodoc Function Header ===
def _make_handler(ctx: _ServerCtx, assets_dir: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "NoemaForgeUI/0.25.1"

        # === NoemaForge Autodoc Function Header ===
        # Function: _json(self, obj: Dict[str, Any], code: int = 200)
        # Purpose: Implement the routine ' json'.
        # Inputs:
        #   - self
        #   - obj: Dict[str, Any]
        #   - code: int = 200
        # Called by:
        #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
        # Calls:
        #   - encode, send_response, send_header, end_headers, write, str, dumps, len
        # Returns / emits: None
        # Side effects:
        #   - serializes structured data
        #   - sends a response or network payload
        # Key locals:
        #   - payload
        # === End NoemaForge Autodoc Function Header ===
        def _json(self, obj: Dict[str, Any], code: int = 200) -> None:
            payload = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        # === NoemaForge Autodoc Function Header ===
        # Function: _bytes(self, b: bytes, ctype: str, code: int = 200)
        # Purpose: Implement the routine ' bytes'.
        # Inputs:
        #   - self
        #   - b: bytes
        #   - ctype: str
        #   - code: int = 200
        # Called by:
        #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
        # Calls:
        #   - send_response, send_header, end_headers, write, str, len
        # Returns / emits: None
        # Side effects:
        #   - sends a response or network payload
        # === End NoemaForge Autodoc Function Header ===
        def _bytes(self, b: bytes, ctype: str, code: int = 200) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        # === NoemaForge Autodoc Function Header ===
        # Function: do_GET(self)
        # Purpose: Implement the routine 'do GET'.
        # Inputs:
        #   - self
        # Called by:
        #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
        # Calls:
        #   - urlparse, startswith, replace, join, _json, isfile, _bytes, snapshot, normpath, _read_file, _guess_type, str
        # Returns / emits: result of ._json(), result of ._bytes()
        # Key locals:
        #   - full, path, u
        # === End NoemaForge Autodoc Function Header ===
        def do_GET(self):  # noqa: N802
            u = urlparse(self.path)
            path = u.path or "/"

            if path == "/api/health":
                return self._json({"ok": True})

            if path == "/api/snapshot":
                return self._json(ctx.snapshot())

            # Static
            if path == "/":
                path = "/index.html"
            if path.startswith("/"):
                path = path[1:]
            path = os.path.normpath(path).replace("\\", "/")
            if path.startswith("../") or path.startswith(".."):
                return self._json({"error": "bad path"}, code=400)

            full = os.path.join(assets_dir, path)
            if not os.path.isfile(full):
                return self._json({"error": "not found", "path": path}, code=404)

            try:
                return self._bytes(_read_file(full), _guess_type(full))
            except Exception as e:
                return self._json({"error": "read failed", "details": str(e)}, code=500)

        # === NoemaForge Autodoc Function Header ===
        # Function: log_message(self, fmt: str, *args)
        # Purpose: Implement the routine 'log message'.
        # Inputs:
        #   - self
        #   - fmt: str
        #   - *args
        # Called by:
        #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
        # Returns / emits: None
        # === End NoemaForge Autodoc Function Header ===
        def log_message(self, fmt: str, *args):  # noqa: N802
            return

    return Handler


# === NoemaForge Autodoc Function Header ===
# Function: _default_configs_dir()
# Purpose: Implement the routine ' default configs dir'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - dirname, abspath, join
# Returns / emits: str
# Key locals:
#   - here
# === End NoemaForge Autodoc Function Header ===
def _default_configs_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "configs"))


# === NoemaForge Autodoc Function Header ===
# Function: cmd_serve(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd serve'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _assets_dir, _ServerCtx, _make_handler, ThreadingHTTPServer, print, isdir, serve_forever, int, server_close
# Returns / emits: int
# Key locals:
#   - Handler, assets, ctx, httpd
# === End NoemaForge Autodoc Function Header ===
def cmd_serve(args: argparse.Namespace) -> int:
    assets = _assets_dir()
    if not os.path.isdir(assets):
        print(f"ERROR: UI assets dir not found: {assets}")
        return 2

    ctx = _ServerCtx(state_root=args.state_root, configs_dir=args.configs_dir)
    Handler = _make_handler(ctx, assets)
    httpd = ThreadingHTTPServer((args.host, int(args.port)), Handler)

    print("NoemaForge UI Dashboard")
    print(f"  state_root:  {args.state_root}")
    print(f"  configs_dir: {args.configs_dir}")
    print(f"  assets:      {assets}")
    print(f"  url:         http://{args.host}:{args.port}")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            httpd.server_close()
        except Exception:
            pass


# === NoemaForge Autodoc Function Header ===
# Function: cmd_snapshot(args: argparse.Namespace)
# Purpose: Implement the routine 'cmd snapshot'.
# Inputs:
#   - args: argparse.Namespace
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - build_snapshot, dumps, print, makedirs, dirname, open, write, abspath
# Returns / emits: int
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - f, payload, snap
# === End NoemaForge Autodoc Function Header ===
def cmd_snapshot(args: argparse.Namespace) -> int:
    if build_snapshot is None:
        print(f"ERROR: ui_snapshot import failed: {_IMPORT_ERR}")
        return 2
    snap = build_snapshot(state_root=args.state_root, configs_dir=args.configs_dir)
    payload = json.dumps(snap, ensure_ascii=False, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(args.out)
    else:
        print(payload)
    return 0


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
#   - src/canary_runner.py
#   - src/doctor.py
#   - src/dream_cycle.py
#   - src/firstboot_eval.py
# Calls:
#   - ArgumentParser, add_subparsers, add_parser, add_argument, set_defaults, parse_args, int, _default_configs_dir, fn
# Returns / emits: int
# Key locals:
#   - ap, args, s, sn, sub
# === End NoemaForge Autodoc Function Header ===
def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="Run a local dashboard server")
    s.add_argument("--state-root", required=True, help="NoemaForge state root (canonical: /var/lib/noemaforge)")
    s.add_argument("--configs-dir", default=_default_configs_dir(), help="Configs dir (default: ../configs)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", default=8787)
    s.set_defaults(fn=cmd_serve)

    sn = sub.add_parser("snapshot", help="Emit a JSON snapshot")
    sn.add_argument("--state-root", required=True)
    sn.add_argument("--configs-dir", default=_default_configs_dir())
    sn.add_argument("--out", default="")
    sn.set_defaults(fn=cmd_snapshot)

    args = ap.parse_args()
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
