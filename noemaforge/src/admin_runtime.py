#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/admin_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-14
Modified: 2026-05-25
Purpose: Provide NoemaForge release functionality for the packaged local runtime.
Inputs: Command-line arguments, environment variables, package files and local NoemaForge runtime state as applicable.
Outputs: Structured command output, files, service state or UI state as documented by the caller.
Side effects: Limited to the documented NoemaForge paths, runtime state directories or systemd units used by this file.
Tests: Syntax validation plus the release setup selftest, consistency-audit and targeted smoke checks.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

Existing module notes:
NoemaForge Admin control-plane runtime.

0.32.2 release-candidate scope:
- route natural-language operator requests to concrete NoemaForge pipelines;
- optionally create/launch the selected pipeline run;
- bridge Admin GUI actions to dev-team, multimodal planning and model-evolution runtimes;
- keep all execution local, auditable and single-active-LLM safe.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:
    from i18n_runtime import normalize_locale, tr
except Exception:  # pragma: no cover
    def normalize_locale(value=None): return str(value or os.environ.get("NOEMAFORGE_LANG") or "en").split(".", 1)[0]
    def tr(root, key, default="", locale=None, **kwargs):
        try: return (default or key).format(**kwargs)
        except Exception: return default or key

import production_ai_contracts
from noemaforge_version import RUNTIME_VERSION
from platform_paths import DEFAULT_PATHS as _pp
DEFAULT_ROOT = _pp.root
DEFAULT_STATE = _pp.pipelines_dir
DEFAULT_EVOLUTION_STATE = _pp.model_evolution_state_dir
DEFAULT_MODEL_SELECTION_STATE = _pp.model_selection_state_dir
SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def nowz() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def safe_id(value: str, *, prefix: str = "task", limit: int = 72) -> str:
    value = SAFE_ID_RE.sub("_", str(value or "").strip()).strip("_")
    if not value:
        value = prefix
    if len(value) > limit:
        value = value[:limit].rstrip("_") or prefix
    return value


ROUTES: List[Dict[str, Any]] = [
    {
        "id": "greeting",
        "label": "Greeting / Admin warm-up",
        "pipeline_id": "dashboard_operator_console",
        "team_id": "admin_console_team",
        "intent": "greeting",
        "keywords": ["привет", "првиет", "здравств", "hello", "hi", "hey", "start gui", "gui"],
        "reply": "Привет. Я Админ NoemaForge: могу открыть pipeline, запустить dev-team, провести model-evolution или подготовить media-пайплайн прямо из GUI.",
        "reply_key": "admin.reply.greeting",
        "execute_mode": "pipeline",
    },
    {
        "id": "code",
        "label": "Code / Dev Team",
        "pipeline_id": "dev_pipeline_member_cells",
        "team_id": "development_member_cell_team",
        "intent": "code_change",
        "keywords": ["код", "программ", "python", "bash", "api", "bug", "ошиб", "тест", "рефактор", "patch", "исправ", "доработ", "верси", "release", "dev team", "разработ"],
        "reply": "Перед передачей в Dev Team уточни, что именно доработать и где лежит проект или файл.",
        "reply_key": "admin.reply.route.code",
        "execute_mode": "pipeline",
        "suggested_commands": [
            "noemaforge dev-team run --request '<task>' --json",
            "noemaforge dev-team replace --project <repo> --path <file> --old '<old>' --new '<new>' --apply --json",
            "noemaforge pipeline member <run_id> run --member developer --project <repo> --request '<task>' --json",
        ],
    },
    {
        "id": "voice",
        "label": "Voice generation / TTS",
        "pipeline_id": "voice_generation",
        "team_id": "media_generation_team",
        "intent": "voice_generation",
        "keywords": ["голос", "озвуч", "tts", "voice", "speaker", "piper", "xtts", "диктор"],
        "reply": "Маршрутизирую в voice generation pipeline. Runtime остаётся explicit-only: сначала plan/prepare, затем выбранный backend adapter.",
        "execute_mode": "pipeline",
        "prepare": ["--json", "prepare", "voice_generate"],
    },
    {
        "id": "music",
        "label": "Music generation",
        "pipeline_id": "music_generation",
        "team_id": "media_generation_team",
        "intent": "music_generation",
        "keywords": ["музык", "трек", "песня", "song", "music", "musicgen", "audiocraft", "riffusion", "stable audio", "саунд"],
        "reply": "Подготовлю music generation pipeline. Если live backend ещё не выбран, верну planned-only artifact, а не готовый аудиофайл.",
        "reply_key": "admin.reply.route.music",
        "execute_mode": "pipeline",
        "prepare": ["--json", "prepare", "music_generate"],
    },
    {
        "id": "photo",
        "label": "Photo / image generation",
        "pipeline_id": "photo_generation",
        "team_id": "media_generation_team",
        "intent": "image_generation",
        "keywords": ["фото", "картин", "изображ", "image", "photo", "sdxl", "diffusion", "comfy", "a1111", "flux", "рисунок"],
        "reply": "Маршрутизирую в photo generation pipeline. Система подготовит план backend adapter, без скрытого автозапуска heavy media backend.",
        "execute_mode": "pipeline",
        "prepare": ["--json", "prepare", "photo_generate"],
    },
    {
        "id": "video",
        "label": "Video generation / editing",
        "pipeline_id": "video_generation",
        "team_id": "media_generation_team",
        "intent": "video_generation",
        "keywords": ["видео", "ролик", "анимац", "video", "clip", "svd", "wan", "hunyuan", "i2v", "t2v"],
        "reply": "Маршрутизирую в video generation pipeline. Generation остаётся manual/explicit-only до выбора backend adapter.",
        "execute_mode": "pipeline",
        "prepare": ["--json", "prepare", "video_generate"],
    },
    {
        "id": "mask",
        "label": "Camera masks / virtual camera",
        "pipeline_id": "camera_mask_bridge",
        "team_id": "media_generation_team",
        "intent": "camera_mask_bridge",
        "keywords": ["маск", "камера", "видеозвон", "obs", "v4l2", "background", "фон", "matting", "segmentation"],
        "reply": "Маршрутизирую в camera mask bridge. Политика: manual-only, no camera hijack, no implicit capture.",
        "execute_mode": "pipeline",
        "prepare": ["--json", "mask-plan"],
    },
    {
        "id": "vision",
        "label": "Image understanding / metadata",
        "pipeline_id": "image_analysis",
        "team_id": "media_generation_team",
        "intent": "image_analysis",
        "keywords": ["распознай", "опиши изображ", "картинку", "metadata", "exif", "image metadata", "vision", "vlm", "caption"],
        "reply": "Маршрутизирую в image-analysis pipeline. Метаданные работают сейчас; live VLM captioning требует выбранного adapter.",
        "execute_mode": "pipeline",
        "prepare": ["--json", "prepare", "image_analyze"],
    },
    {
        "id": "model_selection",
        "label": "Runtime model selection / epoch optimization",
        "pipeline_id": "model_evolution",
        "team_id": "model_evolution_team",
        "intent": "model_selection",
        "keywords": ["оптимизац", "оптимизируй модель", "оптимизир", "используемой модели", "выбор модели", "отбор модели", "смена эпох", "epoch", "first-start", "first start", "fast", "normal", "full_composite", "full", "model selection", "optimize model"],
        "reply": "Выбери режим отбора модели: fast, normal, full или full_composite N; выбери область; затем я покажу кандидатов перед сменой эпохи.",
        "reply_key": "admin.reply.route.model_selection",
        "execute_mode": "model_selection_plan",
        "suggested_commands": [
            "noemaforge model-selection plan --mode normal --scope 'dev team' --json",
            "sudo noemaforge first-start --normal --dry-run --show-candidates",
            "sudo noemaforge first-start --full_composite 3 --dry-run --show-candidates --show-compositions"
        ],
    },
    {
        "id": "model_evolution",
        "label": "Model evolution / measured improvement cycle",
        "pipeline_id": "model_evolution",
        "team_id": "model_evolution_team",
        "intent": "model_evolution",
        "keywords": ["эволюц", "улучши модель", "улучшение модели", "model evolution", "evolve model", "fine tune", "finetune", "adapter", "lora", "scorecard", "baseline", "регресс"],
        "reply": "Запущу measured model-evolution cycle: baseline, mutation_plan, candidate_profile, scorecard и rollback_plan. Для отбора/смены используемой модели скажи: оптимизируй модель.",
        "reply_key": "admin.reply.route.model_evolution",
        "execute_mode": "pipeline_and_model_evolution",
        "suggested_commands": ["noemaforge model-evolution run --request '<task>' --json"],
    },
    {
        "id": "release",
        "label": "Release preparation",
        "pipeline_id": "release_prep",
        "team_id": "release_team",
        "intent": "release_prep",
        "keywords": ["релиз", "release", "changelog", "version", "архив", "checksum", "sha256", "prod", "публикац"],
        "reply": "Маршрутизирую в release_prep pipeline: версии, проверки, changelog, release notes, archive/checksum.",
        "execute_mode": "pipeline",
    },
]


FALLBACK_ROUTE: Dict[str, Any] = {
    "id": "general",
    "label": "General Admin pipeline",
    "pipeline_id": "public_mwp",
    "team_id": "public_onboarding_team",
    "intent": "general_admin",
    "keywords": [],
    "reply": "Запрос принят. Запущу общий Admin/Public MWP pipeline; при необходимости уточню домен внутри pipeline.",
    "execute_mode": "pipeline",
}


def _word_or_substring_match(txt: str, kw: str, *, greeting: bool = False) -> bool:
    kw = str(kw or "").lower().strip()
    if not kw:
        return False
    if greeting:
        # Prevent derived greeting words from matching the greeting intent.
        return bool(re.search(r"(?<![a-zа-яё0-9])" + re.escape(kw) + r"(?![a-zа-яё0-9])", txt, flags=re.I))
    if " " in kw or len(kw) <= 3:
        return kw in txt
    return kw in txt


def score_route(text: str, route: Dict[str, Any]) -> int:
    txt = str(text or "").lower()
    score = 0
    greeting = str(route.get("id") or "") == "greeting"
    for kw in route.get("keywords") or []:
        kw = str(kw).lower()
        if _word_or_substring_match(txt, kw, greeting=greeting):
            score += 3 if len(kw) > 4 else 1
    return score


def route_request(text: str) -> Dict[str, Any]:
    txt = str(text or "").strip()
    lower = txt.lower()
    scored = [(score_route(txt, route), route) for route in ROUTES]
    boosted = []
    strong_domain_hit = bool(re.search(r"(музык|трек|песня|song|music|код|dev team|доработ|исправ|эволюц|оптимизац|оптимизир|выбор модели|отбор модели|full_composite|first-start|маск|камера|video|видео|фото|изображ)", lower))
    greeting_exact = bool(re.match(r"^\s*(првиет|привет|здравствуй|hello|hi|hey)([!?.\s,]|$)", lower))
    for score, route in scored:
        rid = str(route.get("id") or "")
        if rid == "music" and re.search(r"(музык|трек|песня|song|music|musicgen|riffusion|stable audio|саунд)", lower):
            score = max(score, 14)
        if rid == "code" and re.search(r"(код|dev team|доработ|исправ|patch|bug|рефактор|разработ)", lower):
            # Model-evolution requests often mention code-review; do not let the
            # code route steal explicit evolution intent.
            if not re.search(r"(эволюц|model evolution|evolve model|adapter|lora|улучши модель)", lower):
                score = max(score, 13)
        if rid == "model_selection" and re.search(r"(оптимизац|оптимизир|используемой модели|выбор модели|отбор модели|смена эпох|first-start|first start|full_composite|model selection|optimize model)", lower):
            score = max(score, 16)
        if rid == "model_evolution" and re.search(r"(эволюц|model evolution|evolve model|adapter|lora|улучши модель|модель)", lower) and not re.search(r"(оптимизац|оптимизир|выбор модели|отбор модели|first-start|full_composite)", lower):
            score = max(score, 17)
        if rid == "mask" and re.search(r"(маск|mask|matting|segmentation|virtual camera|v4l2|obs)", lower):
            score = max(score, 12)
        if rid == "greeting":
            if greeting_exact and not strong_domain_hit:
                score = max(score, 8)
            elif strong_domain_hit:
                score = 0
        boosted.append((score, route))
    scored = boosted
    scored.sort(key=lambda item: (-item[0], str(item[1].get("id"))))
    best_score, best = scored[0] if scored else (0, FALLBACK_ROUTE)
    if best_score <= 0:
        best = FALLBACK_ROUTE
    doc = {k: v for k, v in best.items() if k != "keywords"}
    doc["score"] = best_score
    doc["confidence"] = 0.0 if best_score <= 0 else min(1.0, round(best_score / 16.0, 3))
    doc["operator_request"] = txt
    doc["task_type"] = doc.get("intent") or doc.get("id")
    doc.setdefault("suggested_commands", [])
    doc.setdefault("prepare", None)
    missing_context: List[str] = []
    if str(doc.get("id") or "") == "code" and not request_has_project_context(txt):
        missing_context.extend(["project path", "change request"])
    if missing_context:
        doc["missing_context"] = missing_context
    non_mutating_policy = {"auto_route_min_confidence": 0.5} if str(doc.get("id") or "") == "greeting" else {}
    doc["abstention"] = production_ai_contracts.decide_abstention(doc, non_mutating_policy)
    return doc


def _run_json(cmd: Sequence[str], *, env: Optional[Dict[str, str]] = None, cwd: Optional[Path] = None) -> Dict[str, Any]:
    proc = subprocess.run(list(cmd), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=str(cwd) if cwd else None)
    parsed: Any = None
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
        except Exception:
            parsed = proc.stdout.strip()
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "cmd": list(cmd),
        "stdout": parsed,
        "stderr": proc.stderr.strip(),
    }


def create_pipeline_run(root: Path, state: Path, pipeline_id: str, request: str, *, allow_degraded: bool = False, dry_run: bool = False, trace_id: str = "") -> Dict[str, Any]:
    task_id = safe_id(f"admin_{pipeline_id}_{request[:48]}")
    cmd = [
        sys.executable,
        str(root / "src" / "pipeline_runtime.py"),
        "--root",
        str(root),
        "--state",
        str(state),
        "run",
        pipeline_id,
        "--task-id",
        task_id,
        "--request",
        request,
    ]
    if trace_id:
        cmd.extend(["--trace-id", trace_id])
    if allow_degraded:
        cmd.append("--allow-degraded")
    if dry_run:
        cmd.append("--dry-run")
    return _run_json(cmd)


def run_prepare(root: Path, route: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    prepare = route.get("prepare")
    if not prepare:
        return None
    script = root / "tools" / "prep" / "noemaforge-multimodal.sh"
    if not script.exists():
        return {"ok": False, "error": f"missing multimodal script: {script}"}
    env = os.environ.copy()
    env["NOEMAFORGE_ROOT"] = str(root)
    argv = [str(x) for x in prepare]
    # ROUTES stores human-facing CLI fragments; when calling the prep script
    # directly, strip the command group prefix if present.
    if argv and argv[0] in {"multimodal", "media", "mm"}:
        argv = argv[1:]
    return _run_json([str(script), *argv], env=env)


def run_model_evolution(root: Path, state: Path, pipeline_state: Path, request: str, *, pipeline_run_id: str = "", apply: bool = False) -> Dict[str, Any]:
    cmd = [
        sys.executable,
        str(root / "src" / "model_evolution_runtime.py"),
        "--root",
        str(root),
        "--state",
        str(state),
        "--pipeline-state",
        str(pipeline_state),
        "run",
        "--request",
        request,
        "--json",
    ]
    if pipeline_run_id:
        cmd.extend(["--pipeline-run-id", pipeline_run_id])
    if apply:
        cmd.append("--apply")
    return _run_json(cmd)



def extract_improvement_budget(text: str, *, max_steps: int = 0, time_budget_minutes: int = 0, until_stop: bool = False) -> Dict[str, Any]:
    lower = str(text or "").lower()
    steps = int(max_steps or 0)
    minutes = int(time_budget_minutes or 0)
    if not steps:
        m = re.search(r"(\d+)\s*(?:шаг|шага|шагов|step|steps|cycle|cycles|цикл|цикла|циклов)", lower)
        if m:
            steps = int(m.group(1))
    if not minutes:
        m = re.search(r"(\d+)\s*(?:мин|минут|minutes?|m\b)", lower)
        if m:
            minutes = int(m.group(1))
    until = bool(until_stop) or bool(re.search(r"(пока\s+.*(?:останов|стоп)|until\s+.*stop|до\s+тех\s+пор)", lower))
    budget: Dict[str, Any] = {"kind": "bounded_improvement", "max_steps": steps, "time_budget_minutes": minutes, "until_stop": until}
    budget["active"] = bool(steps or minutes or until)
    if steps:
        budget["operator_rule"] = f"run up to {steps} sequential improvement steps"
    elif minutes:
        budget["operator_rule"] = f"run improvement cycles for up to {minutes} minutes"
    elif until:
        budget["operator_rule"] = "continue improvement cycles until operator sends stop/abort"
    return budget


def maybe_usecase_help(root: Path, message: str, locale: str) -> Optional[Dict[str, Any]]:
    lower = str(message or "").lower()
    if not re.search(r"(что значит|объясни|help|справка|что такое|как работает)", lower):
        return None
    cases = {
        "model_selection": {
            "triggers": ["оптимиз", "отбор модели", "выбор модели", "dev team"],
            "title": "Оптимизируй модель для Dev Team",
            "ru": "Это отбор лучшей runtime-модели для роли/области Dev Team. NoemaForge сканирует Vault, запускает role-eval, показывает кандидатов, пишет rollback-plan и НЕ меняет эпоху без отдельного approve/apply.",
            "en": "This selects the best runtime model for the Dev Team scope. NoemaForge scans Vault, runs role evals, shows candidates, writes a rollback plan and does not switch epoch without separate approve/apply.",
        },
        "model_evolution": {
            "triggers": ["эволюц", "model evolution", "улучшение модели"],
            "title": "Эволюция модели",
            "ru": "Это measured improvement cycle: baseline_snapshot, mutation_plan, candidate_profile, scorecard и rollback_plan. Это не скрытое обучение и не автоматическая замена production-модели.",
            "en": "This is a measured improvement cycle: baseline snapshot, mutation plan, candidate profile, scorecard and rollback plan. It is not hidden training or automatic production replacement.",
        },
        "dev_team": {
            "triggers": ["dev team", "доработ", "код"],
            "title": "Доработай код через Dev Team",
            "ru": "Admin сначала уточняет задачу и путь проекта/файла. После этого Dev Team создаёт patch/diff, NoemaForge-context.md, NoemaForge-architecture.md и NoemaForge-qa.md. Прямые правки требуют explicit apply.",
            "en": "Admin first asks for task details and project/file path. Dev Team then creates patch/diff plus context, architecture and QA notes. Direct writes require explicit apply.",
        },
        "depth": {
            "triggers": ["глубин", "30 минут", "10 шаг", "until stop"],
            "title": "Глубина улучшения",
            "ru": "Можно ограничить работу числом шагов, временем или режимом until stop. Если система больше не видит полезных улучшений, она должна честно завершить цикл с reason=no_further_improvement_found.",
            "en": "Work can be bounded by step count, time budget or until-stop mode. If no useful next improvement is found, the system should stop honestly with reason=no_further_improvement_found.",
        },
    }
    selected = None
    for cid, spec in cases.items():
        if any(t in lower for t in spec["triggers"]):
            selected = (cid, spec); break
    if not selected:
        selected = ("model_selection", cases["model_selection"])
    cid, spec = selected
    text = spec.get("ru" if locale.startswith("ru") else "en") or spec["en"]
    return {"id": cid, "title": spec["title"], "reply": f"{spec['title']}: {text}", "available_usecases": [v["title"] for v in cases.values()]}


# ---------------------------------------------------------------------------
# Dashboard-state glossary — deterministic, pre-LLM, D-003 fix
# ---------------------------------------------------------------------------

_STATE_GLOSSARY: list[dict] = [
    {
        "term": "degraded_selected",
        "pattern": r"degraded_selected",
        "ru": "degraded_selected: обязательные роли укомплектованы, но часть выбранных ролей не достигла целевого порога качества. Это состояние WARNING, не критический сбой.",
        "en": "degraded_selected: mandatory core roles are staffed, but some selected roles are below target quality thresholds. This is a WARNING state, not a fatal failure.",
    },
    {
        "term": "selected=N",
        "pattern": r"selected\s*=\s*\d+",
        "ru": "selected=N: N runtime-моделей выбрано для активного покрытия ролей/main.",
        "en": "selected=N: N runtime model(s) were selected for active role/main coverage.",
    },
    {
        "term": "applied_no_reboot",
        "pattern": r"applied_no_reboot",
        "ru": "applied_no_reboot: эпоха выбора моделей применена к живому runtime без перезагрузки.",
        "en": "applied_no_reboot: the model-selection epoch was applied to the live runtime without requiring a reboot.",
    },
    {
        "term": "candidate_map_bad",
        "pattern": r"candidate_map_bad",
        "ru": "candidate_map_bad: количество кандидатов ролей, не прошедших валидацию; 0 означает норму.",
        "en": "candidate_map_bad: count of role candidates that failed validation; 0 means healthy.",
    },
    {
        "term": "tournament_bad",
        "pattern": r"tournament_bad",
        "ru": "tournament_bad: количество записей role-tournament, не прошедших валидацию; 0 означает норму.",
        "en": "tournament_bad: count of role-tournament entries that failed validation; 0 means healthy.",
    },
    {
        "term": "unsafe_count",
        "pattern": r"unsafe_count",
        "ru": "unsafe_count (modelstore): число GGUF-шардов, не прошедших проверку безопасности; 0 означает, что все в норме.",
        "en": "unsafe_count (modelstore): number of GGUF model shards that failed safety validation; 0 means all safe.",
    },
    {
        "term": "runtime_safety",
        "pattern": r"runtime_safety",
        "ru": "runtime_safety (runtime_safety_ok / runtime_safety.ok): прошёл ли post-apply runtime проверки безопасности.",
        "en": "runtime_safety (runtime_safety_ok / runtime_safety.ok): whether the post-apply runtime passed its safety checks.",
    },
    {
        "term": "staffing_state",
        "pattern": r"staffing_state",
        "ru": "staffing_state: итоговый вердикт укомплектованности ролей (например, degraded_selected).",
        "en": "staffing_state: the overall role-staffing verdict (e.g. degraded_selected).",
    },
    {
        "term": "full_composite",
        "pattern": r"full_composite",
        "ru": "full_composite: режим первого запуска, при котором для каждой роли компонуется топ-N кандидатов вместо одного.",
        "en": "full_composite: a first-start mode that composes the top-N candidate models per role instead of a single pick.",
    },
]


def maybe_state_glossary(message: str, locale: str) -> Optional[Dict[str, Any]]:
    """Return a deterministic glossary reply if the message mentions known dashboard-state terms.

    Returns None when:
    - the message is not an explanation request, OR
    - no known term is found in the message.
    """
    lower = str(message or "").lower()
    # Self-contained control guard: suppress the glossary only for an explicit
    # imperative to ACT (so a passive/question mention of a term is still
    # explained). Kept LOCAL and verb-only — it does not reuse the shared
    # has_explicit_control_request router (whose noun terms like "epoch"/"vault"
    # would over-suppress, and whose substring "run" collided with
    # "runtime_safety"). Word boundaries keep "run" out of "runtime".
    if re.search(
        r"(\bзапус|\bоткрой|\bпокажи|\bпроведи|\bсоздай|\bдоработай|\bоптимизир|"
        r"\bпереключи|\bпродолж|\bинвентар|\brun\b|\bstart\b|\bopen\b|"
        r"\bexecute\b|\blaunch\b|\bcontinue\b|\binventory\b)",
        lower,
    ):
        return None
    matched: list[dict] = []
    for entry in _STATE_GLOSSARY:
        if re.search(entry["pattern"], lower):
            matched.append(entry)
    if not matched:
        return None
    use_ru = locale.startswith("ru")
    lines = [e["ru" if use_ru else "en"] for e in matched]
    reply = "\n".join(lines)
    canonical = matched[0]["term"] if len(matched) == 1 else ", ".join(e["term"] for e in matched)
    return {
        "id": "state_glossary",
        "term": canonical,
        "reply": reply,
        "matched_terms": [e["term"] for e in matched],
    }


def is_smalltalk(text: str) -> bool:
    lower = str(text or "").lower().strip()
    return bool(re.search(r"^(супер|спасибо|как ты|ты там|ты жив|рад|hello|hi|thanks|thank you|ок|ok)[!?.\sа-яa-z0-9,-]*$", lower))


def has_explicit_control_request(text: str) -> bool:
    lower = str(text or "").lower().strip()
    return bool(re.search(
        r"(запусти|запуск|запустить|открой|покажи|проведи|создай|доработай|"
        r"оптимизируй|переключи|продолжи|инвентар|run|start|open|execute|"
        r"launch|continue|inventory|pipeline|пайп|public_mwp|evolution|"
        r"model evolution|model-selection|model selection|dev team|vault|epoch|"
        r"media|mask|video|book|gui)",
        lower,
    ))


def is_conversational_smalltalk(text: str) -> bool:
    return is_smalltalk(text) and not has_explicit_control_request(text)

def extract_selection_mode(text: str) -> tuple[str, int]:
    lower = str(text or "").lower()
    m = re.search(r"full[_ -]?composite\s*(\d+)?", lower)
    if m:
        return "full_composite", int(m.group(1) or 0)
    for mode in ["fast", "normal", "full"]:
        if re.search(r"(?<![a-z])" + re.escape(mode) + r"(?![a-z])", lower):
            return mode, -1
    return "", -1


def request_has_project_context(text: str) -> bool:
    lower = str(text or "").lower()
    if re.search(r"(/|~|\.py\b|\.md\b|\.js\b|\.ts\b|\.json\b|\.sh\b|проект|project|repo|файл|file|каталог|directory)", lower):
        return True
    return False


def route_reply(root: Path, route: Dict[str, Any], locale: str) -> str:
    return tr(root, str(route.get("reply_key") or ""), str(route.get("reply") or ""), locale=locale)


def detect_locale(message: str, requested: str = "") -> str:
    explicit = (requested or os.environ.get("NOEMAFORGE_LANG") or os.environ.get("LC_ALL") or os.environ.get("LANG") or "").split(".")[0]
    if explicit:
        return normalize_locale(explicit)
    if re.search(r"[А-Яа-яЁёІіЇїЄєҐґ]", message or ""):
        return "uk" if re.search(r"[ІіЇїЄєҐґ]", message or "") else "ru"
    return normalize_locale("")


def persona_switch_for(route_id: str) -> Optional[Dict[str, str]]:
    mapping = {
        "code": "Dev Team",
        "model_evolution": "Model Evolution",
        "model_selection": "Optimizer",
        "music": "Music Team",
        "voice": "Voice Team",
        "photo": "Image Team",
        "video": "Video Team",
        "mask": "Camera Mask Team",
        "vision": "Vision Team",
    }
    to_persona = mapping.get(route_id)
    if not to_persona:
        return None
    return {"from": "Admin", "to": to_persona, "switch_line_key": "persona.switch_line"}


def artifact_card(kind: str, path: str, *, label: str = "", status: str = "ready") -> Dict[str, Any]:
    return {"type": kind, "status": status, "label": label or Path(path).name, "path": path, "open_command": f"sed -n '1,160p' {sh_quote(path)}" if path else ""}


def sh_quote(value: str) -> str:
    return "'" + str(value).replace("'", "'\\''") + "'"


def collect_artifacts(obj: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    def walk(x: Any, hint: str = "artifact") -> None:
        if isinstance(x, dict):
            if isinstance(x.get("stdout"), dict):
                walk(x["stdout"], hint)
            if x.get("run_dir"):
                out.append(artifact_card("run_dir", str(x["run_dir"]), label="run_dir", status=str(x.get("status") or "ready")))
            if x.get("plan_path"):
                out.append(artifact_card("plan", str(x["plan_path"]), label=Path(str(x["plan_path"])).name, status="planned_only"))
            for key in ["diff", "patch", "backup", "path"]:
                if x.get(key) and isinstance(x.get(key), str) and str(x.get(key)).startswith("/"):
                    out.append(artifact_card("file" if key == "path" else key, str(x[key]), label=key, status="created" if key != "backup" else "backup"))
            arts = x.get("artifacts")
            if isinstance(arts, dict):
                for name, path in arts.items():
                    if path:
                        out.append(artifact_card("artifact", str(path), label=str(name), status="ready"))
            if isinstance(x.get("actions"), list):
                for a in x["actions"]:
                    walk(a, hint)
            if isinstance(x.get("result"), dict):
                walk(x["result"], hint)
        elif isinstance(x, list):
            for item in x:
                walk(item, hint)
    walk(obj)
    # de-duplicate by path+label preserving order
    seen=set(); dedup=[]
    for a in out:
        key=(a.get("path"), a.get("label"), a.get("type"))
        if key in seen:
            continue
        seen.add(key); dedup.append(a)
    return dedup


def run_model_selection(root: Path, state: Path, request: str, *, mode: str, composite_top_n: int, scope: str, apply: bool, trace_id: str = "") -> Dict[str, Any]:
    cmd = [
        sys.executable,
        str(root / "src" / "model_selection_runtime.py"),
        "--root", str(root),
        "--state", str(state),
        "plan",
        "--request", request,
        "--mode", mode,
        "--scope", scope,
        "--composite-top-n", str(composite_top_n),
        "--json",
    ]
    if trace_id:
        cmd.extend(["--trace-id", trace_id])
    if apply:
        cmd.append("--apply")
    return _run_json(cmd)



def read_json_obj(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return default
    return default


def write_json_obj(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json_dumps(obj) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_pipeline_specs_for_admin(root: Path) -> Dict[str, Dict[str, Any]]:
    base = read_json_obj(root / "configs" / "pipelines.json", {})
    if not isinstance(base, dict):
        base = {}
    local = read_json_obj(root / "configs" / "pipelines.local.json", {})
    if isinstance(local, dict):
        for key, value in local.items():
            if isinstance(value, dict):
                base[key] = value
    return base


def load_team_specs_for_admin(root: Path) -> Dict[str, Dict[str, Any]]:
    teams = read_json_obj(root / "configs" / "pipeline-teams.json", {})
    return teams if isinstance(teams, dict) else {}


def cmd_modify_pipeline(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    pipeline_id = safe_id(args.pipeline_id, prefix="pipeline")
    pipelines = load_pipeline_specs_for_admin(root)
    teams = load_team_specs_for_admin(root)
    existing = pipelines.get(pipeline_id)
    if existing is None and not args.create:
        result = {"ok": False, "error": "unknown_pipeline", "pipeline_id": pipeline_id, "available_hint": sorted(list(pipelines))[:30]}
        print(json_dumps(result))
        return 1
    spec = dict(existing or {"description": args.description or f"Admin-created pipeline {pipeline_id}", "stages": ["intake", "plan", "admin_review"], "team": args.team or "admin_console_team"})
    stages = list(spec.get("stages") or [])
    actions: List[Dict[str, Any]] = []
    if args.add_stage:
        stage = safe_id(args.add_stage, prefix="stage")
        if stage not in stages:
            if args.before and args.before in stages:
                stages.insert(stages.index(args.before), stage)
            elif args.after and args.after in stages:
                stages.insert(stages.index(args.after) + 1, stage)
            else:
                # Keep explicit review stages at the tail.
                review_markers = ["admin_review", "review", "manual_operator_review", "merge_plan"]
                insert_at = len(stages)
                for marker in review_markers:
                    if marker in stages:
                        insert_at = min(insert_at, stages.index(marker))
                stages.insert(insert_at, stage)
            actions.append({"action": "add_stage", "stage": stage, "after": args.after or None, "before": args.before or None})
    if args.remove_stage:
        stage = safe_id(args.remove_stage, prefix="stage")
        if stage in stages:
            stages.remove(stage)
            actions.append({"action": "remove_stage", "stage": stage})
    if args.description:
        spec["description"] = args.description
        actions.append({"action": "set_description"})
    if args.team:
        if args.team not in teams:
            result = {"ok": False, "error": "unknown_team", "team_id": args.team, "available_hint": sorted(list(teams))[:30]}
            print(json_dumps(result))
            return 1
        spec["team"] = args.team
        actions.append({"action": "set_team", "team_id": args.team})
    spec["stages"] = stages
    spec.setdefault("llm_policy", {"mode": "switchable", "max_active_llms": 1})
    spec.setdefault("review", {})
    spec["review"].update({"modified_by": "administrator", "modified_at": nowz(), "source": "admin_runtime", "version": RUNTIME_VERSION})
    result: Dict[str, Any] = {"ok": True, "version": RUNTIME_VERSION, "pipeline_id": pipeline_id, "apply": bool(args.apply), "actions": actions, "pipeline": spec}
    if args.apply:
        out = root / "configs" / "pipelines.local.json"
        local = read_json_obj(out, {})
        if not isinstance(local, dict):
            local = {}
        local[pipeline_id] = spec
        write_json_obj(out, local)
        result["out"] = str(out)
        result["message"] = "Pipeline override written. Validate with: noemaforge pipeline validate"
    else:
        result["message"] = "Dry-run only. Add --apply to write configs/pipelines.local.json."
    print(json_dumps(result))
    return 0 if result.get("ok") else 1


def cmd_route(args: argparse.Namespace) -> int:
    message = args.message or " ".join(args.text or [])
    result = {"ok": True, "version": RUNTIME_VERSION, "route": route_request(message)}
    print(json_dumps(result) if args.json else result["route"].get("label"))
    return 0


def cmd_message(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    state = Path(args.state).resolve() if args.state else DEFAULT_STATE
    evo_state = Path(args.evolution_state).resolve() if args.evolution_state else DEFAULT_EVOLUTION_STATE
    selection_state = Path(os.environ.get("NOEMAFORGE_MODEL_SELECTION_STATE", str(DEFAULT_MODEL_SELECTION_STATE))).resolve()
    message = args.message or " ".join(args.text or [])
    trace_id = os.environ.get("NOEMAFORGE_TRACE_ID") or production_ai_contracts.new_trace_id("admin")
    locale = detect_locale(message, getattr(args, "locale", ""))
    route = route_request(message)
    rid = str(route.get("id") or "")
    reply = route_reply(root, route, locale)
    switch = persona_switch_for(rid)
    switch_line = ""
    if switch:
        switch_line = tr(root, "persona.switch_line", "-- persona changed from {from_persona} to {to_persona} --", locale=locale, from_persona=switch["from"], to_persona=switch["to"])
        switch["switch_line"] = switch_line
    result: Dict[str, Any] = {
        "ok": True,
        "version": RUNTIME_VERSION,
        "trace_id": trace_id,
        "locale": locale,
        "created_at": nowz(),
        "mode": "admin_message",
        "message": message,
        "reply": reply,
        "route": route,
        "executed": False,
        "clarification_required": False,
        "persona_switch": switch,
        "internal_events": [],
        "artifacts": [],
        "actions": [],
    }
    budget = extract_improvement_budget(message, max_steps=getattr(args, "max_steps", 0), time_budget_minutes=getattr(args, "time_budget_minutes", 0), until_stop=getattr(args, "until_stop", False))
    if budget.get("active"):
        result["improvement_budget"] = budget
        result["internal_events"].append("Admin recorded bounded improvement depth: " + str(budget.get("operator_rule")))
    glossary = maybe_state_glossary(message, locale)
    if glossary:
        result["reply"] = glossary["reply"]
        result["route"] = {"id": "state_glossary", "intent": "explain", "label": "Dashboard state glossary", "operator_request": message}
        result["persona_switch"] = None
        result["mode"] = "conversation"
        result["state_glossary"] = glossary
        print(json_dumps(result) if args.json else result["reply"])
        return 0
    help_doc = maybe_usecase_help(root, message, locale)
    if help_doc:
        result["persona_switch"] = None
        result["route"] = {"id": "usecase_help", "intent": "help", "label": help_doc["title"], "operator_request": message}
        result["reply"] = help_doc["reply"]
        result["usecase_help"] = help_doc
        print(json_dumps(result) if args.json else result["reply"])
        return 0
    if rid in {"general", "greeting"} and is_conversational_smalltalk(message):
        if locale.startswith("ru"):
            result["reply"] = "Я на месте. NoemaForge работает локально: могу вести обычный диалог, открыть Dev Team, подготовить эволюцию модели или показать статус эпохи."
        else:
            result["reply"] = "I am here. NoemaForge is running locally: I can chat, open Dev Team, prepare model evolution, or show epoch status."
        result["mode"] = "conversation"
        result["route"] = {"id": "conversation", "intent": "conversation", "label": "Admin conversation", "operator_request": message, "pipeline_id": "", "execute_mode": "conversation"}
        result["persona_switch"] = None
        result["executed"] = False
        result["actions"] = []
        print(json_dumps(result) if args.json else result["reply"])
        return 0

    if rid == "code" and not request_has_project_context(message):
        result["clarification_required"] = True
        result["reply"] = reply
        result["questions"] = [
            "Что именно доработать?",
            "Где лежит проект или файл?",
            "Применять правки сразу или сначала показать patch?",
        ]
        result["internal_events"].append("Admin held Dev Team handoff until project/file context is provided")
        print(json_dumps(result) if args.json else result["reply"])
        return 0

    if rid == "model_selection":
        mode, n = extract_selection_mode(message)
        if not mode:
            result["clarification_required"] = True
            result["questions"] = [
                "Режим: fast, normal, full или full_composite N?",
                "Область: весь NoemaForge, active runtime, dev team, QA, media или конкретная роль?",
                "Сначала показать кандидатов или применить после review?",
            ]
            result["internal_events"].append("Admin requested model-selection mode before epoch optimization")
            print(json_dumps(result) if args.json else result["reply"])
            return 0
        if args.execute:
            result["executed"] = True
            scope = "dev team" if re.search(r"dev|разработ|код", message.lower()) else "active runtime"
            msel = run_model_selection(root, selection_state, message, mode=mode, composite_top_n=n if n >= 0 else 0, scope=scope, apply=args.apply, trace_id=trace_id)
            result["actions"].append({"type": "model_selection_plan", "result": msel})
            result["internal_events"].append("Admin routed optimization request to Optimizer")
            result["artifacts"] = collect_artifacts(result)
            if locale.startswith("ru"):
                result["reply"] = f"Режим отбора выбран: {mode}. Область: {scope}. План отбора модели создан; кандидаты, решение и rollback-plan прикреплены как артефакты. Эпоха НЕ применена без отдельного approve/apply."
            else:
                result["reply"] = f"Model-selection mode selected: {mode}. Scope: {scope}. Selection plan is ready; candidates, decision and rollback plan are attached. Epoch is NOT applied without separate approve/apply."
            result["ok"] = bool(msel.get("ok"))
        print(json_dumps(result) if args.json else result.get("reply") or "OK")
        return 0 if result.get("ok") else 1

    if args.execute:
        result["executed"] = True
        pipeline_id = str(route.get("pipeline_id") or "public_mwp")
        pipeline = create_pipeline_run(root, state, pipeline_id, message, allow_degraded=args.allow_degraded, dry_run=args.dry_run, trace_id=trace_id)
        result["actions"].append({"type": "pipeline_run", "pipeline_id": pipeline_id, "result": pipeline})
        result["internal_events"].append(f"Admin routed request to pipeline {pipeline_id}")
        run_id = ""
        if isinstance(pipeline.get("stdout"), dict):
            run_id = str(pipeline["stdout"].get("run_id") or "")
        if rid == "code":
            dev_cmd = [
                sys.executable,
                str(root / "src" / "dev_team_runtime.py"),
                "--root", str(root),
                "--pipeline-state", str(state),
                "run", "--request", message, "--json",
            ]
            if args.allow_degraded:
                dev_cmd.append("--allow-degraded")
            result["actions"].append({"type": "dev_team", "result": _run_json(dev_cmd)})
            result["internal_events"].append("Admin passed clarified task details to Dev Team")
        if args.prepare_media and route.get("prepare"):
            prep = run_prepare(root, route)
            result["actions"].append({"type": "media_prepare", "result": prep})
            if rid in {"music", "voice", "photo", "video"}:
                result["internal_events"].append("Media backend remains explicit/manual; prepared plan artifact instead of hidden generation")
        if route.get("execute_mode") == "pipeline_and_model_evolution":
            evo = run_model_evolution(root, evo_state, state, message, pipeline_run_id=run_id, apply=args.apply)
            result["actions"].append({"type": "model_evolution", "result": evo})
            result["internal_events"].append("Measured model-evolution artifacts produced; no production weights mutated automatically")
            if locale.startswith("ru"):
                result["reply"] = "Measured model-evolution cycle создан. Артефакты: baseline_snapshot, mutation_plan, candidate_profile, scorecard и rollback_plan. Production-веса не менялись автоматически."
            else:
                result["reply"] = "Measured model-evolution cycle is ready. Artifacts: baseline snapshot, mutation plan, candidate profile, scorecard and rollback plan. Production weights were not changed automatically."
        result["artifacts"] = collect_artifacts(result)
        result["ok"] = all(bool(action.get("result", {}).get("ok", True)) for action in result["actions"])

    if args.json:
        print(json_dumps(result))
    else:
        print(result.get("reply") or "OK")
        if result.get("persona_switch"):
            print(result["persona_switch"].get("switch_line"))
        if result.get("executed"):
            for action in result.get("actions") or []:
                print(f"- {action.get('type')}: ok={action.get('result', {}).get('ok')}")
            for art in result.get("artifacts") or []:
                print(f"artifact: {art.get('label')} {art.get('path')}")
    return 0 if result.get("ok") else 1

def cmd_pipelines(args: argparse.Namespace) -> int:
    routes = []
    for route in ROUTES + [FALLBACK_ROUTE]:
        item = {k: v for k, v in route.items() if k != "keywords"}
        item["keywords"] = route.get("keywords", [])[:8]
        routes.append(item)
    doc = {"ok": True, "version": RUNTIME_VERSION, "routes": routes}
    print(json_dumps(doc))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noemaforge admin")
    parser.add_argument("--root")
    parser.add_argument("--state")
    parser.add_argument("--evolution-state")
    sub = parser.add_subparsers(dest="cmd", required=True)

    route = sub.add_parser("route")
    route.add_argument("text", nargs="*")
    route.add_argument("--message")
    route.add_argument("--locale", default="")
    route.add_argument("--json", action="store_true")
    route.set_defaults(func=cmd_route)

    msg = sub.add_parser("message")
    msg.add_argument("text", nargs="*")
    msg.add_argument("--message")
    msg.add_argument("--execute", action="store_true")
    msg.add_argument("--dry-run", action="store_true")
    msg.add_argument("--allow-degraded", action="store_true")
    msg.add_argument("--prepare-media", action="store_true")
    msg.add_argument("--apply", action="store_true", help="allow model-evolution/model-selection candidate profile write; still no hidden heavy training")
    msg.add_argument("--max-steps", type=int, default=0, help="bounded improvement depth: maximum sequential steps")
    msg.add_argument("--time-budget-minutes", type=int, default=0, help="bounded improvement depth: time budget in minutes")
    msg.add_argument("--until-stop", action="store_true", help="bounded improvement depth: continue until explicit stop/abort")
    msg.add_argument("--locale", default="")
    msg.add_argument("--json", action="store_true")
    msg.set_defaults(func=cmd_message)

    pipes = sub.add_parser("pipelines")
    pipes.add_argument("--json", action="store_true")
    pipes.set_defaults(func=cmd_pipelines)


    mod = sub.add_parser("modify-pipeline")
    mod.add_argument("pipeline_id")
    mod.add_argument("--create", action="store_true")
    mod.add_argument("--add-stage", default="")
    mod.add_argument("--after", default="")
    mod.add_argument("--before", default="")
    mod.add_argument("--remove-stage", default="")
    mod.add_argument("--description", default="")
    mod.add_argument("--team", default="")
    mod.add_argument("--apply", action="store_true")
    mod.add_argument("--json", action="store_true")
    mod.set_defaults(func=cmd_modify_pipeline)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())


