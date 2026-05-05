"""Baseline recipes — the universal-fallback set.

These cover the slide roles every deck needs:
  - cover         : slide 1 (title slide; bypasses 3-tier header)
  - thesis        : closing slide (full-canvas closing statement)
  - single_bullets: catch-all body slide (one bullet block in the body)
  - split_bullets : two bullet blocks side by side (parallel comparison)

Together with `matrix_2x2_compare` they let any reasonable deck be expressed
without grid coordinate gymnastics from the LLM.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from src.pipeline.recipes import PrimitiveSpec, RecipeEntry, register
from src.pptx.primitives import Grid, Rect


# ---------------------------------------------------------------------------
# single_bullets — body fully filled by one bullet block
# ---------------------------------------------------------------------------

class SingleBulletsData(BaseModel):
    title: Optional[str] = None
    items: List[str] = Field(default_factory=list)

    model_config = {"extra": "ignore"}

    @field_validator("items")
    @classmethod
    def _at_least_one(cls, v):
        if not v:
            raise ValueError("items must contain at least one bullet")
        if len(v) > 7:
            raise ValueError(f"items capped at 7, got {len(v)} — split the slide")
        return v


def _compile_single_bullets(data: SingleBulletsData, body: Rect) -> list[PrimitiveSpec]:
    return [
        PrimitiveSpec(name="bullet_block", rect=body,
                      data={"title": data.title, "items": data.items}),
    ]


register(RecipeEntry(
    name="single_bullets",
    data_model=SingleBulletsData,
    compile_fn=_compile_single_bullets,
    summary="단일 bullet block. 한 가지 결론을 3~6 항목으로 풀 때.",
))


# ---------------------------------------------------------------------------
# split_bullets — two bullet blocks side by side
# ---------------------------------------------------------------------------

class SplitBulletsData(BaseModel):
    left:  SingleBulletsData
    right: SingleBulletsData
    ratio: str = "6_6"   # "5_7", "6_6", "7_5"

    model_config = {"extra": "ignore"}

    @field_validator("ratio")
    @classmethod
    def _valid_ratio(cls, v):
        if v not in ("5_7", "6_6", "7_5"):
            raise ValueError(f"ratio must be one of 5_7|6_6|7_5, got {v!r}")
        return v


def _compile_split_bullets(data: SplitBulletsData, body: Rect) -> list[PrimitiveSpec]:
    weights = {"5_7": (5, 7), "6_6": (6, 6), "7_5": (7, 5)}[data.ratio]
    g = Grid(container=body, row_heights=(1,), col_widths=weights, gutter=0.2)
    return [
        PrimitiveSpec(name="bullet_block", rect=g.cell(0, 0),
                      data={"title": data.left.title, "items": data.left.items}),
        PrimitiveSpec(name="bullet_block", rect=g.cell(0, 1),
                      data={"title": data.right.title, "items": data.right.items}),
    ]


register(RecipeEntry(
    name="split_bullets",
    data_model=SplitBulletsData,
    compile_fn=_compile_split_bullets,
    summary=(
        "두 개의 bullet block 좌우 분할. 평행 비교 (Pros/Cons, A/B, As-Is/To-Be 등). "
        "ratio로 비율 조정: 5_7 | 6_6 | 7_5."
    ),
))


# ---------------------------------------------------------------------------
# cover — full-canvas title slide. Bypasses apply_master.
# ---------------------------------------------------------------------------

class CoverData(BaseModel):
    title: str
    sub: Optional[str] = None
    label: Optional[str] = None
    meta: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("title")
    @classmethod
    def _title_required(cls, v):
        if not str(v).strip():
            raise ValueError("title is required")
        return str(v).strip()


def _compile_cover(data: CoverData, body: Rect) -> list[PrimitiveSpec]:
    return [PrimitiveSpec(name="cover_card", rect=body, data=data.model_dump())]


register(RecipeEntry(
    name="cover",
    data_model=CoverData,
    compile_fn=_compile_cover,
    summary="표지 슬라이드 (full canvas). slide 1에 사용.",
    apply_master=False,
))


# ---------------------------------------------------------------------------
# thesis — full-canvas closing statement
# ---------------------------------------------------------------------------

class ThesisData(BaseModel):
    text: str
    attribution: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("text")
    @classmethod
    def _text_required(cls, v):
        if not str(v).strip():
            raise ValueError("text is required")
        return str(v).strip()


def _compile_thesis(data: ThesisData, body: Rect) -> list[PrimitiveSpec]:
    return [PrimitiveSpec(name="thesis_card", rect=body, data=data.model_dump())]


register(RecipeEntry(
    name="thesis",
    data_model=ThesisData,
    compile_fn=_compile_thesis,
    summary="결론/대표 진술 한 줄 (full canvas). 마지막 슬라이드용.",
    apply_master=False,
))
