"""Tests for the gallery store (codegen path support)."""
from __future__ import annotations

import json
from pathlib import Path

from src.pipeline.gallery import Gallery, MIN_SCORE


def test_examples_for_dedupes_by_approach_and_sorts_by_score(tmp_path: Path):
    g = Gallery(tmp_path)
    g.add("single_metric_emphasis", approach="dom_v1", layout_hint="A", score=7)
    g.add("single_metric_emphasis", approach="dom_v2", layout_hint="B", score=6)
    g.add("single_metric_emphasis", approach="dom_v1", layout_hint="A", score=7)

    examples = g.examples_for("single_metric_emphasis", k=3)
    approaches = [e["approach"] for e in examples]
    scores = [e["score"] for e in examples]

    assert approaches == ["dom_v1", "dom_v2"], f"unexpected: {approaches}"
    assert scores == sorted(scores, reverse=True)


def test_examples_for_unknown_intent_returns_empty(tmp_path: Path):
    g = Gallery(tmp_path)
    assert g.examples_for("two_dim_compare") == []


def test_harvest_only_saves_high_scoring_slides_with_visual_strategy(tmp_path: Path):
    g = Gallery(tmp_path)
    critiques_path = tmp_path / "critiques.json"
    critiques_path.write_text(json.dumps({
        "critiques": [
            {"slide_no": 2, "axes": [{"verdict": "ok"}] * 7},  # 7/7 → save
            {"slide_no": 3, "axes": [{"verdict": "ok"}] * 5},  # 5/7 → skip
            {"slide_no": 4, "axes": [{"verdict": "ok"}] * 7},  # no strategy → skip
        ]
    }), encoding="utf-8")
    plan = {
        "slides": [
            {"slide_no": 2, "intent_label": "numeric_comparison",
             "visual_strategy": {"approach": "v1", "layout_hint": "L"},
             "head_message": "h"},
            {"slide_no": 3, "intent_label": "numeric_comparison",
             "visual_strategy": {"approach": "v2", "layout_hint": "L"},
             "head_message": "h"},
            {"slide_no": 4, "intent_label": "numeric_comparison",
             "visual_strategy": None,
             "head_message": "h"},
        ]
    }
    n = g.harvest_from_run(plan, critiques_path)
    assert n == 1
    saved = g.examples_for("numeric_comparison")
    assert len(saved) == 1
    assert saved[0]["approach"] == "v1"
    assert saved[0]["score"] == 7


def test_harvest_threshold_uses_min_score_constant(tmp_path: Path):
    g = Gallery(tmp_path)
    critiques_path = tmp_path / "critiques.json"
    # exactly MIN_SCORE axes ok → should save
    critiques_path.write_text(json.dumps({
        "critiques": [
            {"slide_no": 1, "axes": [{"verdict": "ok"}] * MIN_SCORE
                                    + [{"verdict": "warn"}] * (7 - MIN_SCORE)},
        ]
    }), encoding="utf-8")
    plan = {"slides": [{"slide_no": 1, "intent_label": "general_facts",
                        "visual_strategy": {"approach": "x", "layout_hint": "L"},
                        "head_message": "h"}]}
    assert g.harvest_from_run(plan, critiques_path) == 1


def test_harvest_missing_critiques_file_returns_zero(tmp_path: Path):
    g = Gallery(tmp_path)
    assert g.harvest_from_run({"slides": []}, tmp_path / "missing.json") == 0
