"""Grid + recipe engine smoke tests.

Run:
    PYTHONIOENCODING=utf-8 python tests/test_grid.py
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

from src.pptx.primitives import Grid, Rect  # noqa: E402
from src.pipeline.recipes import (  # noqa: E402
    PrimitiveSpec, RECIPES, RecipeEntry, compile_recipe, get_recipe, register,
)


def _approx(a: float, b: float, eps: float = 1e-6) -> bool:
    return abs(a - b) < eps


def test_grid_uniform_no_gutter() -> None:
    body = Rect(0, 0, 10, 6)
    g = Grid(container=body, row_heights=(1, 1), col_widths=(1, 1, 1), gutter=0)
    # 2 rows × 3 cols, no gutter → each cell is 10/3 wide × 3 tall
    c = g.cell(0, 0)
    assert _approx(c.x, 0) and _approx(c.y, 0)
    assert _approx(c.w, 10 / 3) and _approx(c.h, 3)
    c = g.cell(1, 2)
    assert _approx(c.x, 10 * 2 / 3) and _approx(c.y, 3)
    print("OK uniform grid no gutter")


def test_grid_weighted_with_gutter() -> None:
    body = Rect(0, 0, 12, 8)
    g = Grid(container=body, row_heights=(1, 3), col_widths=(2, 5), gutter=0.2)
    # avail_w = 12 - 0.2 = 11.8 → col0 = 11.8 * 2/7 ≈ 3.371, col1 = 11.8 * 5/7 ≈ 8.428
    c00 = g.cell(0, 0)
    assert _approx(c00.x, 0)
    assert _approx(c00.w, 11.8 * 2 / 7)
    # avail_h = 8 - 0.2 = 7.8 → row0 = 7.8 * 1/4 = 1.95, row1 = 7.8 * 3/4 = 5.85
    assert _approx(c00.h, 7.8 / 4)
    # row 1 starts at row0_h + gutter = 1.95 + 0.2 = 2.15
    c10 = g.cell(1, 0)
    assert _approx(c10.y, 1.95 + 0.2)
    assert _approx(c10.h, 7.8 * 3 / 4)
    print("OK weighted grid with gutter")


def test_grid_cell_span() -> None:
    body = Rect(0, 0, 10, 6)
    g = Grid(container=body, row_heights=(1, 1, 1), col_widths=(1, 1), gutter=0)
    # span 2 cols → covers full width
    c = g.cell(0, 0, cspan=2)
    assert _approx(c.x, 0) and _approx(c.w, 10)
    # span 2 rows starting from row 1 → covers rows 1+2
    c = g.cell(1, 0, rspan=2)
    assert _approx(c.y, 2) and _approx(c.h, 4)
    print("OK cell span")


def test_grid_overflow_rejected() -> None:
    body = Rect(0, 0, 10, 6)
    g = Grid(container=body, row_heights=(1, 1), col_widths=(1, 1), gutter=0)
    for bad in [
        lambda: g.cell(2, 0),                     # row out of range
        lambda: g.cell(0, 2),                     # col out of range
        lambda: g.cell(0, 0, rspan=3),            # rspan overflow
        lambda: g.cell(0, 0, cspan=3),            # cspan overflow
        lambda: g.cell(1, 1, rspan=2),            # combined overflow
        lambda: g.cell(0, 0, rspan=0),            # invalid span
    ]:
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("should have raised on overflow/invalid span")
    print("OK grid rejects overflow")


def test_recipe_registry_basic() -> None:
    """Sanity-check the registry plumbing with an in-line ad-hoc recipe."""
    from pydantic import BaseModel

    class _Probe(BaseModel):
        n: int

    def _compile(data: _Probe, body: Rect) -> list[PrimitiveSpec]:
        g = Grid(container=body, row_heights=(1,) * data.n, col_widths=(1,), gutter=0)
        return [
            PrimitiveSpec(name="probe", rect=g.cell(i, 0), data={"i": i})
            for i in range(data.n)
        ]

    name = "_test_probe_recipe"
    register(RecipeEntry(name=name, data_model=_Probe, compile_fn=_compile,
                         summary="test probe"))
    try:
        assert name in RECIPES
        e = get_recipe(name)
        assert e.summary == "test probe"
        specs = compile_recipe(name, {"n": 3}, Rect(0, 0, 5, 6))
        assert len(specs) == 3
        assert specs[0].name == "probe"
        assert _approx(specs[0].rect.h, 2)
        # bad data → pydantic raises
        try:
            compile_recipe(name, {"n": "not-int"}, Rect(0, 0, 5, 6))
        except Exception:
            pass
        else:
            raise AssertionError("should have raised on bad data")
        # duplicate registration → raises
        try:
            register(RecipeEntry(name=name, data_model=_Probe, compile_fn=_compile,
                                 summary="dup"))
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate registration should raise")
    finally:
        # leave registry clean for other tests
        RECIPES.pop(name, None)
    print("OK recipe registry")


if __name__ == "__main__":
    test_grid_uniform_no_gutter()
    test_grid_weighted_with_gutter()
    test_grid_cell_span()
    test_grid_overflow_rejected()
    test_recipe_registry_basic()
    print("\nALL TESTS PASS")
