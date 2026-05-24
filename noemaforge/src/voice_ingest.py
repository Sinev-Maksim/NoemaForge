#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/voice_ingest.py
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
# File: src/voice_ingest.py
# Purpose: Provide offline-first and local-live voice runtime helpers behind ToolProxy, including file staging, live microphone capture, local STT execution, and chat-session artifacts.
# Invoked by / imported from:
#   - src/toolproxy.py
#   - tests/test_voice_ingest.py
#   - tests/test_toolproxy_voice_chat.py
# Public API / entry functions:
#   - capture
#   - transcribe
#   - capture_live
#   - transcribe_live
#   - build_chat_turn
#   - update_chat_session
#   - extract_assistant_text
#   - prepare_tool_action
# Inputs:
#   - audio_path / audio_bytes_b64 / manifest_path / transcript_text / transcript_path style arguments passed through ToolProxy.
#   - Live runtime policy from configs/voice-backends-policy.yaml.
#   - Common path inputs: /workspace/inbox/voice, /workspace/outbox/voice, /workspace/state/voice_sessions.
# Output formats / side effects:
#   - JSON manifests in inbox/outbox/state directories.
#   - staged or recorded audio files.
#   - transcript text artifacts and chat-session state files.
# Security considerations:
#   - Never performs network I/O.
#   - All execution is local and intended to be mediated only by ToolProxy.
#   - Live microphone / STT backends are policy-gated and may rely on optional local binaries or Python packages.
# AutoDoc: refreshed 2026-04-10 (manual, review before trusting for policy work)
# === End NoemaForge Autodoc File Header ===

"""voice_ingest.py (v0.26.5)

Offline-first and local-live voice runtime for the NoemaForge seed tree.

The module now supports two complementary modes:

1) Deterministic offline staging/import:
   - capture of an existing audio file
   - capture of base64-encoded audio bytes provided by the caller
   - manual transcript import
   - sidecar transcript import (.txt/.md/.srt/.vtt)

2) Local live voice execution:
   - fixed-duration microphone capture through optional local backends
   - local speech-to-text execution through optional offline backends
   - chat-turn preparation and session-state artifacts for talking to a configured
     assistant role through ToolProxy's routed llm.chat path

This keeps the contract honest: NoemaForge remains offline-first, network-free, and
ToolProxy-mediated, while gaining a real local live-voice path when microphone
and STT backends are enabled in policy.
"""


import base64
import datetime as dt
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import wave
from typing import Any, Dict, List, Optional, Tuple

try:  # Optional dependency used for policy loading.
    import yaml  # type: ignore
except Exception:  # pragma: no cover - checker/test environments may omit PyYAML
    yaml = None  # type: ignore


DEFAULT_INBOX = "/workspace/inbox/voice"
DEFAULT_OUTBOX = "/workspace/outbox/voice"
DEFAULT_SESSION_ROOT = "/workspace/state/voice_sessions"
DEFAULT_POLICY_PATH = "/opt/noemaforge/configs/voice-backends-policy.yaml"


# === NoemaForge Autodoc Function Header ===
# Function: _nowz()
# Purpose: Return an ISO8601 UTC timestamp.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - capture
#   - transcribe
#   - capture_live
#   - transcribe_live
#   - build_chat_turn
#   - update_chat_session
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


# === NoemaForge Autodoc Function Header ===
# Function: _slug()
# Purpose: Build a compact unique identifier for staged voice artifacts.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - capture
#   - transcribe
#   - capture_live
#   - transcribe_live
#   - build_chat_turn
#   - update_chat_session
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _slug() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


# === NoemaForge Autodoc Function Header ===
# Function: _deep_merge(base: Dict[str, Any], extra: Dict[str, Any])
# Purpose: Merge nested dictionaries without mutating the input arguments.
# Inputs:
#   - base: Dict[str, Any]
#   - extra: Dict[str, Any]
# Called by:
#   - _load_policy
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def _deep_merge(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base or {})
    for key, value in (extra or {}).items():
        if isinstance(out.get(key), dict) and isinstance(value, dict):
            out[key] = _deep_merge(dict(out.get(key) or {}), value)
        else:
            out[key] = value
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _default_policy()
# Purpose: Return the default live-voice policy used when no explicit policy file is available.
# Inputs:
#   - No explicit parameters.
# Called by:
#   - _load_policy
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def _default_policy() -> Dict[str, Any]:
    return {
        "apiVersion": "noemaforge.voicebackends/v1",
        "kind": "VoiceBackendsPolicy",
        "enabled": False,
        "microphone": {
            "enabled": False,
            "backend_order": ["sounddevice", "arecord", "ffmpeg", "command"],
            "sample_rate_hz": 16000,
            "channels": 1,
            "max_seconds": 15,
            "device": "",
            "ffmpeg_input_args": ["-f", "alsa", "-i", "default"],
            "command": {"argv": []},
        },
        "stt": {
            "enabled": False,
            "backend_order": ["faster_whisper", "whisper", "whisper_cli", "command"],
            "default_language": "",
            "device": "cpu",
            "model": "small",
            "model_path": "",
            "compute_type": "int8",
            "beam_size": 5,
            "vad_filter": True,
            "whisper_cli": {"executable": "", "argv": []},
            "command": {"argv": [], "result_mode": "stdout_text"},
        },
        "assistant": {
            "default_alias": "administrator",
            "history_root": DEFAULT_SESSION_ROOT,
            "max_turn_history": 12,
        },
        "assistant_targets": {
            "administrator": {
                "stream_id": "operator.admin",
                "role": "administrator",
                "title": "NoemaForge Administrator",
                "system_preamble": "You are the current NoemaForge administrator assistant. Be precise, operational, and explicit about next actions.",
            }
        },
    }


# === NoemaForge Autodoc Function Header ===
# Function: _load_policy(policy_path: str = DEFAULT_POLICY_PATH, policy_override: Optional[Dict[str, Any]] = None)
# Purpose: Load and normalize the live-voice policy.
# Inputs:
#   - policy_path: str = DEFAULT_POLICY_PATH
#   - policy_override: Optional[Dict[str, Any]] = None
# Called by:
#   - capture_live
#   - transcribe_live
#   - build_chat_turn
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads policy files when present
# === End NoemaForge Autodoc Function Header ===
def _load_policy(policy_path: str = DEFAULT_POLICY_PATH, policy_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = _default_policy()
    doc: Dict[str, Any] = {}
    if policy_path and os.path.exists(policy_path) and yaml is not None:
        try:
            with open(policy_path, "r", encoding="utf-8") as f:
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
# Function: _sha256_file(path: str)
# Purpose: Hash a staged file for manifest integrity.
# Inputs:
#   - path: str
# Called by:
#   - capture
#   - capture_live
# Returns / emits: str
# Side effects:
#   - reads files
# === End NoemaForge Autodoc Function Header ===
def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# === NoemaForge Autodoc Function Header ===
# Function: _save_json(path: str, obj: Dict[str, Any])
# Purpose: Save a JSON artifact atomically.
# Inputs:
#   - path: str
#   - obj: Dict[str, Any]
# Called by:
#   - capture
#   - transcribe
#   - capture_live
#   - transcribe_live
#   - update_chat_session
# Returns / emits: None
# Side effects:
#   - creates directories
#   - writes files
# === End NoemaForge Autodoc Function Header ===
def _save_json(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# === NoemaForge Autodoc Function Header ===
# Function: _load_json(path: str)
# Purpose: Load JSON from disk and return an empty dictionary when the file is missing or invalid.
# Inputs:
#   - path: str
# Called by:
#   - transcribe
#   - build_chat_turn
#   - update_chat_session
# Returns / emits: Dict[str, Any]
# Side effects:
#   - reads files
# === End NoemaForge Autodoc Function Header ===
def _load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# === NoemaForge Autodoc Function Header ===
# Function: _normalize_text(text: str)
# Purpose: Normalize transcript text imported from sidecar or STT outputs.
# Inputs:
#   - text: str
# Called by:
#   - _load_transcript_sidecar
#   - transcribe
#   - transcribe_live
#   - build_chat_turn
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _normalize_text(text: str) -> str:
    lines = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.fullmatch(r"\d+", line):
            continue
        if "-->" in line:
            continue
        if line.upper().startswith("WEBVTT"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


# === NoemaForge Autodoc Function Header ===
# Function: _write_audio_bytes(dest: str, audio_bytes_b64: str)
# Purpose: Decode caller-provided base64 audio and store it as a staged file.
# Inputs:
#   - dest: str
#   - audio_bytes_b64: str
# Called by:
#   - capture
# Returns / emits: None
# Side effects:
#   - writes files
# === End NoemaForge Autodoc Function Header ===
def _write_audio_bytes(dest: str, audio_bytes_b64: str) -> None:
    try:
        data = base64.b64decode(str(audio_bytes_b64 or ""), validate=True)
    except Exception as e:
        raise ValueError(f"invalid_audio_bytes_b64:{e!r}") from e
    if not data:
        raise ValueError("empty_audio_bytes")
    with open(dest, "wb") as f:
        f.write(data)


# === NoemaForge Autodoc Function Header ===
# Function: _load_transcript_sidecar(audio_path: str, transcript_path: str = '')
# Purpose: Load transcript text from an explicit path or a sidecar next to the audio file.
# Inputs:
#   - audio_path: str
#   - transcript_path: str = ''
# Called by:
#   - transcribe
#   - transcribe_live
# Returns / emits: Tuple[str, str]
# Side effects:
#   - reads files
# === End NoemaForge Autodoc Function Header ===
def _load_transcript_sidecar(audio_path: str, transcript_path: str = "") -> Tuple[str, str]:
    candidates: List[str] = []
    if str(transcript_path or "").strip():
        candidates.append(os.path.abspath(str(transcript_path)))
    base, _ext = os.path.splitext(os.path.abspath(str(audio_path or "")))
    candidates.extend([base + ".txt", base + ".md", base + ".srt", base + ".vtt"])
    seen = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        if not os.path.exists(cand):
            continue
        with open(cand, "r", encoding="utf-8", errors="replace") as f:
            text = _normalize_text(f.read())
        if text:
            return text, cand
    return "", ""


# === NoemaForge Autodoc Function Header ===
# Function: _format_argv(argv: List[str], values: Dict[str, Any])
# Purpose: Substitute placeholders in command-backend argument vectors.
# Inputs:
#   - argv: List[str]
#   - values: Dict[str, Any]
# Called by:
#   - _run_capture_command_backend
#   - _run_stt_command_backend
# Returns / emits: List[str]
# === End NoemaForge Autodoc Function Header ===
def _format_argv(argv: List[str], values: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for item in argv:
        txt = str(item)
        for key, value in values.items():
            txt = txt.replace("{" + str(key) + "}", str(value))
        out.append(txt)
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _detect_backend(explicit_backend: str, configured_order: List[Any], supported: Tuple[str, ...])
# Purpose: Select a backend name from an explicit override or an ordered configuration list.
# Inputs:
#   - explicit_backend: str
#   - configured_order: List[Any]
#   - supported: Tuple[str, ...]
# Called by:
#   - capture_live
#   - transcribe_live
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _detect_backend(explicit_backend: str, configured_order: List[Any], supported: Tuple[str, ...]) -> str:
    if str(explicit_backend or "").strip():
        return str(explicit_backend).strip()
    for item in configured_order or []:
        name = str(item or "").strip()
        if name and name in supported:
            return name
    return supported[0]


# === NoemaForge Autodoc Function Header ===
# Function: _write_pcm16_wav(path: str, pcm_bytes: bytes, sample_rate_hz: int, channels: int)
# Purpose: Persist PCM16 microphone samples as a WAV file.
# Inputs:
#   - path: str
#   - pcm_bytes: bytes
#   - sample_rate_hz: int
#   - channels: int
# Called by:
#   - _run_capture_sounddevice
# Returns / emits: None
# Side effects:
#   - writes files
# === End NoemaForge Autodoc Function Header ===
def _write_pcm16_wav(path: str, pcm_bytes: bytes, sample_rate_hz: int, channels: int) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(int(max(1, channels)))
        wf.setsampwidth(2)
        wf.setframerate(int(max(8000, sample_rate_hz)))
        wf.writeframes(pcm_bytes)


# === NoemaForge Autodoc Function Header ===
# Function: _run_capture_command_backend(output_path: str, mic_cfg: Dict[str, Any], duration_sec: float)
# Purpose: Record audio through a caller-specified command backend.
# Inputs:
#   - output_path: str
#   - mic_cfg: Dict[str, Any]
#   - duration_sec: float
# Called by:
#   - capture_live
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns local processes
#   - writes audio files through the configured backend
# === End NoemaForge Autodoc Function Header ===
def _run_capture_command_backend(output_path: str, mic_cfg: Dict[str, Any], duration_sec: float) -> Dict[str, Any]:
    cmd_cfg = mic_cfg.get("command") if isinstance(mic_cfg.get("command"), dict) else {}
    argv = [str(x) for x in (cmd_cfg.get("argv") or []) if str(x).strip()]
    if not argv:
        raise ValueError("voice_capture_command_missing_argv")
    values = {
        "output_path": output_path,
        "sample_rate_hz": int(mic_cfg.get("sample_rate_hz") or 16000),
        "channels": int(mic_cfg.get("channels") or 1),
        "max_seconds": float(duration_sec),
        "duration_sec": float(duration_sec),
        "device": str(mic_cfg.get("device") or ""),
    }
    proc = subprocess.run(_format_argv(argv, values), capture_output=True, text=True)
    if proc.returncode != 0:
        raise ValueError(f"voice_capture_command_failed:{proc.returncode}:{proc.stderr.strip()[:200]}")
    if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
        raise ValueError("voice_capture_command_missing_output")
    return {
        "backend": "command",
        "stdout": proc.stdout.strip()[:500],
        "stderr": proc.stderr.strip()[:500],
    }


# === NoemaForge Autodoc Function Header ===
# Function: _run_capture_arecord(output_path: str, mic_cfg: Dict[str, Any], duration_sec: float)
# Purpose: Record audio from ALSA through arecord.
# Inputs:
#   - output_path: str
#   - mic_cfg: Dict[str, Any]
#   - duration_sec: float
# Called by:
#   - capture_live
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns local processes
#   - writes audio files
# === End NoemaForge Autodoc Function Header ===
def _run_capture_arecord(output_path: str, mic_cfg: Dict[str, Any], duration_sec: float) -> Dict[str, Any]:
    binary = shutil.which(str(mic_cfg.get("arecord_bin") or "arecord"))
    if not binary:
        raise ValueError("voice_capture_arecord_missing")
    argv = [
        binary,
        "-q",
        "-f",
        "S16_LE",
        "-c",
        str(int(mic_cfg.get("channels") or 1)),
        "-r",
        str(int(mic_cfg.get("sample_rate_hz") or 16000)),
        "-d",
        str(max(1, int(round(duration_sec)))),
    ]
    device = str(mic_cfg.get("device") or "").strip()
    if device:
        argv.extend(["-D", device])
    argv.append(output_path)
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ValueError(f"voice_capture_arecord_failed:{proc.returncode}:{proc.stderr.strip()[:200]}")
    if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
        raise ValueError("voice_capture_arecord_missing_output")
    return {"backend": "arecord", "stderr": proc.stderr.strip()[:500]}


# === NoemaForge Autodoc Function Header ===
# Function: _run_capture_ffmpeg(output_path: str, mic_cfg: Dict[str, Any], duration_sec: float)
# Purpose: Record audio from a local ffmpeg-supported input source.
# Inputs:
#   - output_path: str
#   - mic_cfg: Dict[str, Any]
#   - duration_sec: float
# Called by:
#   - capture_live
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns local processes
#   - writes audio files
# === End NoemaForge Autodoc Function Header ===
def _run_capture_ffmpeg(output_path: str, mic_cfg: Dict[str, Any], duration_sec: float) -> Dict[str, Any]:
    binary = shutil.which(str(mic_cfg.get("ffmpeg_bin") or "ffmpeg"))
    if not binary:
        raise ValueError("voice_capture_ffmpeg_missing")
    input_args = [str(x) for x in (mic_cfg.get("ffmpeg_input_args") or []) if str(x).strip()]
    if not input_args:
        device = str(mic_cfg.get("device") or "default").strip() or "default"
        input_args = ["-f", "alsa", "-i", device]
    argv = [binary, "-hide_banner", "-loglevel", "error", "-y"] + input_args + [
        "-ac",
        str(int(mic_cfg.get("channels") or 1)),
        "-ar",
        str(int(mic_cfg.get("sample_rate_hz") or 16000)),
        "-t",
        str(float(duration_sec)),
        output_path,
    ]
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ValueError(f"voice_capture_ffmpeg_failed:{proc.returncode}:{proc.stderr.strip()[:200]}")
    if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
        raise ValueError("voice_capture_ffmpeg_missing_output")
    return {"backend": "ffmpeg", "stderr": proc.stderr.strip()[:500]}


# === NoemaForge Autodoc Function Header ===
# Function: _run_capture_sounddevice(output_path: str, mic_cfg: Dict[str, Any], duration_sec: float)
# Purpose: Record audio from a local sounddevice-compatible microphone.
# Inputs:
#   - output_path: str
#   - mic_cfg: Dict[str, Any]
#   - duration_sec: float
# Called by:
#   - capture_live
# Returns / emits: Dict[str, Any]
# Side effects:
#   - accesses the local audio input device
#   - writes audio files
# === End NoemaForge Autodoc Function Header ===
def _run_capture_sounddevice(output_path: str, mic_cfg: Dict[str, Any], duration_sec: float) -> Dict[str, Any]:
    try:
        import sounddevice as sd  # type: ignore
    except Exception as e:  # pragma: no cover - optional dependency
        raise ValueError(f"voice_capture_sounddevice_missing:{e!r}") from e
    sample_rate = int(mic_cfg.get("sample_rate_hz") or 16000)
    channels = int(mic_cfg.get("channels") or 1)
    frames = max(1, int(round(float(duration_sec) * sample_rate)))
    device = mic_cfg.get("device")
    try:
        rec = sd.rec(frames, samplerate=sample_rate, channels=channels, dtype="int16", device=(device or None))
        sd.wait()
        pcm_bytes = rec.tobytes()
    except Exception as e:  # pragma: no cover - hardware-dependent
        raise ValueError(f"voice_capture_sounddevice_failed:{e!r}") from e
    if not pcm_bytes:
        raise ValueError("voice_capture_sounddevice_empty")
    _write_pcm16_wav(output_path, pcm_bytes, sample_rate_hz=sample_rate, channels=channels)
    return {"backend": "sounddevice", "frames": frames}


# === NoemaForge Autodoc Function Header ===
# Function: capture(audio_path: str = '', audio_bytes_b64: str = '', filename: str = '', note: str = '', inbox_root: str = DEFAULT_INBOX)
# Purpose: Stage an audio artifact into the NoemaForge voice inbox and write a capture manifest.
# Inputs:
#   - audio_path: str = ''
#   - audio_bytes_b64: str = ''
#   - filename: str = ''
#   - note: str = ''
#   - inbox_root: str = DEFAULT_INBOX
# Called by:
#   - prepare_tool_action
#   - src/toolproxy.py
#   - tests/test_voice_ingest.py
# Returns / emits: Dict[str, Any]
# Side effects:
#   - copies or decodes audio files
#   - writes JSON manifests
# === End NoemaForge Autodoc Function Header ===
def capture(
    audio_path: str = "",
    audio_bytes_b64: str = "",
    filename: str = "",
    note: str = "",
    inbox_root: str = DEFAULT_INBOX,
) -> Dict[str, Any]:
    """Stage an audio artifact into the NoemaForge voice inbox and write a capture manifest."""
    os.makedirs(inbox_root, exist_ok=True)
    slug = _slug()
    src = os.path.abspath(str(audio_path or "").strip()) if str(audio_path or "").strip() else ""
    if not src and not str(audio_bytes_b64 or "").strip():
        raise ValueError("missing_audio_path_or_bytes")

    if src and not os.path.exists(src):
        raise ValueError("missing_audio_path")

    if src:
        ext = os.path.splitext(src)[1] or ".bin"
        original_name = os.path.basename(src)
    else:
        guessed = os.path.splitext(str(filename or "audio.bin"))[1] or ".bin"
        ext = guessed
        original_name = os.path.basename(str(filename or f"capture{ext}"))

    dest = os.path.join(inbox_root, slug + ext)
    if src:
        shutil.copy2(src, dest)
        source_mode = "file_copy"
    else:
        _write_audio_bytes(dest, str(audio_bytes_b64 or ""))
        source_mode = "inline_bytes"

    size_bytes = int(os.path.getsize(dest))
    media_type = str(mimetypes.guess_type(dest)[0] or "application/octet-stream")
    manifest = {
        "apiVersion": "noemaforge.voice/v1",
        "kind": "VoiceCapture",
        "capture_id": slug,
        "captured_at": _nowz(),
        "source_path": src,
        "source_mode": source_mode,
        "original_name": original_name,
        "captured_path": dest,
        "manifest_path": dest + ".json",
        "media_type": media_type,
        "size_bytes": size_bytes,
        "sha256": _sha256_file(dest),
        "note": str(note or ""),
        "status": "captured",
    }
    _save_json(manifest["manifest_path"], manifest)
    return manifest


# === NoemaForge Autodoc Function Header ===
# Function: capture_live(max_seconds: float = 0.0, note: str = '', inbox_root: str = DEFAULT_INBOX, policy_path: str = DEFAULT_POLICY_PATH, policy_override: Optional[Dict[str, Any]] = None, backend: str = '')
# Purpose: Capture live microphone audio through a local backend and stage the result into the voice inbox.
# Inputs:
#   - max_seconds: float = 0.0
#   - note: str = ''
#   - inbox_root: str = DEFAULT_INBOX
#   - policy_path: str = DEFAULT_POLICY_PATH
#   - policy_override: Optional[Dict[str, Any]] = None
#   - backend: str = ''
# Called by:
#   - prepare_tool_action
#   - transcribe_live
#   - build_chat_turn
#   - tests/test_voice_ingest.py
# Returns / emits: Dict[str, Any]
# Side effects:
#   - accesses the local microphone through the configured backend
#   - writes WAV files and JSON manifests
# === End NoemaForge Autodoc Function Header ===
def capture_live(
    max_seconds: float = 0.0,
    note: str = "",
    inbox_root: str = DEFAULT_INBOX,
    policy_path: str = DEFAULT_POLICY_PATH,
    policy_override: Optional[Dict[str, Any]] = None,
    backend: str = "",
) -> Dict[str, Any]:
    policy = _load_policy(policy_path=policy_path, policy_override=policy_override)
    if not bool(policy.get("enabled", False)):
        raise ValueError("voice_live_disabled")
    mic_cfg = policy.get("microphone") if isinstance(policy.get("microphone"), dict) else {}
    if not bool(mic_cfg.get("enabled", False)):
        raise ValueError("voice_microphone_disabled")

    duration_sec = float(max_seconds or mic_cfg.get("max_seconds") or 15)
    duration_sec = max(1.0, duration_sec)
    selected = _detect_backend(str(backend or ""), list(mic_cfg.get("backend_order") or []), ("sounddevice", "arecord", "ffmpeg", "command"))

    os.makedirs(inbox_root, exist_ok=True)
    slug = _slug()
    dest = os.path.join(inbox_root, slug + ".wav")

    if selected == "sounddevice":
        meta = _run_capture_sounddevice(dest, mic_cfg, duration_sec)
    elif selected == "arecord":
        meta = _run_capture_arecord(dest, mic_cfg, duration_sec)
    elif selected == "ffmpeg":
        meta = _run_capture_ffmpeg(dest, mic_cfg, duration_sec)
    elif selected == "command":
        meta = _run_capture_command_backend(dest, mic_cfg, duration_sec)
    else:
        raise ValueError("unsupported_voice_capture_backend")

    manifest = {
        "apiVersion": "noemaforge.voice/v1",
        "kind": "VoiceCapture",
        "capture_id": slug,
        "captured_at": _nowz(),
        "source_path": "",
        "source_mode": f"microphone:{selected}",
        "captured_path": dest,
        "manifest_path": dest + ".json",
        "media_type": "audio/wav",
        "size_bytes": int(os.path.getsize(dest)),
        "sha256": _sha256_file(dest),
        "note": str(note or ""),
        "status": "captured",
        "backend_meta": meta,
        "duration_sec": duration_sec,
        "policy_path": policy_path,
    }
    _save_json(manifest["manifest_path"], manifest)
    return manifest


# === NoemaForge Autodoc Function Header ===
# Function: transcribe(audio_path: str = '', manifest_path: str = '', transcript_text: str = '', transcript_path: str = '', language: str = '', inbox_root: str = DEFAULT_INBOX, outbox_root: str = DEFAULT_OUTBOX)
# Purpose: Import transcript content or create a deferred transcription request.
# Inputs:
#   - audio_path: str = ''
#   - manifest_path: str = ''
#   - transcript_text: str = ''
#   - transcript_path: str = ''
#   - language: str = ''
#   - inbox_root: str = DEFAULT_INBOX
#   - outbox_root: str = DEFAULT_OUTBOX
# Called by:
#   - prepare_tool_action
#   - src/toolproxy.py
#   - tests/test_voice_ingest.py
# Returns / emits: Dict[str, Any]
# Side effects:
#   - writes JSON artifacts
#   - writes transcript text files when transcript content is available
# === End NoemaForge Autodoc Function Header ===
def transcribe(
    audio_path: str = "",
    manifest_path: str = "",
    transcript_text: str = "",
    transcript_path: str = "",
    language: str = "",
    inbox_root: str = DEFAULT_INBOX,
    outbox_root: str = DEFAULT_OUTBOX,
) -> Dict[str, Any]:
    """Import transcript content or create a deferred transcription request."""
    os.makedirs(outbox_root, exist_ok=True)
    capture_manifest: Dict[str, Any] = {}
    original_audio_path = str(audio_path or "")
    if manifest_path:
        mp = os.path.abspath(manifest_path)
        if not os.path.exists(mp):
            raise ValueError("missing_capture_manifest")
        capture_manifest = _load_json(mp)
        audio_path = str(capture_manifest.get("captured_path") or audio_path or "")
    elif audio_path:
        cap = capture(audio_path=audio_path, note="auto-captured for transcription", inbox_root=inbox_root)
        capture_manifest = cap
        manifest_path = str(cap.get("manifest_path") or "")
        audio_path = str(cap.get("captured_path") or audio_path or "")
    else:
        raise ValueError("missing_audio_or_manifest")

    req_id = _slug()
    normalized_text = _normalize_text(transcript_text)
    sidecar_used = ""
    if not normalized_text:
        normalized_text, sidecar_used = _load_transcript_sidecar(audio_path=audio_path, transcript_path=transcript_path)
    if not normalized_text and str(original_audio_path or "").strip() and os.path.abspath(original_audio_path) != os.path.abspath(str(audio_path or "")):
        normalized_text, sidecar_used = _load_transcript_sidecar(audio_path=original_audio_path, transcript_path=transcript_path)

    if normalized_text:
        txt_path = os.path.join(outbox_root, req_id + ".txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(normalized_text)
        artifact = {
            "apiVersion": "noemaforge.voice/v1",
            "kind": "VoiceTranscript",
            "request_id": req_id,
            "created_at": _nowz(),
            "source_audio_path": audio_path,
            "capture_manifest_path": manifest_path,
            "language": str(language or ""),
            "transcript_path": txt_path,
            "transcript_preview": normalized_text[:200],
            "status": "complete",
            "mode": "manual" if str(transcript_text or "").strip() else "sidecar_import",
            "sidecar_path": sidecar_used,
        }
        json_path = os.path.join(outbox_root, req_id + ".json")
        artifact["artifact_path"] = json_path
        _save_json(json_path, artifact)
        return artifact

    job = {
        "apiVersion": "noemaforge.voice/v1",
        "kind": "VoiceTranscriptionRequest",
        "request_id": req_id,
        "created_at": _nowz(),
        "source_audio_path": audio_path,
        "capture_manifest_path": manifest_path,
        "language": str(language or ""),
        "preferred_engine": "bundle_or_plugin",
        "status": "queued",
        "mode": "deferred",
    }
    job_path = os.path.join(outbox_root, req_id + ".json")
    job["job_path"] = job_path
    _save_json(job_path, job)
    return job


# === NoemaForge Autodoc Function Header ===
# Function: _run_stt_command_backend(audio_path: str, stt_cfg: Dict[str, Any], language: str, outbox_root: str)
# Purpose: Run a caller-defined STT command backend and normalize its output.
# Inputs:
#   - audio_path: str
#   - stt_cfg: Dict[str, Any]
#   - language: str
#   - outbox_root: str
# Called by:
#   - transcribe_live
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns local processes
#   - may write temp files requested by the backend
# === End NoemaForge Autodoc Function Header ===
def _run_stt_command_backend(audio_path: str, stt_cfg: Dict[str, Any], language: str, outbox_root: str) -> Dict[str, Any]:
    cmd_cfg = stt_cfg.get("command") if isinstance(stt_cfg.get("command"), dict) else {}
    argv = [str(x) for x in (cmd_cfg.get("argv") or []) if str(x).strip()]
    if not argv:
        raise ValueError("voice_stt_command_missing_argv")
    request_id = _slug()
    os.makedirs(outbox_root, exist_ok=True)
    out_txt = os.path.join(outbox_root, request_id + ".backend.txt")
    out_json = os.path.join(outbox_root, request_id + ".backend.json")
    values = {
        "audio_path": audio_path,
        "language": str(language or stt_cfg.get("default_language") or ""),
        "model": str(stt_cfg.get("model") or "small"),
        "model_path": str(stt_cfg.get("model_path") or ""),
        "output_text_path": out_txt,
        "output_json_path": out_json,
        "request_id": request_id,
    }
    proc = subprocess.run(_format_argv(argv, values), capture_output=True, text=True)
    if proc.returncode != 0:
        raise ValueError(f"voice_stt_command_failed:{proc.returncode}:{proc.stderr.strip()[:200]}")

    mode = str(cmd_cfg.get("result_mode") or "stdout_text").strip()
    if mode == "stdout_text":
        text = _normalize_text(proc.stdout)
        return {"text": text, "language": values["language"], "segments": []}
    if mode == "stdout_json":
        try:
            data = json.loads(proc.stdout)
        except Exception as e:
            raise ValueError(f"voice_stt_command_bad_json:{e!r}") from e
        if not isinstance(data, dict):
            raise ValueError("voice_stt_command_json_not_object")
        return data
    if mode == "text_file":
        if not os.path.exists(out_txt):
            raise ValueError("voice_stt_command_missing_text_file")
        with open(out_txt, "r", encoding="utf-8", errors="replace") as f:
            return {"text": _normalize_text(f.read()), "language": values["language"], "segments": []}
    if mode == "json_file":
        if not os.path.exists(out_json):
            raise ValueError("voice_stt_command_missing_json_file")
        data = _load_json(out_json)
        if not data:
            raise ValueError("voice_stt_command_empty_json_file")
        return data
    raise ValueError("voice_stt_command_unknown_result_mode")


# === NoemaForge Autodoc Function Header ===
# Function: _run_stt_faster_whisper(audio_path: str, stt_cfg: Dict[str, Any], language: str)
# Purpose: Transcribe audio through the optional faster-whisper Python backend.
# Inputs:
#   - audio_path: str
#   - stt_cfg: Dict[str, Any]
#   - language: str
# Called by:
#   - transcribe_live
# Returns / emits: Dict[str, Any]
# Side effects:
#   - loads a local STT model into memory
# === End NoemaForge Autodoc Function Header ===
def _run_stt_faster_whisper(audio_path: str, stt_cfg: Dict[str, Any], language: str) -> Dict[str, Any]:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as e:  # pragma: no cover - optional dependency
        raise ValueError(f"voice_stt_faster_whisper_missing:{e!r}") from e
    model_name = str(stt_cfg.get("model_path") or stt_cfg.get("model") or "small")
    model = WhisperModel(
        model_name,
        device=str(stt_cfg.get("device") or "cpu"),
        compute_type=str(stt_cfg.get("compute_type") or "int8"),
    )
    segments_iter, info = model.transcribe(
        audio_path,
        language=(str(language or "").strip() or None),
        beam_size=int(stt_cfg.get("beam_size") or 5),
        vad_filter=bool(stt_cfg.get("vad_filter", True)),
    )
    segments = []
    texts = []
    for seg in segments_iter:
        txt = str(getattr(seg, "text", "") or "").strip()
        if txt:
            texts.append(txt)
        segments.append(
            {
                "start": float(getattr(seg, "start", 0.0) or 0.0),
                "end": float(getattr(seg, "end", 0.0) or 0.0),
                "text": txt,
            }
        )
    return {
        "text": _normalize_text(" ".join(texts)),
        "language": str(getattr(info, "language", language or "") or ""),
        "segments": segments,
    }


# === NoemaForge Autodoc Function Header ===
# Function: _run_stt_whisper(audio_path: str, stt_cfg: Dict[str, Any], language: str)
# Purpose: Transcribe audio through the optional openai-whisper Python backend.
# Inputs:
#   - audio_path: str
#   - stt_cfg: Dict[str, Any]
#   - language: str
# Called by:
#   - transcribe_live
# Returns / emits: Dict[str, Any]
# Side effects:
#   - loads a local STT model into memory
# === End NoemaForge Autodoc Function Header ===
def _run_stt_whisper(audio_path: str, stt_cfg: Dict[str, Any], language: str) -> Dict[str, Any]:
    try:
        import whisper  # type: ignore
    except Exception as e:  # pragma: no cover - optional dependency
        raise ValueError(f"voice_stt_whisper_missing:{e!r}") from e
    model_name = str(stt_cfg.get("model_path") or stt_cfg.get("model") or "small")
    model = whisper.load_model(model_name)
    result = model.transcribe(
        audio_path,
        language=(str(language or "").strip() or None),
        fp16=False,
        condition_on_previous_text=False,
        temperature=0.0,
    )
    segments = []
    for seg in (result.get("segments") or []):
        if not isinstance(seg, dict):
            continue
        segments.append(
            {
                "start": float(seg.get("start") or 0.0),
                "end": float(seg.get("end") or 0.0),
                "text": str(seg.get("text") or "").strip(),
            }
        )
    return {
        "text": _normalize_text(str(result.get("text") or "")),
        "language": str(result.get("language") or language or ""),
        "segments": segments,
    }


# === NoemaForge Autodoc Function Header ===
# Function: _run_stt_whisper_cli(audio_path: str, stt_cfg: Dict[str, Any], language: str, outbox_root: str)
# Purpose: Transcribe audio through an external whisper.cpp-style CLI backend.
# Inputs:
#   - audio_path: str
#   - stt_cfg: Dict[str, Any]
#   - language: str
#   - outbox_root: str
# Called by:
#   - transcribe_live
# Returns / emits: Dict[str, Any]
# Side effects:
#   - spawns local processes
#   - writes backend output files
# === End NoemaForge Autodoc Function Header ===
def _run_stt_whisper_cli(audio_path: str, stt_cfg: Dict[str, Any], language: str, outbox_root: str) -> Dict[str, Any]:
    cli_cfg = stt_cfg.get("whisper_cli") if isinstance(stt_cfg.get("whisper_cli"), dict) else {}
    binary = str(cli_cfg.get("executable") or stt_cfg.get("whisper_cli_bin") or "").strip()
    if not binary:
        binary = shutil.which("whisper-cli") or shutil.which("main") or ""
    if not binary:
        raise ValueError("voice_stt_whisper_cli_missing")
    model_path = str(stt_cfg.get("model_path") or cli_cfg.get("model_path") or "").strip()
    if not model_path:
        raise ValueError("voice_stt_whisper_cli_missing_model")
    prefix = os.path.join(outbox_root, _slug())
    argv = [binary, "-m", model_path, "-f", audio_path, "-otxt", "-of", prefix]
    lang = str(language or "").strip()
    if lang:
        argv.extend(["-l", lang])
    extra = [str(x) for x in (cli_cfg.get("argv") or []) if str(x).strip()]
    argv.extend(extra)
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ValueError(f"voice_stt_whisper_cli_failed:{proc.returncode}:{proc.stderr.strip()[:200]}")
    txt_path = prefix + ".txt"
    if not os.path.exists(txt_path):
        raise ValueError("voice_stt_whisper_cli_missing_output")
    with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
        text = _normalize_text(f.read())
    return {"text": text, "language": lang, "segments": []}


# === NoemaForge Autodoc Function Header ===
# Function: transcribe_live(audio_path: str = '', manifest_path: str = '', transcript_text: str = '', transcript_path: str = '', language: str = '', from_microphone: bool = False, max_seconds: float = 0.0, inbox_root: str = DEFAULT_INBOX, outbox_root: str = DEFAULT_OUTBOX, policy_path: str = DEFAULT_POLICY_PATH, policy_override: Optional[Dict[str, Any]] = None, backend: str = '')
# Purpose: Run local STT on audio or live microphone input and emit transcript artifacts.
# Inputs:
#   - audio_path: str = ''
#   - manifest_path: str = ''
#   - transcript_text: str = ''
#   - transcript_path: str = ''
#   - language: str = ''
#   - from_microphone: bool = False
#   - max_seconds: float = 0.0
#   - inbox_root: str = DEFAULT_INBOX
#   - outbox_root: str = DEFAULT_OUTBOX
#   - policy_path: str = DEFAULT_POLICY_PATH
#   - policy_override: Optional[Dict[str, Any]] = None
#   - backend: str = ''
# Called by:
#   - prepare_tool_action
#   - build_chat_turn
#   - tests/test_voice_ingest.py
# Returns / emits: Dict[str, Any]
# Side effects:
#   - may access the local microphone
#   - writes transcript artifacts and staged capture manifests
# === End NoemaForge Autodoc Function Header ===
def transcribe_live(
    audio_path: str = "",
    manifest_path: str = "",
    transcript_text: str = "",
    transcript_path: str = "",
    language: str = "",
    from_microphone: bool = False,
    max_seconds: float = 0.0,
    inbox_root: str = DEFAULT_INBOX,
    outbox_root: str = DEFAULT_OUTBOX,
    policy_path: str = DEFAULT_POLICY_PATH,
    policy_override: Optional[Dict[str, Any]] = None,
    backend: str = "",
) -> Dict[str, Any]:
    policy = _load_policy(policy_path=policy_path, policy_override=policy_override)
    if not bool(policy.get("enabled", False)):
        raise ValueError("voice_live_disabled")
    stt_cfg = policy.get("stt") if isinstance(policy.get("stt"), dict) else {}
    if not bool(stt_cfg.get("enabled", False)):
        raise ValueError("voice_stt_disabled")

    cap_manifest: Dict[str, Any] = {}
    original_audio_path = str(audio_path or "")
    if manifest_path:
        cap_manifest = _load_json(os.path.abspath(manifest_path))
        if not cap_manifest:
            raise ValueError("missing_capture_manifest")
        audio_path = str(cap_manifest.get("captured_path") or audio_path or "")
    elif audio_path:
        cap_manifest = capture(audio_path=audio_path, note="auto-captured for live transcription", inbox_root=inbox_root)
        manifest_path = str(cap_manifest.get("manifest_path") or "")
        audio_path = str(cap_manifest.get("captured_path") or audio_path or "")
    elif from_microphone:
        cap_manifest = capture_live(
            max_seconds=max_seconds,
            note="live microphone capture",
            inbox_root=inbox_root,
            policy_path=policy_path,
            policy_override=policy,
        )
        manifest_path = str(cap_manifest.get("manifest_path") or "")
        audio_path = str(cap_manifest.get("captured_path") or "")
    else:
        raise ValueError("missing_audio_or_manifest")

    req_id = _slug()
    normalized_text = _normalize_text(transcript_text)
    sidecar_used = ""
    if not normalized_text:
        normalized_text, sidecar_used = _load_transcript_sidecar(audio_path=audio_path, transcript_path=transcript_path)
    if not normalized_text and str(original_audio_path or "").strip() and os.path.abspath(original_audio_path) != os.path.abspath(str(audio_path or "")):
        normalized_text, sidecar_used = _load_transcript_sidecar(audio_path=original_audio_path, transcript_path=transcript_path)

    segments: List[Dict[str, Any]] = []
    selected = ""
    if not normalized_text:
        selected = _detect_backend(str(backend or ""), list(stt_cfg.get("backend_order") or []), ("faster_whisper", "whisper", "whisper_cli", "command"))
        lang = str(language or stt_cfg.get("default_language") or "")
        if selected == "faster_whisper":
            data = _run_stt_faster_whisper(audio_path, stt_cfg, lang)
        elif selected == "whisper":
            data = _run_stt_whisper(audio_path, stt_cfg, lang)
        elif selected == "whisper_cli":
            data = _run_stt_whisper_cli(audio_path, stt_cfg, lang, outbox_root)
        elif selected == "command":
            data = _run_stt_command_backend(audio_path, stt_cfg, lang, outbox_root)
        else:
            raise ValueError("unsupported_voice_stt_backend")
        normalized_text = _normalize_text(str((data or {}).get("text") or ""))
        language = str((data or {}).get("language") or lang or "")
        segments = [seg for seg in ((data or {}).get("segments") or []) if isinstance(seg, dict)]
        if not normalized_text:
            raise ValueError("voice_stt_empty_transcript")

    txt_path = os.path.join(outbox_root, req_id + ".txt")
    os.makedirs(outbox_root, exist_ok=True)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(normalized_text)
    artifact = {
        "apiVersion": "noemaforge.voice/v1",
        "kind": "VoiceTranscript",
        "request_id": req_id,
        "created_at": _nowz(),
        "source_audio_path": audio_path,
        "capture_manifest_path": manifest_path,
        "language": str(language or ""),
        "transcript_path": txt_path,
        "transcript_preview": normalized_text[:200],
        "status": "complete",
        "mode": (
            "manual"
            if str(transcript_text or "").strip()
            else ("sidecar_import" if sidecar_used else "live_stt")
        ),
        "sidecar_path": sidecar_used,
        "backend": selected or ("manual" if str(transcript_text or "").strip() else "sidecar"),
        "segments": segments,
    }
    json_path = os.path.join(outbox_root, req_id + ".json")
    artifact["artifact_path"] = json_path
    _save_json(json_path, artifact)
    return artifact


# === NoemaForge Autodoc Function Header ===
# Function: _resolve_assistant_target(policy: Dict[str, Any], args: Dict[str, Any])
# Purpose: Resolve the configured assistant alias and routing target for a chat turn.
# Inputs:
#   - policy: Dict[str, Any]
#   - args: Dict[str, Any]
# Called by:
#   - build_chat_turn
# Returns / emits: Dict[str, Any]
# === End NoemaForge Autodoc Function Header ===
def _resolve_assistant_target(policy: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    assistant_cfg = policy.get("assistant") if isinstance(policy.get("assistant"), dict) else {}
    targets = policy.get("assistant_targets") if isinstance(policy.get("assistant_targets"), dict) else {}
    alias = str(args.get("assistant_alias") or assistant_cfg.get("default_alias") or "administrator").strip() or "administrator"
    target = targets.get(alias) if isinstance(targets.get(alias), dict) else {}
    out = dict(target)
    out.setdefault("alias", alias)
    if str(args.get("stream_id") or "").strip():
        out["stream_id"] = str(args.get("stream_id") or "").strip()
    if str(args.get("role") or "").strip():
        out["role"] = str(args.get("role") or "").strip()
    out.setdefault("stream_id", str(target.get("stream_id") or "operator.admin"))
    out.setdefault("role", str(target.get("role") or "administrator"))
    out.setdefault("title", str(target.get("title") or alias))
    out.setdefault("system_preamble", str(target.get("system_preamble") or ""))
    out.setdefault("history_root", str(target.get("history_root") or assistant_cfg.get("history_root") or DEFAULT_SESSION_ROOT))
    out.setdefault("max_turn_history", int(target.get("max_turn_history") or assistant_cfg.get("max_turn_history") or 12))
    return out


# === NoemaForge Autodoc Function Header ===
# Function: _history_path(history_root: str, session_id: str)
# Purpose: Build a deterministic session-state path for voice chat.
# Inputs:
#   - history_root: str
#   - session_id: str
# Called by:
#   - build_chat_turn
#   - update_chat_session
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def _history_path(history_root: str, session_id: str) -> str:
    return os.path.join(history_root, f"{session_id}.json")


# === NoemaForge Autodoc Function Header ===
# Function: build_chat_turn(args: Dict[str, Any], policy_path: str = DEFAULT_POLICY_PATH, policy_override: Optional[Dict[str, Any]] = None, inbox_root: str = DEFAULT_INBOX, outbox_root: str = DEFAULT_OUTBOX)
# Purpose: Resolve voice input into a transcript and prepare a routed chat turn for ToolProxy.
# Inputs:
#   - args: Dict[str, Any]
#   - policy_path: str = DEFAULT_POLICY_PATH
#   - policy_override: Optional[Dict[str, Any]] = None
#   - inbox_root: str = DEFAULT_INBOX
#   - outbox_root: str = DEFAULT_OUTBOX
# Called by:
#   - src/toolproxy.py
#   - tests/test_voice_ingest.py
# Returns / emits: Dict[str, Any]
# Side effects:
#   - may access the microphone or STT backend
#   - may write capture/transcript artifacts
# === End NoemaForge Autodoc Function Header ===
def build_chat_turn(
    args: Dict[str, Any],
    policy_path: str = DEFAULT_POLICY_PATH,
    policy_override: Optional[Dict[str, Any]] = None,
    inbox_root: str = DEFAULT_INBOX,
    outbox_root: str = DEFAULT_OUTBOX,
) -> Dict[str, Any]:
    args = args if isinstance(args, dict) else {}
    policy = _load_policy(policy_path=policy_path, policy_override=policy_override)
    target = _resolve_assistant_target(policy, args)
    session_id = str(args.get("session_id") or _slug()).strip()
    hist_path = str(args.get("session_path") or _history_path(str(target.get("history_root") or DEFAULT_SESSION_ROOT), session_id))
    session = _load_json(hist_path)
    history_messages = session.get("messages") if isinstance(session.get("messages"), list) else []
    max_turn_history = int(target.get("max_turn_history") or 12)
    trimmed_history = history_messages[-max_turn_history * 2 :] if history_messages else []

    transcript_text = _normalize_text(str(args.get("transcript_text") or ""))
    transcript_artifact: Optional[Dict[str, Any]] = None
    if not transcript_text:
        if bool(args.get("from_microphone", False)) or not str(args.get("audio_path") or args.get("manifest_path") or "").strip():
            transcript_artifact = transcribe_live(
                audio_path=str(args.get("audio_path") or ""),
                manifest_path=str(args.get("manifest_path") or ""),
                transcript_text="",
                transcript_path=str(args.get("transcript_path") or ""),
                language=str(args.get("language") or ""),
                from_microphone=True,
                max_seconds=float(args.get("max_seconds") or 0.0),
                inbox_root=str(args.get("inbox_root") or inbox_root),
                outbox_root=str(args.get("outbox_root") or outbox_root),
                policy_path=policy_path,
                policy_override=policy,
                backend=str(args.get("stt_backend") or ""),
            )
        else:
            use_live = bool(args.get("use_live_stt", True))
            if use_live:
                transcript_artifact = transcribe_live(
                    audio_path=str(args.get("audio_path") or ""),
                    manifest_path=str(args.get("manifest_path") or ""),
                    transcript_text="",
                    transcript_path=str(args.get("transcript_path") or ""),
                    language=str(args.get("language") or ""),
                    from_microphone=bool(args.get("from_microphone", False)),
                    max_seconds=float(args.get("max_seconds") or 0.0),
                    inbox_root=str(args.get("inbox_root") or inbox_root),
                    outbox_root=str(args.get("outbox_root") or outbox_root),
                    policy_path=policy_path,
                    policy_override=policy,
                    backend=str(args.get("stt_backend") or ""),
                )
            else:
                transcript_artifact = transcribe(
                    audio_path=str(args.get("audio_path") or ""),
                    manifest_path=str(args.get("manifest_path") or ""),
                    transcript_text="",
                    transcript_path=str(args.get("transcript_path") or ""),
                    language=str(args.get("language") or ""),
                    inbox_root=str(args.get("inbox_root") or inbox_root),
                    outbox_root=str(args.get("outbox_root") or outbox_root),
                )
        transcript_text = _normalize_text(str((transcript_artifact or {}).get("transcript_preview") or ""))
        if not transcript_text and transcript_artifact and str(transcript_artifact.get("transcript_path") or ""):
            try:
                with open(str(transcript_artifact.get("transcript_path") or ""), "r", encoding="utf-8", errors="replace") as f:
                    transcript_text = _normalize_text(f.read())
            except Exception:
                transcript_text = transcript_text
    else:
        request_id = _slug()
        txt_path = os.path.join(str(args.get("outbox_root") or outbox_root), request_id + ".txt")
        os.makedirs(os.path.dirname(txt_path), exist_ok=True)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(transcript_text)
        transcript_artifact = {
            "apiVersion": "noemaforge.voice/v1",
            "kind": "VoiceTranscript",
            "request_id": request_id,
            "created_at": _nowz(),
            "transcript_path": txt_path,
            "transcript_preview": transcript_text[:200],
            "status": "complete",
            "mode": "manual",
            "artifact_path": os.path.join(str(args.get("outbox_root") or outbox_root), request_id + ".json"),
        }
        _save_json(str(transcript_artifact["artifact_path"]), transcript_artifact)

    if not transcript_text:
        raise ValueError("voice_chat_missing_transcript")

    messages = list(trimmed_history) + [{"role": "user", "content": transcript_text}]
    return {
        "apiVersion": "noemaforge.voice/v1",
        "kind": "VoiceChatTurn",
        "created_at": _nowz(),
        "session_id": session_id,
        "session_path": hist_path,
        "assistant_target": target,
        "assistant_system_prompt": str(target.get("system_preamble") or ""),
        "messages": messages,
        "transcript": transcript_text,
        "transcript_artifact": transcript_artifact or {},
        "capture_manifest_path": str((transcript_artifact or {}).get("capture_manifest_path") or args.get("manifest_path") or ""),
        "max_turn_history": max_turn_history,
    }


# === NoemaForge Autodoc Function Header ===
# Function: extract_assistant_text(result: Dict[str, Any])
# Purpose: Extract a plain assistant reply from common llm.chat response shapes.
# Inputs:
#   - result: Dict[str, Any]
# Called by:
#   - update_chat_session
#   - src/toolproxy.py
#   - tests/test_voice_ingest.py
# Returns / emits: str
# === End NoemaForge Autodoc Function Header ===
def extract_assistant_text(result: Dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return str(result or "").strip()
    choices = result.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        msg = first.get("message") if isinstance(first.get("message"), dict) else {}
        if isinstance(msg.get("content"), str):
            return str(msg.get("content") or "").strip()
        if isinstance(first.get("text"), str):
            return str(first.get("text") or "").strip()
    if isinstance(result.get("output_text"), str):
        return str(result.get("output_text") or "").strip()
    if isinstance(result.get("text"), str):
        return str(result.get("text") or "").strip()
    if isinstance(result.get("raw"), str):
        return str(result.get("raw") or "").strip()
    return ""


# === NoemaForge Autodoc Function Header ===
# Function: update_chat_session(session_path: str, session_id: str, assistant_target: Dict[str, Any], transcript_text: str, llm_result: Dict[str, Any], transcript_artifact: Optional[Dict[str, Any]] = None)
# Purpose: Persist chat-session history after a successful assistant turn.
# Inputs:
#   - session_path: str
#   - session_id: str
#   - assistant_target: Dict[str, Any]
#   - transcript_text: str
#   - llm_result: Dict[str, Any]
#   - transcript_artifact: Optional[Dict[str, Any]] = None
# Called by:
#   - src/toolproxy.py
#   - tests/test_voice_ingest.py
# Returns / emits: Dict[str, Any]
# Side effects:
#   - writes session-state JSON files
# === End NoemaForge Autodoc Function Header ===
def update_chat_session(
    session_path: str,
    session_id: str,
    assistant_target: Dict[str, Any],
    transcript_text: str,
    llm_result: Dict[str, Any],
    transcript_artifact: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    session = _load_json(session_path)
    assistant_text = extract_assistant_text(llm_result)
    max_turn_history = int(assistant_target.get("max_turn_history") or 12)
    messages = session.get("messages") if isinstance(session.get("messages"), list) else []
    messages = list(messages) + [
        {"role": "user", "content": transcript_text},
        {"role": "assistant", "content": assistant_text},
    ]
    messages = messages[-max_turn_history * 2 :]
    turns = session.get("turns") if isinstance(session.get("turns"), list) else []
    turns = list(turns) + [
        {
            "turn_id": _slug(),
            "created_at": _nowz(),
            "user_text": transcript_text,
            "assistant_text": assistant_text,
            "transcript_artifact_path": str((transcript_artifact or {}).get("artifact_path") or ""),
            "model": str((llm_result or {}).get("model") or ""),
        }
    ]
    turns = turns[-max_turn_history:]
    doc = {
        "apiVersion": "noemaforge.voice/v1",
        "kind": "VoiceChatSession",
        "session_id": session_id,
        "updated_at": _nowz(),
        "created_at": str(session.get("created_at") or _nowz()),
        "assistant_alias": str(assistant_target.get("alias") or "administrator"),
        "assistant_stream_id": str(assistant_target.get("stream_id") or ""),
        "assistant_role": str(assistant_target.get("role") or ""),
        "messages": messages,
        "turns": turns,
        "last_transcript_artifact_path": str((transcript_artifact or {}).get("artifact_path") or ""),
        "session_path": session_path,
    }
    _save_json(session_path, doc)
    return doc


# === NoemaForge Autodoc Function Header ===
# Function: prepare_tool_action(action: str, args: Dict[str, Any], inbox_root: str = DEFAULT_INBOX, outbox_root: str = DEFAULT_OUTBOX, policy_path: str = DEFAULT_POLICY_PATH)
# Purpose: Provide a ToolProxy-facing entrypoint for file, live-capture, and STT actions.
# Inputs:
#   - action: str
#   - args: Dict[str, Any]
#   - inbox_root: str = DEFAULT_INBOX
#   - outbox_root: str = DEFAULT_OUTBOX
#   - policy_path: str = DEFAULT_POLICY_PATH
# Called by:
#   - src/toolproxy.py
# Returns / emits: Tuple[bool, Dict[str, Any], str]
# === End NoemaForge Autodoc Function Header ===
def prepare_tool_action(
    action: str,
    args: Dict[str, Any],
    inbox_root: str = DEFAULT_INBOX,
    outbox_root: str = DEFAULT_OUTBOX,
    policy_path: str = DEFAULT_POLICY_PATH,
) -> Tuple[bool, Dict[str, Any], str]:
    action = str(action or "").strip()
    args = args if isinstance(args, dict) else {}
    try:
        if action == "voice.capture":
            res = capture(
                audio_path=str(args.get("audio_path") or args.get("source_path") or ""),
                audio_bytes_b64=str(args.get("audio_bytes_b64") or args.get("audio_b64") or ""),
                filename=str(args.get("filename") or ""),
                note=str(args.get("note") or ""),
                inbox_root=str(args.get("inbox_root") or inbox_root),
            )
            return True, res, "ok"
        if action == "voice.transcribe":
            res = transcribe(
                audio_path=str(args.get("audio_path") or ""),
                manifest_path=str(args.get("manifest_path") or ""),
                transcript_text=str(args.get("transcript_text") or ""),
                transcript_path=str(args.get("transcript_path") or ""),
                language=str(args.get("language") or ""),
                inbox_root=str(args.get("inbox_root") or inbox_root),
                outbox_root=str(args.get("outbox_root") or outbox_root),
            )
            return True, res, "ok"
        if action == "voice.capture_live":
            res = capture_live(
                max_seconds=float(args.get("max_seconds") or 0.0),
                note=str(args.get("note") or ""),
                inbox_root=str(args.get("inbox_root") or inbox_root),
                policy_path=str(args.get("policy_path") or policy_path),
                backend=str(args.get("capture_backend") or args.get("backend") or ""),
            )
            return True, res, "ok"
        if action == "voice.transcribe_live":
            res = transcribe_live(
                audio_path=str(args.get("audio_path") or ""),
                manifest_path=str(args.get("manifest_path") or ""),
                transcript_text=str(args.get("transcript_text") or ""),
                transcript_path=str(args.get("transcript_path") or ""),
                language=str(args.get("language") or ""),
                from_microphone=bool(args.get("from_microphone", False)),
                max_seconds=float(args.get("max_seconds") or 0.0),
                inbox_root=str(args.get("inbox_root") or inbox_root),
                outbox_root=str(args.get("outbox_root") or outbox_root),
                policy_path=str(args.get("policy_path") or policy_path),
                backend=str(args.get("stt_backend") or args.get("backend") or ""),
            )
            return True, res, "ok"
        return False, {}, "unsupported_action"
    except Exception as e:
        return False, {"error": repr(e)}, "voice_runtime_failed"
