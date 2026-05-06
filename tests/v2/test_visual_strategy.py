import pytest
from pathlib import Path

from src.pipeline_v2.gallery import Gallery
from src.pipeline_v2.visual_strategy import (
    add_visual_strategy, _format_gallery_refs, _format_used_approaches,
)


def test_format_used_approaches_empty():
    assert _format_used_approaches([]).strip() == "(none yet)"


def test_format_used_approaches_some():
    out = _format_used_approaches(["a_b", "c_d"])
    assert "- a_b" in out and "- c_d" in out


def test_format_gallery_refs_empty(tmp_path: Path):
    g = Gallery(tmp_path / "index.json")
    out = _format_gallery_refs(g, categories={"comparison", "metric"})
    assert "(no references" in out


@pytest.mark.live
def test_add_visual_strategy_smoke():
    plan = {"slides": [
        {"index": 1, "kind": "title", "headline": "Hello", "subtitle": "Sub"},
        {"index": 2, "kind": "body", "headline": "A vs B",
         "takeaway": "B wins on cost", "implication": "",
         "content_structure": "comparison"},
        {"index": 3, "kind": "closing", "headline": "Thanks", "subtitle": "Q&A"},
    ]}
    out = add_visual_strategy(plan, gallery=None)
    body = [s for s in out["slides"] if s["kind"] == "body"][0]
    vs = body["visual_strategy"]
    assert vs["approach"]
    assert vs["layout_hint"]
    assert isinstance(vs["key_elements"], list) and vs["key_elements"]
