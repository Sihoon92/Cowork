import pytest
from pydantic import ValidationError

from src.pipeline_v2.schemas import (
    SlideOutline, VisualStrategy, SlidePlanV2,
    CritiqueIssue, SlideCritique, GalleryEntry,
)


def test_slide_outline_title_minimal():
    s = SlideOutline(index=1, kind="title", subtitle="hello")
    assert s.kind == "title"
    assert s.content_structure is None


def test_slide_outline_body_requires_kind_value():
    s = SlideOutline(index=2, kind="body", headline="h",
                     takeaway="t", content_structure="comparison")
    assert s.content_structure == "comparison"


def test_slide_outline_invalid_kind():
    with pytest.raises(ValidationError):
        SlideOutline(index=1, kind="bogus")


def test_visual_strategy_requires_all_fields():
    vs = VisualStrategy(approach="two_card_compare",
                        rationale="A vs B is the simplest contrast",
                        layout_hint="grid 1x2, equal",
                        key_elements=["a", "b"])
    assert vs.approach == "two_card_compare"


def test_slide_plan_v2_body_with_strategy():
    p = SlidePlanV2(
        index=2, kind="body", headline="h", takeaway="t",
        content_structure="metric",
        visual_strategy=VisualStrategy(
            approach="big_number_with_caption",
            rationale="single hero metric",
            layout_hint="centered 96pt + caption",
            key_elements=["value"]),
    )
    assert p.visual_strategy.approach == "big_number_with_caption"


def test_critique_issue_and_critique():
    issue = CritiqueIssue(
        location="3rd card bottom note",
        root_cause="card width includes padding",
        code_hint="card_w = (SLIDE_W - 4*pad)//3",
    )
    c = SlideCritique(score_strategy=8, score_visual=6, score_content=9,
                      issues=[issue], verdict="REVISE")
    assert min(c.score_strategy, c.score_visual, c.score_content) == 6


def test_critique_score_range_validation():
    with pytest.raises(ValidationError):
        SlideCritique(score_strategy=11, score_visual=5, score_content=5,
                      issues=[], verdict="KEEP")


def test_gallery_entry_round_trip():
    g = GalleryEntry(
        deck_id="work_v2_demo", slide_no=3, category="comparison",
        approach="horizontal_metric_cards_dominant_emphasis",
        rationale="emphasize winner",
        layout_hint="grid 1x3, center 1.4x",
        key_elements=["a", "b", "c"],
        scores={"strategy": 9, "visual": 8, "content": 9},
        quality_score=8.0,
        code_snippet="    set_bg(slide, BG)\n",
        created_at="2026-05-06T14:23:11",
    )
    assert g.quality_score == 8.0
    assert g.model_dump()["category"] == "comparison"
