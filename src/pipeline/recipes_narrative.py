"""Narrative recipes — transformations, dividers, quotes, timelines."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from src.pipeline.recipes import PrimitiveSpec, RecipeEntry, register
from src.pipeline.recipes_basic import SingleBulletsData
from src.pptx.primitives import Grid, Rect


# ---------------------------------------------------------------------------
# transformation_lr — As-Is | arrow | To-Be
#
# ┌────────────┐    →    ┌────────────┐
# │   As-Is    │  label  │   To-Be    │
# │  bullets   │         │  bullets   │
# └────────────┘         └────────────┘
# ---------------------------------------------------------------------------

class TransformationLrData(BaseModel):
    as_is: SingleBulletsData
    to_be: SingleBulletsData
    arrow_label: Optional[str] = None  # e.g. "AI 도입", "자동화", "표준화"

    model_config = {"extra": "ignore"}


def _compile_transformation_lr(data: TransformationLrData, body: Rect) -> list[PrimitiveSpec]:
    g = Grid(container=body, row_heights=(1,), col_widths=(5, 2, 5), gutter=0.15)
    return [
        PrimitiveSpec(name="bullet_block", rect=g.cell(0, 0),
                      data={"title": data.as_is.title or "As-Is",
                            "items": list(data.as_is.items)}),
        PrimitiveSpec(name="arrow_transform", rect=g.cell(0, 1),
                      data={"label": data.arrow_label}),
        PrimitiveSpec(name="bullet_block", rect=g.cell(0, 2),
                      data={"title": data.to_be.title or "To-Be",
                            "items": list(data.to_be.items)}),
    ]


register(RecipeEntry(
    name="transformation_lr",
    data_model=TransformationLrData,
    compile_fn=_compile_transformation_lr,
    summary=(
        "좌측 As-Is + 가운데 화살표 + 우측 To-Be. 변화·이행을 명시적으로 보고할 때. "
        "ex: 수동→자동, 분산→통합, 사일로→연결."
    ),
))


# ---------------------------------------------------------------------------
# section_divider_strip — full canvas section opener
# ---------------------------------------------------------------------------

class SectionDividerData(BaseModel):
    number: str
    title: str
    sub: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("number")
    @classmethod
    def _number_short(cls, v):
        s = str(v).strip()
        if not s:
            raise ValueError("number is required (e.g. '01', 'I', '1')")
        if len(s) > 4:
            raise ValueError(f"number must be ≤4 chars, got {len(s)}")
        return s

    @field_validator("title")
    @classmethod
    def _title_required(cls, v):
        if not str(v).strip():
            raise ValueError("title is required")
        return str(v).strip()


def _compile_section_divider(data: SectionDividerData, body: Rect) -> list[PrimitiveSpec]:
    return [PrimitiveSpec(name="section_band", rect=body, data=data.model_dump())]


register(RecipeEntry(
    name="section_divider_strip",
    data_model=SectionDividerData,
    compile_fn=_compile_section_divider,
    summary=(
        "섹션 전환 슬라이드 (full canvas). 좌측 액센트 띠 + 큰 번호 + 우측 섹션 제목. "
        "deck의 섹션 경계에 1장씩."
    ),
    apply_master=False,
))


# ---------------------------------------------------------------------------
# pull_quote — large quotation with attribution
# ---------------------------------------------------------------------------

class PullQuoteData(BaseModel):
    text: str
    attribution: Optional[str] = None
    context: Optional[str] = None  # e.g. publication / source line

    model_config = {"extra": "ignore"}

    @field_validator("text")
    @classmethod
    def _text_required(cls, v):
        s = str(v).strip()
        if not s:
            raise ValueError("text is required")
        if len(s) > 200:
            raise ValueError(f"quote text too long ({len(s)} chars > 200)")
        return s


def _compile_pull_quote(data: PullQuoteData, body: Rect) -> list[PrimitiveSpec]:
    return [PrimitiveSpec(name="pull_quote", rect=body, data=data.model_dump())]


register(RecipeEntry(
    name="pull_quote",
    data_model=PullQuoteData,
    compile_fn=_compile_pull_quote,
    summary=(
        "외부 인용·내부 멘트를 큰 따옴표로 강조. 인터뷰·리포트·관계자 발언 인용용. "
        "200자 이내."
    ),
))


# ---------------------------------------------------------------------------
# timeline_horizontal — 3-5 nodes in a horizontal sequence
# ---------------------------------------------------------------------------

class _TimelineNode(BaseModel):
    when: str   # "2022", "Q1", "1단계" 등
    title: str
    note: Optional[str] = None

    model_config = {"extra": "ignore"}


class TimelineHorizontalData(BaseModel):
    nodes: List[_TimelineNode]

    model_config = {"extra": "ignore"}

    @field_validator("nodes")
    @classmethod
    def _nodes_3_to_5(cls, v):
        if not (3 <= len(v) <= 5):
            raise ValueError(f"nodes must have 3-5 entries, got {len(v)}")
        return v


def _compile_timeline_horizontal(
    data: TimelineHorizontalData, body: Rect,
) -> list[PrimitiveSpec]:
    n = len(data.nodes)
    # 1 row containing N node columns. Connector spans the whole width
    # at the same vertical position as the nodes' marker circles.
    g = Grid(container=body, row_heights=(1,), col_widths=tuple([1] * n),
             gutter=0.4)
    out: list[PrimitiveSpec] = []
    # Connector under the markers — full width slice across the top portion
    # of the body. timeline_connector's draw fn uses rect.y + 0.275 as line y
    # (same offset the node uses for its marker center).
    connector_rect = Rect(body.x, body.y, body.w, 0.6)
    out.append(PrimitiveSpec(name="timeline_connector", rect=connector_rect,
                             data={}))
    for i, node in enumerate(data.nodes):
        out.append(PrimitiveSpec(name="timeline_node", rect=g.cell(0, i),
                                 data=node.model_dump()))
    return out


register(RecipeEntry(
    name="timeline_horizontal",
    data_model=TimelineHorizontalData,
    compile_fn=_compile_timeline_horizontal,
    summary=(
        "3-5개 시점·단계를 가로 타임라인으로. 시간 흐름·도입 단계·로드맵 보고에 적합. "
        "각 노드는 when (시점) + title + 선택 note."
    ),
))
