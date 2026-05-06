"""Pydantic models for the v2 pipeline.

See docs/superpowers/specs/2026-05-06-v2-freeform-codegen-design.md §5.4.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, conint


CONTENT_STRUCTURES = Literal[
    "comparison", "process", "hierarchy", "matrix", "metric",
    "narrative", "enumeration", "timeline", "system", "other",
]


class SlideOutline(BaseModel):
    index: int
    kind: Literal["title", "body", "closing"]
    headline: str = ""
    takeaway: str = ""
    subtitle: str = ""
    implication: str = ""
    content_structure: Optional[CONTENT_STRUCTURES] = None


class VisualStrategy(BaseModel):
    approach: str            # snake_case, unique within deck
    rationale: str
    layout_hint: str
    key_elements: list[str]


class SlidePlanV2(SlideOutline):
    visual_strategy: Optional[VisualStrategy] = None


class CritiqueIssue(BaseModel):
    location: str
    root_cause: str
    code_hint: str


class SlideCritique(BaseModel):
    score_strategy: conint(ge=0, le=10)  # type: ignore[valid-type]
    score_visual: conint(ge=0, le=10)    # type: ignore[valid-type]
    score_content: conint(ge=0, le=10)   # type: ignore[valid-type]
    issues: list[CritiqueIssue] = Field(default_factory=list)
    verdict: Literal["KEEP", "REVISE", "REGENERATE"]

    @property
    def min_score(self) -> int:
        return min(self.score_strategy, self.score_visual, self.score_content)


class GalleryEntry(BaseModel):
    deck_id: str
    slide_no: int
    category: str            # = content_structure
    approach: str
    rationale: str
    layout_hint: str
    key_elements: list[str]
    scores: dict[str, int]
    quality_score: float
    code_snippet: str
    created_at: str          # ISO 8601
