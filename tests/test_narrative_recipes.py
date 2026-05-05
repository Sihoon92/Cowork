"""End-to-end render test for the narrative recipes (transformation/divider/quote/timeline).

Run:
    PYTHONIOENCODING=utf-8 python tests/test_narrative_recipes.py
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

from pptx import Presentation  # noqa: E402
from pptx.util import Inches  # noqa: E402

from src.pptx.renderer import render_slide  # noqa: E402


def _new_prs() -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    return prs


def _deck_meta() -> dict:
    return {
        "title": "narrative recipes smoke",
        "theme": {
            "background": "#FFFFFF", "head_text": "#1C2833", "head_rule": "#065A82",
            "body_text": "#1C2833", "bullet": "#065A82", "accent": "#1F497D",
        },
        "fonts": {"header": "Pretendard Bold", "body": "Pretendard"},
        "slide_size": {"width_in": 13.333, "height_in": 7.5},
        "section_titles": {"action": "대응 방향"},
    }


def test_narrative_recipes_render() -> None:
    prs = _new_prs()
    plans = [
        # transformation_lr
        {
            "slide_no": 1,
            "head_message": "사무 자동화 As-Is/To-Be 비교",
            "section_id": "action",
            "recipe": "transformation_lr",
            "data": {
                "as_is": {"title": "As-Is",
                          "items": ["보고서 수동 작성", "회의록 사후 정리",
                                    "문서 검색 비효율"]},
                "to_be": {"title": "To-Be",
                          "items": ["보고 템플릿 자동 채움", "회의록 실시간 요약",
                                    "사내 RAG 챗봇"]},
                "arrow_label": "AI 도입",
            },
        },
        # section_divider_strip
        {
            "slide_no": 2,
            "head_message": "(unused for full canvas)",
            "section_id": "action",
            "recipe": "section_divider_strip",
            "data": {"number": "03", "title": "대응 방향",
                     "sub": "조직·개인·기술 3축 정리"},
        },
        # pull_quote
        {
            "slide_no": 3,
            "head_message": "전문가 발언 인용",
            "section_id": "action",
            "recipe": "pull_quote",
            "data": {
                "text": "AI는 도구다. 도메인 전문성을 가진 사람이 가장 빠르게 활용한다.",
                "attribution": "안드레이 카르파시",
                "context": "X 발언, 2024.06",
            },
        },
        # timeline_horizontal
        {
            "slide_no": 4,
            "head_message": "AI 도입 단계별 로드맵",
            "section_id": "action",
            "recipe": "timeline_horizontal",
            "data": {
                "nodes": [
                    {"when": "1단계",
                     "title": "PoC",
                     "note": "단일 부서 실험"},
                    {"when": "2단계",
                     "title": "확산",
                     "note": "성공 사례 → 부서별 전개"},
                    {"when": "3단계",
                     "title": "표준화",
                     "note": "전사 가이드 + 보안 정책"},
                    {"when": "4단계",
                     "title": "내재화",
                     "note": "직무 평가 항목 반영"},
                ],
            },
        },
    ]
    for p in plans:
        render_slide(prs, _deck_meta(), p)
    out = ROOT / "output" / "test_narrative_recipes.pptx"
    out.parent.mkdir(exist_ok=True)
    prs.save(str(out))
    print(f"OK narrative recipes rendered ({len(plans)} slides) -> {out}")


if __name__ == "__main__":
    test_narrative_recipes_render()
    print("\nALL TESTS PASS")
