#!/usr/bin/env python3
from __future__ import annotations
# === NoemaForge File Header ===
# File: src/model_capabilities.py
# Zone: vault/model-intel
# Purpose: Infer artifact format, runtime family, capability vector, and role eligibility hints for heterogeneous local model artifacts.
# Callers: vault_inventory.py, role_tournament.py, noemaforge CLI.
# Safety notes: read-only; classification is heuristic and must be represented as observed/inferred, not truth.
# === End NoemaForge File Header ===

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set

LLM_NAMES = [
    "qwen", "llama", "mistral", "mixtral", "deepseek", "phi", "falcon", "granite", "olmo",
    "jamba", "openelm", "command-r", "nemotron", "minicpm", "gemma", "yi", "internlm", "starcoder",
    "codestral", "wizard", "vicuna", "nous", "orca", "gpt2",
]
CODE_NAMES = ["coder", "code", "starcoder", "codestral", "openreasoning", "opencode", "deepseek-coder"]
EMBED_NAMES = ["bge", "e5", "gte", "embedding", "embeddings", "sentence-transformers", "colbert"]
RERANK_NAMES = ["rerank", "reranker", "cross-encoder"]
ASR_NAMES = ["whisper", "asr", "transcrib", "speech-recognition"]
TTS_NAMES = ["tts", "xtts", "piper", "bark", "voice", "speech-synthesis"]
VISION_NAMES = ["sam", "segment-anything", "segmentation", "vision", "vit", "clip", "siglip", "image"]
VIDEO_NAMES = ["video", "cogvideo", "stable-video", "img2vid", "sora", "diffusion"]
AUDIO_NAMES = ["audio", "music", "musdb", "sound"]
ADAPTER_NAMES = ["adapter", "lora", "qlora", "peft"]


def _norm_text(*parts: Any) -> str:
    return " ".join(str(x or "") for x in parts).lower().replace("_", "-")


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    return any(t in text for t in terms)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def infer_artifact_format(path: str, files: Sequence[str] | None = None) -> str:
    p = Path(path)
    files_l = [str(x).lower() for x in (files or [])]
    text = _norm_text(path, " ".join(files_l))
    if p.is_file():
        ext = p.suffix.lower()
        if ext == ".gguf":
            return "gguf"
        if ext == ".safetensors":
            return "safetensors"
        if ext in (".pt", ".pth", ".bin"):
            return "pytorch"
        if ext == ".onnx":
            return "onnx"
        if ext in (".zip", ".tar", ".gz", ".tgz"):
            return "archive"
    if "adapter_config.json" in files_l or _contains_any(text, ADAPTER_NAMES):
        return "adapter"
    if any(x.endswith(".gguf") for x in files_l):
        return "gguf"
    if any(x.endswith(".onnx") for x in files_l):
        return "onnx"
    if any(x.endswith(".safetensors") for x in files_l):
        return "hf_snapshot"
    if "config.json" in files_l and ("tokenizer.json" in files_l or "tokenizer_config.json" in files_l or "vocab.json" in files_l):
        return "hf_snapshot"
    if any(x in files_l for x in ("model.pth", "dvae.pth", "mel_stats.pth")):
        return "pytorch_bundle"
    return "directory" if p.is_dir() else "unknown"


def infer_capabilities(name: str, path: str = "", files: Sequence[str] | None = None, config: Dict[str, Any] | None = None) -> List[str]:
    """Return a stable, explainable capability vector.

    The result is deliberately inclusive: eligibility/tournaments will later decide what is runnable.
    """
    cfg = config or {}
    files = list(files or [])
    text = _norm_text(name, path, " ".join(files), cfg.get("model_type"), cfg.get("architectures"))
    caps: Set[str] = set()

    # Core text/LLM capabilities.
    if _contains_any(text, LLM_NAMES) or _contains_any(text, ["instruct", "chat"]):
        caps.update(["chat", "instruction_following", "reasoning", "json_output", "summarization", "planning", "admin_ops", "safety_review", "writing", "fact_check"])
    if _contains_any(text, ["instruct", "chat", "assistant"]):
        caps.update(["chat", "instruction_following"])
    if _contains_any(text, CODE_NAMES):
        caps.update(["code", "debugging", "dev_ops"])
    if _contains_any(text, ["reason", "r1", "qwq", "math"]):
        caps.update(["reasoning", "math"])
    if _contains_any(text, ["admin", "ops", "system", "surgeon"]):
        caps.update(["admin_ops", "safety_review"])

    # Retrieval / embedding.
    if _contains_any(text, EMBED_NAMES):
        caps.update(["embedding", "retrieval", "semantic_search"])
    if _contains_any(text, RERANK_NAMES):
        caps.update(["reranking", "retrieval"])
    if "colbert" in text:
        caps.update(["embedding", "retrieval", "late_interaction"])

    # Speech/audio.
    if _contains_any(text, ASR_NAMES):
        caps.update(["asr", "audio_transcription"])
    if _contains_any(text, TTS_NAMES):
        caps.update(["tts"])
        if "xtts" in text or "voice-cloning" in text or "voice_clone" in text:
            caps.add("voice_clone")
    if _contains_any(text, AUDIO_NAMES):
        caps.add("audio")

    # Vision/video.
    if _contains_any(text, VISION_NAMES):
        caps.add("vision")
    if _contains_any(text, ["sam", "segment", "segmentation"]):
        caps.update(["vision", "segmentation"])
    if _contains_any(text, VIDEO_NAMES):
        caps.update(["video", "video_generation"])
        if "img2vid" in text:
            caps.add("image_to_video")

    if _contains_any(text, ADAPTER_NAMES):
        caps.add("adapter")

    # Config-driven refinements.
    arch = _norm_text(cfg.get("architectures"), cfg.get("model_type"))
    if "whisper" in arch:
        caps.update(["asr", "audio_transcription"])
    if "clip" in arch or "vision" in arch or "vit" in arch:
        caps.add("vision")
    if "bert" in arch and not caps:
        caps.update(["embedding", "retrieval"])

    return sorted(caps)


def infer_runtime_family(artifact_format: str, capabilities: Sequence[str], path: str = "") -> str:
    caps = set(capabilities)
    text = _norm_text(path)
    if artifact_format == "gguf":
        return "llama.cpp"
    if "embedding" in caps or "reranking" in caps:
        return "sentence-transformers"
    if "asr" in caps:
        return "whisper"
    if "tts" in caps:
        if "piper" in text or artifact_format == "onnx":
            return "piper"
        if "xtts" in text:
            return "xtts"
        if "bark" in text:
            return "bark"
        return "tts"
    if "segmentation" in caps or "vision" in caps:
        return "torch-vision"
    if "video_generation" in caps:
        return "diffusers"
    if artifact_format in ("hf_snapshot", "safetensors", "pytorch", "pytorch_bundle"):
        return "transformers"
    return "unknown"


def runtime_probe(runtime_family: str) -> Dict[str, Any]:
    """Cheap host runtime availability probe. Does not import heavy libraries."""
    import shutil
    fam = (runtime_family or "").lower()
    if fam == "llama.cpp":
        path = os.environ.get("NOEMAFORGE_LLAMA_SERVER", "/opt/noemaforge/bin/llama-server")
        return {"runtime_family": runtime_family, "available": os.path.exists(path) and os.access(path, os.X_OK), "probe": path}
    if fam == "piper":
        p = shutil.which("piper") or shutil.which("piper-tts")
        return {"runtime_family": runtime_family, "available": bool(p), "probe": p or "piper/piper-tts"}
    if fam == "whisper":
        p = shutil.which("whisper") or shutil.which("whisper-ctranslate2")
        return {"runtime_family": runtime_family, "available": bool(p), "probe": p or "whisper"}
    if fam in ("sentence-transformers", "transformers", "xtts", "bark", "torch-vision", "diffusers"):
        # Avoid heavy imports in GUI prep. First-start can install runners later.
        module = {
            "sentence-transformers": "sentence_transformers",
            "transformers": "transformers",
            "xtts": "TTS",
            "bark": "bark",
            "torch-vision": "torch",
            "diffusers": "diffusers",
        }.get(fam, fam)
        return {"runtime_family": runtime_family, "available": False, "probe": f"python module {module} not probed during light prep", "deferred": True}
    return {"runtime_family": runtime_family, "available": False, "probe": "unknown runtime", "deferred": True}


def summarize_model(name: str, path: str, files: Sequence[str] | None = None, config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    fmt = infer_artifact_format(path, files)
    caps = infer_capabilities(name=name, path=path, files=files, config=config)
    runtime = infer_runtime_family(fmt, caps, path)
    return {
        "artifact_format": fmt,
        "capabilities": caps,
        "runtime_family": runtime,
        "runtime_probe": runtime_probe(runtime),
        "classification_source": "heuristic:v0.32.2",
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    args = ap.parse_args()
    p = Path(args.path)
    files: List[str] = []
    if p.is_dir():
        try:
            files = [x.name for x in p.iterdir()]
        except Exception:
            files = []
    cfg = _read_json(p / "config.json") if p.is_dir() else {}
    print(json.dumps(summarize_model(p.name, str(p), files, cfg), ensure_ascii=False, indent=2))
