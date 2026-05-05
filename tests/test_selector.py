"""Unit tests for src/pipeline/selector.py.

Run:
    PYTHONIOENCODING=utf-8 python tests/test_selector.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_HERE = str(Path(__file__).resolve().parent)
if sys.path and sys.path[0] in ("", _HERE):
    sys.path.pop(0)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.schemas import (  # noqa: E402
    KnowledgeBlock, MatrixCellFact, MatrixData, MetricFact, NarrativePoint,
    QuoteFact, SlideContent, SoWhatQA, TimelineData, TimelineNodeFact,
    TransformBranchFact, TransformData,
)
from src.pipeline.selector import select_recipe  # noqa: E402


def _base_so_what():
    return [
        SoWhatQA(type="WHY", question="왜?", answer="...", evidence=["raw[0]"]),
        SoWhatQA(type="HOW_MUCH", question="얼마나?", answer="...", evidence=["raw[1]"]),
    ]


def _content(intent: str, knowledge: KnowledgeBlock, *, head="head 메시지",
             takeaway="takeaway 메시지") -> SlideContent:
    return SlideContent(
        slide_no=1,
        section_id="s",
        intent_label=intent,  # type: ignore[arg-type]
        so_what=_base_so_what(),
        head_message=head,
        head_derivation="so_what[0]",
        key_takeaway=takeaway,
        key_takeaway_derivation="so_what[0]",
        knowledge=knowledge,
    )


def test_headline_metric_path() -> None:
    k = KnowledgeBlock(
        metrics=[MetricFact(value="92", unit="%", label="도입률",
                            sub_label="Fortune 500 2024")],
        narratives=[NarrativePoint(text="배경 설명 1"),
                    NarrativePoint(text="배경 설명 2")],
    )
    r = select_recipe(_content("single_metric_emphasis", k))
    assert r.recipe == "headline_metric", r.recipe
    assert not r.fell_back, r.reason
    assert r.data["metric"]["value"] == "92"
    assert len(r.data["context_items"]) == 2
    print("OK headline_metric")


def test_bar_compare_path() -> None:
    k = KnowledgeBlock(metrics=[
        MetricFact(value="5", unit="일", label="Threads"),
        MetricFact(value="60", unit="일", label="ChatGPT"),
        MetricFact(value="270", unit="일", label="TikTok"),
    ])
    r = select_recipe(_content("numeric_comparison", k))
    assert r.recipe == "bar_compare_h", r.recipe
    assert not r.fell_back, r.reason
    assert len(r.data["items"]) == 3
    assert r.data["items"][0]["value"] == 5.0
    print("OK bar_compare_h")


def test_kpi_dashboard_path() -> None:
    k = KnowledgeBlock(metrics=[
        MetricFact(value=str(v), unit="%", label=f"KPI {i}")
        for i, v in enumerate([92, 70, 39, 5])
    ])
    r = select_recipe(_content("multi_metric_dashboard", k))
    assert r.recipe == "kpi_dashboard_2x2"
    assert len(r.data["metrics"]) == 4
    print("OK kpi_dashboard_2x2")


def test_matrix_path() -> None:
    k = KnowledgeBlock(matrix=MatrixData(
        col_headers=["현수준", "추진계획"],
        row_labels=["공장", "사무"],
        cells=[
            [MatrixCellFact(bullets=["a", "b"]), MatrixCellFact(bullets=["c", "d"])],
            [MatrixCellFact(bullets=["e", "f"]), MatrixCellFact(bullets=["g", "h"])],
        ],
    ))
    r = select_recipe(_content("two_dim_compare", k))
    assert r.recipe == "matrix_2x2_compare"
    assert len(r.data["cells"]) == 2
    print("OK matrix_2x2_compare")


def test_transformation_path() -> None:
    k = KnowledgeBlock(transformation=TransformData(
        as_is=TransformBranchFact(title="As-Is", items=["수동 작성", "비효율"]),
        to_be=TransformBranchFact(title="To-Be", items=["자동 채움", "RAG"]),
        arrow_label="AI 도입",
    ))
    r = select_recipe(_content("before_after", k))
    assert r.recipe == "transformation_lr"
    assert r.data["arrow_label"] == "AI 도입"
    print("OK transformation_lr")


def test_timeline_path() -> None:
    k = KnowledgeBlock(timeline=TimelineData(nodes=[
        TimelineNodeFact(when="1단계", title="PoC"),
        TimelineNodeFact(when="2단계", title="확산"),
        TimelineNodeFact(when="3단계", title="표준화"),
    ]))
    r = select_recipe(_content("sequence_or_timeline", k))
    assert r.recipe == "timeline_horizontal"
    assert len(r.data["nodes"]) == 3
    print("OK timeline_horizontal")


def test_quotation_path() -> None:
    k = KnowledgeBlock(quotes=[
        QuoteFact(text="AI는 도구다.", attribution="X"),
    ])
    r = select_recipe(_content("quotation", k))
    assert r.recipe == "pull_quote"
    print("OK pull_quote")


def test_cover_thesis_paths() -> None:
    k = KnowledgeBlock()
    r = select_recipe(_content("deck_opening", k, head="AI 시대"))
    assert r.recipe == "cover"
    r = select_recipe(_content("closing_thesis", k))
    assert r.recipe == "thesis"
    print("OK cover + thesis")


def test_general_facts_path() -> None:
    k = KnowledgeBlock(narratives=[NarrativePoint(text=f"fact {i}") for i in range(3)])
    r = select_recipe(_content("general_facts", k))
    assert r.recipe == "single_bullets"
    assert len(r.data["items"]) == 3
    print("OK general_facts → single_bullets")


def test_fallback_when_data_invalid() -> None:
    # bar_compare 의도인데 metric value가 텍스트라 변환 실패 → fallback
    k = KnowledgeBlock(metrics=[
        MetricFact(value="텍스트값", unit=None, label="A"),
        MetricFact(value="다른값", unit=None, label="B"),
    ])
    r = select_recipe(_content("numeric_comparison", k))
    assert r.fell_back, "should have fallen back"
    assert r.recipe == "single_bullets", r.recipe
    assert "bar_compare_h" in r.reason
    print(f"OK fallback ({r.reason[:60]})")


def test_fallback_when_intent_lacks_data() -> None:
    # two_dim_compare 의도인데 matrix 비어있음 → fallback
    k = KnowledgeBlock(narratives=[NarrativePoint(text="x")])
    r = select_recipe(_content("two_dim_compare", k))
    assert r.fell_back
    assert r.recipe == "single_bullets"
    print(f"OK matrix missing → fallback")


if __name__ == "__main__":
    test_headline_metric_path()
    test_bar_compare_path()
    test_kpi_dashboard_path()
    test_matrix_path()
    test_transformation_path()
    test_timeline_path()
    test_quotation_path()
    test_cover_thesis_paths()
    test_general_facts_path()
    test_fallback_when_data_invalid()
    test_fallback_when_intent_lacks_data()
    print("\nALL TESTS PASS")
