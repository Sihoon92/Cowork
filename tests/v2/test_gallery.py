from pathlib import Path

from src.pipeline_v2.gallery import Gallery
from src.pipeline_v2.schemas import GalleryEntry


def _entry(deck="d1", slide_no=1, category="comparison",
           approach="a1", quality=8.0):
    return GalleryEntry(
        deck_id=deck, slide_no=slide_no, category=category,
        approach=approach, rationale="r", layout_hint="hint",
        key_elements=["x"],
        scores={"strategy": int(quality), "visual": int(quality), "content": int(quality)},
        quality_score=quality,
        code_snippet="pass",
        created_at="2026-05-06T00:00:00",
    )


def test_gallery_append_and_load(tmp_path: Path):
    g = Gallery(tmp_path / "index.json")
    g.append(_entry())
    g2 = Gallery(tmp_path / "index.json")
    assert len(g2.all()) == 1
    assert g2.all()[0].approach == "a1"


def test_gallery_dedup_keeps_higher_score(tmp_path: Path):
    g = Gallery(tmp_path / "index.json")
    g.append(_entry(quality=7.5))
    g.append(_entry(quality=9.0))
    rows = g.all()
    assert len(rows) == 1
    assert rows[0].quality_score == 9.0


def test_gallery_top_k_per_category(tmp_path: Path):
    g = Gallery(tmp_path / "index.json")
    for i, q in enumerate([7.0, 9.0, 8.5, 6.0]):
        g.append(_entry(slide_no=i, approach=f"a{i}", quality=q))
    g.append(_entry(slide_no=99, category="metric",
                    approach="m1", quality=10.0))
    refs = g.top_k(category="comparison", k=2)
    assert [r.quality_score for r in refs] == [9.0, 8.5]


def test_gallery_pruning_per_category(tmp_path: Path):
    g = Gallery(tmp_path / "index.json", per_category_cap=3)
    for i in range(5):
        g.append(_entry(slide_no=i, approach=f"a{i}",
                        quality=7.0 + i * 0.1))
    rows = [r for r in g.all() if r.category == "comparison"]
    assert len(rows) == 3
    # Oldest pruned: a0, a1 dropped (lowest quality + oldest)
    approaches = {r.approach for r in rows}
    assert "a0" not in approaches
