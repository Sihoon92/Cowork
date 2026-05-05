"""Plan patcher — translates per-slide critiques into whitelisted ops.

Two-step design:
  1. `generate_patches(critiques, plan, model)` — LLM call. Output is a
     PatchPlan (list of typed ops). LLM cannot invent op kinds.
  2. `apply_patches(plan, ops)` — pure code. Mutates plan deterministically.
     For each op: mutate, re-run selector, re-run deterministic checks.
     If any check fails for that op, roll back ONLY that op; keep others.

This split is intentional: critic diagnoses, patcher prescribes, apply
executes. LLM hallucinations are caged inside the op vocabulary; the
deterministic apply step is the safety floor.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from src.llm.client import DEFAULT_MODEL, chat
from src.pipeline.checks import check_slide_content
from src.pipeline.planner import parse_json_block
from src.pipeline.schemas import (
    PatchPlan, SlideContent, SlideCritique,
)
from src.pipeline.selector import select_recipe
from src.util import log

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


# ---------------------------------------------------------------------------
# Stage 1: LLM call to produce ops
# ---------------------------------------------------------------------------

_FRAMING_INTENTS = {"deck_opening", "closing_thesis", "section_transition"}


def _slides_needing_patch(critiques: list[SlideCritique]) -> set[int]:
    needs: set[int] = set()
    for c in critiques:
        if c.fail_or_warn_axes(min_severity="medium"):
            needs.add(c.slide_no)
    return needs


def _format_critiques_block(
    critiques: list[SlideCritique], target_slides: set[int],
) -> str:
    """Render only the non-ok axes for slides in target_slides."""
    lines: list[str] = []
    for c in critiques:
        if c.slide_no not in target_slides:
            continue
        lines.append(f"--- slide {c.slide_no} ---")
        for ax in c.axes:
            if ax.verdict == "ok":
                continue
            sug = f" → suggestion: {ax.suggestion}" if ax.suggestion else ""
            lines.append(
                f"  [{ax.severity}] {ax.code}: {ax.msg}{sug}"
            )
        if c.summary:
            lines.append(f"  summary: {c.summary}")
    return "\n".join(lines) or "(no slides flagged)"


def _format_plan_block(plan: dict, target_slides: set[int]) -> str:
    """Compact slide slices the patcher needs to make grounded decisions."""
    lines: list[str] = []
    for s in plan.get("slides", []):
        if s["slide_no"] not in target_slides:
            continue
        full = s.get("_full") or {}
        content = full.get("content") or {}
        knowledge = content.get("knowledge") or {}
        metrics = knowledge.get("metrics") or []
        narratives = knowledge.get("narratives") or []
        is_framing = content.get("intent_label") in _FRAMING_INTENTS

        lines.append(f"--- slide {s['slide_no']} ---")
        lines.append(f"  intent_label : {s.get('intent_label', '?')}"
                     + ("  [FRAMING — limited ops]" if is_framing else ""))
        lines.append(f"  recipe       : {s.get('recipe', '?')}")
        lines.append(f"  head_message : {s.get('head_message', '')!r}")
        lines.append(f"  key_takeaway : {(s.get('sub_message') or '')!r}")
        if metrics:
            lines.append(f"  metrics ({len(metrics)}):")
            for i, m in enumerate(metrics):
                lines.append(
                    f"    [{i}] value={m.get('value')!r}  "
                    f"label={m.get('label')!r}  "
                    f"trend={m.get('trend')!r}"
                )
        if narratives:
            lines.append(f"  narratives ({len(narratives)}):")
            for i, n in enumerate(narratives):
                lines.append(f"    [{i}] {n.get('text')!r}")
    return "\n".join(lines) or "(no plan slices)"


def generate_patches(
    critiques: list[SlideCritique],
    plan: dict,
    *,
    model: str = DEFAULT_MODEL,
) -> PatchPlan:
    """Ask the LLM for a PatchPlan grounded in critiques + plan slices.

    Returns an empty PatchPlan if no slides need patching, the LLM
    produces unparseable output, or all proposed ops fail validation.
    """
    target_slides = _slides_needing_patch(critiques)
    if not target_slides:
        log.info("patcher: no slides flagged at severity ≥ medium; skipping")
        return PatchPlan(ops=[])

    template = (PROMPTS_DIR / "plan_patcher.md").read_text(encoding="utf-8")
    prompt = template.format(
        critiques_block=_format_critiques_block(critiques, target_slides),
        plan_block=_format_plan_block(plan, target_slides),
    )

    log.step(f"LLM call: plan patcher ({len(target_slides)} slide(s) flagged)")
    try:
        response = chat(prompt, model=model, format="json")
    except Exception as exc:  # noqa: BLE001
        log.warn(f"patcher LLM call failed: {exc}; returning empty PatchPlan")
        return PatchPlan(ops=[])

    try:
        parsed = parse_json_block(response)
    except ValueError as exc:
        log.warn(f"patcher response unparseable: {exc}; returning empty PatchPlan")
        return PatchPlan(ops=[])

    # The LLM occasionally returns a bare ops array. Wrap it.
    if isinstance(parsed, list):
        parsed = {"ops": parsed}

    try:
        plan_obj = PatchPlan.model_validate(parsed)
    except Exception as exc:  # noqa: BLE001
        log.warn(f"patcher schema invalid: {exc}; returning empty PatchPlan")
        return PatchPlan(ops=[])

    log.ok(f"patcher proposed {len(plan_obj.ops)} op(s)")
    return plan_obj


# ---------------------------------------------------------------------------
# Stage 2: Deterministic op application
# ---------------------------------------------------------------------------

def _slide_index(plan: dict, slide_no: int) -> int:
    for i, s in enumerate(plan.get("slides", [])):
        if int(s.get("slide_no", -1)) == slide_no:
            return i
    return -1


def _refresh_top_level(slide: dict) -> None:
    """Sync flat fields (head_message, recipe, ...) from `_full.content`.

    The renderer reads the flat fields, but ops mutate `_full.content`
    (the SlideContent dict) since that's the source of truth.
    """
    full = slide.get("_full") or {}
    content = full.get("content") or {}
    slide["head_message"] = content.get("head_message", "")
    slide["sub_message"] = content.get("key_takeaway")
    slide["intent_label"] = content.get("intent_label")
    slide["recipe"] = full.get("recipe", slide.get("recipe"))
    slide["data"] = full.get("data", slide.get("data"))


def _re_select(slide: dict) -> tuple[bool, str]:
    """Re-run the selector after content fields changed. Returns (ok, reason)."""
    full = slide.setdefault("_full", {})
    content_dict = full.get("content") or {}
    try:
        content_obj = SlideContent.model_validate(content_dict)
    except Exception as exc:  # noqa: BLE001
        return False, f"SlideContent invalid: {exc}"
    sel = select_recipe(content_obj)
    full["recipe"] = sel.recipe
    full["data"] = sel.data
    return True, sel.reason if sel.fell_back else ""


def _re_check(slide: dict, deck_meta: dict) -> list[tuple[str, str]]:
    """Run deterministic checks on the patched content."""
    full = slide.get("_full") or {}
    content_dict = full.get("content") or {}
    try:
        content_obj = SlideContent.model_validate(content_dict)
    except Exception as exc:  # noqa: BLE001
        return [("schema_invalid", str(exc))]
    section_id = content_obj.section_id
    section_title = (deck_meta.get("section_titles") or {}).get(section_id, "")
    return check_slide_content(content_obj, section_title=section_title)


# ---- per-op mutators (operate on _full.content dict) ----

def _apply_shorten_head(content: dict, op) -> str:
    content["head_message"] = op.new_text
    return ""


def _apply_truncate_bullets(content: dict, op) -> str:
    knowledge = content.setdefault("knowledge", {})
    changed = False
    if knowledge.get("narratives"):
        knowledge["narratives"] = knowledge["narratives"][:op.keep]
        changed = True
    timeline = knowledge.get("timeline")
    if isinstance(timeline, dict) and isinstance(timeline.get("nodes"), list):
        timeline["nodes"] = timeline["nodes"][:op.keep]
        changed = True
    matrix = knowledge.get("matrix")
    if isinstance(matrix, dict) and isinstance(matrix.get("cells"), list):
        for row in matrix["cells"]:
            for cell in row:
                if isinstance(cell, dict) and isinstance(cell.get("bullets"), list):
                    cell["bullets"] = cell["bullets"][:op.keep]
                    changed = True
    if not changed:
        return "no truncatable list found in knowledge"
    return ""


def _apply_change_intent(content: dict, op) -> str:
    if content.get("intent_label") in _FRAMING_INTENTS:
        return "cannot change intent on framing slide"
    content["intent_label"] = op.new_intent
    return ""


def _apply_drop_metric(content: dict, op) -> str:
    metrics = (content.get("knowledge") or {}).get("metrics") or []
    if op.index >= len(metrics):
        return f"index {op.index} out of range (have {len(metrics)} metrics)"
    if len(metrics) <= 1:
        return "cannot drop the only metric"
    metrics.pop(op.index)
    return ""


def _apply_swap_emphasis(content: dict, op) -> str:
    metrics = (content.get("knowledge") or {}).get("metrics") or []
    if op.new_hero_index >= len(metrics):
        return f"index {op.new_hero_index} out of range"
    if op.new_hero_index == 0:
        return ""  # already hero
    hero = metrics.pop(op.new_hero_index)
    metrics.insert(0, hero)
    return ""


def _apply_rewrite_takeaway(content: dict, op) -> str:
    content["key_takeaway"] = op.new_text
    return ""


_APPLIERS = {
    "shorten_head":     _apply_shorten_head,
    "truncate_bullets": _apply_truncate_bullets,
    "change_intent":    _apply_change_intent,
    "drop_metric":      _apply_drop_metric,
    "swap_emphasis":    _apply_swap_emphasis,
    "rewrite_takeaway": _apply_rewrite_takeaway,
}


# ---------------------------------------------------------------------------
# apply_patches — the deterministic orchestrator
# ---------------------------------------------------------------------------

class PatchResult:
    __slots__ = ("plan", "applied", "rejected")

    def __init__(self, plan: dict, applied: list[dict], rejected: list[dict]):
        self.plan = plan
        self.applied = applied
        self.rejected = rejected

    def to_dict(self) -> dict:
        return {"applied": self.applied, "rejected": self.rejected}


def apply_patches(plan: dict, ops: Iterable, *, copy: bool = True) -> PatchResult:
    """Apply ops to plan in order, with per-op rollback on check failure.

    Args:
        plan: full plan dict (must have `deck_meta` and `slides`).
        ops: iterable of validated PatchOp instances.
        copy: deep-copy plan before mutating (default True for safety).

    Returns:
        PatchResult with the mutated plan, list of applied ops (with
        before/after snapshots), and list of rejected ops with reasons.
    """
    import copy as _copy

    work = _copy.deepcopy(plan) if copy else plan
    deck_meta = work.get("deck_meta") or {}
    applied: list[dict] = []
    rejected: list[dict] = []

    for op in ops:
        slide_no = int(op.slide_no)
        idx = _slide_index(work, slide_no)
        if idx < 0:
            rejected.append({
                "op": op.op, "slide_no": slide_no,
                "reason": "slide_no not found in plan",
            })
            continue

        slide = work["slides"][idx]
        full = slide.setdefault("_full", {})
        content = full.setdefault("content", {})

        # Snapshot for potential rollback
        before = _copy.deepcopy(content)
        before_recipe = full.get("recipe")
        before_data = full.get("data")

        applier = _APPLIERS.get(op.op)
        if applier is None:
            rejected.append({
                "op": op.op, "slide_no": slide_no,
                "reason": f"no applier registered for op {op.op!r}",
            })
            continue

        mutate_err = applier(content, op)
        if mutate_err:
            rejected.append({
                "op": op.op, "slide_no": slide_no,
                "reason": f"mutator: {mutate_err}",
            })
            continue

        # Re-select recipe/data based on mutated content
        sel_ok, sel_reason = _re_select(slide)
        if not sel_ok:
            full["content"] = before
            full["recipe"] = before_recipe
            full["data"] = before_data
            rejected.append({
                "op": op.op, "slide_no": slide_no,
                "reason": f"reselect failed: {sel_reason}",
            })
            continue

        # Run deterministic checks. If any non-trivial issue surfaces
        # that the patch CAUSED (not pre-existing), roll back.
        issues = _re_check(slide, deck_meta)
        # We tolerate issues that already existed before the op — only
        # newly-introduced issues are rollback-worthy. To detect that we
        # compare the issue codes.
        before_slide = {"_full": {"content": before}}
        before_issues = _re_check(before_slide, deck_meta)
        before_codes = {code for code, _ in before_issues}
        new_issues = [(c, m) for c, m in issues if c not in before_codes]
        if new_issues:
            # roll back this op
            full["content"] = before
            full["recipe"] = before_recipe
            full["data"] = before_data
            rejected.append({
                "op": op.op, "slide_no": slide_no,
                "reason": "new deterministic issues: " + "; ".join(
                    f"{c}:{m}" for c, m in new_issues
                ),
            })
            continue

        _refresh_top_level(slide)
        applied.append({
            "op": op.op, "slide_no": slide_no,
            "before_recipe": before_recipe,
            "after_recipe": full.get("recipe"),
            "fallback_reason": sel_reason or None,
        })

    return PatchResult(work, applied, rejected)


def dump_patch_result(result: PatchResult, out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path
