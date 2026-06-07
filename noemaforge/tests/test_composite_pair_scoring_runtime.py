#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_composite_pair_scoring_runtime.py
Zone: release/package
Created: 2026-06-04
Modified: 2026-06-04
Purpose: Validate composite-pair diversity scoring used for full_composite planning.
Inputs: composite_pair_scoring module API and CLI.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import composite_pair_scoring as cps


class CompositePairScoringTests(unittest.TestCase):
    def _candidates(self):
        # a,b are a homogeneous llama/llama.cpp/chat pair; c is diverse on every axis.
        return [
            {"id": "a", "family": "llama", "runtime": "llama.cpp", "score": 30.0, "tags": ["chat"]},
            {"id": "b", "family": "llama", "runtime": "llama.cpp", "score": 28.0, "tags": ["chat"]},
            {"id": "c", "family": "qwen", "runtime": "vllm", "score": 26.0, "tags": ["code", "router"]},
        ]

    def _by_models(self, candidates=None):
        pairs = cps.rank_composite_pairs(candidates if candidates is not None else self._candidates())
        return {tuple(p["models"]): p for p in pairs}

    def test_pairs_are_unordered_combinations(self):
        pairs = cps.rank_composite_pairs(self._candidates())
        self.assertEqual(3, len(pairs))  # C(3,2)
        self.assertEqual(3, len({tuple(p["models"]) for p in pairs}))
        for p in pairs:
            self.assertEqual(p["models"], sorted(p["models"]))  # order-independent identity

    def test_diversity_bonus_rewards_heterogeneous_pair(self):
        pairs = self._by_models()
        ab, ac = pairs[("a", "b")], pairs[("a", "c")]
        self.assertEqual(0.0, ab["diversity_bonus"])
        self.assertEqual(
            cps.FAMILY_DIVERSITY_BONUS + cps.RUNTIME_DIVERSITY_BONUS + cps.ROLE_DIVERSITY_BONUS,
            ac["diversity_bonus"],
        )
        self.assertEqual(round(ac["base_score"] + ac["diversity_bonus"], 3), ac["score"])
        self.assertIn("family diversity", ac["reasons"])
        self.assertEqual(["homogeneous pair"], ab["reasons"])

    def test_ranking_is_score_descending(self):
        scores = [p["score"] for p in cps.rank_composite_pairs(self._candidates())]
        self.assertEqual(scores, sorted(scores, reverse=True))
        # a+c (36) beats b+c (35) beats a+b (29): diversity lifts the lower raw pair above the homogeneous top pair.
        self.assertEqual([["a", "c"], ["b", "c"], ["a", "b"]],
                         [p["models"] for p in cps.rank_composite_pairs(self._candidates())])

    def test_composite_top_n_limits_candidates_before_pairing(self):
        pairs = cps.rank_composite_pairs(self._candidates(), composite_top_n=2)
        self.assertEqual(1, len(pairs))  # only the top-2 candidates (a,b) are paired
        self.assertEqual(["a", "b"], pairs[0]["models"])

    def test_fewer_than_two_candidates_yields_no_pairs(self):
        self.assertEqual([], cps.rank_composite_pairs([]))
        self.assertEqual([], cps.rank_composite_pairs([{"id": "solo", "score": 10.0}]))

    def test_missing_fields_are_tolerated(self):
        pairs = cps.rank_composite_pairs([{"id": "x", "score": 5.0}, {"id": "y", "score": 4.0}])
        self.assertEqual(1, len(pairs))
        self.assertEqual(0.0, pairs[0]["diversity_bonus"])
        self.assertEqual(4.5, pairs[0]["base_score"])

    def test_non_numeric_score_does_not_crash(self):
        pairs = cps.rank_composite_pairs([{"id": "x", "score": "n/a"}, {"id": "y"}])
        self.assertEqual(1, len(pairs))
        self.assertEqual(0.0, pairs[0]["base_score"])

    def test_ranking_is_deterministic_regardless_of_input_order(self):
        cands = self._candidates()
        forward = cps.rank_composite_pairs(cands)
        backward = cps.rank_composite_pairs(list(reversed(cands)))
        self.assertEqual(forward, backward)

    def test_cli_emits_ranked_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cand.json"
            path.write_text(json.dumps(self._candidates()), encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cps.main(["--candidates", str(path), "--composite-top-n", "0", "--limit", "2"])
            self.assertEqual(0, rc)
            report = json.loads(buf.getvalue())
            self.assertEqual("CompositePairRanking", report["kind"])
            self.assertEqual(3, report["candidate_count"])
            self.assertEqual(3, report["total_pair_count"])     # full ranking, before --limit
            self.assertEqual(2, report["returned_pair_count"])  # limited to top 2
            self.assertEqual(2, len(report["pairs"]))
            self.assertEqual(["a", "c"], report["pairs"][0]["models"])

    def test_cli_accepts_object_with_candidates_or_models_key(self):
        # _load_candidates() accepts a bare list or an object with a 'candidates'/'models' list.
        for key in ("candidates", "models"):
            with tempfile.TemporaryDirectory() as d:
                path = Path(d) / "obj.json"
                path.write_text(json.dumps({key: self._candidates()}), encoding="utf-8")
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = cps.main(["--candidates", str(path)])
                self.assertEqual(0, rc, key)
                report = json.loads(buf.getvalue())
                self.assertEqual(3, report["candidate_count"], key)
                self.assertEqual(3, report["total_pair_count"], key)

    def test_family_runtime_case_whitespace_not_counted_as_diversity(self):
        # "Llama" vs " llama " and "vLLM" vs "vllm" must normalize to equal -> no family/runtime bonus.
        pairs = cps.rank_composite_pairs([
            {"id": "x", "family": "Llama", "runtime": "vLLM", "score": 10.0, "tags": ["chat"]},
            {"id": "y", "family": " llama ", "runtime": "vllm", "score": 9.0, "tags": ["chat"]},
        ])
        self.assertEqual(1, len(pairs))
        self.assertEqual(0.0, pairs[0]["diversity_bonus"])
        self.assertEqual(["homogeneous pair"], pairs[0]["reasons"])

    def test_unknown_vs_known_metadata_earns_no_bonus(self):
        # If one candidate has an empty/absent family or runtime (missing information),
        # it must NOT earn the diversity bonus vs a candidate with known metadata.
        pairs = cps.rank_composite_pairs([
            {"id": "known", "family": "llama", "runtime": "llama.cpp", "score": 10.0},
            {"id": "unknown", "family": "", "runtime": "", "score": 9.0},
        ])
        self.assertEqual(1, len(pairs))
        self.assertEqual(0.0, pairs[0]["diversity_bonus"],
                         "empty family/runtime must not earn a diversity bonus")

    def test_both_known_and_different_earns_bonus(self):
        # Two candidates with distinct, non-empty family AND runtime both earn the full bonus.
        pairs = cps.rank_composite_pairs([
            {"id": "a", "family": "llama", "runtime": "llama.cpp", "score": 10.0},
            {"id": "b", "family": "qwen", "runtime": "vllm", "score": 9.0},
        ])
        self.assertEqual(1, len(pairs))
        self.assertIn("family diversity", pairs[0]["reasons"])
        self.assertIn("runtime diversity", pairs[0]["reasons"])

    def test_loader_rejects_non_object_entry(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.json"
            path.write_text(json.dumps([{"id": "a", "score": 1}, "not-an-object"]), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                cps._load_candidates(str(path))
            self.assertIn("index 1", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
