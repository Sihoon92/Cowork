"""Metric / data-visualization recipes.

These recipes activate when raw_facts contain numeric content. They turn
"92%" into a hero number rather than a bullet, and "Threads 5일, ChatGPT
60일, TikTok 270일" into a horizontal bar chart.

Trigger guidance for the LLM:
- 1 dominant number with supporting context → headline_metric
- 3-4 parallel KPIs (no single dominant) → kpi_dashboard_2x2
- 2-6 items being compared on a single numeric axis → bar_compare_h
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from src.pipeline.recipes import PrimitiveSpec, RecipeEntry, register
from src.pptx.primitives import Grid, Rect


# ---------------------------------------------------------------------------
# headline_metric — hero number on the left + supporting bullets on the right
# ---------------------------------------------------------------------------

class _MetricSpec(BaseModel):
    value: str
    unit: Optional[str] = None
    label: Optional[str] = None
    trend: Optional[str] = None

    model_config = {"extra": "ignore"}


class HeadlineMetricData(BaseModel):
    metric: _MetricSpec
    context_title: Optional[str] = None
    context_items: List[str] = Field(default_factory=list)

    model_config = {"extra": "ignore"}

    @field_validator("context_items")
    @classmethod
    def _cap_items(cls, v):
        if len(v) > 5:
            raise ValueError(f"context_items capped at 5, got {len(v)}")
        return v


def _compile_headline_metric(data: HeadlineMetricData, body: Rect) -> list[PrimitiveSpec]:
    g = Grid(container=body, row_heights=(1,), col_widths=(5, 7), gutter=0.3)
    return [
        PrimitiveSpec(name="big_number", rect=g.cell(0, 0),
                      data=data.metric.model_dump()),
        PrimitiveSpec(name="bullet_block", rect=g.cell(0, 1),
                      data={"title": data.context_title,
                            "items": list(data.context_items)}),
    ]


register(RecipeEntry(
    name="headline_metric",
    data_model=HeadlineMetricData,
    compile_fn=_compile_headline_metric,
    summary=(
        "한 개의 강력한 숫자(좌측 hero)를 본문(우측 bullet)으로 받침. "
        "raw_facts에 단일 압도 숫자 + 부연 설명 ≥2개일 때."
    ),
))


# ---------------------------------------------------------------------------
# kpi_dashboard_2x2 — four parallel metrics in 2x2 grid
# ---------------------------------------------------------------------------

class KpiDashboard2x2Data(BaseModel):
    metrics: List[_MetricSpec]

    model_config = {"extra": "ignore"}

    @field_validator("metrics")
    @classmethod
    def _exactly_four(cls, v):
        if len(v) != 4:
            raise ValueError(f"metrics must have exactly 4 entries, got {len(v)}")
        return v


def _compile_kpi_dashboard_2x2(data: KpiDashboard2x2Data, body: Rect) -> list[PrimitiveSpec]:
    g = Grid(container=body, row_heights=(1, 1), col_widths=(1, 1), gutter=0.25)
    out: list[PrimitiveSpec] = []
    for i, m in enumerate(data.metrics):
        r, c = divmod(i, 2)
        out.append(PrimitiveSpec(name="big_number", rect=g.cell(r, c),
                                 data=m.model_dump()))
    return out


register(RecipeEntry(
    name="kpi_dashboard_2x2",
    data_model=KpiDashboard2x2Data,
    compile_fn=_compile_kpi_dashboard_2x2,
    summary=(
        "4개 동등한 KPI를 2x2 격자로 한눈에. 단일 압도 숫자가 없고 "
        "동등한 지표 4개가 있을 때."
    ),
))


# ---------------------------------------------------------------------------
# bar_compare_h — horizontal bar chart for 2-6 numeric items
# ---------------------------------------------------------------------------

class _BarItem(BaseModel):
    name: str
    value: float
    unit: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_value(cls, v):
        try:
            return float(v)
        except (TypeError, ValueError):
            raise ValueError(f"value must be numeric, got {v!r}")


class BarCompareHData(BaseModel):
    title: Optional[str] = None
    items: List[_BarItem]

    model_config = {"extra": "ignore"}

    @field_validator("items")
    @classmethod
    def _items_2_to_6(cls, v):
        if not (2 <= len(v) <= 6):
            raise ValueError(f"items must have 2-6 entries, got {len(v)}")
        return v


def _compile_bar_compare_h(data: BarCompareHData, body: Rect) -> list[PrimitiveSpec]:
    return [
        PrimitiveSpec(name="bar_compare", rect=body,
                      data={"title": data.title,
                            "items": [it.model_dump() for it in data.items]}),
    ]


register(RecipeEntry(
    name="bar_compare_h",
    data_model=BarCompareHData,
    compile_fn=_compile_bar_compare_h,
    summary=(
        "2-6개 항목을 단일 숫자 축으로 가로바 비교. 동일 단위의 정량 비교 "
        "(ex: 사용자 1억까지 걸린 일수, 시장 점유율 등)."
    ),
))
