#!/usr/bin/env bash
# === NoemaForge File Header ===
# File: noemaforge/tools/prep/noemaforge-av-readiness.sh
# Zone: release/package
# Version: 0.31.13.alpha-patched1
# Created: 2026-05-14
# Modified: 2026-05-14
# Purpose: Provide NoemaForge release functionality for the packaged local runtime.
# Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
# Outputs: Structured command output, files, service state or UI state as documented by the caller.
# Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
# Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
# Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
# === End NoemaForge File Header ===
# NoemaForge audio/video readiness audit. Read-only.
set -euo pipefail
FORMAT="human"
ROOT="${NOEMAFORGE_ROOT:-/opt/noemaforge}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) FORMAT="json"; shift ;;
    --root) ROOT="$2"; shift 2 ;;
    -h|--help|help|\?) cat <<'USAGE'
Usage: noemaforge av-readiness [--json]

Read-only check for audio/video prerequisites. This does not start cameras,
record microphones, install packages, or start LLM backends.
USAGE
      exit 0 ;;
    *) echo "[av-readiness][ERROR] unknown argument: $1" >&2; exit 2 ;;
  esac
done
python3 - "$ROOT" "$FORMAT" <<'PY'
import json, os, shutil, subprocess, sys
from pathlib import Path
root=Path(sys.argv[1]); fmt=sys.argv[2]
checks=[]
def cmd_exists(name): return shutil.which(name) is not None
def add(id, ok, message, **extra):
    d={"id":id,"ok":bool(ok),"message":message}; d.update(extra); checks.append(d)
add("ffmpeg", cmd_exists("ffmpeg"), "ffmpeg available for media demux/transcode" if cmd_exists("ffmpeg") else "ffmpeg missing")
add("ffprobe", cmd_exists("ffprobe"), "ffprobe available for metadata" if cmd_exists("ffprobe") else "ffprobe missing")
add("audio_server", cmd_exists("pactl") or cmd_exists("wpctl") or cmd_exists("pw-cli"), "PulseAudio/PipeWire client present" if (cmd_exists("pactl") or cmd_exists("wpctl") or cmd_exists("pw-cli")) else "no PulseAudio/PipeWire client found")
add("alsa_tools", cmd_exists("arecord") and cmd_exists("aplay"), "ALSA record/playback tools present" if (cmd_exists("arecord") and cmd_exists("aplay")) else "ALSA arecord/aplay missing")
add("camera_tools", cmd_exists("v4l2-ctl"), "v4l2-ctl present for camera enumeration" if cmd_exists("v4l2-ctl") else "v4l2-ctl missing")
add("gstreamer", cmd_exists("gst-launch-1.0"), "GStreamer present" if cmd_exists("gst-launch-1.0") else "GStreamer missing")
# NoemaForge policy/config presence, not capability guarantee.
for cfg in ["voice-backends-policy.yaml", "tts-backends-policy.yaml", "photos-diary.yaml"]:
    p=root/"configs"/cfg
    add(f"config_{cfg}", p.exists(), f"{cfg} present" if p.exists() else f"{cfg} missing")
# Model families / assets
vault=Path("/mnt/noemaforge-share/noemaforge-lab/data/Vault")
models=vault/"models-gguf"
add("vault", vault.exists(), f"Vault exists at {vault}" if vault.exists() else f"Vault missing at {vault}")
add("gguf_models", models.exists() and any(models.rglob("*.gguf")) if models.exists() else False, "GGUF model files found" if models.exists() and any(models.rglob("*.gguf")) else "No GGUF model files found")
policy=root/"configs"/"multimodal-backends-policy.json"
add("multimodal_policy", policy.exists(), "multimodal-backends-policy.json present" if policy.exists() else "multimodal-backends-policy.json missing")
# Check obvious non-GGUF media models and directories.
media_hints=[]; non_gguf_models=[]
if vault.exists():
    for pat in ["*whisper*", "*tts*", "*audio*", "*vision*", "*vlm*", "*clip*", "*video*", "*diffusion*", "*music*", "*mask*", "*segment*"]:
        media_hints.extend([str(p) for p in vault.rglob(pat) if p.is_dir()][:10])
    for ext in ["*.safetensors", "*.ckpt", "*.onnx", "*.pt", "*.pth", "*.bin", "*.ggml", "*.tflite"]:
        non_gguf_models.extend([str(p) for p in vault.rglob(ext)][:50])
add("media_model_hints", bool(media_hints) or bool(non_gguf_models), "possible audio/vision/video model assets found" if (media_hints or non_gguf_models) else "no obvious audio/video model assets found", hints=media_hints[:30], non_gguf_models=non_gguf_models[:80])
# Interpret readiness honestly.
missing=[c for c in checks if not c["ok"]]
blocking=[c for c in missing if c["id"] in {"ffmpeg","ffprobe"}]
policy_ready = not blocking
report={
    "ok": policy_ready,
    "ready_for_text_gguf_llm": True,
    "ready_for_audio_video_production": False,
    "summary": "Text/GGUF local LLM path is primary. Audio/video has partial scaffolding but is not production-ready until capture/transcode/STT/TTS/VLM adapters and tests are installed.",
    "checks": checks,
    "missing": missing,
    "recommendations": [
        "Keep GGUF for local text/code LLM backends because current runtime is llama.cpp-compatible and predictable.",
        "Add explicit STT adapter (for example Whisper-class local backend), TTS adapter, media ingestion pipeline and test cases before claiming audio/video readiness.",
        "Add ffmpeg/ffprobe/gstreamer/v4l2/PipeWire checks to first-run if media mode is requested.",
        "Separate model stores: text GGUF, audio STT/TTS, vision/VLM and video indexing assets; do not force all media into GGUF."
    ]
}
if fmt=="json":
    print(json.dumps(report, indent=2, ensure_ascii=False))
else:
    print("NoemaForge audio/video readiness")
    print("overall: NOT PRODUCTION READY for audio/video" if not report["ready_for_audio_video_production"] else "overall: OK")
    print("text/GGUF LLM path: ready/primary")
    for c in checks:
        status="ok" if c["ok"] else "missing"
        print(f"- {c['id']}: {status} — {c['message']}")
    print("summary:", report["summary"])
sys.exit(0 if policy_ready else 1)
PY
