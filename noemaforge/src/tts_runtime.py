#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/tts_runtime.py
Zone: release/package
Version: 0.32.1
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
# File: src/tts_runtime.py
# Purpose: Provide a local text-to-speech runtime and backchannel injection path for live calls without bypassing ToolProxy.
# Invoked by / imported from:
#   - src/toolproxy.py
#   - tests/test_tts_runtime.py
# Public API / entry functions:
#   - synthesize_text
#   - inject_audio
#   - tts_backchannel
#   - prepare_tool_action
# Inputs:
#   - text, voice_id, session_id, and optional policy overrides passed through ToolProxy or direct callers.
#   - Runtime policy from configs/tts-backends-policy.yaml.
# Output formats / side effects:
#   - WAV artifacts and JSON manifests under the configured outbox/state roots.
#   - Optional command or ffmpeg subprocesses for audio injection into a virtual microphone path.
# Security considerations:
#   - Never performs network I/O.
#   - Only uses local command backends or local binaries explicitly allowed by policy.
#   - Intended to be mediated by ToolProxy when exposed to roles.
# AutoDoc: refreshed 2026-04-11 (manual)
# === End NoemaForge Autodoc File Header ===

"""tts_runtime.py (v0.27.0)

Local text-to-speech runtime for NoemaForge.

This module closes the "listen -> transcribe -> route -> speak back" loop for the
Administrator path without introducing direct app-specific media APIs. The runtime
synthesizes a local audio artifact and injects it into a configured virtual-microphone
handoff backend.

Supported synthesis backends:
- command: host-specific wrapper or test helper.
- espeak_ng: local CLI synthesis when installed.
- piper: local neural TTS CLI when installed.

Supported injection backends:
- command: host-specific bridge into PipeWire/Pulse/other routing.
- ffmpeg: stream an audio file into a Pulse sink or write a delayed local file.
- file_copy: deterministic artifact handoff for testing or manual routing.
"""


import datetime as dt
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

DEFAULT_POLICY_PATH = "/opt/noemaforge/configs/tts-backends-policy.yaml"
DEFAULT_ARTIFACTS_ROOT = "/workspace/outbox/tts"
DEFAULT_SESSIONS_ROOT = "/workspace/state/tts_sessions"
LIVE_PROCS: Dict[int, subprocess.Popen[Any]] = {}


def _nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _slug(prefix: str = 'tts') -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _write_json(path: str, payload: Dict[str, Any]) -> str:
    _ensure_dir(os.path.dirname(path) or '.')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(dict(out.get(key) or {}), value)
        else:
            out[key] = value
    return out


def _default_policy() -> Dict[str, Any]:
    return {
        'apiVersion': 'noemaforge.tts/v1',
        'kind': 'TTSBackendsPolicy',
        'enabled': False,
        'artifacts_root': DEFAULT_ARTIFACTS_ROOT,
        'sessions_root': DEFAULT_SESSIONS_ROOT,
        'synthesis': {
            'enabled': False,
            'backend_order': ['command', 'espeak_ng', 'piper'],
            'default_voice_id': 'administrator',
            'sample_rate_hz': 22050,
            'command': {'argv': []},
            'espeak_ng': {'executable': 'espeak-ng', 'voice': 'en', 'speed_wpm': 170, 'pitch': 45},
            'piper': {'executable': 'piper', 'model_path': '', 'speaker': 0, 'noise_scale': 0.667},
        },
        'backchannel': {
            'enabled': False,
            'backend_order': ['command', 'ffmpeg', 'file_copy'],
            'output_mode': 'pulse_sink',
            'output_target': 'noemaforge-discord',
            'output_path': '',
            'ffmpeg_executable': 'ffmpeg',
            'command': {'argv': []},
            'retain_artifacts': True,
        },
    }


def _load_policy(policy_path: str = DEFAULT_POLICY_PATH, policy_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = _default_policy()
    loaded: Dict[str, Any] = {}
    if policy_path and os.path.exists(policy_path) and yaml is not None:
        try:
            with open(policy_path, 'r', encoding='utf-8') as f:
                doc = yaml.safe_load(f) or {}
            if isinstance(doc, dict):
                loaded = doc
        except Exception:
            loaded = {}
    merged = _deep_merge(base, loaded)
    if isinstance(policy_override, dict):
        merged = _deep_merge(merged, policy_override)
    return merged


def _format_argv(argv: List[str], mapping: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for item in (argv or []):
        token = str(item)
        for key, value in mapping.items():
            token = token.replace('{' + key + '}', str(value))
        out.append(token)
    return out


def _run(argv: List[str], *, input_text: Optional[str] = None) -> Tuple[bool, Dict[str, Any], str]:
    if not argv:
        return False, {'error': 'missing_argv'}, 'tts_missing_argv'
    try:
        cp = subprocess.run(argv, input=(input_text.encode('utf-8') if input_text is not None else None), capture_output=True, check=False)
        ok = cp.returncode == 0
        result = {
            'argv': argv,
            'returncode': cp.returncode,
            'stdout': cp.stdout.decode('utf-8', 'replace'),
            'stderr': cp.stderr.decode('utf-8', 'replace'),
        }
        return ok, result, 'ok' if ok else 'tts_exec_failed'
    except Exception as e:
        return False, {'error': repr(e), 'argv': argv}, 'tts_exec_failed'


def synthesize_text(
    *,
    text: str,
    voice_id: str = '',
    session_id: str = '',
    policy_path: str = DEFAULT_POLICY_PATH,
    policy_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    policy = _load_policy(policy_path=policy_path, policy_override=policy_override)
    synth = policy.get('synthesis') if isinstance(policy.get('synthesis'), dict) else {}
    if not bool(policy.get('enabled')) or not bool((synth or {}).get('enabled')):
        raise RuntimeError('tts_disabled_by_policy')
    text_norm = str(text or '').strip()
    if not text_norm:
        raise RuntimeError('tts_missing_text')

    sess = str(session_id or _slug('tts'))
    voice = str(voice_id or (synth or {}).get('default_voice_id') or 'default').strip() or 'default'
    artifacts_root = _ensure_dir(str(policy.get('artifacts_root') or DEFAULT_ARTIFACTS_ROOT))
    session_root = _ensure_dir(os.path.join(str(policy.get('sessions_root') or DEFAULT_SESSIONS_ROOT), sess))
    wav_path = os.path.join(artifacts_root, f'{sess}.wav')
    manifest_path = os.path.join(session_root, 'tts_manifest.json')

    mapping = {
        'text': text_norm,
        'voice_id': voice,
        'output_path': wav_path,
        'session_id': sess,
    }
    attempts: List[Dict[str, Any]] = []

    for backend in [str(x) for x in (synth or {}).get('backend_order', []) if str(x).strip()]:
        if backend == 'command':
            argv = _format_argv(list((((synth or {}).get('command') or {}).get('argv') or [])), mapping)
            ok, result, reason = _run(argv, input_text=text_norm)
            attempts.append({'backend': backend, 'result': result, 'reason': reason})
            if ok and os.path.exists(wav_path):
                manifest = {
                    'ok': True,
                    'session_id': sess,
                    'text': text_norm,
                    'voice_id': voice,
                    'backend': backend,
                    'audio_path': wav_path,
                    'manifest_path': manifest_path,
                    'attempts': attempts,
                    'generated_at': _nowz(),
                }
                _write_json(manifest_path, manifest)
                return manifest
            continue

        if backend == 'espeak_ng':
            cfg = (synth or {}).get('espeak_ng') or {}
            argv = [
                str(cfg.get('executable') or 'espeak-ng'), '-w', wav_path,
                '-v', str(cfg.get('voice') or 'en'), '-s', str(int(cfg.get('speed_wpm') or 170)),
                '-p', str(int(cfg.get('pitch') or 45)), text_norm,
            ]
            ok, result, reason = _run(argv)
            attempts.append({'backend': backend, 'result': result, 'reason': reason})
            if ok and os.path.exists(wav_path):
                manifest = {
                    'ok': True,
                    'session_id': sess,
                    'text': text_norm,
                    'voice_id': voice,
                    'backend': backend,
                    'audio_path': wav_path,
                    'manifest_path': manifest_path,
                    'attempts': attempts,
                    'generated_at': _nowz(),
                }
                _write_json(manifest_path, manifest)
                return manifest
            continue

        if backend == 'piper':
            cfg = (synth or {}).get('piper') or {}
            model_path = str(cfg.get('model_path') or '').strip()
            if not model_path:
                attempts.append({'backend': backend, 'reason': 'tts_model_missing'})
                continue
            argv = [str(cfg.get('executable') or 'piper'), '--model', model_path, '--output_file', wav_path]
            speaker = cfg.get('speaker')
            if speaker not in (None, ''):
                argv.extend(['--speaker', str(speaker)])
            noise_scale = cfg.get('noise_scale')
            if noise_scale not in (None, ''):
                argv.extend(['--noise_scale', str(noise_scale)])
            ok, result, reason = _run(argv, input_text=text_norm)
            attempts.append({'backend': backend, 'result': result, 'reason': reason})
            if ok and os.path.exists(wav_path):
                manifest = {
                    'ok': True,
                    'session_id': sess,
                    'text': text_norm,
                    'voice_id': voice,
                    'backend': backend,
                    'audio_path': wav_path,
                    'manifest_path': manifest_path,
                    'attempts': attempts,
                    'generated_at': _nowz(),
                }
                _write_json(manifest_path, manifest)
                return manifest
            continue

        attempts.append({'backend': backend, 'reason': 'tts_unknown_backend'})

    raise RuntimeError(json.dumps({'reason': 'tts_no_backend_succeeded', 'attempts': attempts}, ensure_ascii=False))


def inject_audio(
    *,
    artifact_path: str,
    session_id: str = '',
    policy_path: str = DEFAULT_POLICY_PATH,
    policy_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    policy = _load_policy(policy_path=policy_path, policy_override=policy_override)
    back = policy.get('backchannel') if isinstance(policy.get('backchannel'), dict) else {}
    if not bool(policy.get('enabled')) or not bool((back or {}).get('enabled')):
        raise RuntimeError('tts_backchannel_disabled')
    src = str(artifact_path or '').strip()
    if not src or not os.path.exists(src):
        raise RuntimeError('tts_audio_missing')

    sess = str(session_id or _slug('tts-inject'))
    session_root = _ensure_dir(os.path.join(str(policy.get('sessions_root') or DEFAULT_SESSIONS_ROOT), sess))
    manifest_path = os.path.join(session_root, 'backchannel_manifest.json')
    mapping = {
        'artifact_path': src,
        'session_id': sess,
        'output_target': str((back or {}).get('output_target') or ''),
        'output_path': str((back or {}).get('output_path') or ''),
    }
    attempts: List[Dict[str, Any]] = []

    for backend in [str(x) for x in ((back or {}).get('backend_order') or []) if str(x).strip()]:
        if backend == 'command':
            argv = _format_argv(list((((back or {}).get('command') or {}).get('argv') or [])), mapping)
            ok, result, reason = _run(argv)
            attempts.append({'backend': backend, 'result': result, 'reason': reason})
            if ok:
                manifest = {
                    'ok': True,
                    'session_id': sess,
                    'backend': backend,
                    'artifact_path': src,
                    'output_target': mapping['output_target'],
                    'output_path': mapping['output_path'],
                    'manifest_path': manifest_path,
                    'attempts': attempts,
                    'generated_at': _nowz(),
                }
                _write_json(manifest_path, manifest)
                return manifest
            continue

        if backend == 'ffmpeg':
            exe = str((back or {}).get('ffmpeg_executable') or 'ffmpeg')
            mode = str((back or {}).get('output_mode') or 'pulse_sink')
            target = str((back or {}).get('output_target') or '').strip()
            argv = [exe, '-nostdin', '-y', '-re', '-i', src]
            if mode == 'pulse_sink':
                if not target:
                    attempts.append({'backend': backend, 'reason': 'tts_missing_output_target'})
                    continue
                argv.extend(['-f', 'pulse', target])
            elif mode == 'file_copy':
                out_path = str((back or {}).get('output_path') or '').strip()
                if not out_path:
                    attempts.append({'backend': backend, 'reason': 'tts_missing_output_path'})
                    continue
                argv.append(out_path)
            else:
                attempts.append({'backend': backend, 'reason': 'tts_unknown_output_mode'})
                continue
            ok, result, reason = _run(argv)
            attempts.append({'backend': backend, 'result': result, 'reason': reason})
            if ok:
                manifest = {
                    'ok': True,
                    'session_id': sess,
                    'backend': backend,
                    'artifact_path': src,
                    'output_target': target,
                    'manifest_path': manifest_path,
                    'attempts': attempts,
                    'generated_at': _nowz(),
                }
                _write_json(manifest_path, manifest)
                return manifest
            continue

        if backend == 'file_copy':
            out_path = str((back or {}).get('output_path') or '').strip()
            if not out_path:
                attempts.append({'backend': backend, 'reason': 'tts_missing_output_path'})
                continue
            _ensure_dir(os.path.dirname(out_path) or '.')
            shutil.copy2(src, out_path)
            manifest = {
                'ok': True,
                'session_id': sess,
                'backend': backend,
                'artifact_path': src,
                'output_path': out_path,
                'manifest_path': manifest_path,
                'attempts': attempts + [{'backend': backend, 'reason': 'ok'}],
                'generated_at': _nowz(),
            }
            _write_json(manifest_path, manifest)
            return manifest

        attempts.append({'backend': backend, 'reason': 'tts_unknown_backend'})

    raise RuntimeError(json.dumps({'reason': 'tts_inject_failed', 'attempts': attempts}, ensure_ascii=False))


def tts_backchannel(
    *,
    text: str,
    voice_id: str = '',
    session_id: str = '',
    policy_path: str = DEFAULT_POLICY_PATH,
    policy_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    session = str(session_id or _slug('tts-roundtrip'))
    synth = synthesize_text(text=text, voice_id=voice_id, session_id=session, policy_path=policy_path, policy_override=policy_override)
    inject = inject_audio(artifact_path=str(synth.get('audio_path') or ''), session_id=session, policy_path=policy_path, policy_override=policy_override)
    return {
        'ok': True,
        'session_id': session,
        'text': text,
        'voice_id': voice_id or synth.get('voice_id') or 'default',
        'audio': synth,
        'tts': synth,
        'backchannel': inject,
        'generated_at': _nowz(),
    }


def prepare_tool_action(action: str, args: Dict[str, Any], policy_path: str = DEFAULT_POLICY_PATH) -> Tuple[bool, Dict[str, Any], str]:
    args = args if isinstance(args, dict) else {}
    policy_override = args.get('tts_policy_override') if isinstance(args.get('tts_policy_override'), dict) else args.get('policy_override')
    try:
        if action == 'voice.tts_backchannel':
            result = tts_backchannel(
                text=str(args.get('text') or ''),
                voice_id=str(args.get('voice_id') or ''),
                session_id=str(args.get('session_id') or ''),
                policy_path=policy_path,
                policy_override=policy_override,
            )
            return True, result, 'ok'
    except Exception as e:
        return False, {'error': repr(e)}, 'tts_failed'
    return False, {'error': f'unsupported_action:{action}'}, 'unsupported_action'
