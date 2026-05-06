"""Pydantic schemas for LLM outputs (recipe era).

These models define the contract between LLM responses and downstream code.
They enforce required keys, coerce types, and absorb missing optional fields
so a slightly malformed LLM response (very common with smaller models like
gemma4:e4b) is rejected with a specific error rather than crashing later.

Layered with Ollama's `format=json` constraint, the combo gives:
  Layer 1: Ollama enforces JSON syntax at decode time
  Layer 2: Pydantic enforces semantics + provides defaults
"""
from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Outline (story_outline stage — one item per slide)
# ---------------------------------------------------------------------------

class SlideOutline(BaseModel):
    """One slide's outline as emitted by the planner LLM (story_outline stage).

    Strict on slide_no/head_message (these matter downstream); tolerant on
    everything else. Empty section_id strings collapse to None so the cover
    slide and unsectioned slides resolve identically.
    """
    slide_no: int
    head_message: str
    purpose: str = ""
    section_id: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("slide_no", mode="before")
    @classmethod
    def _coerce_slide_no(cls, v):
        if isinstance(v, bool):
            raise ValueError("slide_no must be an integer, got bool")
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.strip().isdigit():
            return int(v.strip())
        raise ValueError(f"slide_no must be an integer, got {v!r}")

    @field_validator("head_message", mode="before")
    @classmethod
    def _require_head_message(cls, v):
        if v is None:
            raise ValueError("head_message is required and must be non-empty")
        s = str(v).strip()
        if not s:
            raise ValueError("head_message must be non-empty")
        return s

    @field_validator("section_id", mode="before")
    @classmethod
    def _normalize_section_id(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s or None


# ---------------------------------------------------------------------------
# Slide plan (slide_detail stage)
# ---------------------------------------------------------------------------

class SlideRecipe(BaseModel):
    """One slide's full plan as emitted by the planner LLM (recipe era).

    The LLM picks a recipe by name and fills its data. Geometry, primitive
    placement, and zone counts are all decided by the recipe compiler, NOT
    the LLM.
    """
    slide_no: int
    head_message: str
    sub_message: Optional[str] = None
    section_id: Optional[str] = None
    intent: str = ""           # one short phrase describing the slide's job
    rationale: str = ""        # 1-line why-this-recipe; used by critic
    recipe: str
    data: dict = Field(default_factory=dict)

    model_config = {"extra": "ignore"}

    @field_validator("slide_no", mode="before")
    @classmethod
    def _coerce_slide_no(cls, v):
        if isinstance(v, bool):
            raise ValueError("slide_no must be an integer, got bool")
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.strip().isdigit():
            return int(v.strip())
        raise ValueError(f"slide_no must be an integer, got {v!r}")

    @field_validator("head_message", mode="before")
    @classmethod
    def _require_head_message(cls, v):
        if v is None:
            raise ValueError("head_message is required and must be non-empty")
        s = str(v).strip()
        if not s:
            raise ValueError("head_message must be non-empty")
        return s

    @field_validator("sub_message", mode="before")
    @classmethod
    def _normalize_sub(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @field_validator("section_id", mode="before")
    @classmethod
    def _normalize_section_id(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @field_validator("recipe", mode="before")
    @classmethod
    def _require_recipe(cls, v):
        if v is None:
            raise ValueError("recipe is required")
        s = str(v).strip()
        if not s:
            raise ValueError("recipe must be non-empty")
        return s


# ---------------------------------------------------------------------------
# Plan v2 — content layer (LLM 출력) + layout layer (코드 selector 출력)
# ---------------------------------------------------------------------------

# 12개 intent label. recipe 카탈로그와 1:1 매핑 (selector가 INTENT_TO_RECIPE
# dict 통해 변환). 카탈로그 확장 시 1:N으로 확장 가능.
IntentLabel = Literal[
    "deck_opening",            # cover
    "section_transition",      # section_divider_strip
    "single_metric_emphasis",  # headline_metric
    "multi_metric_dashboard",  # kpi_dashboard_2x2
    "numeric_comparison",      # bar_compare_h
    "two_dim_compare",         # matrix_2x2_compare
    "before_after",            # transformation_lr
    "sequence_or_timeline",    # timeline_horizontal
    "quotation",               # pull_quote
    "parallel_compare",        # split_bullets
    "general_facts",           # single_bullets (default)
    "closing_thesis",          # thesis
]


class SoWhatQA(BaseModel):
    """Per-slide so-what interrogation Q&A.

    Each slide has at least 2 of {WHY, HOW_MUCH, WHAT_NEXT}. evidence empty
    means "raw_facts에 근거가 없음 → 슬라이드 약체 신호".
    """
    type: Literal["WHY", "HOW_MUCH", "WHAT_NEXT"]
    question: str
    answer: str
    evidence: List[str] = Field(default_factory=list)
    feeds: List[str] = Field(default_factory=list)

    model_config = {"extra": "ignore"}

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, v):
        if v in ("WHY", "HOW_MUCH", "WHAT_NEXT"):
            return v
        # tolerate variants
        s = str(v).upper().replace(" ", "_").replace("-", "_")
        if s in ("WHY", "HOW_MUCH", "WHAT_NEXT"):
            return s
        if s in ("HOWMUCH", "MUCH", "SCALE"):
            return "HOW_MUCH"
        if s in ("WHATNEXT", "NEXT", "ACTION", "IMPLICATION"):
            return "WHAT_NEXT"
        raise ValueError(f"so_what type must be WHY|HOW_MUCH|WHAT_NEXT, got {v!r}")


class MetricFact(BaseModel):
    """One numeric metric (universal knowledge field)."""
    id: str = ""
    value: str                          # 항상 string ("1.5억" 표현 자유)
    unit: Optional[str] = None
    label: str                          # ≤25자
    sub_label: Optional[str] = None     # 시점/출처/조건
    trend: Optional[str] = None         # 부호·방향 포함
    comparison: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_value_to_str(cls, v):
        if v is None:
            raise ValueError("metric.value is required")
        return str(v).strip()

    @field_validator("label", mode="before")
    @classmethod
    def _label_required(cls, v):
        if v is None or not str(v).strip():
            raise ValueError("metric.label is required")
        return str(v).strip()


class NarrativePoint(BaseModel):
    """One textual fact (universal knowledge field)."""
    id: str = ""
    text: str
    sub: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("text", mode="before")
    @classmethod
    def _text_required(cls, v):
        if v is None or not str(v).strip():
            raise ValueError("narrative.text is required")
        return str(v).strip()


class QuoteFact(BaseModel):
    """One quotation (universal knowledge field)."""
    id: str = ""
    text: str
    attribution: Optional[str] = None
    context: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("text", mode="before")
    @classmethod
    def _text_required(cls, v):
        if v is None or not str(v).strip():
            raise ValueError("quote.text is required")
        return str(v).strip()


# Intent-specific knowledge structures (only filled when the intent demands it)

class MatrixCellFact(BaseModel):
    bullets: List[str] = Field(default_factory=list)

    model_config = {"extra": "ignore"}


class MatrixData(BaseModel):
    col_headers: List[str]
    row_labels: List[str]
    cells: List[List[MatrixCellFact]]

    model_config = {"extra": "ignore"}

    @field_validator("col_headers")
    @classmethod
    def _two_cols(cls, v):
        if len(v) != 2:
            raise ValueError(f"matrix.col_headers must have 2 entries, got {len(v)}")
        return v

    @field_validator("row_labels")
    @classmethod
    def _two_rows(cls, v):
        if len(v) != 2:
            raise ValueError(f"matrix.row_labels must have 2 entries, got {len(v)}")
        return v


class TimelineNodeFact(BaseModel):
    when: str
    title: str
    note: Optional[str] = None

    model_config = {"extra": "ignore"}


class TimelineData(BaseModel):
    nodes: List[TimelineNodeFact]

    model_config = {"extra": "ignore"}

    @field_validator("nodes")
    @classmethod
    def _three_to_five(cls, v):
        if not (3 <= len(v) <= 5):
            raise ValueError(f"timeline.nodes must have 3-5 entries, got {len(v)}")
        return v


class TransformBranchFact(BaseModel):
    title: str
    items: List[str]

    model_config = {"extra": "ignore"}


class TransformData(BaseModel):
    as_is: TransformBranchFact
    to_be: TransformBranchFact
    arrow_label: Optional[str] = None

    model_config = {"extra": "ignore"}


class KnowledgeBlock(BaseModel):
    """All facts the slide draws from. Universal fields plus intent-specific
    structured fields (only filled when the intent demands them)."""
    metrics: List[MetricFact] = Field(default_factory=list)
    narratives: List[NarrativePoint] = Field(default_factory=list)
    quotes: List[QuoteFact] = Field(default_factory=list)
    matrix: Optional[MatrixData] = None
    timeline: Optional[TimelineData] = None
    transformation: Optional[TransformData] = None

    model_config = {"extra": "ignore"}


_QUESTION_TAILS = ("?", "까", "는가", "할까", "일까", "인가")


class VisualStrategy(BaseModel):
    """Per-slide free-form visual strategy (legacy Phase 1b).

    Attached to SlideContent when the codegen path is enabled. The recipe
    path ignores this field; the LLM-codegen path consumes `layout_hint`
    as natural-language layout instruction.

    `approach` is a snake_case identifier the planner LLM coins per slide;
    distinct slides should pick distinct names (gallery enforces variety).
    """
    approach: str
    rationale: str = ""
    layout_hint: str
    key_elements: List[str] = Field(default_factory=list)

    model_config = {"extra": "ignore"}

    @field_validator("approach", mode="before")
    @classmethod
    def _norm_approach(cls, v):
        if v is None or not str(v).strip():
            raise ValueError("visual_strategy.approach must be non-empty")
        s = str(v).strip()
        # Only allow [a-z0-9_]; LLM occasionally emits camelCase or spaces.
        import re as _re
        s = _re.sub(r"\s+", "_", s).lower()
        s = _re.sub(r"[^a-z0-9_]", "", s)
        if not s:
            raise ValueError(f"visual_strategy.approach reduced to empty: {v!r}")
        return s

    @field_validator("layout_hint", mode="before")
    @classmethod
    def _require_hint(cls, v):
        if v is None or not str(v).strip():
            raise ValueError("visual_strategy.layout_hint must be non-empty")
        return str(v).strip()


class SlideContent(BaseModel):
    """Stage 2 LLM output — content layer only. No recipe/data here.

    Strict on head_message (standalone meaningfulness enforced by checks
    module + self-review; pydantic only does basic non-empty + non-question
    enforcement here)."""
    slide_no: int
    section_id: Optional[str] = None
    intent_label: IntentLabel
    so_what: List[SoWhatQA] = Field(default_factory=list)
    head_message: str
    head_derivation: str = ""
    key_takeaway: str
    key_takeaway_derivation: str = ""
    knowledge: KnowledgeBlock = Field(default_factory=KnowledgeBlock)
    visual_strategy: Optional[VisualStrategy] = None

    model_config = {"extra": "ignore"}

    @field_validator("slide_no", mode="before")
    @classmethod
    def _coerce_slide_no(cls, v):
        if isinstance(v, bool):
            raise ValueError("slide_no must be int, got bool")
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.strip().isdigit():
            return int(v.strip())
        raise ValueError(f"slide_no must be int, got {v!r}")

    @field_validator("section_id", mode="before")
    @classmethod
    def _norm_sid(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @field_validator("head_message", mode="before")
    @classmethod
    def _validate_head(cls, v):
        if v is None:
            raise ValueError("head_message is required")
        s = str(v).strip()
        if not s:
            raise ValueError("head_message must be non-empty")
        # Reject question forms (deterministic check does richer detection;
        # this is the schema's hard floor)
        for tail in _QUESTION_TAILS:
            if s.endswith(tail):
                raise ValueError(
                    f"head_message must not be a question (ends with {tail!r}). "
                    f"Use a noun phrase or short statement instead."
                )
        return s

    @field_validator("key_takeaway", mode="before")
    @classmethod
    def _validate_takeaway(cls, v):
        # Allow empty here — body slides have non-empty enforced by the
        # model_validator below; framing slides may be empty.
        if v is None:
            return ""
        return str(v).strip()

    @model_validator(mode="after")
    def _enforce_body_slide_requirements(self):
        """Body slides require so_what (≥2 QAs) AND non-empty takeaway.

        Framing slides (cover/thesis/section divider) are about deck structure,
        not factual content — they can have empty so_what and empty takeaway.
        """
        framing_intents = {"deck_opening", "closing_thesis", "section_transition"}
        if self.intent_label in framing_intents:
            return self
        if len(self.so_what) < 2:
            raise ValueError(
                f"so_what must contain at least 2 entries from "
                f"WHY/HOW_MUCH/WHAT_NEXT for body slides, got {len(self.so_what)}"
            )
        if not self.key_takeaway.strip():
            raise ValueError(
                "key_takeaway must be non-empty for body slides"
            )
        return self


class SlidePlan(BaseModel):
    """Final per-slide plan after selector runs. Combines content + layout."""
    content: SlideContent
    recipe: str
    data: dict = Field(default_factory=dict)

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Deck-level critique (deck_storyline + deck_visual)
# Stripped down to what the recipe-era critic actually needs.
# ---------------------------------------------------------------------------

class CritiqueIssue(BaseModel):
    slide_no: Optional[int] = None
    axis: str = ""
    msg: str = ""

    model_config = {"extra": "ignore"}


class DeckCritique(BaseModel):
    """Deck-level critique (storyline or visual consistency)."""
    scores: dict[str, int] = Field(default_factory=dict)
    issues: List[CritiqueIssue] = Field(default_factory=list)
    verdict: Literal["PASS", "REVISE"] = "REVISE"

    model_config = {"extra": "ignore"}

    @field_validator("verdict", mode="before")
    @classmethod
    def _coerce_verdict(cls, v):
        return v if v in ("PASS", "REVISE") else "REVISE"

    @field_validator("scores", mode="before")
    @classmethod
    def _coerce_scores(cls, v):
        if not isinstance(v, dict):
            return {}
        out: dict[str, int] = {}
        for k, val in v.items():
            try:
                out[str(k)] = int(val)
            except (ValueError, TypeError):
                continue
        return out


# ---------------------------------------------------------------------------
# Per-slide visual critique (Phase B of visual revision loop)
# ---------------------------------------------------------------------------

VISUAL_AXIS_CODES = (
    "overflow", "collision", "alignment", "whitespace",
    "hierarchy", "readability", "data_grounding",
)


class AxisVerdict(BaseModel):
    code: Literal[
        "overflow", "collision", "alignment", "whitespace",
        "hierarchy", "readability", "data_grounding",
    ]
    verdict: Literal["ok", "warn", "fail"] = "ok"
    severity: Literal["low", "medium", "high"] = "low"
    msg: str = ""
    suggestion: str = ""

    model_config = {"extra": "ignore"}

    @field_validator("verdict", mode="before")
    @classmethod
    def _coerce_verdict(cls, v):
        return v if v in ("ok", "warn", "fail") else "ok"

    @field_validator("severity", mode="before")
    @classmethod
    def _coerce_severity(cls, v):
        return v if v in ("low", "medium", "high") else "low"


class SlideCritique(BaseModel):
    """Per-slide visual critique (vision LLM output)."""
    slide_no: int
    axes: List[AxisVerdict] = Field(default_factory=list)
    summary: str = ""

    model_config = {"extra": "ignore"}

    @model_validator(mode="after")
    def _ensure_seven_axes(self):
        # Don't reject — fill missing axes with ok/low so callers can
        # always assume 7 axes are present in a stable order.
        seen = {a.code: a for a in self.axes}
        ordered: list[AxisVerdict] = []
        for code in VISUAL_AXIS_CODES:
            if code in seen:
                ordered.append(seen[code])
            else:
                ordered.append(AxisVerdict(
                    code=code, verdict="ok", severity="low",
                    msg="(axis missing from LLM output)", suggestion="",
                ))
        self.axes = ordered
        return self

    def fail_or_warn_axes(self, *, min_severity: str = "medium") -> list[AxisVerdict]:
        """Return axes whose verdict ≠ ok and severity ≥ min_severity."""
        rank = {"low": 0, "medium": 1, "high": 2}
        floor = rank.get(min_severity, 1)
        return [
            a for a in self.axes
            if a.verdict != "ok" and rank.get(a.severity, 0) >= floor
        ]


# ---------------------------------------------------------------------------
# Plan patcher (Phase C of visual revision loop)
# ---------------------------------------------------------------------------

# Intent labels valid as `change_intent` targets (framing intents excluded —
# those are position-locked by the planner).
SWAPPABLE_INTENTS = (
    "single_metric_emphasis", "multi_metric_dashboard", "numeric_comparison",
    "two_dim_compare", "before_after", "sequence_or_timeline",
    "quotation", "parallel_compare", "general_facts",
)


class _PatchOpBase(BaseModel):
    slide_no: int
    model_config = {"extra": "ignore"}


class ShortenHeadOp(_PatchOpBase):
    op: Literal["shorten_head"]
    new_text: str = Field(min_length=1, max_length=120)


class TruncateBulletsOp(_PatchOpBase):
    op: Literal["truncate_bullets"]
    keep: int = Field(ge=1, le=10)


class ChangeIntentOp(_PatchOpBase):
    op: Literal["change_intent"]
    new_intent: str

    @field_validator("new_intent")
    @classmethod
    def _validate_intent(cls, v):
        if v not in SWAPPABLE_INTENTS:
            raise ValueError(
                f"new_intent must be one of {SWAPPABLE_INTENTS}, got {v!r}"
            )
        return v


class DropMetricOp(_PatchOpBase):
    op: Literal["drop_metric"]
    index: int = Field(ge=0)


class SwapEmphasisOp(_PatchOpBase):
    op: Literal["swap_emphasis"]
    new_hero_index: int = Field(ge=0)


class RewriteTakeawayOp(_PatchOpBase):
    op: Literal["rewrite_takeaway"]
    new_text: str = Field(min_length=1, max_length=200)


# Discriminated union — pydantic dispatches on the `op` field.
from typing import Annotated, Union  # noqa: E402

PatchOp = Annotated[
    Union[
        ShortenHeadOp, TruncateBulletsOp, ChangeIntentOp,
        DropMetricOp, SwapEmphasisOp, RewriteTakeawayOp,
    ],
    Field(discriminator="op"),
]


class PatchPlan(BaseModel):
    """Top-level shape of patcher LLM output."""
    ops: List[PatchOp] = Field(default_factory=list)
    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def parse_slide_outline(raw: dict) -> SlideOutline:
    """Validate a single outline item. Raises ValidationError on hard failures."""
    return SlideOutline.model_validate(raw)


def parse_slide_recipe(raw: dict) -> SlideRecipe:
    """Validate a slide recipe plan. Raises ValidationError on hard failures."""
    return SlideRecipe.model_validate(raw)


def parse_slide_content(raw: dict) -> SlideContent:
    """Validate Stage 2 content output. Raises ValidationError on hard failures."""
    return SlideContent.model_validate(raw)


def parse_deck_critique(raw: dict | Any) -> DeckCritique:
    if not isinstance(raw, dict):
        return DeckCritique()
    return DeckCritique.model_validate(raw)
