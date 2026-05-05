"""End-to-end render test for the data-viz recipes.

Run:
    PYTHONIOENCODING=utf-8 python tests/test_metrics_recipes.py

Renders one slide per metric recipe so we can eyeball the visual result.
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
        "title": "metric recipes smoke",
        "theme": {
            "background": "#FFFFFF", "head_text": "#1C2833", "head_rule": "#065A82",
            "body_text": "#1C2833", "bullet": "#065A82", "accent": "#1F497D",
        },
        "fonts": {"header": "Pretendard Bold", "body": "Pretendard"},
        "slide_size": {"width_in": 13.333, "height_in": 7.5},
        "section_titles": {"scale": "변화의 규모"},
    }


def test_metric_recipes_render() -> None:
    prs = _new_prs()
    plans = [
        # headline_metric
        {
            "slide_no": 1,
            "head_message": "Fortune 500의 92%가 도입",
            "sub_message": "도입 검토에서 운영 단계로 이동 중",
            "section_id": "scale",
            "recipe": "headline_metric",
            "data": {
                "metric": {"value": "92", "unit": "%",
                           "label": "Fortune 500 생성형 AI 도입/검토",
                           "trend": "+11pp YoY"},
                "context_title": "배경",
                "context_items": [
                    "도입 단계 → 운영 단계로 빠르게 이동",
                    "비도입 기업의 경쟁 압력 가중",
                    "Capex보다 Opex 모델 채택 가속",
                ],
            },
        },
        # kpi_dashboard_2x2
        {
            "slide_no": 2,
            "head_message": "한 눈에 보는 시장 신호",
            "sub_message": None,
            "section_id": "scale",
            "recipe": "kpi_dashboard_2x2",
            "data": {
                "metrics": [
                    {"value": "92",  "unit": "%",  "label": "Fortune 500 도입"},
                    {"value": "70",  "unit": "%",  "label": "개발자 활용"},
                    {"value": "39",  "unit": "%",  "label": "시장 연 성장"},
                    {"value": "5.2", "unit": "배", "label": "AI 논문 증가"},
                ],
            },
        },
        # bar_compare_h
        {
            "slide_no": 3,
            "head_message": "ChatGPT가 모든 기록을 깼다",
            "sub_message": "1억 MAU 도달 일수",
            "section_id": "scale",
            "recipe": "bar_compare_h",
            "data": {
                "title": "1억 사용자까지 걸린 일수 (적을수록 빠름)",
                "items": [
                    {"name": "Threads",  "value": 5,   "unit": "일"},
                    {"name": "ChatGPT",  "value": 60,  "unit": "일"},
                    {"name": "TikTok",   "value": 270, "unit": "일"},
                    {"name": "Instagram","value": 750, "unit": "일"},
                    {"name": "Facebook", "value": 1582,"unit": "일"},
                ],
            },
        },
    ]
    for p in plans:
        render_slide(prs, _deck_meta(), p)
    out = ROOT / "output" / "test_metrics_recipes.pptx"
    out.parent.mkdir(exist_ok=True)
    prs.save(str(out))
    print(f"OK metric recipes rendered ({len(plans)} slides) -> {out}")


if __name__ == "__main__":
    test_metric_recipes_render()
    print("\nALL TESTS PASS")
