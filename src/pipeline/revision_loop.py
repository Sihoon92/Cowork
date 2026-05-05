"""Stage 5 — visual revision loop.

Orchestrates capture → critique → patch → re-render → re-merge until the
deck is clean, max iterations reached, or progress stalls. Each iteration
writes its artifacts under workdir/iter_N/ for audit.

Termination conditions (any one):
  - All slides clean at severity ≥ medium.
  - max_iterations reached.
  - Patcher produced no actionable ops.
  - All proposed ops rejected by deterministic checks.
  - Stagnation: this iter's issue signature equals the previous iter's
    AND the previous iter's "light only" mode also stagnated → bail.

Stagnation handling: when issue count doesn't decrease between iters, the
NEXT iter operates in "light only" mode (only `shorten_head` and
`rewrite_takeaway` ops applied). If light-only also stagnates, stop.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from pptx import Presentation
from pptx.util import Inches

from src.llm.ollama_client import DEFAULT_MODEL, VISION_MODEL
from src.pipeline.patcher import (
    PatchResult, apply_patches, dump_patch_result, generate_patches,
)
from src.pipeline.schemas import SlideCritique
from src.pipeline.slide_critic import critique_slides, dump_critiques
from src.pptx.capture import CaptureError, screenshot_deck
from src.pptx.merger import merge_slides
from src.pptx.renderer import render_slide
from src.util import log


_LIGHT_OP_KINDS = frozenset({"shorten_head", "rewrite_takeaway"})


def _new_prs() -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    return prs


def _render_one_slide(deck_meta: dict, slide_plan: dict, out_path: Path) -> Path:
    prs = _new_prs()
    render_slide(prs, deck_meta, slide_plan)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))
    return out_path


def _critique_signature(critiques: list[SlideCritique]) -> frozenset:
    """Set of (slide_no, axis_code) for axes with verdict ≠ ok and severity ≥ medium.

    Used to detect "same issues as last iter" stagnation.
    """
    rank = {"low": 0, "medium": 1, "high": 2}
    sig = set()
    for c in critiques:
        for ax in c.axes:
            if ax.verdict != "ok" and rank.get(ax.severity, 0) >= 1:
                sig.add((c.slide_no, ax.code))
    return frozenset(sig)


def _filter_light_ops(ops: list, kept_log: list[dict]) -> list:
    """Return only ops whose kind is in _LIGHT_OP_KINDS."""
    out = []
    for op in ops:
        if op.op in _LIGHT_OP_KINDS:
            out.append(op)
        else:
            kept_log.append({
                "op": op.op, "slide_no": op.slide_no,
                "reason": "light-only mode (stagnation)",
            })
    return out


def visual_revision_loop(
    plan: dict,
    deck_path: Path,
    slide_paths: list[Path],
    workdir: Path,
    *,
    max_iterations: int = 3,
    model: str = DEFAULT_MODEL,
    vision_model: str = VISION_MODEL,
) -> tuple[dict, Path, list[Path]]:
    """Run the revision loop. Return (plan, final_deck_path, slide_paths).

    On any unrecoverable failure (capture broken, all iters fail to patch),
    returns the original (or partially-revised) state without raising.
    The pipeline must keep producing output even if revision can't help.
    """
    deck_path = Path(deck_path)
    workdir = Path(workdir)
    slides_dir = workdir / "slides"

    prev_signature: frozenset | None = None
    prev_was_light = False

    for iteration in range(1, max_iterations + 1):
        log.stage(f"Stage 5: visual revision (iter {iteration}/{max_iterations})")
        iter_dir = workdir / f"iter_{iteration}"
        iter_dir.mkdir(parents=True, exist_ok=True)

        # 5a. Screenshot
        try:
            png_paths = screenshot_deck(
                deck_path, iter_dir / "screenshots",
            )
        except CaptureError as exc:
            log.warn(f"capture failed: {exc}; aborting revision loop")
            return plan, deck_path, slide_paths

        # Pair each plan slide with its PNG. Capture returns one PNG per
        # actual deck slide; if those counts diverge something has gone
        # very wrong upstream — bail.
        if len(png_paths) != len(plan["slides"]):
            log.warn(
                f"png count {len(png_paths)} != plan slides "
                f"{len(plan['slides'])}; aborting revision loop"
            )
            return plan, deck_path, slide_paths

        # 5b. Per-slide critique
        critiques = critique_slides(
            png_paths, plan["slides"], model=vision_model,
        )
        dump_critiques(critiques, iter_dir / "critiques.json")

        # 5c. Stop if clean
        signature = _critique_signature(critiques)
        if not signature:
            log.ok(f"iter {iteration}: deck clean (no severity≥medium issues)")
            return plan, deck_path, slide_paths

        log.info(f"iter {iteration}: {len(signature)} issue(s) flagged")

        # 5d. Stagnation detection. If same issue set as last iter,
        # next pass will run light-only.
        light_only = False
        if prev_signature is not None and signature == prev_signature:
            if prev_was_light:
                # Already tried light-only and didn't help — stop.
                log.warn(
                    f"iter {iteration}: stagnation in light-only mode; stopping"
                )
                return plan, deck_path, slide_paths
            light_only = True
            log.info(f"iter {iteration}: stagnation detected — light-only mode")

        # 5e. Generate ops
        patch_plan = generate_patches(critiques, plan, model=model)
        if not patch_plan.ops:
            log.warn(f"iter {iteration}: patcher returned no ops; stopping")
            return plan, deck_path, slide_paths

        # If light-only or this is the final iteration, drop heavy ops.
        skipped: list[dict] = []
        ops_to_apply = list(patch_plan.ops)
        if light_only or iteration == max_iterations:
            kept_count = len(ops_to_apply)
            ops_to_apply = _filter_light_ops(ops_to_apply, skipped)
            if skipped:
                log.info(
                    f"iter {iteration}: dropped {len(skipped)} non-light op(s) "
                    f"(kept {len(ops_to_apply)}/{kept_count})"
                )
        if not ops_to_apply:
            log.warn(
                f"iter {iteration}: no ops left after light filter; stopping"
            )
            (iter_dir / "patch_skipped.json").write_text(
                json.dumps(skipped, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return plan, deck_path, slide_paths

        # 5f. Apply
        result = apply_patches(plan, ops_to_apply)
        if skipped:
            # Stash light-only filtered ops alongside the apply result for audit
            result.rejected.extend(skipped)
        dump_patch_result(result, iter_dir / "patch_result.json")

        if not result.applied:
            log.warn(f"iter {iteration}: all ops rejected; stopping")
            return plan, deck_path, slide_paths

        plan = result.plan
        log.ok(
            f"iter {iteration}: applied {len(result.applied)}, "
            f"rejected {len(result.rejected)}"
        )

        # 5g. Re-render only changed slides
        changed_slide_nos = {a["slide_no"] for a in result.applied}
        log.step(f"iter {iteration}: re-rendering slides {sorted(changed_slide_nos)}")
        deck_meta = plan["deck_meta"]
        for slide_no in changed_slide_nos:
            slide_plan = next(
                s for s in plan["slides"] if s["slide_no"] == slide_no
            )
            target = slides_dir / f"slide_{slide_no:02d}.pptx"
            try:
                _render_one_slide(deck_meta, slide_plan, target)
            except Exception as exc:  # noqa: BLE001
                log.warn(f"slide {slide_no} re-render failed: {exc}; keeping old")

        # 5h. Re-merge
        deck_path = merge_slides(slide_paths, deck_path)
        log.ok(f"iter {iteration}: re-merged → {deck_path}")

        prev_signature = signature
        prev_was_light = light_only

    log.info(f"revision loop exited after {max_iterations} iterations")
    return plan, deck_path, slide_paths
