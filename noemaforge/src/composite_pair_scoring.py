#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/composite_pair_scoring.py
Zone: release/package
Created: 2026-06-04
Modified: 2026-06-04
Purpose: Rank diversity-aware composite model pairs for full_composite selection planning.
Inputs: A list of scored model candidates (id/family/runtime/score plus optional tags).
Outputs: Ranked composite-pair descriptors (JSON) via the API or the read-only CLI.
Side effects: None; pure scoring with an optional read-only JSON CLI.
Tests: python3 -m py_compile noemaforge/src/composite_pair_scoring.py; python3 -m unittest test_composite_pair_scoring_runtime.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===

Composite-pair diversity scorer for the full_composite model-selection mode.

`model_selection_runtime.py` plans "role compositions from top N candidates" but
delegates the actual ranking to the heavy `first-start` model-selection run. This
module adds a small, deterministic, dependency-free primitive that ranks candidate *pairs* by
combined fit score plus a diversity bonus (different model family / runtime /
role tag), so the planner and operators can preview which compositions are worth
evaluating before committing to a heavy first-start epoch run.

The scorer is intentionally schema-light: a candidate is any mapping carrying an
`id` and a numeric `score` (its own fit score from the upstream scorecard), plus
optional `family`, `runtime` and `tags`. Missing fields are treated as empty and
never raise.
"""
from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Diversity bonuses (additive, applied once per differing dimension between the two
# models in a pair). Kept small relative to typical fit scores so they break ties
# toward heterogeneous compositions without overriding a clearly stronger pair.
FAMILY_DIVERSITY_BONUS = 4.0
RUNTIME_DIVERSITY_BONUS = 2.0
ROLE_DIVERSITY_BONUS = 2.0

# API version for the CompositePairRanking output schema.
# This is a schema identifier, not the product/runtime version.
_API_VERSION = "noemaforge.composite-pair-scoring/v1"


def _field(candidate: Dict[str, Any], name: str, default: Any = "") -> Any:
    value = candidate.get(name, default)
    return value if value is not None else default


def _norm(value: Any) -> str:
    """Normalize a scalar field (family/runtime) for comparison: stripped, lowercased.

    Matches the normalization applied to tags, so case/whitespace differences such as
    "Llama" vs "llama" do not count as diversity.
    """
    return str(value or "").strip().lower()


def _score_of(candidate: Dict[str, Any]) -> float:
    try:
        return float(_field(candidate, "score", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _role_tags(candidate: Dict[str, Any]) -> set:
    tags = candidate.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return {str(t).strip().lower() for t in tags if str(t).strip()}


def pair_score(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """Score one composite pair: mean fit score plus diversity bonuses."""
    base = (_score_of(left) + _score_of(right)) / 2.0

    reasons: List[str] = []
    diversity = 0.0
    # Award family/runtime diversity only when BOTH sides have non-empty metadata AND they
    # differ. An unknown-vs-known comparison (one side empty) must not receive the bonus,
    # since an empty field signals missing information rather than a different family/runtime.
    left_fam, right_fam = _norm(_field(left, "family")), _norm(_field(right, "family"))
    if left_fam and right_fam and left_fam != right_fam:
        diversity += FAMILY_DIVERSITY_BONUS
        reasons.append("family diversity")
    left_rt, right_rt = _norm(_field(left, "runtime")), _norm(_field(right, "runtime"))
    if left_rt and right_rt and left_rt != right_rt:
        diversity += RUNTIME_DIVERSITY_BONUS
        reasons.append("runtime diversity")
    left_tags, right_tags = _role_tags(left), _role_tags(right)
    if left_tags != right_tags and (left_tags or right_tags):
        diversity += ROLE_DIVERSITY_BONUS
        reasons.append("role/tag diversity")

    # Sort the two model ids so a pair's identity is order-independent.
    models = sorted([str(_field(left, "id", "?")), str(_field(right, "id", "?"))])
    return {
        "kind": "composite_pair",
        "models": models,
        "base_score": round(base, 3),
        "diversity_bonus": round(diversity, 3),
        "score": round(base + diversity, 3),
        "reasons": reasons or ["homogeneous pair"],
    }


def rank_composite_pairs(candidates: Sequence[Dict[str, Any]], composite_top_n: int = 0) -> List[Dict[str, Any]]:
    """Return composite pairs ranked by score desc, then by model ids for stability.

    `composite_top_n` limits how many top candidates (by their own fit score) are
    paired before scoring; 0 (or negative) means use every candidate. Fewer than
    two candidates yields no pairs.
    """
    # Stable, deterministic candidate order: score desc, then id asc within ties.
    ranked = sorted(candidates, key=lambda c: str(_field(c, "id", "")))
    ranked.sort(key=_score_of, reverse=True)
    if composite_top_n and composite_top_n > 0:
        ranked = ranked[:composite_top_n]

    pairs = [pair_score(left, right) for left, right in combinations(ranked, 2)]
    # Stable, deterministic pair order: score desc, then model ids asc within ties.
    pairs.sort(key=lambda p: p["models"])
    pairs.sort(key=lambda p: p["score"], reverse=True)
    return pairs


def _load_candidates(path: str) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        # Use explicit key presence so an explicitly-empty "candidates" is not overridden by "models".
        if "candidates" in data:
            data = data["candidates"]
        elif "models" in data:
            data = data["models"]
        else:
            data = []
    if not isinstance(data, list):
        raise ValueError("candidate inventory must be a JSON list or an object with a 'candidates'/'models' list")
    out: List[Dict[str, Any]] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"candidate at index {i} must be a JSON object, got {type(item).__name__}")
        out.append(dict(item))
    return out


def build_report(candidates: Sequence[Dict[str, Any]], composite_top_n: int = 0, limit: int = 0) -> Dict[str, Any]:
    pairs = rank_composite_pairs(candidates, composite_top_n=composite_top_n)
    total_pairs = len(pairs)
    if limit and limit > 0:
        pairs = pairs[:limit]
    return {
        "apiVersion": _API_VERSION,
        "kind": "CompositePairRanking",
        "composite_top_n": int(composite_top_n),
        "candidate_count": len(candidates),
        "total_pair_count": total_pairs,
        "returned_pair_count": len(pairs),
        "pairs": pairs,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="noemaforge composite-pairs",
        description="Rank diversity-aware composite model pairs for full_composite planning.",
    )
    parser.add_argument("--candidates", required=True,
                        help="Path to a JSON list of scored candidates (id/family/runtime/score[/tags]).")
    parser.add_argument("--composite-top-n", type=int, default=0,
                        help="Pair only the top N candidates by fit score (0 = all).")
    parser.add_argument("--limit", type=int, default=0,
                        help="Print only the top L ranked pairs (0 = all).")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    candidates = _load_candidates(args.candidates)
    report = build_report(candidates, composite_top_n=args.composite_top_n, limit=args.limit)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
