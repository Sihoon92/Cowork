"""Matrix-family recipes — two-dimensional comparison layouts."""
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field, field_validator

from src.pipeline.recipes import (
    PrimitiveSpec, RecipeEntry, register,
)
from src.pptx.primitives import Grid, Rect


# ---------------------------------------------------------------------------
# matrix_2x2_compare
#
# Layout (3 × 3 grid):
#
#   ┌──────────┬──────────────┬──────────────┐
#   │  (empty) │ header_strip │ header_strip │  ← col_headers
#   ├──────────┼──────────────┼──────────────┤
#   │ label    │  cell[0][0]  │  cell[0][1]  │
#   ├──────────┼──────────────┼──────────────┤
#   │ label    │  cell[1][0]  │  cell[1][1]  │
#   └──────────┴──────────────┴──────────────┘
#
# Use when the slide compares two categories (col axis) across two attributes
# (row axis). The matrix structure itself is the visual anchor.
# ---------------------------------------------------------------------------

# For Stage 2 we ship one cell primitive: bullet_block. The schema accepts a
# `primitive` field so future stages can add candidates (e.g. metric, takeaway)
# without changing the cell payload contract.
CellPrimitiveName = Literal["bullet_block"]


class MatrixCellSpec(BaseModel):
    primitive: CellPrimitiveName = "bullet_block"
    data: dict = Field(default_factory=dict)

    model_config = {"extra": "ignore"}


class Matrix2x2CompareData(BaseModel):
    col_headers: List[str]
    row_labels: List[str]
    cells: List[List[MatrixCellSpec]]

    model_config = {"extra": "ignore"}

    @field_validator("col_headers")
    @classmethod
    def _exactly_two_cols(cls, v):
        if len(v) != 2:
            raise ValueError(f"col_headers must have exactly 2 entries, got {len(v)}")
        return v

    @field_validator("row_labels")
    @classmethod
    def _exactly_two_rows(cls, v):
        if len(v) != 2:
            raise ValueError(f"row_labels must have exactly 2 entries, got {len(v)}")
        return v

    @field_validator("cells")
    @classmethod
    def _shape_2x2(cls, v):
        if len(v) != 2 or any(len(r) != 2 for r in v):
            raise ValueError("cells must be a 2x2 array of cell specs")
        return v


def _compile_matrix_2x2_compare(
    data: Matrix2x2CompareData, body: Rect,
) -> list[PrimitiveSpec]:
    # 3 rows: thin header band + 2 equal content rows
    # 3 cols: narrow label col + 2 equal content cols
    grid = Grid(
        container=body,
        row_heights=(0.5, 1.7, 1.7),
        col_widths=(2.0, 5.0, 5.0),
        gutter=0.1,
    )

    out: list[PrimitiveSpec] = [
        # Column headers (top row, cols 1-2)
        PrimitiveSpec(name="header_strip", rect=grid.cell(0, 1),
                      data={"text": data.col_headers[0]}),
        PrimitiveSpec(name="header_strip", rect=grid.cell(0, 2),
                      data={"text": data.col_headers[1]}),
        # Row labels (col 0, rows 1-2)
        PrimitiveSpec(name="label_card", rect=grid.cell(1, 0),
                      data={"text": data.row_labels[0]}),
        PrimitiveSpec(name="label_card", rect=grid.cell(2, 0),
                      data={"text": data.row_labels[1]}),
    ]

    # Content cells
    for r in (0, 1):
        for c in (0, 1):
            spec = data.cells[r][c]
            out.append(PrimitiveSpec(
                name=spec.primitive,
                rect=grid.cell(r + 1, c + 1),
                data=spec.data,
            ))
    return out


register(RecipeEntry(
    name="matrix_2x2_compare",
    data_model=Matrix2x2CompareData,
    compile_fn=_compile_matrix_2x2_compare,
    summary=(
        "두 차원 교차 비교 (2 col headers × 2 row labels). 각 cell은 "
        "bullet_block primitive로 채움."
    ),
))
