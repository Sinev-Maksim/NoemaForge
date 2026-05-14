#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/netguard.py
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
"""
from __future__ import annotations


# === NoemaForge Autodoc File Header ===
# File: src/netguard.py
# Purpose: Provide the module 'netguard'.
# Invoked by / imported from:
#   - src/sandbox.py
# Public API / entry functions:
#   - nft_available
#   - shutil_which
#   - egress_guard
# Inputs:
#   - Environment: PATH
#   - Imports: __future__, contextlib, ipaddress, os, subprocess, tempfile, uuid, typing
# Output formats / side effects:
#   - Returns Python values and/or performs in-memory orchestration.
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""netguard.py (v0.17.0)

Best-effort outbound network *egress guard* using nftables.

Why?
-----
Some gloves (e.g., LocalGateway uplink agents) must perform a very small,
well-defined network action (upload a file to a printer). We want a hard
boundary so even if the glove code is tricked into attempting an unexpected
connection, the kernel blocks it.

We implement this as an nftables table that hooks the OUTPUT chain and applies
*only* to a dedicated uid (meta skuid). That means we don't risk blocking the
rest of the host.

This is not a replacement for true microVM isolation. It's a pragmatic,
offline-first spine control that works when:
  - nft is available
  - we can run the glove process as a dedicated uid
"""


import contextlib
import ipaddress
import os
import subprocess
import tempfile
import uuid
from typing import Dict, Iterable, List, Optional, Tuple


# === NoemaForge Autodoc Function Header ===
# Function: nft_available()
# Purpose: Implement the routine 'nft available'.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - bool, shutil_which
# Returns / emits: bool
# === End NoemaForge Autodoc Function Header ===
def nft_available() -> bool:
    try:
        return bool(shutil_which("nft"))
    except Exception:
        return False


# === NoemaForge Autodoc Function Header ===
# Function: shutil_which(cmd: str)
# Purpose: Implement the routine 'shutil which'.
# Inputs:
#   - cmd: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - split, join, isfile, access, get
# Returns / emits: Optional[str]
# Key locals:
#   - cand, p
# === End NoemaForge Autodoc Function Header ===
def shutil_which(cmd: str) -> Optional[str]:
    # local tiny which to avoid importing shutil in hot paths.
    for p in (os.environ.get("PATH") or "").split(":"):
        cand = os.path.join(p, cmd)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


# === NoemaForge Autodoc Function Header ===
# Function: _normalize_targets(targets: Iterable[Dict[str, object]])
# Purpose: Implement the routine ' normalize targets'.
# Inputs:
#   - targets: Iterable[Dict[str, object]]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - set, strip, int, append, add, isinstance, ip_address, lower, str, get
# Returns / emits: List[Tuple[str, int]]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - ip, k, out, port, proto, seen, t, uniq
# === End NoemaForge Autodoc Function Header ===
def _normalize_targets(targets: Iterable[Dict[str, object]]) -> List[Tuple[str, int]]:
    out: List[Tuple[str, int]] = []
    for t in targets:
        if not isinstance(t, dict):
            continue
        proto = str(t.get("proto") or "tcp").lower().strip()
        if proto != "tcp":
            continue
        ip = str(t.get("ip") or "").strip()
        port = int(t.get("port") or 0)
        if not ip or port <= 0 or port > 65535:
            continue
        try:
            ipaddress.ip_address(ip)
        except Exception:
            continue
        out.append((ip, port))
    # dedupe
    uniq: List[Tuple[str, int]] = []
    seen = set()
    for ip, port in out:
        k = f"{ip}:{port}"
        if k in seen:
            continue
        seen.add(k)
        uniq.append((ip, port))
    return uniq


# === NoemaForge Autodoc Function Header ===
# Function: _build_nft_script(table: str, uid: int, targets: List[Tuple[str, int]], allow_loopback: bool = False)
# Purpose: Implement the routine ' build nft script'.
# Inputs:
#   - table: str
#   - uid: int
#   - targets: List[Tuple[str, int]]
#   - allow_loopback: bool = False
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - append, join, int
# Returns / emits: str
# Side effects:
#   - appends to logs or files
# Key locals:
#   - lines
# === End NoemaForge Autodoc Function Header ===
def _build_nft_script(*, table: str, uid: int, targets: List[Tuple[str, int]], allow_loopback: bool = False) -> str:
    # NOTE: we keep policy accept and only reject traffic for the guarded uid.
    lines: List[str] = []
    lines.append(f"table inet {table} {{")
    lines.append("  chain output {")
    lines.append("    type filter hook output priority 0; policy accept;")
    # allow established/related for that uid
    lines.append(f"    meta skuid {int(uid)} ct state established,related accept")
    if allow_loopback:
        lines.append(f"    meta skuid {int(uid)} ip daddr 127.0.0.1 accept")
        lines.append(f"    meta skuid {int(uid)} ip6 daddr ::1 accept")
    for ip, port in targets:
        # ipv4 vs ipv6
        if ":" in ip:
            lines.append(f"    meta skuid {int(uid)} ip6 daddr {ip} tcp dport {int(port)} accept")
        else:
            lines.append(f"    meta skuid {int(uid)} ip daddr {ip} tcp dport {int(port)} accept")
    # hard stop for everything else from that uid
    lines.append(f"    meta skuid {int(uid)} reject with icmpx type admin-prohibited")
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


# === NoemaForge Autodoc Function Header ===
# Function: egress_guard(uid: int, targets: Iterable[Dict[str, object]], require_root: bool = True, allow_loopback: bool = False, table_prefix: str = 'noemaforge_ng')
# Purpose: Install a temporary nftables egress ACL for a given uid.
# Inputs:
#   - uid: int
#   - targets: Iterable[Dict[str, object]]
#   - require_root: bool = True
#   - allow_loopback: bool = False
#   - table_prefix: str = 'noemaforge_ng'
# Called by:
#   - src/sandbox.py
# Calls:
#   - shutil_which, _normalize_targets, _build_nft_script, PermissionError, FileNotFoundError, ValueError, NamedTemporaryFile, write, run, geteuid, int, bool
# Returns / emits: Iterable[Dict[str, object]]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - applied, nft, norm, p, script, script_path, table, tf
# === End NoemaForge Autodoc Function Header ===
@contextlib.contextmanager
def egress_guard(
    *,
    uid: int,
    targets: Iterable[Dict[str, object]],
    require_root: bool = True,
    allow_loopback: bool = False,
    table_prefix: str = "noemaforge_ng",
) -> Iterable[Dict[str, object]]:
    """Install a temporary nftables egress ACL for a given uid.

    Args:
      uid: the uid the rule applies to (meta skuid)
      targets: iterable of {ip, port, proto:'tcp'}
      require_root: if True, raise if not running as root
      allow_loopback: allow uid traffic to localhost

    Yields:
      meta dict with table name and normalized targets.
    """

    if require_root and os.geteuid() != 0:
        raise PermissionError("netguard_requires_root")

    nft = shutil_which("nft")
    if not nft:
        raise FileNotFoundError("nft_not_found")

    norm = _normalize_targets(targets)
    if not norm:
        raise ValueError("netguard_no_targets")

    table = f"{table_prefix}_{uuid.uuid4().hex[:10]}"
    script = _build_nft_script(table=table, uid=int(uid), targets=norm, allow_loopback=bool(allow_loopback))

    # Apply
    with tempfile.NamedTemporaryFile("w", delete=False, prefix="noemaforge-netguard-", suffix=".nft", encoding="utf-8") as tf:
        tf.write(script)
        script_path = tf.name

    applied = False
    try:
        p = subprocess.run([nft, "-f", script_path], capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"nft_apply_failed:{(p.stderr or p.stdout or '').strip()[:200]}")
        applied = True
        yield {"ok": True, "table": table, "uid": int(uid), "targets": [{"ip": ip, "port": port, "proto": "tcp"} for ip, port in norm]}
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass
        if applied:
            try:
                # Best-effort cleanup.
                subprocess.run([nft, "delete", "table", "inet", table], capture_output=True, text=True)
            except Exception:
                pass
