"""Deterministic slide renderer — recipe era.

Plan schema (per slide):

    {
      "slide_no": int,
      "head_message": str,
      "sub_message": str | null,
      "section_id": str | null,
      "intent": str,
      "rationale": str,
      "recipe": "<recipe-name>",
      "data": { ...recipe-specific... }
    }

Recipes that set `apply_master=False` (cover, thesis, section_divider_strip)
get the full canvas Rect; everything else gets the body Rect produced by the
3-tier header. Per-primitive failures are isolated — a placeholder rect
replaces the failing primitive, the rest of the slide still renders.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List

from src.pipeline.recipes import compile_recipe, get_recipe
from src.pptx.primitives import (
    PRIMITIVES, Rect,
    add_rect, add_text, apply_master,
)


class PlanValidationError(ValueError):
    """Raised when a slide_plan fails structural validation before rendering."""


def _draw_placeholder(slide, rect: Rect, label: str) -> None:
    """Visible fallback for a failing zone — light-grey rect with a label."""
    add_rect(slide, rect=rect, fill="#F5F5F5",
             border_color="#CCCCCC", border_width=0.75, rounded=False)
    add_text(slide, rect=rect, text=label,
             font_size=12, color="#888888", align="center")


def render_slide(prs, deck_meta: Dict[str, Any], plan: Dict[str, Any]):
    """Render one slide from a recipe plan. Returns the new slide.

    Per-primitive failures are isolated so a single bad primitive can't kill
    the whole slide.
    """
    if "recipe" not in plan:
        raise PlanValidationError("plan missing key: recipe")
    if "head_message" not in plan:
        raise PlanValidationError("plan missing key: head_message")

    entry = get_recipe(plan["recipe"])  # KeyError early if unknown

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    section_id = plan.get("section_id")

    if entry.apply_master:
        section_titles = deck_meta.get("section_titles") or {}
        section_title = section_titles.get(section_id) if section_id else None
        body = apply_master(
            slide, deck_meta,
            head_message=plan["head_message"],
            section_title=section_title,
            sub_message=plan.get("sub_message"),
            page_no=plan.get("slide_no"),
            section_id=section_id,
        )
    else:
        # Full canvas — no master header. The recipe's primitive paints the bg.
        body = Rect(0.6, 0.6, 12.13, 6.3)

    try:
        specs = compile_recipe(plan["recipe"], plan.get("data") or {}, body)
    except Exception as exc:  # noqa: BLE001
        print(f"[renderer] recipe {plan['recipe']!r} compile failed: {exc}",
              file=sys.stderr)
        _draw_placeholder(slide, body, f"[recipe {plan['recipe']} compile failed]")
        return slide

    for i, spec in enumerate(specs):
        draw = PRIMITIVES.get(spec.name)
        if draw is None:
            print(f"[renderer] primitive {i}: unknown primitive {spec.name!r}",
                  file=sys.stderr)
            _draw_placeholder(slide, spec.rect, f"[unknown {spec.name}]")
            continue
        try:
            draw(slide, spec.rect, spec.data, deck_meta)
        except Exception as exc:  # noqa: BLE001
            print(f"[renderer] primitive {i} {spec.name!r} failed: {exc}",
                  file=sys.stderr)
            _draw_placeholder(slide, spec.rect, f"[{spec.name} failed]")
    return slide


def render_deck(prs, deck_meta: Dict[str, Any], slides: List[Dict[str, Any]]) -> int:
    """Render every slide in a plan list. Returns count of successfully rendered."""
    ok = 0
    for plan in slides:
        try:
            render_slide(prs, deck_meta, plan)
            ok += 1
        except PlanValidationError as exc:
            print(f"[renderer] slide {plan.get('slide_no', '?')} validation failed: {exc}",
                  file=sys.stderr)
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            _draw_placeholder(
                slide, Rect(0.6, 0.6, 12.13, 6.3),
                f"slide {plan.get('slide_no', '?')} unrenderable: {exc}",
            )
    return ok
