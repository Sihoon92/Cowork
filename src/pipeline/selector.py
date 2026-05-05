"""Recipe selector — content layer (intent + knowledge) → layout layer (recipe + data).

Pure code, no LLM. Each transformer takes a SlideContent and produces the
recipe-specific data dict, then validates against the recipe's pydantic data
model. If transformation or validation fails, fall back to single_bullets.

This module is the bridge between the LLM's content output and the renderer's
geometry expectations. Adding a new recipe usually means: register it,
optionally add an intent_label, optionally add a transformer here.
"""
from __future__ import annotations

from typing import Callable

from src.pipeline.recipes import RECIPES
from src.pipeline.schemas import (
    IntentLabel, KnowledgeBlock, SlideContent,
)


# ---------------------------------------------------------------------------
# Intent → recipe mapping (1:1 today; 1:N possible later)
# ---------------------------------------------------------------------------

INTENT_TO_RECIPE: dict[str, str] = {
    "deck_opening":            "cover",
    "section_transition":      "section_divider_strip",
    "single_metric_emphasis":  "headline_metric",
    "multi_metric_dashboard":  "kpi_dashboard_2x2",
    "numeric_comparison":      "bar_compare_h",
    "two_dim_compare":         "matrix_2x2_compare",
    "before_after":            "transformation_lr",
    "sequence_or_timeline":    "timeline_horizontal",
    "quotation":               "pull_quote",
    "parallel_compare":        "split_bullets",
    "general_facts":           "single_bullets",
    "closing_thesis":          "thesis",
}


# ---------------------------------------------------------------------------
# Per-recipe transformers: SlideContent → dict (matching recipe.data_model)
# ---------------------------------------------------------------------------

def _take_items(items: list, limit: int) -> list:
    return list(items)[:limit] if items else []


def _to_cover_data(content: SlideContent) -> dict:
    return {
        "title": content.head_message,
        "sub": content.key_takeaway or None,
        "label": "Briefing",
        "meta": None,
    }


def _to_thesis_data(content: SlideContent) -> dict:
    return {
        "text": content.key_takeaway or content.head_message,
        "attribution": None,
    }


def _to_section_divider_data(content: SlideContent) -> dict:
    # number/title/sub from head_message + slide_no fallback
    return {
        "number": f"{content.slide_no:02d}",
        "title": content.head_message,
        "sub": content.key_takeaway or None,
    }


def _to_headline_metric_data(content: SlideContent) -> dict:
    k = content.knowledge
    if not k.metrics:
        raise ValueError("headline_metric requires at least 1 metric in knowledge")
    metric = k.metrics[0]
    context_items = [n.text for n in _take_items(k.narratives, 5)]
    return {
        "metric": metric.model_dump(),
        "context_title": "배경" if context_items else None,
        "context_items": context_items,
    }


def _to_kpi_dashboard_data(content: SlideContent) -> dict:
    metrics = list(content.knowledge.metrics)
    if len(metrics) < 4:
        raise ValueError(
            f"kpi_dashboard_2x2 requires exactly 4 metrics, got {len(metrics)}"
        )
    return {
        "metrics": [m.model_dump() for m in metrics[:4]],
    }


def _to_bar_compare_data(content: SlideContent) -> dict:
    metrics = list(content.knowledge.metrics)
    if not (2 <= len(metrics) <= 6):
        raise ValueError(
            f"bar_compare_h requires 2-6 metrics, got {len(metrics)}"
        )
    items = []
    for m in metrics:
        # value를 숫자로 강제 변환 시도. 실패하면 폴백.
        try:
            value = float(str(m.value).replace(",", "").strip().rstrip("%일명배"))
        except ValueError:
            raise ValueError(f"bar_compare_h: metric.value {m.value!r} cannot become numeric")
        items.append({
            "name": m.label,
            "value": value,
            "unit": m.unit,
        })
    return {
        "title": content.head_message,
        "items": items,
    }


def _to_matrix_data(content: SlideContent) -> dict:
    m = content.knowledge.matrix
    if m is None:
        raise ValueError("two_dim_compare requires knowledge.matrix to be filled")
    cells_payload = [
        [
            {"primitive": "bullet_block", "data": {"items": cell.bullets}}
            for cell in row
        ]
        for row in m.cells
    ]
    return {
        "col_headers": m.col_headers,
        "row_labels": m.row_labels,
        "cells": cells_payload,
    }


def _to_transformation_data(content: SlideContent) -> dict:
    t = content.knowledge.transformation
    if t is None:
        raise ValueError("before_after requires knowledge.transformation to be filled")
    return {
        "as_is": {"title": t.as_is.title, "items": t.as_is.items},
        "to_be": {"title": t.to_be.title, "items": t.to_be.items},
        "arrow_label": t.arrow_label,
    }


def _to_timeline_data(content: SlideContent) -> dict:
    t = content.knowledge.timeline
    if t is None:
        raise ValueError("sequence_or_timeline requires knowledge.timeline to be filled")
    return {"nodes": [n.model_dump() for n in t.nodes]}


def _to_pull_quote_data(content: SlideContent) -> dict:
    quotes = content.knowledge.quotes
    if not quotes:
        raise ValueError("quotation requires at least 1 quote in knowledge")
    q = quotes[0]
    return q.model_dump()


def _to_split_bullets_data(content: SlideContent) -> dict:
    narratives = content.knowledge.narratives
    if len(narratives) < 4:
        raise ValueError(
            f"parallel_compare prefers ≥4 narratives, got {len(narratives)}"
        )
    half = len(narratives) // 2
    left_items = [n.text for n in narratives[:half]]
    right_items = [n.text for n in narratives[half: half * 2]]
    return {
        "left":  {"title": "A", "items": left_items},
        "right": {"title": "B", "items": right_items},
        "ratio": "6_6",
    }


def _to_single_bullets_data(content: SlideContent) -> dict:
    """Universal default. Tries narratives → metric labels → head_message."""
    k = content.knowledge
    items: list[str] = []
    if k.narratives:
        items = [n.text for n in _take_items(k.narratives, 7)]
    elif k.metrics:
        items = [
            f"{m.value}{m.unit or ''} — {m.label}"
            for m in _take_items(k.metrics, 7)
        ]
    elif k.quotes:
        items = [
            (f"{q.text} — {q.attribution}" if q.attribution else q.text)
            for q in _take_items(k.quotes, 7)
        ]
    if not items:
        items = [content.head_message]
    return {"title": None, "items": items}


TRANSFORMERS: dict[str, Callable[[SlideContent], dict]] = {
    "cover":                  _to_cover_data,
    "thesis":                 _to_thesis_data,
    "section_divider_strip":  _to_section_divider_data,
    "headline_metric":        _to_headline_metric_data,
    "kpi_dashboard_2x2":      _to_kpi_dashboard_data,
    "bar_compare_h":          _to_bar_compare_data,
    "matrix_2x2_compare":     _to_matrix_data,
    "transformation_lr":      _to_transformation_data,
    "timeline_horizontal":    _to_timeline_data,
    "pull_quote":             _to_pull_quote_data,
    "split_bullets":          _to_split_bullets_data,
    "single_bullets":         _to_single_bullets_data,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class SelectionResult:
    __slots__ = ("recipe", "data", "fell_back", "reason")

    def __init__(self, recipe: str, data: dict, *, fell_back: bool = False,
                 reason: str = ""):
        self.recipe = recipe
        self.data = data
        self.fell_back = fell_back
        self.reason = reason


def select_recipe(content: SlideContent) -> SelectionResult:
    """Map content (intent + knowledge) → (recipe, data).

    1. Look up intent → recipe.
    2. Run transformer to build recipe.data.
    3. Validate against the recipe's data_model.
    4. If anything fails, fall back to single_bullets.
    """
    intent = content.intent_label
    primary_recipe = INTENT_TO_RECIPE.get(intent)
    if primary_recipe is None:
        return _fallback(content, reason=f"unknown intent_label: {intent!r}")

    transformer = TRANSFORMERS.get(primary_recipe)
    if transformer is None:
        return _fallback(content, reason=f"no transformer for recipe {primary_recipe!r}")

    try:
        data = transformer(content)
        # Validate against the recipe's pydantic data model
        entry = RECIPES.get(primary_recipe)
        if entry is None:
            return _fallback(content,
                             reason=f"recipe {primary_recipe!r} not registered")
        entry.data_model.model_validate(data)
        return SelectionResult(primary_recipe, data)
    except Exception as exc:  # noqa: BLE001
        return _fallback(content,
                         reason=f"{primary_recipe} transform/validate failed: {exc}")


def _fallback(content: SlideContent, *, reason: str) -> SelectionResult:
    """Safe fallback: single_bullets always succeeds."""
    data = _to_single_bullets_data(content)
    return SelectionResult("single_bullets", data, fell_back=True, reason=reason)
