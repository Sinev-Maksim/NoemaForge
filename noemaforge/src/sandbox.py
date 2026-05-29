#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/sandbox.py
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
# File: src/sandbox.py
# Purpose: Provide the module 'sandbox'.
# Invoked by / imported from:
#   - src/glove_runner.py
#   - src/localgw_uplink.py
#   - src/plugin_runner.py
#   - src/toolproxy.py
# Public API / entry functions:
#   - class Quota
#   - roots_from_allowlist_patterns
#   - quota_from_policy
#   - host_fallback_mode
#   - microvm_available
#   - run
# Inputs:
#   - Common path inputs: /var, /var/tmp, /var/log, /run, /run/noemaforge, /var/lib/noemaforge/microvm/runs
#   - Imports: __future__, os, uuid, shutil, subprocess, base64, json, tempfile
# Output formats / side effects:
#   - JSON files
#   - copied filesystem artifacts
# AutoDoc: refreshed 2026-04-09 (heuristic, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""sandbox.py (v0.14.0)

Best-effort isolation runner for ToolProxy.

Why "best-effort"?
- True microVM isolation (e.g., firecracker) depends on host setup and is not
  assumed in the seed kit.
- We provide a pluggable backend interface and support the most common
  *offline-first* hardening backends:
    - bwrap (bubblewrap): mount+namespace isolation using host binaries
    - podman: container isolation when images are available offline
    - host: fallback with RLIMIT fuses only (degraded)

This module is intentionally dependency-light.
"""


import os
import uuid
import shutil
import subprocess
import base64
import json
import tempfile
import time
import resource
import contextlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Quota:
    cpu_time_sec: int = 30
    mem_max_mib: int = 2048
    pids_max: int = 256
    file_max_mib: int = 256
    timeout_sec: int = 120


# === NoemaForge Autodoc Function Header ===
# Function: _which(cmd: str)
# Purpose: Implement the routine ' which'.
# Inputs:
#   - cmd: str
# Called by:
#   - src/lsm.py
#   - src/role_runner.py
# Calls:
#   - which
# Returns / emits: Optional[str]
# === End NoemaForge Autodoc Function Header ===
def _which(cmd: str) -> Optional[str]:
    try:
        return shutil.which(cmd)
    except Exception:
        return None


# === NoemaForge Autodoc Function Header ===
# Function: _is_glob_char(ch: str)
# Purpose: Implement the routine ' is glob char'.
# Inputs:
#   - ch: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Returns / emits: bool
# === End NoemaForge Autodoc Function Header ===
def _is_glob_char(ch: str) -> bool:
    return ch in "*?["  # fnmatch special chars


# === NoemaForge Autodoc Function Header ===
# Function: roots_from_allowlist_patterns(patterns: List[str])
# Purpose: Convert fnmatch-style allowlist patterns into mountable root prefixes.
# Inputs:
#   - patterns: List[str]
# Called by:
#   - src/plugin_runner.py
#   - src/toolproxy.py
# Calls:
#   - enumerate, rstrip, _is_glob_char, isdir, dirname, append
# Returns / emits: List[str]
# Side effects:
#   - appends to logs or files
# Key locals:
#   - idx, p, pat, root, roots
# === End NoemaForge Autodoc Function Header ===
def roots_from_allowlist_patterns(patterns: List[str]) -> List[str]:
    """Convert fnmatch-style allowlist patterns into mountable root prefixes.

    Examples:
      /workspace/inbox/photos/** -> /workspace/inbox/photos
      /var/lib/noemaforge/projects/*  -> /var/lib/noemaforge/projects

    This is conservative: it strips from the first glob char and then trims
    to the nearest directory.
    """
    roots: List[str] = []
    for pat in patterns:
        if not pat:
            continue
        p = pat
        # Find first glob char
        idx = None
        for i, ch in enumerate(p):
            if _is_glob_char(ch):
                idx = i
                break
        if idx is None:
            root = p
        else:
            root = p[:idx]
        root = root.rstrip("/")
        if not root:
            continue
        # Trim to directory boundary
        if not os.path.isdir(root):
            root = os.path.dirname(root)
        root = root.rstrip("/")
        if root and root not in roots:
            roots.append(root)
    return roots


# === NoemaForge Autodoc Function Header ===
# Function: quota_from_policy(policy: Dict[str, Any], profile_name: str)
# Purpose: Implement the routine 'quota from policy'.
# Inputs:
#   - policy: Dict[str, Any]
#   - profile_name: str
# Called by:
#   - src/localgw_uplink.py
#   - src/plugin_runner.py
#   - src/toolproxy.py
# Calls:
#   - Quota, get, int
# Returns / emits: Quota
# Key locals:
#   - p, profs
# === End NoemaForge Autodoc Function Header ===
def quota_from_policy(policy: Dict[str, Any], profile_name: str) -> Quota:
    profs = (policy.get("quota_profiles") or {})
    p = (profs.get(profile_name) or {})
    return Quota(
        cpu_time_sec=int(p.get("cpu_time_sec") or 30),
        mem_max_mib=int(p.get("mem_max_mib") or 2048),
        pids_max=int(p.get("pids_max") or 256),
        file_max_mib=int(p.get("file_max_mib") or 256),
        timeout_sec=int(p.get("timeout_sec") or 120),
    )


# === NoemaForge Autodoc Function Header ===
# Function: host_fallback_mode(policy: Dict[str, Any])
# Purpose: Return host fallback mode: allow | deny | quarantine.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - get, isinstance, strip, lower, bool, str
# Returns / emits: str
# Key locals:
#   - back, hf, mode
# === End NoemaForge Autodoc Function Header ===
def host_fallback_mode(policy: Dict[str, Any]) -> str:
    """Return host fallback mode: allow | deny | quarantine.

    Backward compatibility:
      - backends.host_fallback_allowed (bool) -> allow/deny
      - missing config defaults to quarantine (safer)
    """
    back = (policy.get("backends") or {}) if isinstance(policy, dict) else {}
    hf = back.get("host_fallback")
    if isinstance(hf, dict):
        mode = str(hf.get("mode") or "").lower().strip()
        if mode in ("allow", "deny", "quarantine"):
            return mode
    if "host_fallback_allowed" in back:
        try:
            return "allow" if bool(back.get("host_fallback_allowed")) else "deny"
        except Exception:
            return "deny"
    return "quarantine"


# Backward-compatible alias (older internal name)
_quota_from_policy = quota_from_policy


# === NoemaForge Autodoc Function Header ===
# Function: _apply_rlimits(quota: Quota)
# Purpose: Implement the routine ' apply rlimits'.
# Inputs:
#   - quota: Quota
# Called by:
#   - src/canary_runner.py
# Calls:
#   - setrlimit, int
# Returns / emits: None
# Key locals:
#   - asb, fsz
# === End NoemaForge Autodoc Function Header ===
def _apply_rlimits(quota: Quota) -> None:
    # CPU time
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (int(quota.cpu_time_sec), int(quota.cpu_time_sec)))
    except Exception:
        pass
    # Max file size
    try:
        fsz = int(quota.file_max_mib) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsz, fsz))
    except Exception:
        pass
    # Address space
    try:
        asb = int(quota.mem_max_mib) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (asb, asb))
    except Exception:
        pass
    # Process count
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (int(quota.pids_max), int(quota.pids_max)))
    except Exception:
        pass


# === NoemaForge Autodoc Function Header ===
# Function: _make_minimal_etc(tmpdir: str)
# Purpose: Create a minimal /etc to avoid leaking host secrets into bwrap.
# Inputs:
#   - tmpdir: str
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - join, makedirs, write, exists, open, copy2
# Returns / emits: str
# Side effects:
#   - reads or writes files
#   - creates directories
#   - copies filesystem artifacts
# Key locals:
#   - etc_dir, f, src
# === End NoemaForge Autodoc Function Header ===
def _make_minimal_etc(tmpdir: str) -> str:
    """Create a minimal /etc to avoid leaking host secrets into bwrap."""
    etc_dir = os.path.join(tmpdir, "etc")
    os.makedirs(etc_dir, exist_ok=True)

    # === NoemaForge Autodoc Function Header ===
    # Function: write(name: str, content: str)
    # Purpose: Implement the routine 'write'.
    # Inputs:
    #   - name: str
    #   - content: str
    # Called by:
    #   - bootstrap/microvm/noemaforge-microvm-run.py
    #   - src/audit_remediation.py
    #   - src/bootdoctor.py
    #   - src/brainctl.py
    #   - src/noemaforge_core.py
    #   - src/brainui.py
    #   - src/bundles.py
    #   - src/coordinator_fanout.py
    # Calls:
    #   - open, write, join
    # Returns / emits: None
    # Side effects:
    #   - reads or writes files
    # Key locals:
    #   - f
    # === End NoemaForge Autodoc Function Header ===
    def write(name: str, content: str) -> None:
        with open(os.path.join(etc_dir, name), "w", encoding="utf-8") as f:
            f.write(content)

    write("passwd", "root:x:0:0:root:/root:/bin/sh\n")
    write("group", "root:x:0:\n")
    write("hosts", "127.0.0.1 localhost\n")
    write("nsswitch.conf", "passwd: files\ngroup: files\nhosts: files\n")
    write("resolv.conf", "# network disabled\n")

    # ld.so.cache is not secret; copy if present for faster dynamic linking.
    try:
        src = "/etc/ld.so.cache"
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(etc_dir, "ld.so.cache"))
    except Exception:
        pass

    return etc_dir


# === NoemaForge Autodoc Function Header ===
# Function: _run_host(argv: List[str], cwd: str, env: Dict[str, str], quota: Quota, stdin_bytes: Optional[bytes] = None, network_guard: Optional[Dict[str, Any]] = None)
# Purpose: Implement the routine ' run host'.
# Inputs:
#   - argv: List[str]
#   - cwd: str
#   - env: Dict[str, str]
#   - quota: Quota
#   - stdin_bytes: Optional[bytes] = None
#   - network_guard: Optional[Dict[str, Any]] = None
# Called by:
#   - src/role_runner.py
# Calls:
#   - nullcontext, bool, _apply_rlimits, run, get, egress_guard, int, float, str, setgid, setuid, geteuid
# Returns / emits: Tuple[int, bytes, bytes, Dict[str, Any]]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - guard_ctx, guard_meta, meta, p, uid
# === End NoemaForge Autodoc Function Header ===
def _run_host(
    argv: List[str],
    cwd: str,
    env: Dict[str, str],
    quota: Quota,
    stdin_bytes: Optional[bytes] = None,
    network_guard: Optional[Dict[str, Any]] = None,
) -> Tuple[int, bytes, bytes, Dict[str, Any]]:
    meta: Dict[str, Any] = {"backend": "host", "isolation": "degraded"}

    guard_ctx: contextlib.AbstractContextManager = contextlib.nullcontext()
    guard_meta: Dict[str, Any] = {"enabled": False}
    if network_guard and bool(network_guard.get("enabled", True)):
        try:
            import netguard  # local import

            guard_ctx = netguard.egress_guard(
                uid=int(network_guard.get("uid") or 0),
                targets=network_guard.get("targets") or [],
                allow_loopback=bool(network_guard.get("allow_loopback", False)),
            )
            guard_meta = {"enabled": True, "require": bool(network_guard.get("require", True))}
        except Exception as e:
            if bool(network_guard.get("require", True)):
                raise
            guard_meta = {"enabled": False, "error": str(e), "require": False}
    meta["netguard"] = guard_meta

    # === NoemaForge Autodoc Function Header ===
    # Function: _preexec()
    # Purpose: Implement the routine ' preexec'.
    # Inputs:
    #   - No explicit parameters.
    # Called by:
    #   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
    # Calls:
    #   - _apply_rlimits, bool, get, int, setgid, setuid, geteuid
    # Returns / emits: None
    # Key locals:
    #   - uid
    # === End NoemaForge Autodoc Function Header ===
    def _preexec() -> None:
        _apply_rlimits(quota)
        if network_guard and bool(network_guard.get("enabled", True)):
            try:
                uid = int(network_guard.get("uid") or 0)
                if uid > 0 and os.geteuid() == 0:
                    os.setgid(uid)
                    os.setuid(uid)
            except Exception:
                # If we can't drop privileges, netguard will still be installed but may not apply.
                pass

    with guard_ctx:
        p = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            input=stdin_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=float(quota.timeout_sec),
            preexec_fn=_preexec,
            text=False,
        )
    return p.returncode, p.stdout, p.stderr, meta


# === NoemaForge Autodoc Function Header ===
# Function: _run_bwrap(policy: Dict[str, Any], argv: List[str], cwd: str, env: Dict[str, str], quota: Quota, ro_binds: List[str], rw_binds: List[str], allow_network: bool, extra_ro_binds: Optional[List[str]] = None, stdin_bytes: Optional[bytes] = None, network_guard: Optional[Dict[str, Any]] = None)
# Purpose: Implement the routine ' run bwrap'.
# Inputs:
#   - policy: Dict[str, Any]
#   - argv: List[str]
#   - cwd: str
#   - env: Dict[str, str]
#   - quota: Quota
#   - ro_binds: List[str]
#   - rw_binds: List[str]
#   - allow_network: bool
#   - extra_ro_binds: Optional[List[str]] = None
#   - stdin_bytes: Optional[bytes] = None
#   - network_guard: Optional[Dict[str, Any]] = None
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - _which, bool, FileNotFoundError, get, TemporaryDirectory, dict, setdefault, items, nullcontext, _make_minimal_etc, exists, run
# Returns / emits: Tuple[int, bytes, bytes, Dict[str, Any]]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - bcfg, bwrap, cmd, env_effective, etc_dir, guard_ctx, guard_meta, meta, minimal_etc, p, run_uid, sys_ro
# === End NoemaForge Autodoc Function Header ===
def _run_bwrap(
    policy: Dict[str, Any],
    argv: List[str],
    cwd: str,
    env: Dict[str, str],
    quota: Quota,
    ro_binds: List[str],
    rw_binds: List[str],
    allow_network: bool,
    extra_ro_binds: Optional[List[str]] = None,
    stdin_bytes: Optional[bytes] = None,
    network_guard: Optional[Dict[str, Any]] = None,
) -> Tuple[int, bytes, bytes, Dict[str, Any]]:
    bwrap = _which("bwrap")
    if not bwrap:
        raise FileNotFoundError("bwrap_not_found")

    bcfg = (policy.get("backends") or {}).get("bwrap") or {}
    unshare_net = bool(bcfg.get("unshare_net", True)) and (not allow_network)
    minimal_etc = bool(bcfg.get("minimal_etc", True))

    with tempfile.TemporaryDirectory(prefix="noemaforge-bwrap-") as tmp:
        # Minimal filesystem scaffolding
        etc_dir = _make_minimal_etc(tmp) if minimal_etc else None

        cmd: List[str] = [bwrap, "--die-with-parent", "--new-session"]

        # Optional run-as uid/gid for netguard (so rules apply only to this glove).
        run_uid = None
        if network_guard and bool(network_guard.get("enabled", True)):
            try:
                run_uid = int(network_guard.get("uid") or 0)
            except Exception:
                run_uid = None
        if run_uid and run_uid > 0:
            cmd += ["--uid", str(run_uid), "--gid", str(run_uid)]

        # Namespaces
        cmd += ["--unshare-pid", "--unshare-uts", "--unshare-ipc"]
        if unshare_net:
            cmd += ["--unshare-net"]

        # Minimal proc/dev
        cmd += ["--proc", "/proc", "--dev", "/dev"]

        # Scratch roots: hide host state by default. Order matters.
        # /tmp is always tmpfs. /var,/home,/run are tmpfs so tools cannot see host secrets.
        cmd += ["--tmpfs", "/tmp"]
        cmd += ["--tmpfs", "/var", "--dir", "/var/tmp", "--dir", "/var/log"]
        cmd += ["--tmpfs", "/home", "--dir", "/home/noemaforge"]
        cmd += ["--tmpfs", "/run", "--dir", "/run/noemaforge"]
        cmd += ["--dir", "/mnt", "--dir", "/media", "--dir", "/root"]

        # Bind system dirs read-only
        sys_ro = (bcfg.get("bind_system_ro") or ["/usr", "/bin", "/lib", "/lib64", "/sbin"])
        for p in sys_ro:
            if os.path.exists(p):
                cmd += ["--ro-bind", p, p]

        # Bind minimal /etc
        if etc_dir:
            cmd += ["--ro-bind", etc_dir, "/etc"]

        # Optional extra ro-binds (files/dirs)
        for p in (extra_ro_binds or []):
            if os.path.exists(p):
                cmd += ["--ro-bind", p, p]

        # Stream allowlisted binds
        for p in ro_binds:
            if os.path.exists(p):
                cmd += ["--ro-bind", p, p]
        for p in rw_binds:
            if os.path.exists(p):
                cmd += ["--bind", p, p]

        # Working directory
        if cwd and os.path.exists(cwd):
            cmd += ["--chdir", cwd]

        # Environment (default-minimal + overrides)
        env_effective = dict(env or {})
        env_effective.setdefault("HOME", "/home/noemaforge")
        env_effective.setdefault("TMPDIR", "/tmp")
        env_effective.setdefault("PYTHONNOUSERSITE", "1")
        for k, v in env_effective.items():
            cmd += ["--setenv", str(k), str(v)]

        # Execute (optionally wrapped in netguard)
        cmd += ["--"] + argv

        guard_ctx: contextlib.AbstractContextManager = contextlib.nullcontext()
        guard_meta: Dict[str, Any] = {"enabled": False}
        if allow_network and network_guard and bool(network_guard.get("enabled", True)):
            try:
                import netguard  # local import

                guard_ctx = netguard.egress_guard(
                    uid=int(network_guard.get("uid") or 0),
                    targets=network_guard.get("targets") or [],
                    allow_loopback=bool(network_guard.get("allow_loopback", False)),
                )
                guard_meta = {"enabled": True, "require": bool(network_guard.get("require", True))}
            except Exception as e:
                if bool(network_guard.get("require", True)):
                    raise
                guard_meta = {"enabled": False, "error": str(e), "require": False}

        with guard_ctx:
            p = subprocess.run(
                cmd,
                env={},
                input=stdin_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=float(quota.timeout_sec),
                preexec_fn=lambda: _apply_rlimits(quota),
                text=False,
            )
        meta = {"backend": "bwrap", "isolation": "namespace", "unshare_net": bool(unshare_net), "netguard": guard_meta}
        return p.returncode, p.stdout, p.stderr, meta


# === NoemaForge Autodoc Function Header ===
# Function: _run_podman(policy: Dict[str, Any], argv: List[str], cwd: str, env: Dict[str, str], quota: Quota, ro_binds: List[str], rw_binds: List[str], allow_network: bool, stdin_bytes: Optional[bytes] = None, network_guard: Optional[Dict[str, Any]] = None)
# Purpose: Implement the routine ' run podman'.
# Inputs:
#   - policy: Dict[str, Any]
#   - argv: List[str]
#   - cwd: str
#   - env: Dict[str, str]
#   - quota: Quota
#   - ro_binds: List[str]
#   - rw_binds: List[str]
#   - allow_network: bool
#   - stdin_bytes: Optional[bytes] = None
#   - network_guard: Optional[Dict[str, Any]] = None
# Called by:
#   - src/role_runner.py
# Calls:
#   - _which, str, int, items, run, FileNotFoundError, get, exists, bool, float, basename
# Returns / emits: Tuple[int, bytes, bytes, Dict[str, Any]]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - cmd, image, images, meta, net, p, pcfg, pids, pod, pull
# === End NoemaForge Autodoc Function Header ===
def _run_podman(
    policy: Dict[str, Any],
    argv: List[str],
    cwd: str,
    env: Dict[str, str],
    quota: Quota,
    ro_binds: List[str],
    rw_binds: List[str],
    allow_network: bool,
    stdin_bytes: Optional[bytes] = None,
    network_guard: Optional[Dict[str, Any]] = None,
) -> Tuple[int, bytes, bytes, Dict[str, Any]]:
    pod = _which("podman")
    if not pod:
        raise FileNotFoundError("podman_not_found")

    pcfg = (policy.get("backends") or {}).get("podman") or {}
    pull = str(pcfg.get("pull_policy") or "never")
    net = str(pcfg.get("network") or "none")
    if allow_network:
        net = "slirp4netns"  # still isolated, but has egress

    images = pcfg.get("images") or {}
    image = str(images.get(os.path.basename(argv[0])) or images.get("python3") or "python:3.11-slim")

    pids = int(pcfg.get("pids_limit") or quota.pids_max or 256)

    cmd: List[str] = [
        pod,
        "run",
        "--rm",
        "--pull",
        pull,
        "--network",
        net,
        "--pids-limit",
        str(pids),
        "--memory",
        f"{int(quota.mem_max_mib)}m",
        "--cpus",
        "1",
        "--read-only",
        "--security-opt",
        "no-new-privileges",
    ]

    # Mounts
    for p in ro_binds:
        if os.path.exists(p):
            cmd += ["-v", f"{p}:{p}:ro,Z"]
    for p in rw_binds:
        if os.path.exists(p):
            cmd += ["-v", f"{p}:{p}:Z"]

    # tmpfs for /tmp
    cmd += ["--tmpfs", "/tmp:rw,size=256m"]

    if cwd:
        cmd += ["-w", cwd]

    for k, v in env.items():
        cmd += ["--env", f"{k}={v}"]

    cmd += [image] + argv

    p = subprocess.run(cmd, input=stdin_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=float(quota.timeout_sec), text=False)
    meta = {"backend": "podman", "isolation": "container", "image": image, "network": net}
    if network_guard and bool(network_guard.get("enabled", True)):
        meta["netguard"] = {"enabled": False, "note": "unsupported_in_podman_backend"}
    return p.returncode, p.stdout, p.stderr, meta



# === NoemaForge Autodoc Function Header ===
# Function: microvm_available(policy: Dict[str, Any])
# Purpose: Check if microVM backend is configured and available on this host.
# Inputs:
#   - policy: Dict[str, Any]
# Called by:
#   - src/plugin_runner.py
#   - src/toolproxy.py
# Calls:
#   - strip, get, bool, _which, str, exists
# Returns / emits: Tuple[bool, str]
# Key locals:
#   - kernel, mcfg, rootfs, runtime
# === End NoemaForge Autodoc Function Header ===
def microvm_available(policy: Dict[str, Any]) -> Tuple[bool, str]:
    """Check if microVM backend is configured and available on this host."""
    mcfg = ((policy.get("backends") or {}).get("microvm") or {})
    if not bool(mcfg.get("enabled", False)):
        return False, "disabled"
    runtime = str(mcfg.get("runtime") or "firecracker").strip()
    if not runtime:
        return False, "runtime_missing"
    if not _which(runtime):
        return False, f"runtime_not_found:{runtime}"
    kernel = str(mcfg.get("kernel_path") or "").strip()
    rootfs = str(mcfg.get("rootfs_path") or "").strip()
    if not kernel or not os.path.exists(kernel):
        return False, "kernel_missing"
    if not rootfs or not os.path.exists(rootfs):
        return False, "rootfs_missing"
    return True, "ok"


# === NoemaForge Autodoc Function Header ===
# Function: _run_microvm(policy: Dict[str, Any], argv: List[str], cwd: str, env: Dict[str, str], quota: Quota, ro_binds: List[str], rw_binds: List[str], allow_network: bool, stdin_bytes: Optional[bytes] = None)
# Purpose: Execute argv in a microVM.
# Inputs:
#   - policy: Dict[str, Any]
#   - argv: List[str]
#   - cwd: str
#   - env: Dict[str, str]
#   - quota: Quota
#   - ro_binds: List[str]
#   - rw_binds: List[str]
#   - allow_network: bool
#   - stdin_bytes: Optional[bytes] = None
# Called by:
#   - No external Python callsite detected; may be internal-only, callback-based, or CLI-dispatched.
# Calls:
#   - microvm_available, strip, int, makedirs, join, FileNotFoundError, get, uuid4, bool, decode, open, dump
# Returns / emits: Tuple[int, bytes, bytes, Dict[str, Any]]
# Side effects:
#   - reads or writes files
#   - serializes structured data
#   - creates directories
# Key locals:
#   - cmd, f, kernel, mcfg, mem_mib, meta, outj, p, rc, rootfs, run_dir, run_id
# === End NoemaForge Autodoc Function Header ===
def _run_microvm(
    policy: Dict[str, Any],
    argv: List[str],
    cwd: str,
    env: Dict[str, str],
    quota: Quota,
    ro_binds: List[str],
    rw_binds: List[str],
    allow_network: bool,
    stdin_bytes: Optional[bytes] = None,
) -> Tuple[int, bytes, bytes, Dict[str, Any]]:
    """Execute argv in a microVM.

    Implementation note
    -------------------
    A real microVM runner is host-dependent (firecracker/qemu/cloud-hypervisor).
    The seed kit therefore implements microVM execution via a **delegated runner**:

      backends.microvm.runtime: <runner binary>

    The runner receives a JSON spec and is responsible for:
      - booting the microVM (network disabled by default)
      - mounting ro_binds/rw_binds
      - executing argv and returning outputs deterministically

    This keeps the spine code stable while allowing operators to swap/upgrade
    the microVM runtime out-of-band.

    Contract: runner must print a JSON object to stdout with:
      {"exit_code": int, "stdout_b64": str, "stderr_b64": str, "meta": {...}}

    If runner is missing or returns non-JSON output, we fail closed.
    """

    ok, reason = microvm_available(policy)
    if not ok:
        raise FileNotFoundError(f"microvm_unavailable:{reason}")

    mcfg = ((policy.get("backends") or {}).get("microvm") or {})
    runtime = str(mcfg.get("runtime") or "").strip()
    kernel = str(mcfg.get("kernel_path") or "").strip()
    rootfs = str(mcfg.get("rootfs_path") or "").strip()
    work_dir = str(mcfg.get("work_dir") or "/var/lib/noemaforge/microvm/runs").strip()
    vcpu = int(mcfg.get("default_vcpu") or 1)
    mem_mib = int(mcfg.get("default_mem_mib") or 1024)

    os.makedirs(work_dir, exist_ok=True)
    run_id = uuid.uuid4().hex
    run_dir = os.path.join(work_dir, run_id)
    os.makedirs(run_dir, exist_ok=True)

    spec = {
        "run_id": run_id,
        "kernel_path": kernel,
        "rootfs_path": rootfs,
        "vcpu": vcpu,
        "mem_mib": mem_mib,
        "argv": argv,
        "cwd": cwd,
        "env": env,
        "quota": {
            "cpu_time_sec": quota.cpu_time_sec,
            "mem_max_mib": quota.mem_max_mib,
            "pids_max": quota.pids_max,
            "file_max_mib": quota.file_max_mib,
            "timeout_sec": quota.timeout_sec,
        },
        "mounts": {"ro": ro_binds, "rw": rw_binds},
        "allow_network": bool(allow_network),
        "stdin_b64": base64.b64encode(stdin_bytes or b"").decode("ascii"),
    }

    spec_path = os.path.join(run_dir, "spec.json")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2, sort_keys=True)

    cmd = [runtime, "--spec", spec_path]

    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=float(quota.timeout_sec), text=False)
    except FileNotFoundError:
        raise
    except Exception as e:
        meta = {"backend": "microvm", "isolation": "microvm", "runtime": runtime, "run_id": run_id, "error": repr(e)}
        return 126, b"", f"microvm runner failed: {e!r}\n".encode("utf-8"), meta

    # Runner must emit JSON to stdout
    try:
        outj = json.loads(p.stdout.decode("utf-8", errors="replace") or "{}")
        rc = int(outj.get("exit_code") if isinstance(outj, dict) else p.returncode)
        sout = base64.b64decode(outj.get("stdout_b64") or "") if isinstance(outj, dict) else b""
        serr = base64.b64decode(outj.get("stderr_b64") or "") if isinstance(outj, dict) else b""
        meta = outj.get("meta") if isinstance(outj, dict) else {}
        if not isinstance(meta, dict):
            meta = {}
        meta.update({"backend": "microvm", "isolation": "microvm", "runtime": runtime, "run_id": run_id})
        return rc, sout, serr, meta
    except Exception:
        meta = {
            "backend": "microvm",
            "isolation": "microvm",
            "runtime": runtime,
            "run_id": run_id,
            "blocked": True,
            "blocked_reason": "runner_non_json_output",
        }
        # Treat runner stderr as the primary error channel.
        return 126, b"", p.stderr or b"microvm runner produced non-json output\n", meta


# === NoemaForge Autodoc Function Header ===
# Function: run(policy: Dict[str, Any], argv: List[str], cwd: str, env: Dict[str, str], quota: Quota, ro_binds: Optional[List[str]] = None, rw_binds: Optional[List[str]] = None, allow_network: bool = False, extra_ro_binds: Optional[List[str]] = None, prefer_backends: Optional[List[str]] = None, stdin_bytes: Optional[bytes] = None, network_guard: Optional[Dict[str, Any]] = None)
# Purpose: Run command in the best available sandbox backend.
# Inputs:
#   - policy: Dict[str, Any]
#   - argv: List[str]
#   - cwd: str
#   - env: Dict[str, str]
#   - quota: Quota
#   - ro_binds: Optional[List[str]] = None
#   - rw_binds: Optional[List[str]] = None
#   - allow_network: bool = False
#   - extra_ro_binds: Optional[List[str]] = None
#   - prefer_backends: Optional[List[str]] = None
#   - stdin_bytes: Optional[bytes] = None
#   - network_guard: Optional[Dict[str, Any]] = None
# Called by:
#   - src/bootdoctor.py
#   - src/brainctl.py
#   - src/firstboot_eval.py
#   - src/hwscan.py
#   - src/knowledge_maintainer.py
#   - src/lan_discovery.py
#   - src/localgateway.py
#   - src/localgw_connectors/ipp.py
# Calls:
#   - host_fallback_mode, get, bool, int, _run_microvm, _run_bwrap, decode, str, _run_podman, RuntimeError, _run_host, type
# Returns / emits: Tuple[bool, Dict[str, Any]]
# Side effects:
#   - spawns subprocesses or workers
# Key locals:
#   - b, bp, exit_code, hf_mode, last_err, last_meta, ok, res, ro_binds, rw_binds
# === End NoemaForge Autodoc Function Header ===
def run(
    *,
    policy: Dict[str, Any],
    argv: List[str],
    cwd: str,
    env: Dict[str, str],
    quota: Quota,
    ro_binds: Optional[List[str]] = None,
    rw_binds: Optional[List[str]] = None,
    allow_network: bool = False,
    extra_ro_binds: Optional[List[str]] = None,
    prefer_backends: Optional[List[str]] = None,
    stdin_bytes: Optional[bytes] = None,
    network_guard: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """Run command in the best available sandbox backend.

    Returns: (ok, result)

    result includes:
      - exit_code
      - stdout, stderr (utf-8, replace)
      - backend meta
      - truncated flags
    """

    ro_binds = ro_binds or []
    rw_binds = rw_binds or []

    # Decide backend order
    bp = (policy.get("backends") or {}).get("preference") or ["bwrap", "podman", "host"]
    if prefer_backends:
        bp = prefer_backends

    hf_mode = host_fallback_mode(policy)

    last_err = ""
    last_meta: Dict[str, Any] = {}

    for b in bp:
        try:
            if b == "microvm" and bool(((policy.get("backends") or {}).get("microvm") or {}).get("enabled", False)):
                rc, out, err, bmeta = _run_microvm(policy, argv, cwd, env, quota, ro_binds, rw_binds, allow_network, stdin_bytes)
                return (rc == 0), {"exit_code": rc, "stdout": out, "stderr": err, "backend": bmeta}

            if b == "bwrap" and bool(((policy.get("backends") or {}).get("bwrap") or {}).get("enabled", True)):
                rc, out, err, meta = _run_bwrap(
                    policy,
                    argv,
                    cwd,
                    env,
                    quota,
                    ro_binds,
                    rw_binds,
                    allow_network,
                    extra_ro_binds=extra_ro_binds,
                    stdin_bytes=stdin_bytes,
                    network_guard=network_guard,
                )
            elif b == "podman" and bool(((policy.get("backends") or {}).get("podman") or {}).get("enabled", True)):
                if network_guard and bool(network_guard.get("enabled", True)) and bool(network_guard.get("require", True)):
                    # podman backend cannot enforce per-destination egress rules today.
                    raise RuntimeError("netguard_required_but_podman_unsupported")
                rc, out, err, meta = _run_podman(policy, argv, cwd, env, quota, ro_binds, rw_binds, allow_network, stdin_bytes=stdin_bytes, network_guard=network_guard)
            elif b == "host":
                if hf_mode == "allow":
                    rc, out, err, meta = _run_host(argv, cwd, env, quota, stdin_bytes=stdin_bytes, network_guard=network_guard)
                else:
                    # Do NOT execute. Report as blocked.
                    last_err = "host_fallback_blocked"
                    last_meta = {
                        "backend": "host",
                        "isolation": "degraded",
                        "blocked": True,
                        "blocked_reason": "host_fallback_quarantine" if hf_mode == "quarantine" else "host_fallback_denied",
                    }
                    # If host is blocked, no need to try further.
                    continue
            else:
                continue

            res = {
                "exit_code": int(rc),
                "stdout": (out or b"").decode("utf-8", "replace"),
                "stderr": (err or b"").decode("utf-8", "replace"),
                "backend": meta,
            }
            ok = (rc == 0)
            return ok, res
        except subprocess.TimeoutExpired:
            last_err = "timeout"
            last_meta = {"backend": b, "isolation": "unknown"}
        except FileNotFoundError as e:
            last_err = str(e)
            last_meta = {"backend": b, "isolation": "missing"}
        except Exception as e:
            last_err = f"{type(e).__name__}:{e}"
            last_meta = {"backend": b, "isolation": "error"}

    exit_code = 126 if bool((last_meta or {}).get("blocked")) else 127
    return False, {"exit_code": int(exit_code), "stdout": "", "stderr": last_err, "backend": last_meta}
