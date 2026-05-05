"""End-to-end smoke test for the matrix_2x2_compare recipe (LLM not involved).

Run:
    PYTHONIOENCODING=utf-8 python tests/test_matrix_recipe.py

Generates output/test_matrix_recipe.pptx which should reproduce the user's
reference matrix slide tone:
  - Tier 1 (28pt) section title
  - Tier 2 (18pt ■) head_message
  - Tier 3 (16pt -) sub_message
  - body matrix: 2 navy header strips + 2 grey label cards + 4 plain bullet blocks
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


def _matrix_plan() -> dict:
    """Hardcoded plan that mirrors the user's example automation matrix."""
    return {
        "slide_no": 1,
        "head_message": "자동화 도입 우선순위",
        "sub_message": "현수준 vs 추진계획 — 영역별 격차 가시화",
        "section_id": "automation",
        "recipe": "matrix_2x2_compare",
        "data": {
            "col_headers": ["현수준", "추진계획"],
            "row_labels":  ["공장 자동화", "사무 자동화"],
            "cells": [
                # row 0: 공장 자동화
                [
                    {"primitive": "bullet_block",
                     "data": {"items": [
                         "조립 라인 부분 자동화",
                         "품질 검사 수동 의존",
                         "다운타임 데이터 분산",
                     ]}},
                    {"primitive": "bullet_block",
                     "data": {"items": [
                         "비전 AI 기반 검사 도입",
                         "예지 정비 시스템 PoC",
                         "통합 OEE 대시보드",
                     ]}},
                ],
                # row 1: 사무 자동화
                [
                    {"primitive": "bullet_block",
                     "data": {"items": [
                         "이메일·문서 작업 수동",
                         "보고 자료 반복 작성",
                         "사내 검색 비효율",
                     ]}},
                    {"primitive": "bullet_block",
                     "data": {"items": [
                         "사내 RAG 챗봇 도입",
                         "회의록 자동 요약",
                         "보고 템플릿 자동 채움",
                     ]}},
                ],
            ],
        },
    }


def _deck_meta() -> dict:
    return {
        "title": "matrix recipe smoke",
        "theme": {
            "background": "#FFFFFF", "head_text": "#1C2833", "head_rule": "#065A82",
            "body_text": "#1C2833", "bullet": "#065A82", "accent": "#1F497D",
        },
        "fonts": {"header": "Pretendard Bold", "body": "Pretendard"},
        "slide_size": {"width_in": 13.333, "height_in": 7.5},
        "section_titles": {"automation": "자동화 전략"},
    }


def test_matrix_recipe_renders() -> None:
    prs = _new_prs()
    render_slide(prs, _deck_meta(), _matrix_plan())
    out = ROOT / "output" / "test_matrix_recipe.pptx"
    out.parent.mkdir(exist_ok=True)
    prs.save(str(out))
    print(f"OK matrix recipe rendered -> {out}")


def test_matrix_recipe_invalid_data_isolated() -> None:
    """Bad cell shape should not crash the slide — placeholder appears."""
    plan = _matrix_plan()
    plan["data"]["cells"] = [[{"primitive": "bullet_block", "data": {}}] * 2,
                             [{"primitive": "bullet_block", "data": {}}] * 2]
    plan["data"]["col_headers"] = ["a", "b", "c"]  # invalid: 3 cols
    prs = _new_prs()
    render_slide(prs, _deck_meta(), plan)  # should NOT raise
    out = ROOT / "output" / "test_matrix_recipe_bad.pptx"
    prs.save(str(out))
    print(f"OK invalid recipe data isolated to placeholder -> {out}")


if __name__ == "__main__":
    test_matrix_recipe_renders()
    test_matrix_recipe_invalid_data_isolated()
    print("\nALL TESTS PASS")
