#!/usr/bin/env python3
from __future__ import annotations

# === NoemaForge Autodoc File Header ===
# File: src/administrator.py
# Purpose: Provide the module 'administrator'.
# Invoked by / imported from:
#   - direct operator invocation or test discovery
# Public API / entry functions:
#   - module-level helpers / CLI entrypoint
# Inputs:
#   - local filesystem paths, command-line arguments, and NoemaForge runtime/install state
# Output formats / side effects:
#   - local JSON/YAML/text artifacts or process exit status
# AutoDoc: refreshed 2026-04-13 (manual)
# === End NoemaForge Autodoc File Header ===


# === NoemaForge File Header ===
# File: src/administrator.py
# Zone: brain
# Purpose: Provide lightweight request-domain inference and delegation planning for the first-class administrator role.
# Callers: future head-gateway / operator entrypoints, voice or text front-door handlers, tests.
# Inputs: user text, optional modality hints, local capability/dataset availability.
# Outputs: structured administrator decision JSON (domain, delegated roles, ask-boundaries flag, guidance).
# Side effects: none.
# Security notes:
#   - Pure compute helper; no tool execution and no epoch mutation.
#   - Designed to prefer explicit clarification when confidence is low.
# === End NoemaForge File Header ===


from typing import Any, Dict, List

DOMAIN_RULES = {
    'code': ['python', 'api', 'bug', 'sql', 'refactor', 'code', 'test', 'backend', 'frontend', 'код', 'ошибка', 'исправ', 'доработ', 'тест', 'версия', 'релиз'],
    'writing': ['book', 'novel', 'story', 'article', 'edit', 'writer', 'chapter', 'scene', 'книга', 'текст', 'статья', 'сцена', 'редак'],
    'video': ['video', 'edit video', 'clip', 'camera', 'discord', 'meet', 'stream', 'видео', 'ролик', 'камера', 'маск', 'звонок'],
    'music': ['music', 'audio', 'song', 'mix', 'master', 'voice', 'музык', 'трек', 'песня', 'голос', 'озвуч'],
    'knowledge': ['what is', 'explain', 'knowledge', 'grounded', 'graph', 'memory', 'объясни', 'что такое', 'знани', 'граф', 'память'],
    'learning': ['learn', 'teacher', 'coach', 'language', 'discipline', 'lesson', 'учить', 'урок', 'коуч', 'язык'],
    'ops': ['security', 'policy', 'epoch', 'pre-start', 'firstboot', 'toolproxy', 'безопас', 'политик', 'аудит'],
    'model_evolution': ['эволюц', 'model evolution', 'evolve model', 'fine tune', 'finetune', 'lora', 'scorecard', 'улучши модель'],
}

DOMAIN_ROLES = {
    'code': ['solution_architect', 'dev', 'qa'],
    'writing': ['writer', 'editor.literary', 'fact_checker'],
    'video': ['video_editor', 'media_operator'],
    'music': ['media_operator', 'administrator'],
    'knowledge': ['administrator', 'ssr'],
    'learning': ['coach'],
    'ops': ['surgeon', 'scary'],
    'model_evolution': ['administrator', 'test_architect', 'optimizer', 'rollback_reviewer'],
}

DOMAIN_PIPELINES = {
    'code': 'dev_pipeline_member_cells',
    'writing': 'book',
    'video': 'video_generation',
    'music': 'music_generation',
    'knowledge': 'knowledge_graph',
    'learning': 'curriculum_training_plan',
    'ops': 'release_prep',
    'model_evolution': 'model_evolution',
}


def infer_mode(text: str) -> Dict[str, Any]:
    txt = str(text or '').lower()
    hits: Dict[str, int] = {}
    for domain, needles in DOMAIN_RULES.items():
        score = sum(1 for n in needles if n in txt)
        if score:
            hits[domain] = score
    if not hits:
        return {
            'domain': 'unknown',
            'confidence': 0.0,
            'delegated_roles': [],
            'pipeline_id': 'public_mwp',
            'ask_boundaries': True,
            'candidate_domains': sorted(DOMAIN_RULES.keys()),
            'guidance': ['Clarify the requested domain or desired outcome before delegating work.'],
        }
    ordered = sorted(hits.items(), key=lambda kv: (-kv[1], kv[0]))
    primary = ordered[0][0]
    secondary = [d for d, _ in ordered[1:3]]
    total = sum(hits.values()) or 1
    conf = float(hits[primary]) / float(total)
    ask = conf < 0.65 or (len(secondary) > 0 and hits[primary] == hits.get(secondary[0], 0))
    delegated = list(DOMAIN_ROLES.get(primary, ['administrator']))
    if secondary:
        for dom in secondary:
            for role in DOMAIN_ROLES.get(dom, []):
                if role not in delegated:
                    delegated.append(role)
    return {
        'domain': primary,
        'confidence': round(conf, 3),
        'delegated_roles': delegated,
        'pipeline_id': DOMAIN_PIPELINES.get(primary, 'public_mwp'),
        'ask_boundaries': ask,
        'candidate_domains': [primary] + secondary,
        'guidance': ['Ask for boundaries before routing.' if ask else 'Proceed with the inferred specialist roles and pipeline.'],
    }


def explain_capabilities() -> List[str]:
    return [
        'Interpret user text or audio and identify the working domain.',
        'Delegate to specialist roles or combine roles when the request spans multiple domains.',
        'Answer from grounded local knowledge when available.',
        'Create, inspect, and update tasks.',
        'Route requests to concrete NoemaForge pipelines including dev-team, media generation and measured model-evolution.',
        'Explain available NoemaForge workflows, policies, and operator controls.',
    ]



def respond(text: str, *, store=None, prep_store=None, grounded_preferred: bool = True, book_id: str = '', limit: int = 5) -> Dict[str, Any]:
    """Return an administrator response plan.

    If a knowledge store and prep-store are supplied, the administrator prefers a
    grounded answer for knowledge-like requests. Otherwise it falls back to domain
    inference and delegation guidance.
    """
    decision = infer_mode(text)
    if grounded_preferred and store is not None and prep_store is not None:
        dom = str(decision.get('domain') or '')
        if dom in {'knowledge', 'unknown'} or str(text or '').strip().endswith('?'):
            try:
                from knowledge.grounded_administrator import answer_query
                grounded = answer_query(store=store, prep_store=prep_store, query=str(text), book_id=str(book_id or ''), limit=int(limit))
                grounded['delegation'] = decision
                return grounded
            except Exception as e:  # pragma: no cover - safety fallback
                return {
                    'ok': False,
                    'mode': 'administrator_error',
                    'error': repr(e),
                    'delegation': decision,
                }
    return {
        'ok': True,
        'mode': 'delegation_plan',
        'delegation': decision,
        'capabilities': explain_capabilities(),
    }
