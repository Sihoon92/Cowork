import json
import pytest
from pathlib import Path

from src.pipeline_v2.builder import build_presentation_v2
from src.pipeline_v2.gallery import Gallery


pytestmark = pytest.mark.live


def test_pipeline_v2_end_to_end(tmp_path: Path):
    content = {
        "meta": {"title": "Tiny v2 smoke"},
        "sections": [
            {"heading": "A vs B", "body": "A is fast; B is cheap."},
            {"heading": "Action", "body": "Pilot A this quarter."},
        ],
    }
    out = tmp_path / "smoke_v2.pptx"
    workdir = tmp_path / "work"
    gallery = Gallery(tmp_path / "gallery.json")
    result = build_presentation_v2(
        content,
        output_path=out,
        workdir=workdir,
        gallery=gallery,
        enable_revision=False,
        enable_gallery=False,
        max_iter=1,
    )
    assert result.exists() and result.stat().st_size > 0
    assert (workdir / "outline.json").exists()
    assert (workdir / "plan.json").exists()
    plan = json.loads((workdir / "plan.json").read_text(encoding="utf-8"))
    assert plan["slides"][0]["kind"] == "title"
    assert plan["slides"][-1]["kind"] == "closing"
