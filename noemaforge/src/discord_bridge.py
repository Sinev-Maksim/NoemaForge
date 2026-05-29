#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/discord_bridge.py
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
# File: src/discord_bridge.py
# Purpose: Provide a ToolProxy-mediated Discord desktop bridge that prepares background/mask assets and starts or stops local delayed audio/video pipelines for use as Discord virtual devices.
# Invoked by / imported from:
#   - src/toolproxy.py
#   - tests/test_discord_bridge.py
# Public API / entry functions:
#   - prepare_assets
#   - start_bridge
#   - stop_bridge
#   - bridge_status
#   - prepare_tool_action
# Inputs:
#   - User prompts for background_prompt and mask_prompt.
#   - Local runtime policy from configs/discord-bridge-policy.yaml.
#   - Optional live capture devices, ffmpeg paths, or command backend templates.
# Output formats / side effects:
#   - Session JSON manifests under the configured sessions root.
#   - Background/mask asset files under the configured artifacts root.
#   - Optional local worker subprocesses for video and audio bridge pipelines.
# Security considerations:
#   - Never performs network I/O.
#   - Does not talk to Discord APIs directly; it only prepares local bridge devices or files for the Discord desktop client.
#   - All execution is intended to be mediated only by ToolProxy.
# AutoDoc: refreshed 2026-04-10 (manual, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""discord_bridge.py (v0.26.6)

Local Discord desktop bridge for NoemaForge.

The module deliberately avoids Discord HTTP or Gateway control. Instead, it prepares
local audio/video bridge sessions that the Discord desktop client can consume via
virtual camera or microphone devices. This keeps the implementation compatible with
the offline-first and ToolProxy-only NoemaForge posture.

Shipped capabilities:
- Deterministic background asset generation from user prompts.
- Deterministic mask asset generation from user prompts.
- Local session manifests and process lifecycle management.
- Built-in ffmpeg command planning for delayed video/audio bridges.
- Command backends for host-specific capture, segmentation, or composition stacks.

Non-goals in this seed release:
- Direct Discord API streaming.
- Host package installation or kernel module setup.
- Full real-time person segmentation without an external backend.
"""


import datetime as dt
import hashlib
import json
import math
import os
import shutil
import signal
import subprocess
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:  # Optional dependency used for policy loading.
    import yaml  # type: ignore
except Exception:  # pragma: no cover - checker/test environments may omit PyYAML
    yaml = None  # type: ignore


DEFAULT_POLICY_PATH = "/opt/noemaforge/configs/discord-bridge-policy.yaml"
DEFAULT_SESSIONS_ROOT = "/workspace/state/discord_bridge/sessions"
DEFAULT_ARTIFACTS_ROOT = "/workspace/outbox/discord_bridge/assets"
LIVE_PROCS: Dict[int, subprocess.Popen[Any]] = {}


# === NoemaForge Autodoc Function Header ===
# Function: _nowz()
# Purpose: Return an ISO-8601 UTC timestamp suitable for manifests.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - _write_json
#   - prepare_assets
#   - start_bridge
#   - stop_bridge
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


# === NoemaForge Autodoc Function Header ===
# Function: _slug(prefix: str = "discord")
# Purpose: Create a collision-resistant identifier for assets and sessions.
# Inputs:
#   - prefix: str = "discord"
# Called by:
#   - prepare_assets
#   - start_bridge
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _slug(prefix: str = "discord") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# === NoemaForge Autodoc Function Header ===
# Function: _ensure_dir(path: str)
# Purpose: Create a directory tree when it does not yet exist.
# Inputs:
#   - path: str
# Called by:
#   - prepare_assets
#   - start_bridge
#   - _write_json
# Returns / emits: str
# Side effects:
#   - creates directories on disk
# === End NoemaForge Autodoc Function Header ===
def _ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


# === NoemaForge Autodoc Function Header ===
# Function: _write_json(path: str, payload: Dict[str, Any])
# Purpose: Persist structured state to UTF-8 JSON.
# Inputs:
#   - path: str
#   - payload: Dict[str, Any]
# Called by:
#   - prepare_assets
#   - start_bridge
#   - stop_bridge
# Returns / emits: str
# Side effects:
#   - writes JSON files
# === End NoemaForge Autodoc Function Header ===
def _write_json(path: str, payload: Dict[str, Any]) -> str:
    _ensure_dir(os.path.dirname(path) or ".")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


# === NoemaForge Autodoc Function Header ===
# Function: _read_json(path: str)
# Purpose: Read a JSON document or return an empty object when unavailable.
# Inputs:
#   - path: str
# Called by:
#   - bridge_status
#   - stop_bridge
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads JSON files
# === End NoemaForge Autodoc Function Header ===
def _read_json(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _deep_merge(base: Dict[str, Any], override: Dict[str, Any])
# Purpose: Merge nested policy dictionaries without mutating caller input.
# Inputs:
#   - base: Dict[str, Any]
#   - override: Dict[str, Any]
# Called by:
#   - _load_policy
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged.get(key) or {}), value)
        else:
            merged[key] = value
    return merged


# === NoemaForge Autodoc Function Header ===
# Function: _default_policy()
# Purpose: Return the seed Discord bridge policy used when no file is present.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - _load_policy
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def _default_policy() -> Dict[str, Any]:
    return {
        "apiVersion": "noemaforge.discordbridge/v1",
        "kind": "DiscordBridgePolicy",
        "enabled": False,
        "mode": "desktop_bridge",
        "sessions_root": DEFAULT_SESSIONS_ROOT,
        "artifacts_root": DEFAULT_ARTIFACTS_ROOT,
        "discord_client": {
            "handoff_mode": "desktop_virtual_devices",
            "application_name": "Discord",
            "recommended_video_device": "/dev/video10",
            "recommended_audio_source": "noemaforge-discord.monitor",
            "launch_notes": [
                "Start the NoemaForge Discord bridge session first.",
                "In Discord desktop settings, select the configured virtual camera and microphone.",
                "Discord transport itself is handled by the desktop client, not by NoemaForge."
            ],
        },
        "capture": {
            "av_delay_ms": 350,
            "video": {
                "enabled": False,
                "backend_order": ["ffmpeg", "command"],
                "camera_device": "/dev/video0",
                "input_path": "",
                "width": 1280,
                "height": 720,
                "fps": 24,
                "input_format": "v4l2",
                "ffmpeg_executable": "ffmpeg",
                "output_mode": "v4l2loopback",
                "output_device": "/dev/video10",
                "output_path": "",
                "command": {"argv": []},
            },
            "audio": {
                "enabled": False,
                "backend_order": ["ffmpeg", "command"],
                "input_device": "default",
                "sample_rate_hz": 48000,
                "channels": 2,
                "input_format": "pulse",
                "ffmpeg_executable": "ffmpeg",
                "output_mode": "pulse_sink",
                "output_target": "noemaforge-discord",
                "output_path": "",
                "delay_ms": 350,
                "command": {"argv": []},
            },
        },
        "processing": {
            "background": {
                "enabled": True,
                "backend_order": ["prompt_gradient_ppm", "command"],
                "width": 1280,
                "height": 720,
                "command": {"argv": []},
            },
            "mask": {
                "enabled": True,
                "backend_order": ["soft_center_mask_pgm", "command", "passthrough"],
                "width": 1280,
                "height": 720,
                "blur_px": 28,
                "command": {"argv": []},
            },
        },
        "assistant_bridge": {
            "default_alias": "administrator",
            "overlay_title": "NoemaForge Administrator",
        },
    }


# === NoemaForge Autodoc Function Header ===
# Function: _load_policy(policy_path: str = DEFAULT_POLICY_PATH, policy_override: Optional[Dict[str, Any]] = None)
# Purpose: Load and normalize the Discord bridge runtime policy.
# Inputs:
#   - policy_path: str = DEFAULT_POLICY_PATH
#   - policy_override: Optional[Dict[str, Any]] = None
# Called by:
#   - prepare_assets
#   - start_bridge
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads policy files when present
# === End NoemaForge Autodoc Function Header ===
def _load_policy(policy_path: str = DEFAULT_POLICY_PATH, policy_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = _default_policy()
    doc: Dict[str, Any] = {}
    if policy_path and os.path.exists(policy_path) and yaml is not None:
        try:
            with open(policy_path, 'r', encoding='utf-8') as f:
                loaded = yaml.safe_load(f) or {}
            if isinstance(loaded, dict):
                doc = loaded
        except Exception:
            doc = {}
    merged = _deep_merge(base, doc)
    if isinstance(policy_override, dict):
        merged = _deep_merge(merged, policy_override)
    return merged


# === NoemaForge Autodoc Function Header ===
# Function: _safe_prompt_token(prompt: str)
# Purpose: Reduce arbitrary prompt text to a filesystem-safe token.
# Inputs:
#   - prompt: str
# Called by:
#   - prepare_assets
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _safe_prompt_token(prompt: str) -> str:
    raw = "-".join([p for p in ''.join(ch.lower() if ch.isalnum() else '-' for ch in str(prompt or '')).split('-') if p])
    if raw:
        return raw[:48]
    return hashlib.sha256(str(prompt or '').encode('utf-8')).hexdigest()[:12]


# === NoemaForge Autodoc Function Header ===
# Function: _palette_from_prompt(prompt: str)
# Purpose: Generate deterministic color anchors from a user prompt.
# Inputs:
#   - prompt: str
# Called by:
#   - _write_prompt_gradient_ppm
# Returns / emits: Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]
# === End NoemaForge Autodoc Function Header ===
def _palette_from_prompt(prompt: str) -> Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]:
    digest = hashlib.sha256(str(prompt or '').encode('utf-8')).digest()
    def _rgb(offset: int) -> Tuple[int, int, int]:
        return tuple(48 + (digest[offset + i] % 176) for i in range(3))  # type: ignore[return-value]
    return _rgb(0), _rgb(3), _rgb(6)


# === NoemaForge Autodoc Function Header ===
# Function: _write_prompt_gradient_ppm(path: str, prompt: str, width: int, height: int)
# Purpose: Create a deterministic prompt-driven gradient background without external image libraries.
# Inputs:
#   - path: str
#   - prompt: str
#   - width: int
#   - height: int
# Called by:
#   - _generate_background_asset
# Returns / emits: Dict[str, Any]
# Side effects:
#   - writes image files
# === End NoemaForge Autodoc Function Header ===
def _write_prompt_gradient_ppm(path: str, prompt: str, width: int, height: int) -> Dict[str, Any]:
    c1, c2, c3 = _palette_from_prompt(prompt)
    _ensure_dir(os.path.dirname(path) or '.')
    width = max(16, int(width or 1280))
    height = max(16, int(height or 720))
    with open(path, 'wb') as f:
        f.write(f"P6\n{width} {height}\n255\n".encode('ascii'))
        for y in range(height):
            yr = y / max(1, height - 1)
            row = bytearray()
            for x in range(width):
                xr = x / max(1, width - 1)
                wave = (math.sin((xr + yr) * math.pi * 2.0) + 1.0) / 2.0
                r = int((1 - xr) * c1[0] + xr * c2[0])
                g = int((1 - yr) * c1[1] + yr * c3[1])
                b = int((1 - wave) * c2[2] + wave * c3[2])
                row.extend((max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))))
            f.write(row)
    return {
        'backend': 'prompt_gradient_ppm',
        'asset_kind': 'background',
        'path': path,
        'width': width,
        'height': height,
        'prompt_token': _safe_prompt_token(prompt),
        'format': 'ppm',
    }


# === NoemaForge Autodoc Function Header ===
# Function: _write_soft_center_mask_pgm(path: str, prompt: str, width: int, height: int, blur_px: int)
# Purpose: Create a deterministic soft matte mask influenced by prompt hints such as portrait, wide, left, or right.
# Inputs:
#   - path: str
#   - prompt: str
#   - width: int
#   - height: int
#   - blur_px: int
# Called by:
#   - _generate_mask_asset
# Returns / emits: Dict[str, Any]
# Side effects:
#   - writes image files
# === End NoemaForge Autodoc Function Header ===
def _write_soft_center_mask_pgm(path: str, prompt: str, width: int, height: int, blur_px: int) -> Dict[str, Any]:
    prompt_l = str(prompt or '').lower()
    width = max(16, int(width or 1280))
    height = max(16, int(height or 720))
    blur_px = max(8, int(blur_px or 28))
    cx = 0.5
    cy = 0.52
    rx = 0.34
    ry = 0.42
    if 'portrait' in prompt_l:
        rx, ry = 0.26, 0.43
    if 'wide' in prompt_l or 'landscape' in prompt_l:
        rx, ry = 0.42, 0.36
    if 'circle' in prompt_l or 'round' in prompt_l:
        rx = ry = min(rx, ry)
    if 'left' in prompt_l:
        cx = 0.40
    if 'right' in prompt_l:
        cx = 0.60
    if 'upper' in prompt_l or 'top' in prompt_l:
        cy = 0.44
    if 'lower' in prompt_l or 'bottom' in prompt_l:
        cy = 0.60
    blur_norm_x = blur_px / max(1.0, width)
    blur_norm_y = blur_px / max(1.0, height)
    _ensure_dir(os.path.dirname(path) or '.')
    with open(path, 'wb') as f:
        f.write(f"P5\n{width} {height}\n255\n".encode('ascii'))
        for y in range(height):
            ny = (y / max(1, height - 1) - cy) / max(0.001, ry)
            row = bytearray()
            for x in range(width):
                nx = (x / max(1, width - 1) - cx) / max(0.001, rx)
                dist = math.sqrt(nx * nx + ny * ny)
                if dist <= 1.0:
                    alpha = 255
                else:
                    edge = (dist - 1.0) / max(0.0001, max(blur_norm_x / max(0.001, rx), blur_norm_y / max(0.001, ry)))
                    alpha = int(max(0.0, 255.0 * (1.0 - min(1.0, edge))))
                row.append(alpha)
            f.write(row)
    return {
        'backend': 'soft_center_mask_pgm',
        'asset_kind': 'mask',
        'path': path,
        'width': width,
        'height': height,
        'prompt_token': _safe_prompt_token(prompt),
        'format': 'pgm',
    }


# === NoemaForge Autodoc Function Header ===
# Function: _run_command_backend(argv_template: List[str], mapping: Dict[str, Any], stdout_path: str, stderr_path: str, wait: bool)
# Purpose: Materialize and optionally execute a command backend from placeholder-aware argv templates.
# Inputs:
#   - argv_template: List[str]
#   - mapping: Dict[str, Any]
#   - stdout_path: str
#   - stderr_path: str
#   - wait: bool
# Called by:
#   - _generate_background_asset
#   - _generate_mask_asset
#   - _start_command_worker
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# Side effects:
#   - spawns subprocesses
#   - writes stdout/stderr logs
# === End NoemaForge Autodoc Function Header ===
def _run_command_backend(argv_template: List[str], mapping: Dict[str, Any], stdout_path: str, stderr_path: str, wait: bool) -> Tuple[bool, Dict[str, Any], str]:
    argv = [str(part).format(**mapping) for part in list(argv_template or [])]
    if not argv:
        return False, {'error': 'empty_command_argv'}, 'command_backend_missing'
    _ensure_dir(os.path.dirname(stdout_path) or '.')
    _ensure_dir(os.path.dirname(stderr_path) or '.')
    with open(stdout_path, 'ab') as out, open(stderr_path, 'ab') as err:
        proc = subprocess.Popen(argv, stdout=out, stderr=err, start_new_session=True)
    if wait:
        rc = proc.wait(timeout=300)
        return rc == 0, {'argv': argv, 'returncode': rc}, 'ok' if rc == 0 else 'command_backend_failed'
    LIVE_PROCS[int(proc.pid)] = proc
    return True, {'argv': argv, 'pid': proc.pid}, 'ok'


# === NoemaForge Autodoc Function Header ===
# Function: _generate_background_asset(prompt: str, policy: Dict[str, Any], output_dir: str, requested_backend: str = "")
# Purpose: Generate or register a background asset for the Discord bridge.
# Inputs:
#   - prompt: str
#   - policy: Dict[str, Any]
#   - output_dir: str
#   - requested_backend: str = ""
# Called by:
#   - prepare_assets
#   - start_bridge
# Returns / emits: Dict[str, Any]
# Side effects:
#   - writes assets and logs
# === End NoemaForge Autodoc Function Header ===
def _generate_background_asset(prompt: str, policy: Dict[str, Any], output_dir: str, requested_backend: str = "") -> Dict[str, Any]:
    bg = (policy.get('processing') or {}).get('background') or {}
    if not bool(bg.get('enabled', True)):
        return {'status': 'disabled', 'asset_kind': 'background'}
    backend_order = [str(x).strip() for x in (bg.get('backend_order') or []) if str(x).strip()]
    if requested_backend:
        backend_order = [requested_backend] + [b for b in backend_order if b != requested_backend]
    width = int(bg.get('width') or 1280)
    height = int(bg.get('height') or 720)
    token = _safe_prompt_token(prompt or 'background')
    _ensure_dir(output_dir)
    for backend in backend_order:
        if backend == 'prompt_gradient_ppm':
            out = os.path.join(output_dir, f'background-{token}.ppm')
            meta = _write_prompt_gradient_ppm(out, prompt or 'noemaforge background', width, height)
            meta['status'] = 'ready'
            return meta
        if backend == 'command':
            out = os.path.join(output_dir, f'background-{token}.png')
            stdout_path = os.path.join(output_dir, f'background-{token}.stdout.log')
            stderr_path = os.path.join(output_dir, f'background-{token}.stderr.log')
            ok, res, reason = _run_command_backend(
                argv_template=list(((bg.get('command') or {}).get('argv') or [])),
                mapping={'output_path': out, 'prompt': prompt or '', 'width': width, 'height': height},
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                wait=True,
            )
            if ok and os.path.exists(out):
                return {
                    'status': 'ready',
                    'backend': 'command',
                    'asset_kind': 'background',
                    'path': out,
                    'width': width,
                    'height': height,
                    'stdout_path': stdout_path,
                    'stderr_path': stderr_path,
                    'command': res.get('argv') or [],
                }
    return {'status': 'skipped', 'asset_kind': 'background', 'reason': 'no_background_backend'}


# === NoemaForge Autodoc Function Header ===
# Function: _generate_mask_asset(prompt: str, policy: Dict[str, Any], output_dir: str, requested_backend: str = "")
# Purpose: Generate or register a mask asset for the Discord bridge.
# Inputs:
#   - prompt: str
#   - policy: Dict[str, Any]
#   - output_dir: str
#   - requested_backend: str = ""
# Called by:
#   - prepare_assets
#   - start_bridge
# Returns / emits: Dict[str, Any]
# Side effects:
#   - writes assets and logs
# === End NoemaForge Autodoc Function Header ===
def _generate_mask_asset(prompt: str, policy: Dict[str, Any], output_dir: str, requested_backend: str = "") -> Dict[str, Any]:
    mask = (policy.get('processing') or {}).get('mask') or {}
    if not bool(mask.get('enabled', True)):
        return {'status': 'disabled', 'asset_kind': 'mask'}
    backend_order = [str(x).strip() for x in (mask.get('backend_order') or []) if str(x).strip()]
    if requested_backend:
        backend_order = [requested_backend] + [b for b in backend_order if b != requested_backend]
    width = int(mask.get('width') or 1280)
    height = int(mask.get('height') or 720)
    blur_px = int(mask.get('blur_px') or 28)
    token = _safe_prompt_token(prompt or 'mask')
    _ensure_dir(output_dir)
    for backend in backend_order:
        if backend == 'passthrough':
            return {'status': 'ready', 'asset_kind': 'mask', 'backend': 'passthrough', 'path': ''}
        if backend == 'soft_center_mask_pgm':
            out = os.path.join(output_dir, f'mask-{token}.pgm')
            meta = _write_soft_center_mask_pgm(out, prompt or 'portrait', width, height, blur_px)
            meta['status'] = 'ready'
            return meta
        if backend == 'command':
            out = os.path.join(output_dir, f'mask-{token}.png')
            stdout_path = os.path.join(output_dir, f'mask-{token}.stdout.log')
            stderr_path = os.path.join(output_dir, f'mask-{token}.stderr.log')
            ok, res, reason = _run_command_backend(
                argv_template=list(((mask.get('command') or {}).get('argv') or [])),
                mapping={'output_path': out, 'prompt': prompt or '', 'width': width, 'height': height, 'blur_px': blur_px},
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                wait=True,
            )
            if ok and os.path.exists(out):
                return {
                    'status': 'ready',
                    'backend': 'command',
                    'asset_kind': 'mask',
                    'path': out,
                    'width': width,
                    'height': height,
                    'stdout_path': stdout_path,
                    'stderr_path': stderr_path,
                    'command': res.get('argv') or [],
                }
    return {'status': 'skipped', 'asset_kind': 'mask', 'reason': 'no_mask_backend'}


# === NoemaForge Autodoc Function Header ===
# Function: prepare_assets(background_prompt: str = "", mask_prompt: str = "", policy_path: str = DEFAULT_POLICY_PATH, policy_override: Optional[Dict[str, Any]] = None)
# Purpose: Generate background and mask assets on demand before starting a live Discord bridge session.
# Inputs:
#   - background_prompt: str = ""
#   - mask_prompt: str = ""
#   - policy_path: str = DEFAULT_POLICY_PATH
#   - policy_override: Optional[Dict[str, Any]] = None
# Called by:
#   - prepare_tool_action
#   - start_bridge
# Returns / emits: Dict[str, Any]
# Side effects:
#   - writes asset and manifest files
# === End NoemaForge Autodoc Function Header ===
def prepare_assets(
    background_prompt: str = "",
    mask_prompt: str = "",
    policy_path: str = DEFAULT_POLICY_PATH,
    policy_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    policy = _load_policy(policy_path=policy_path, policy_override=policy_override)
    artifacts_root = _ensure_dir(str(policy.get('artifacts_root') or DEFAULT_ARTIFACTS_ROOT))
    asset_id = _slug('discord-assets')
    asset_dir = _ensure_dir(os.path.join(artifacts_root, asset_id))
    background = _generate_background_asset(background_prompt, policy, asset_dir)
    mask = _generate_mask_asset(mask_prompt, policy, asset_dir)
    manifest = {
        'apiVersion': 'noemaforge.discordbridge/v1',
        'kind': 'DiscordBridgeAssets',
        'asset_id': asset_id,
        'created_at': _nowz(),
        'asset_dir': asset_dir,
        'background_prompt': str(background_prompt or ''),
        'mask_prompt': str(mask_prompt or ''),
        'background': background,
        'mask': mask,
    }
    manifest_path = _write_json(os.path.join(asset_dir, 'assets.json'), manifest)
    manifest['manifest_path'] = manifest_path
    return manifest


# === NoemaForge Autodoc Function Header ===
# Function: _build_ffmpeg_video_argv(policy: Dict[str, Any], session_root: str, background: Dict[str, Any], mask: Dict[str, Any])
# Purpose: Build a deterministic ffmpeg argv for video passthrough or matte compositing into a virtual camera target.
# Inputs:
#   - policy: Dict[str, Any]
#   - session_root: str
#   - background: Dict[str, Any]
#   - mask: Dict[str, Any]
# Called by:
#   - start_bridge
# Returns / emits: List[str]
# === End NoemaForge Autodoc Function Header ===
def _build_ffmpeg_video_argv(policy: Dict[str, Any], session_root: str, background: Dict[str, Any], mask: Dict[str, Any]) -> List[str]:
    capture = ((policy.get('capture') or {}).get('video') or {})
    ffmpeg = str(capture.get('ffmpeg_executable') or 'ffmpeg')
    width = int(capture.get('width') or 1280)
    height = int(capture.get('height') or 720)
    fps = int(capture.get('fps') or 24)
    delay_ms = int(((policy.get('capture') or {}).get('av_delay_ms') or 0))
    input_path = str(capture.get('input_path') or '').strip()
    camera_device = str(capture.get('camera_device') or '/dev/video0').strip()
    input_format = str(capture.get('input_format') or 'v4l2').strip()
    output_mode = str(capture.get('output_mode') or 'v4l2loopback').strip()
    output_device = str(capture.get('output_device') or '/dev/video10').strip()
    output_path = str(capture.get('output_path') or os.path.join(session_root, 'video-bridge.mkv')).strip()
    argv: List[str] = [ffmpeg, '-hide_banner', '-loglevel', 'warning', '-y']
    if input_path:
        argv.extend(['-re', '-stream_loop', '-1', '-i', input_path])
    else:
        argv.extend(['-f', input_format, '-framerate', str(fps), '-video_size', f'{width}x{height}', '-i', camera_device])
    has_bg = bool(background.get('path')) and os.path.exists(str(background.get('path') or ''))
    has_mask = bool(mask.get('path')) and os.path.exists(str(mask.get('path') or '')) and str(mask.get('backend') or '') != 'passthrough'
    filter_chain = ''
    if has_bg:
        argv.extend(['-stream_loop', '-1', '-i', str(background.get('path') or '')])
    if has_mask:
        argv.extend(['-stream_loop', '-1', '-i', str(mask.get('path') or '')])
    if has_bg and has_mask:
        filter_chain = (
            f"[0:v]scale={width}:{height},setpts=PTS+{delay_ms/1000.0}/TB,format=rgba[fg];"
            f"[1:v]scale={width}:{height},format=rgba[bg];"
            f"[2:v]scale={width}:{height},format=gray[mask];"
            f"[fg][mask]alphamerge[cut];"
            f"[bg][cut]overlay=shortest=1,format=yuv420p[outv]"
        )
    else:
        filter_chain = f"[0:v]scale={width}:{height},setpts=PTS+{delay_ms/1000.0}/TB,format=yuv420p[outv]"
    argv.extend(['-filter_complex', filter_chain, '-map', '[outv]', '-r', str(fps), '-pix_fmt', 'yuv420p'])
    if output_mode == 'v4l2loopback':
        argv.extend(['-f', 'v4l2', output_device])
    else:
        argv.append(output_path)
    return argv


# === NoemaForge Autodoc Function Header ===
# Function: _build_ffmpeg_audio_argv(policy: Dict[str, Any], session_root: str)
# Purpose: Build a deterministic ffmpeg argv for delayed audio output toward a local file or pulse sink.
# Inputs:
#   - policy: Dict[str, Any]
#   - session_root: str
# Called by:
#   - start_bridge
# Returns / emits: List[str]
# === End NoemaForge Autodoc Function Header ===
def _build_ffmpeg_audio_argv(policy: Dict[str, Any], session_root: str) -> List[str]:
    capture = ((policy.get('capture') or {}).get('audio') or {})
    ffmpeg = str(capture.get('ffmpeg_executable') or 'ffmpeg')
    input_device = str(capture.get('input_device') or 'default').strip()
    input_format = str(capture.get('input_format') or 'pulse').strip()
    sample_rate_hz = int(capture.get('sample_rate_hz') or 48000)
    channels = int(capture.get('channels') or 2)
    output_mode = str(capture.get('output_mode') or 'pulse_sink').strip()
    output_target = str(capture.get('output_target') or 'noemaforge-discord').strip()
    output_path = str(capture.get('output_path') or os.path.join(session_root, 'audio-bridge.wav')).strip()
    delay_ms = int(capture.get('delay_ms') or ((policy.get('capture') or {}).get('av_delay_ms') or 0))
    delay_expr = '|'.join([str(delay_ms) for _ in range(max(1, channels))])
    argv: List[str] = [ffmpeg, '-hide_banner', '-loglevel', 'warning', '-y', '-f', input_format, '-i', input_device, '-af', f'adelay={delay_expr}', '-ar', str(sample_rate_hz), '-ac', str(channels)]
    if output_mode == 'pulse_sink':
        argv.extend(['-f', 'pulse', output_target])
    else:
        argv.append(output_path)
    return argv


# === NoemaForge Autodoc Function Header ===
# Function: _pid_alive(pid: int)
# Purpose: Best-effort liveness check for a previously started worker process.
# Inputs:
#   - pid: int
# Called by:
#   - bridge_status
#   - stop_bridge
# Returns / emits: bool
# === End NoemaForge Autodoc Function Header ===
def _pid_alive(pid: int) -> bool:
    if int(pid or 0) <= 0:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


# === NoemaForge Autodoc Function Header ===
# Function: _terminate_pid(pid: int)
# Purpose: Best-effort termination for a managed worker process.
# Inputs:
#   - pid: int
# Called by:
#   - stop_bridge
# Returns / emits: bool
# Side effects:
#   - sends POSIX signals
# === End NoemaForge Autodoc Function Header ===
def _terminate_pid(pid: int) -> bool:
    if int(pid or 0) <= 0:
        return False
    proc = LIVE_PROCS.get(int(pid))
    try:
        os.kill(int(pid), signal.SIGTERM)
        for _ in range(15):
            if not _pid_alive(pid):
                if proc is not None:
                    try:
                        proc.wait(timeout=0.1)
                    except Exception:
                        pass
                    LIVE_PROCS.pop(int(pid), None)
                return True
            time.sleep(0.1)
        os.kill(int(pid), signal.SIGKILL)
        if proc is not None:
            try:
                proc.wait(timeout=0.5)
            except Exception:
                pass
            LIVE_PROCS.pop(int(pid), None)
        return True
    except Exception:
        return False


# === NoemaForge Autodoc Function Header ===
# Function: _start_worker(label: str, backend: str, argv: List[str], session_root: str)
# Purpose: Spawn a long-running bridge worker and capture its lifecycle metadata.
# Inputs:
#   - label: str
#   - backend: str
#   - argv: List[str]
#   - session_root: str
# Called by:
#   - start_bridge
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns subprocesses
#   - writes stdout/stderr logs
# === End NoemaForge Autodoc Function Header ===
def _start_worker(label: str, backend: str, argv: List[str], session_root: str) -> Dict[str, Any]:
    stdout_path = os.path.join(session_root, f'{label}.stdout.log')
    stderr_path = os.path.join(session_root, f'{label}.stderr.log')
    ok, res, reason = _run_command_backend(argv, {}, stdout_path, stderr_path, wait=False)
    return {
        'label': label,
        'backend': backend,
        'argv': res.get('argv') or argv,
        'pid': int(res.get('pid') or 0),
        'started_at': _nowz(),
        'stdout_path': stdout_path,
        'stderr_path': stderr_path,
        'status': 'running' if ok else 'failed',
        'reason': reason,
    }


# === NoemaForge Autodoc Function Header ===
# Function: _handoff_notes(policy: Dict[str, Any], session_id: str)
# Purpose: Build human-readable Discord desktop handoff instructions.
# Inputs:
#   - policy: Dict[str, Any]
#   - session_id: str
# Called by:
#   - start_bridge
# Returns / emits: List[str]
# === End NoemaForge Autodoc Function Header ===
def _handoff_notes(policy: Dict[str, Any], session_id: str) -> List[str]:
    client = policy.get('discord_client') or {}
    notes = [str(x) for x in (client.get('launch_notes') or []) if str(x).strip()]
    notes.append(f'Session id: {session_id}')
    if str(client.get('recommended_video_device') or '').strip():
        notes.append(f"Video device: {str(client.get('recommended_video_device') or '').strip()}")
    if str(client.get('recommended_audio_source') or '').strip():
        notes.append(f"Audio source: {str(client.get('recommended_audio_source') or '').strip()}")
    return notes


# === NoemaForge Autodoc Function Header ===
# Function: start_bridge(background_prompt: str = "", mask_prompt: str = "", policy_path: str = DEFAULT_POLICY_PATH, policy_override: Optional[Dict[str, Any]] = None, existing_assets_manifest: str = "")
# Purpose: Start a local Discord desktop bridge session and persist a session manifest.
# Inputs:
#   - background_prompt: str = ""
#   - mask_prompt: str = ""
#   - policy_path: str = DEFAULT_POLICY_PATH
#   - policy_override: Optional[Dict[str, Any]] = None
#   - existing_assets_manifest: str = ""
# Called by:
#   - prepare_tool_action
# Returns / emits: Dict[str, Any]
# Side effects:
#   - writes session manifests
#   - may spawn video/audio worker subprocesses
# === End NoemaForge Autodoc Function Header ===
def start_bridge(
    background_prompt: str = "",
    mask_prompt: str = "",
    policy_path: str = DEFAULT_POLICY_PATH,
    policy_override: Optional[Dict[str, Any]] = None,
    existing_assets_manifest: str = "",
) -> Dict[str, Any]:
    policy = _load_policy(policy_path=policy_path, policy_override=policy_override)
    if not bool(policy.get('enabled', False)):
        raise RuntimeError('discord_bridge_disabled')
    capture = policy.get('capture') or {}
    video_cfg = capture.get('video') or {}
    audio_cfg = capture.get('audio') or {}
    if not bool(video_cfg.get('enabled', False)) and not bool(audio_cfg.get('enabled', False)):
        raise RuntimeError('discord_bridge_no_enabled_media')

    sessions_root = _ensure_dir(str(policy.get('sessions_root') or DEFAULT_SESSIONS_ROOT))
    session_id = _slug('discord-session')
    session_root = _ensure_dir(os.path.join(sessions_root, session_id))
    assets: Dict[str, Any]
    if existing_assets_manifest:
        assets = _read_json(existing_assets_manifest)
    else:
        assets = prepare_assets(background_prompt=background_prompt, mask_prompt=mask_prompt, policy_override=policy, policy_path=policy_path)
    background = assets.get('background') if isinstance(assets.get('background'), dict) else {}
    mask = assets.get('mask') if isinstance(assets.get('mask'), dict) else {}
    workers: List[Dict[str, Any]] = []

    if bool(video_cfg.get('enabled', False)):
        backend_order = [str(x).strip() for x in (video_cfg.get('backend_order') or []) if str(x).strip()]
        started = False
        for backend in backend_order:
            if backend == 'ffmpeg':
                argv = _build_ffmpeg_video_argv(policy, session_root, background, mask)
                workers.append(_start_worker('video', 'ffmpeg', argv, session_root))
                started = True
                break
            if backend == 'command':
                output_path = str(video_cfg.get('output_path') or os.path.join(session_root, 'video-bridge.bin'))
                argv = [str(p).format(
                    session_id=session_id,
                    session_root=session_root,
                    output_path=output_path,
                    background_path=str(background.get('path') or ''),
                    mask_path=str(mask.get('path') or ''),
                    av_delay_ms=int(capture.get('av_delay_ms') or 0),
                ) for p in list(((video_cfg.get('command') or {}).get('argv') or []))]
                if argv:
                    workers.append(_start_worker('video', 'command', argv, session_root))
                    started = True
                    break
        if not started:
            raise RuntimeError('discord_video_backend_unavailable')

    if bool(audio_cfg.get('enabled', False)):
        backend_order = [str(x).strip() for x in (audio_cfg.get('backend_order') or []) if str(x).strip()]
        started = False
        for backend in backend_order:
            if backend == 'ffmpeg':
                argv = _build_ffmpeg_audio_argv(policy, session_root)
                workers.append(_start_worker('audio', 'ffmpeg', argv, session_root))
                started = True
                break
            if backend == 'command':
                output_path = str(audio_cfg.get('output_path') or os.path.join(session_root, 'audio-bridge.bin'))
                argv = [str(p).format(
                    session_id=session_id,
                    session_root=session_root,
                    output_path=output_path,
                    av_delay_ms=int(audio_cfg.get('delay_ms') or capture.get('av_delay_ms') or 0),
                ) for p in list(((audio_cfg.get('command') or {}).get('argv') or []))]
                if argv:
                    workers.append(_start_worker('audio', 'command', argv, session_root))
                    started = True
                    break
        if not started:
            raise RuntimeError('discord_audio_backend_unavailable')

    manifest = {
        'apiVersion': 'noemaforge.discordbridge/v1',
        'kind': 'DiscordBridgeSession',
        'session_id': session_id,
        'created_at': _nowz(),
        'updated_at': _nowz(),
        'mode': str(policy.get('mode') or 'desktop_bridge'),
        'session_root': session_root,
        'assets_manifest_path': str(assets.get('manifest_path') or ''),
        'background': background,
        'mask': mask,
        'workers': workers,
        'assistant_alias': str(((policy.get('assistant_bridge') or {}).get('default_alias') or 'administrator')),
        'handoff_notes': _handoff_notes(policy, session_id),
    }
    manifest_path = _write_json(os.path.join(session_root, 'session.json'), manifest)
    manifest['manifest_path'] = manifest_path
    return manifest


# === NoemaForge Autodoc Function Header ===
# Function: bridge_status(manifest_path: str = "", session_id: str = "", policy_path: str = DEFAULT_POLICY_PATH, policy_override: Optional[Dict[str, Any]] = None)
# Purpose: Return runtime status for a Discord bridge session.
# Inputs:
#   - manifest_path: str = ""
#   - session_id: str = ""
#   - policy_path: str = DEFAULT_POLICY_PATH
#   - policy_override: Optional[Dict[str, Any]] = None
# Called by:
#   - prepare_tool_action
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads session manifests
# === End NoemaForge Autodoc Function Header ===
def bridge_status(
    manifest_path: str = "",
    session_id: str = "",
    policy_path: str = DEFAULT_POLICY_PATH,
    policy_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    policy = _load_policy(policy_path=policy_path, policy_override=policy_override)
    if not manifest_path and session_id:
        manifest_path = os.path.join(str(policy.get('sessions_root') or DEFAULT_SESSIONS_ROOT), session_id, 'session.json')
    manifest = _read_json(manifest_path)
    workers = []
    for worker in manifest.get('workers') or []:
        if not isinstance(worker, dict):
            continue
        doc = dict(worker)
        pid = int(doc.get('pid') or 0)
        doc['alive'] = _pid_alive(pid)
        if doc['status'] == 'running' and not doc['alive']:
            doc['status'] = 'stopped'
        workers.append(doc)
    manifest['workers'] = workers
    manifest['updated_at'] = _nowz()
    return manifest


# === NoemaForge Autodoc Function Header ===
# Function: stop_bridge(manifest_path: str = "", session_id: str = "", policy_path: str = DEFAULT_POLICY_PATH, policy_override: Optional[Dict[str, Any]] = None)
# Purpose: Stop a running Discord bridge session and persist final worker state.
# Inputs:
#   - manifest_path: str = ""
#   - session_id: str = ""
#   - policy_path: str = DEFAULT_POLICY_PATH
#   - policy_override: Optional[Dict[str, Any]] = None
# Called by:
#   - prepare_tool_action
# Returns / emits: Dict[str, Any]
# Side effects:
#   - sends termination signals
#   - writes session manifests
# === End NoemaForge Autodoc Function Header ===
def stop_bridge(
    manifest_path: str = "",
    session_id: str = "",
    policy_path: str = DEFAULT_POLICY_PATH,
    policy_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    status = bridge_status(manifest_path=manifest_path, session_id=session_id, policy_path=policy_path, policy_override=policy_override)
    stopped: List[Dict[str, Any]] = []
    for worker in status.get('workers') or []:
        if not isinstance(worker, dict):
            continue
        pid = int(worker.get('pid') or 0)
        terminated = _terminate_pid(pid) if worker.get('alive') else False
        doc = dict(worker)
        doc['alive'] = _pid_alive(pid)
        doc['terminated'] = terminated
        doc['status'] = 'stopped'
        stopped.append(doc)
    status['workers'] = stopped
    status['updated_at'] = _nowz()
    status['stopped_at'] = _nowz()
    manifest_path_final = str(status.get('manifest_path') or manifest_path or '')
    if manifest_path_final:
        _write_json(manifest_path_final, status)
    return status


# === NoemaForge Autodoc Function Header ===
# Function: prepare_tool_action(action: str, args: Dict[str, Any], policy_path: str = DEFAULT_POLICY_PATH)
# Purpose: ToolProxy-facing facade for Discord bridge asset and session actions.
# Inputs:
#   - action: str
#   - args: Dict[str, Any]
#   - policy_path: str = DEFAULT_POLICY_PATH
# Called by:
#   - src/toolproxy.py
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# === End NoemaForge Autodoc Function Header ===
def prepare_tool_action(action: str, args: Dict[str, Any], policy_path: str = DEFAULT_POLICY_PATH) -> Tuple[bool, Dict[str, Any], str]:
    action = str(action or '').strip()
    args = args if isinstance(args, dict) else {}
    override = args.get('policy_override') if isinstance(args.get('policy_override'), dict) else None
    try:
        if action == 'discord.assets.prepare':
            res = prepare_assets(
                background_prompt=str(args.get('background_prompt') or ''),
                mask_prompt=str(args.get('mask_prompt') or ''),
                policy_path=str(args.get('policy_path') or policy_path),
                policy_override=override,
            )
            return True, res, 'ok'
        if action == 'discord.bridge.start':
            res = start_bridge(
                background_prompt=str(args.get('background_prompt') or ''),
                mask_prompt=str(args.get('mask_prompt') or ''),
                existing_assets_manifest=str(args.get('assets_manifest_path') or ''),
                policy_path=str(args.get('policy_path') or policy_path),
                policy_override=override,
            )
            return True, res, 'ok'
        if action == 'discord.bridge.status':
            res = bridge_status(
                manifest_path=str(args.get('manifest_path') or ''),
                session_id=str(args.get('session_id') or ''),
                policy_path=str(args.get('policy_path') or policy_path),
                policy_override=override,
            )
            return True, res, 'ok'
        if action == 'discord.bridge.stop':
            res = stop_bridge(
                manifest_path=str(args.get('manifest_path') or ''),
                session_id=str(args.get('session_id') or ''),
                policy_path=str(args.get('policy_path') or policy_path),
                policy_override=override,
            )
            return True, res, 'ok'
    except Exception as e:
        return False, {'error': repr(e)}, 'discord_bridge_failed'
    return False, {'error': 'unsupported_action', 'action': action}, 'unsupported_action'
