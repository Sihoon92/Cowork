"""Unit tests for src/pipeline/checks.py.

Run:
    PYTHONIOENCODING=utf-8 python tests/test_checks.py
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

from src.pipeline.checks import (  # noqa: E402
    check_slide_content,
    estimated_line_count,
    evidence_sufficient,
    is_question,
    jaccard_overlap,
    metric_label_valid,
    same_as_section_title,
    trend_has_direction,
)
from src.pipeline.schemas import (  # noqa: E402
    KnowledgeBlock, MetricFact, SlideContent, SoWhatQA,
)


def test_line_count() -> None:
    # very short → 1 line
    assert estimated_line_count("ChatGPT 1억") == 1
    # exact 25 KO chars + space + numbers → fits in ~6.5in → 1 line
    assert estimated_line_count("ChatGPT, 2개월 만에 1억 사용자") == 1
    # very long → multi-line
    long = "이 문장은 일부러 매우 길게 작성된 헤드메시지로 한 줄을 명백히 초과해야 합니다 추가추가추가" * 2
    assert estimated_line_count(long) >= 2
    print("OK line count")


def test_is_question() -> None:
    assert is_question("어떻게 대처해야 할까")
    assert is_question("AI는 어떻게 변화시키는가")
    assert is_question("정말로?")
    assert not is_question("Fortune 500의 92%가 도입")
    assert not is_question("ChatGPT 1억 사용자 달성 사례")
    print("OK is_question")


def test_same_as_section_title() -> None:
    assert same_as_section_title("변화의 규모", "변화의 규모")
    assert same_as_section_title("변화의 규모.", "변화의 규모")
    assert not same_as_section_title("ChatGPT 1억 명", "변화의 규모")
    print("OK same_as_section_title")


def test_jaccard() -> None:
    a = "ChatGPT 1억 사용자"
    b = "ChatGPT 1억 사용자 달성"
    assert jaccard_overlap(a, b) > 0.7  # 매우 비슷
    c = "법률 의료 자동화 변화"
    assert jaccard_overlap(a, c) < 0.3  # 다름
    assert jaccard_overlap("", "") == 1.0
    assert jaccard_overlap("a", "") == 0.0
    print("OK jaccard")


def test_metric_label_valid() -> None:
    assert metric_label_valid("Fortune 500 도입률")
    assert not metric_label_valid("")
    assert not metric_label_valid("이 라벨은 25자를 명백히 넘어가는 매우 긴 라벨이라서 거절돼야 한다")
    assert not metric_label_valid("어떻게 측정하는가")  # 의문형
    print("OK metric_label_valid")


def test_trend_has_direction() -> None:
    assert trend_has_direction(None)            # 빈 값 OK
    assert trend_has_direction("+12pp YoY")
    assert trend_has_direction("역대 최단")
    assert trend_has_direction("증가 추세")
    assert not trend_has_direction("그냥 빠름")  # 부호·방향어 없음
    print("OK trend_has_direction")


def test_evidence_sufficient() -> None:
    sw = [
        SoWhatQA(type="WHY", question="왜?", answer="...", evidence=["raw[0]"]),
        SoWhatQA(type="HOW_MUCH", question="얼마나?", answer="...", evidence=["raw[1]"]),
    ]
    ok, _ = evidence_sufficient(sw)
    assert ok
    sw_no_ev = [
        SoWhatQA(type="WHY", question="왜?", answer="...", evidence=[]),
        SoWhatQA(type="HOW_MUCH", question="얼마나?", answer="...", evidence=[]),
    ]
    ok, reason = evidence_sufficient(sw_no_ev)
    assert not ok and "evidence" in reason
    print("OK evidence_sufficient")


def _make_content(**overrides) -> SlideContent:
    base = dict(
        slide_no=2,
        section_id="scale",
        intent_label="single_metric_emphasis",
        so_what=[
            SoWhatQA(type="WHY", question="왜?", answer="..", evidence=["raw[0]"]),
            SoWhatQA(type="HOW_MUCH", question="얼마나?", answer="..", evidence=["raw[1]"]),
        ],
        head_message="ChatGPT, 2개월 만에 1억 사용자 — 역대 최단",
        head_derivation="so_what[0]+[1]",
        key_takeaway="AI 채택 속도가 인터넷 시대를 능가",
        key_takeaway_derivation="so_what[0]",
        knowledge=KnowledgeBlock(
            metrics=[MetricFact(value="1억", unit="명", label="MAU 도달")],
        ),
    )
    base.update(overrides)
    return SlideContent.model_validate(base)


def test_check_slide_content_clean() -> None:
    issues = check_slide_content(_make_content(), section_title="변화의 규모")
    assert issues == [], f"unexpected issues: {issues}"
    print("OK check_slide_content (clean)")


def test_check_slide_content_catches() -> None:
    # head too long (must be >60 KO chars to break line at 0.20in/char × 12.13in)
    long_head = (
        "이 헤드는 일부러 매우 길게 작성되어 한 줄에 들어가지 않아야 합니다 "
        "추가 추가 또 추가 더 많은 글자가 필요해서 계속 적어 봅니다 끝없이"
    )
    c = _make_content(head_message=long_head)
    issues = dict(check_slide_content(c))
    assert "head_too_long" in issues, issues

    # head duplicates section title
    c = _make_content(head_message="변화의 규모")
    issues = dict(check_slide_content(c, section_title="변화의 규모"))
    assert "head_duplicates_section" in issues

    # takeaway duplicates head
    c = _make_content(
        head_message="Fortune 500의 92% 도입",
        key_takeaway="Fortune 500 92% 도입",
    )
    issues = dict(check_slide_content(c))
    assert "takeaway_duplicates_head" in issues, issues

    # bad metric label
    c = _make_content(knowledge=KnowledgeBlock(metrics=[
        MetricFact(value="92", unit="%",
                   label="이 라벨은 절대 25자보다 명백하게 길게 작성되었으므로 거절돼야"),
    ]))
    issues = dict(check_slide_content(c))
    assert "metric[0].label_invalid" in issues, issues

    # bad trend
    c = _make_content(knowledge=KnowledgeBlock(metrics=[
        MetricFact(value="92", unit="%", label="도입률", trend="그냥 빠름"),
    ]))
    issues = dict(check_slide_content(c))
    assert "metric[0].trend_no_direction" in issues, issues

    print("OK check_slide_content (catches)")


if __name__ == "__main__":
    test_line_count()
    test_is_question()
    test_same_as_section_title()
    test_jaccard()
    test_metric_label_valid()
    test_trend_has_direction()
    test_evidence_sufficient()
    test_check_slide_content_clean()
    test_check_slide_content_catches()
    print("\nALL TESTS PASS")
