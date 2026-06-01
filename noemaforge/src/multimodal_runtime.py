#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/multimodal_runtime.py
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

Existing module notes:
NoemaForge multimodal runtime scaffold.

This is a discovery/planning layer. It discovers non-GGUF and media models in the
Vault, validates prerequisites, extracts image metadata, and writes explicit
pipeline plans. It does not auto-start heavy non-text backends.
"""
from __future__ import annotations

import argparse, datetime as dt, json, mimetypes, os, shutil, subprocess, sys
from pathlib import Path
from typing import Any, Dict, List

try:
    import model_inventory_normalize
except Exception:  # pragma: no cover - installed path fallback
    model_inventory_normalize = None  # type: ignore[assignment]

try:
    from noemaforge_version import RUNTIME_VERSION as VERSION
except Exception:
    VERSION = "0.32.2"
from platform_paths import DEFAULT_PATHS as _pp
DEFAULT_ROOT = _pp.root
DEFAULT_STATE = Path(os.environ.get("NOEMAFORGE_MULTIMODAL_STATE", "/var/lib/noemaforge/multimodal"))
DEFAULT_VAULT = Path(os.environ.get("NOEMAFORGE_VAULT", "/mnt/noemaforge-share/noemaforge-lab/data/Vault"))
MODEL_EXTENSIONS = {".gguf", ".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".onnx", ".ggml", ".tflite", ".pb", ".engine"}
MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff", ".gif", ".mp4", ".mov", ".mkv", ".webm", ".avi", ".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}
CAP_KEYWORDS = {
    "text_llm_gguf": ["llama", "qwen", "mistral", "gemma", "coder", "instruct"],
    "vision_understanding": ["llava", "bakllava", "moondream", "qwen-vl", "qwen2-vl", "clip", "siglip", "vit", "vision", "vlm", "mmproj"],
    "stt": ["whisper", "faster-whisper", "stt", "speech-to-text"],
    "tts_voice": ["piper", "tts", "xtts", "bark", "vits", "voice", "speaker"],
    "music_generation": ["musicgen", "audiocraft", "riffusion", "stable-audio", "music", "audio-gen"],
    "image_generation": ["stable-diffusion", "sdxl", "sd15", "flux", "controlnet", "lora", "vae", "diffusion"],
    "video_generation": ["animatediff", "svd", "wan", "hunyuanvideo", "video", "motion", "i2v", "t2v"],
    "segmentation_masks": ["sam", "segment", "u2net", "rvm", "modnet", "matting", "mask"],
}
PIPELINE_CAPS = {
    "image_analyze": ["image_metadata"],
    "voice_generate": ["tts_voice"],
    "music_generate": ["music_generation"],
    "photo_generate": ["image_generation"],
    "video_generate": ["video_generation"],
    "video_call_masks": ["segmentation_masks", "virtual_camera_masks"],
}

def nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def dumps(x: Any) -> str:
    return json.dumps(x, indent=2, ensure_ascii=False)

def command_exists(name: str) -> bool:
    return shutil.which(name) is not None

def run_capture(cmd: List[str], timeout: int = 8) -> Dict[str, Any]:
    try:
        p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return {"ok": p.returncode == 0, "rc": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
    except Exception as e:
        return {"ok": False, "rc": None, "stdout": "", "stderr": str(e)}

def classify(path: Path) -> List[str]:
    name = str(path).casefold()
    ext = path.suffix.casefold()
    caps: List[str] = []
    if ext == ".gguf":
        caps.append("text_llm_gguf")
    for cap, kws in CAP_KEYWORDS.items():
        if any(k in name for k in kws):
            if cap not in caps: caps.append(cap)
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff", ".gif"}:
        caps.append("image_metadata")
    if ext in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
        caps.append("video_media")
    if ext in {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}:
        caps.append("audio_media")
    if not caps and ext in MODEL_EXTENSIONS:
        caps.append("unknown_model")
    return sorted(set(caps))

def gguf_shard_info(path: Path) -> Dict[str, Any] | None:
    if path.suffix.casefold() != ".gguf" or model_inventory_normalize is None:
        return None
    info = model_inventory_normalize.parse_shard(str(path))
    if not info:
        return None
    return {
        "sharded": True,
        "shard_index": int(info.get("index") or 0),
        "shard_count": int(info.get("total") or 0),
        "shard_prefix": str(info.get("prefix") or ""),
    }


def canonical_first_shard(path: Path, info: Dict[str, Any]) -> str:
    idx = int(info.get("shard_index") or 0)
    total = int(info.get("shard_count") or 0)
    prefix = str(info.get("shard_prefix") or path.stem)
    if idx <= 0 or total <= 0:
        return ""
    width = max(3, len(str(total)))
    return str(path.with_name(f"{prefix}-{1:0{width}d}-of-{total:0{width}d}.gguf"))


def scan_vault(vault: Path, max_files: int = 20000) -> Dict[str, Any]:
    entries=[]; counts={}; caps={}; skipped=0; excluded_non_head_shards=[]
    if not vault.exists():
        return {"ok": False, "version": VERSION, "vault": str(vault), "message": "Vault not found", "entries": [], "counts": {}, "capabilities": {}, "excluded_non_head_shards": []}
    for i,p in enumerate(vault.rglob("*")):
        if i > max_files:
            skipped += 1
            continue
        if not p.is_file(): continue
        ext=p.suffix.casefold()
        if ext not in MODEL_EXTENSIONS and ext not in MEDIA_EXTENSIONS:
            continue
        shard = gguf_shard_info(p)
        if shard and int(shard.get("shard_index") or 0) != 1:
            excluded_non_head_shards.append({
                "path": str(p),
                "name": p.name,
                "reason": "non_head_gguf_shard_excluded_from_runtime_candidates",
                "shard_index": shard.get("shard_index"),
                "shard_count": shard.get("shard_count"),
                "canonical_first_shard": canonical_first_shard(p, shard),
            })
            continue
        try: size=p.stat().st_size
        except OSError: size=0
        pcaps=classify(p)
        kind="model" if ext in MODEL_EXTENSIONS else "media"
        item={"path": str(p), "name": p.name, "extension": ext, "kind": kind, "size_bytes": size, "capabilities": pcaps}
        if ext == ".gguf":
            if shard:
                item.update({"runtime_candidate": True, "sharded": True, "shard_index": shard.get("shard_index"), "shard_count": shard.get("shard_count"), "complete_shard_set": None})
            else:
                item.update({"runtime_candidate": True, "sharded": False})
        entries.append(item)
        counts[ext]=counts.get(ext,0)+1
        for c in pcaps:
            caps[c]=caps.get(c,0)+1
    entries.sort(key=lambda x: (-x["size_bytes"], x["path"]))
    excluded_non_head_shards.sort(key=lambda x: x["path"])
    return {"ok": True, "version": VERSION, "scanned_at": nowz(), "vault": str(vault), "entries": entries, "counts": counts, "capabilities": caps, "skipped_after_limit": skipped, "excluded_non_head_shards": excluded_non_head_shards}

def prerequisites() -> Dict[str, Any]:
    checks={
        "ffmpeg": command_exists("ffmpeg"),
        "ffprobe": command_exists("ffprobe"),
        "exiftool": command_exists("exiftool"),
        "identify": command_exists("identify"),
        "v4l2_ctl": command_exists("v4l2-ctl"),
        "v4l2loopback_ctl": command_exists("v4l2loopback-ctl"),
        "obs": command_exists("obs"),
        "pactl": command_exists("pactl"),
        "wpctl": command_exists("wpctl"),
        "gst_launch": command_exists("gst-launch-1.0"),
        "python3": command_exists("python3"),
    }
    return {"checks": checks, "ok_core_metadata": checks["ffprobe"] or checks["exiftool"] or checks["identify"], "ok_virtual_camera_tools": checks["v4l2_ctl"] or checks["obs"]}

def write_state(state: Path, name: str, data: Any) -> Path:
    candidates = [state]
    home = Path.home() / ".local" / "state" / "noemaforge" / "multimodal"
    if home not in candidates:
        candidates.append(home)
    last_error = None
    for base in candidates:
        try:
            base.mkdir(parents=True, exist_ok=True)
            path = base / name
            path.write_text(dumps(data)+"\n", encoding="utf-8")
            return path
        except Exception as e:
            last_error = e
            continue
    raise RuntimeError(f"cannot write multimodal state {name}: {last_error}")

def cmd_scan(args):
    report=scan_vault(Path(args.vault), args.max_files)
    state=Path(args.state)
    if report.get("ok"):
        idx=write_state(state, "model-index.json", report)
        report["state_index"] = str(idx)
    if args.json: print(dumps(report))
    else:
        print(f"NoemaForge multimodal scan: vault={report.get('vault')} ok={report.get('ok')}")
        print("capabilities:")
        for k,v in sorted(report.get("capabilities",{}).items()): print(f"  {k}: {v}")
        print("extensions:")
        for k,v in sorted(report.get("counts",{}).items()): print(f"  {k}: {v}")
        print("top assets:")
        for e in report.get("entries",[])[:20]: print(f"  {e['size_bytes']/1024/1024/1024:.2f} GiB {','.join(e['capabilities'])} {e['path']}")

def cmd_status(args):
    vault=Path(args.vault); state=Path(args.state); idx=state/"model-index.json"
    report={"version":VERSION,"vault":str(vault),"state":str(state),"index_exists":idx.exists(),"prerequisites":prerequisites()}
    if idx.exists():
        try: report["index"]=json.loads(idx.read_text())
        except Exception as e: report["index_error"]=str(e)
    if args.json: print(dumps(report))
    else:
        print("NoemaForge multimodal status")
        print(f"vault: {vault} exists={vault.exists()}")
        print(f"index: {idx} exists={idx.exists()}")
        caps=(report.get("index") or {}).get("capabilities",{})
        if caps:
            for k,v in sorted(caps.items()): print(f"  {k}: {v}")
        print("prerequisites:")
        for k,v in report["prerequisites"]["checks"].items(): print(f"  {k}: {'ok' if v else 'missing'}")

def ffprobe_json(path: Path) -> Dict[str, Any]:
    if not command_exists("ffprobe"): return {}
    r=run_capture(["ffprobe","-v","quiet","-print_format","json","-show_format","-show_streams",str(path)], timeout=15)
    if not r["ok"]: return {"ffprobe_error": r["stderr"][:500]}
    try: return json.loads(r["stdout"] or "{}")
    except Exception: return {"ffprobe_raw": r["stdout"][:2000]}

def cmd_image_metadata(args):
    p=Path(args.image)
    report={"ok":p.exists(),"version":VERSION,"image":str(p),"metadata":{},"recognition":{"ready":False,"reason":"Vision captioning requires discovered VLM backend; metadata extraction is available."}}
    if not p.exists():
        if args.json: print(dumps(report)); return 1
        print(f"image not found: {p}"); return 1
    st=p.stat()
    report["metadata"].update({"name":p.name,"size_bytes":st.st_size,"extension":p.suffix.casefold(),"mime":mimetypes.guess_type(str(p))[0]})
    if command_exists("identify"):
        r=run_capture(["identify","-verbose",str(p)], timeout=10); report["metadata"]["identify"]={"ok":r["ok"],"text":r["stdout"][:4000]}
    elif command_exists("exiftool"):
        r=run_capture(["exiftool","-json",str(p)], timeout=10)
        if r["ok"]:
            try: report["metadata"]["exiftool"]=json.loads(r["stdout"])
            except Exception: report["metadata"]["exiftool_raw"]=r["stdout"][:4000]
    else:
        report["metadata"]["fallback"]="install exiftool or ImageMagick identify for richer metadata"
    report["metadata"]["ffprobe"]=ffprobe_json(p)
    if args.out:
        out=Path(args.out); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(dumps(report)+"\n")
    if args.json: print(dumps(report))
    else:
        print("NoemaForge image metadata")
        print(f"image: {p}")
        print(f"mime: {report['metadata'].get('mime')} size={st.st_size}")
        print("recognition:", report["recognition"]["reason"])

def plan_for(pipeline: str, scan: Dict[str, Any], state: Path) -> Dict[str, Any]:
    req=PIPELINE_CAPS.get(pipeline)
    if not req: return {"ok":False,"pipeline":pipeline,"error":"unknown pipeline","known":sorted(PIPELINE_CAPS)}
    caps=scan.get("capabilities",{})
    missing=[]
    for c in req:
        if c == "image_metadata": continue
        if c == "virtual_camera_masks":
            prereq=prerequisites()["checks"]
            if not (prereq.get("v4l2_ctl") or prereq.get("obs")): missing.append(c)
        elif not caps.get(c): missing.append(c)
    plan={"ok":not missing,"version":VERSION,"pipeline":pipeline,"required":req,"missing":missing,"created_at":nowz(),"autostart":False,"manual_only":True,"state":str(state),"notes":[]}
    if pipeline=="video_call_masks": plan["notes"].append("Requires explicit v4l2loopback/OBS/PipeWire setup; NoemaForge will not hijack camera without operator command.")
    if missing: plan["notes"].append("Missing model/tool capabilities; scan Vault or install appropriate backend before live generation.")
    return plan

def cmd_prepare(args):
    state=Path(args.state); scan=scan_vault(Path(args.vault), args.max_files)
    plan=plan_for(args.pipeline, scan, state)
    path=write_state(state, f"{args.pipeline}-plan.json", plan)
    plan["plan_path"]=str(path)
    if args.json: print(dumps(plan))
    else:
        print(f"NoemaForge multimodal prepare: {args.pipeline}")
        print(f"ok: {plan['ok']} missing={','.join(plan['missing']) or 'none'}")
        print(f"plan: {path}")
        for n in plan.get("notes",[]): print("-",n)

def cmd_mask_plan(args):
    state=Path(args.state); scan=scan_vault(Path(args.vault), args.max_files); prereq=prerequisites()
    caps=scan.get("capabilities",{})
    report={"version":VERSION,"ok": bool(caps.get("segmentation_masks")) and prereq["ok_virtual_camera_tools"],"created_at":nowz(),"capabilities":caps,"prerequisites":prereq,"steps":[
        "Load/install v4l2loopback or configure OBS Virtual Camera explicitly.",
        "Select segmentation/matting model from Vault.",
        "Run a manual mask session; no automatic camera hijack.",
        "Expose virtual camera device to the video-call app only after operator approval."
    ],"autostart":False,"privacy":"manual-only; no camera capture without explicit command"}
    path=write_state(state,"video-call-mask-plan.json",report); report["plan_path"]=str(path)
    print(dumps(report) if args.json else f"mask plan ok={report['ok']} path={path}")

def cmd_persona_gui(args):
    root=Path(args.root); portraits=root/"ui/personas/portraits"; dashboard=root/"templates/pipeline-dashboard"; cat=root/"configs/persona-catalog.json"
    problems=[]; warnings=[]
    if not dashboard.exists(): problems.append(f"missing dashboard UI: {dashboard}")
    if not cat.exists(): problems.append(f"missing persona catalog: {cat}")
    persona_count=0; portrait_count=0
    if cat.exists():
        try:
            data=json.loads(cat.read_text()); persona_count=len(data.get("personas",{}))
            for role,spec in data.get("personas",{}).items():
                ptr=spec.get("portrait") or ""
                if ptr and not (root/ptr.lstrip("/")).exists(): warnings.append(f"portrait path missing for {role}: {ptr}")
        except Exception as e: problems.append(f"persona catalog invalid: {e}")
    if portraits.exists(): portrait_count=len(list(portraits.glob("*.svg")))
    else: warnings.append(f"portrait dir missing: {portraits}")
    report={"ok":not problems,"version":VERSION,"persona_count":persona_count,"portrait_svg_count":portrait_count,"dashboard_ui":str(dashboard),"portrait_dir":str(portraits),"problems":problems,"warnings":warnings,"start_commands":["noemaforge dashboard start","noemaforge dashboard status","open http://127.0.0.1:8765/"],"autostart_options":{"manual":"noemaforge dashboard start","autostart_user_service":"planned: noemaforge dashboard enable-user-service","system_autostart":"not recommended for MVP; keep GUI timer for runtime only"}}
    if args.json: print(dumps(report))
    else:
        print("NoemaForge persona GUI/portraits")
        print("overall:", "OK" if report["ok"] else "FAIL")
        print(f"personas={persona_count} portraits={portrait_count}")
        for p in problems: print("problem:",p)
        for w in warnings[:20]: print("warning:",w)
        print("start: noemaforge dashboard start")
        print("status: noemaforge dashboard status")

def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    json_flag = False
    cleaned = []
    for item in argv:
        if item == "--json":
            json_flag = True
        else:
            cleaned.append(item)
    ap=argparse.ArgumentParser()
    ap.add_argument("--root", default=str(DEFAULT_ROOT)); ap.add_argument("--state", default=str(DEFAULT_STATE)); ap.add_argument("--vault", default=str(DEFAULT_VAULT)); ap.add_argument("--json", action="store_true"); ap.add_argument("--max-files", type=int, default=25000)
    sub=ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    sub.add_parser("status")
    im=sub.add_parser("image-metadata"); im.add_argument("image"); im.add_argument("--out", default="")
    pr=sub.add_parser("prepare"); pr.add_argument("pipeline", choices=sorted(PIPELINE_CAPS))
    sub.add_parser("mask-plan")
    sub.add_parser("persona-gui")
    args=ap.parse_args(cleaned)
    if json_flag:
        args.json = True
    if args.cmd=="scan": return cmd_scan(args) or 0
    if args.cmd=="status": return cmd_status(args) or 0
    if args.cmd=="image-metadata": return cmd_image_metadata(args) or 0
    if args.cmd=="prepare": return cmd_prepare(args) or 0
    if args.cmd=="mask-plan": return cmd_mask_plan(args) or 0
    if args.cmd=="persona-gui": return cmd_persona_gui(args) or 0
    return 2
if __name__=="__main__": raise SystemExit(main())
