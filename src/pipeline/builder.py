"""End-to-end orchestrator: content.json -> output.pptx (recipe era).

Pipeline:
  Stage 1  load content
  Stage 2  planner (outline + per-slide recipe selection via Ollama)
  Stage 3  per-slide deterministic render (no LLM)
  Stage 4  merge slides into final deck
  Stage 5  visual revision loop (capture → critique → patch → re-render)
  Stage 6  deck-level critique (storyline + visual consistency)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from src.pipeline.critic import critique_deck_storyline, critique_deck_visual
from src.pipeline.planner import make_plan
from src.pipeline.revision_loop import visual_revision_loop
from src.pptx.merger import merge_slides
from src.pptx.renderer import PlanValidationError, render_slide
from src.util import log

# Codegen path is imported lazily inside build_presentation so unit tests
# that exercise the recipe path don't pull in code_runner / subprocess.


def _new_prs() -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    return prs


def _save_single_slide(deck_meta: dict, slide_plan: dict, out_path: Path) -> Path:
    """Render one slide into its own pptx file (one per merger input)."""
    prs = _new_prs()
    render_slide(prs, deck_meta, slide_plan)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))
    return out_path


def _write_placeholder_slide(
    out_path: Path, slide_no: int, head_message: str, reason: str,
) -> Path:
    """Fallback when render_slide itself raises (rare, structural issue)."""
    from src.pptx.primitives import Rect, add_text, set_bg

    prs = _new_prs()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, "#2B2B2B")
    add_text(slide, rect=Rect(0.6, 0.6, 12.1, 1.0),
             text=f"Slide {slide_no}: render failed",
             font_size=28, bold=True, color="#FF6B6B")
    add_text(slide, rect=Rect(0.6, 1.8, 12.1, 1.2),
             text=head_message or "(no head message)",
             font_size=20, color="#FFFFFF")
    add_text(slide, rect=Rect(0.6, 3.2, 12.1, 3.5),
             text=f"reason: {reason}",
             font_size=14, color="#CCCCCC")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))
    return out_path


def build_presentation(
    content: dict,
    *,
    output_path: Path,
    workdir: Path,
    use_codegen: bool = False,
) -> Path:
    t0 = time.time()
    output_path = Path(output_path)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    slides_dir = workdir / "slides"
    slides_dir.mkdir(exist_ok=True)

    # Lazy imports for the optional codegen path + gallery store.
    gallery = None
    render_via_codegen = None
    if use_codegen:
        from src.pipeline.codegen_path import render_via_codegen as _rvc
        from src.pipeline.gallery import Gallery
        render_via_codegen = _rvc
        gallery = Gallery.default()
        log.info(f"codegen path ENABLED — gallery: {gallery.path}")

    # ------------------------------------------------------------------
    # Stage 1 — load content
    # ------------------------------------------------------------------
    log.stage("Stage 1: load content")
    meta = content.get("meta", {})
    sections = content.get("sections", [])
    log.info(f"title: {meta.get('title', '(no title)')!r}")
    log.info(f"sections: {len(sections)}")

    # ------------------------------------------------------------------
    # Stage 2 — planner (outline + per-slide recipe)
    # ------------------------------------------------------------------
    log.stage("Stage 2: planner")
    plan = make_plan(
        content,
        with_visual_strategy=use_codegen,
        gallery=gallery,
    )
    (workdir / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.ok(f"plan: {len(plan['slides'])} slides")
    for s in plan["slides"]:
        log.info(
            f"  slide {s['slide_no']:02d}  "
            f"recipe={s.get('recipe', '?')!r}  "
            f"msg={s.get('head_message', '')[:60]!r}"
        )

    # ------------------------------------------------------------------
    # Stage 3 — per-slide deterministic render
    # ------------------------------------------------------------------
    deck_meta = plan["deck_meta"]
    total = len(plan["slides"])
    slide_paths: list[Path] = []

    for idx, slide_plan in enumerate(plan["slides"], start=1):
        slide_no = slide_plan["slide_no"]
        recipe = slide_plan.get("recipe", "?")
        head_msg = slide_plan.get("head_message", "")

        log.stage(f"Stage 3: slide {idx}/{total} — recipe={recipe!r}")
        log.info(f"slide_no={slide_no}  head_message={head_msg[:70]!r}")

        out = slides_dir / f"slide_{slide_no:02d}.pptx"
        t_render = time.time()

        rendered = False
        if use_codegen and render_via_codegen is not None and slide_plan.get("visual_strategy"):
            try:
                render_via_codegen(deck_meta, slide_plan, out)
                rendered = True
                size_kb = out.stat().st_size // 1024
                log.ok(
                    f"slide_{slide_no:02d}.pptx (codegen)  {size_kb} KB  "
                    f"({time.time() - t_render:.1f}s)"
                )
            except Exception as exc:  # noqa: BLE001
                log.warn(
                    f"slide {slide_no} codegen failed: {exc}; "
                    "falling back to recipe path"
                )

        if not rendered:
            try:
                _save_single_slide(deck_meta, slide_plan, out)
                size_kb = out.stat().st_size // 1024
                log.ok(
                    f"slide_{slide_no:02d}.pptx (recipe)  {size_kb} KB  "
                    f"({time.time() - t_render:.1f}s)"
                )
            except (PlanValidationError, Exception) as exc:  # noqa: BLE001
                log.warn(f"slide {slide_no} render failed: {exc}; substituting placeholder")
                _write_placeholder_slide(out, slide_no, head_msg, str(exc))
        slide_paths.append(out)

    # ------------------------------------------------------------------
    # Stage 4 — merge
    # ------------------------------------------------------------------
    log.stage("Stage 4: merge")
    final_path = merge_slides(slide_paths, output_path)
    size_kb = final_path.stat().st_size // 1024
    log.ok(f"-> {final_path}  ({size_kb} KB)")

    # ------------------------------------------------------------------
    # Stage 5 — visual revision loop (capture → critique → patch → re-render)
    # ------------------------------------------------------------------
    try:
        plan, final_path, slide_paths = visual_revision_loop(
            plan, final_path, slide_paths, workdir,
            max_iterations=3,
        )
    except Exception as exc:  # noqa: BLE001
        log.warn(f"visual revision loop crashed: {exc}; keeping pre-revision deck")
    # Persist (possibly revised) plan for audit
    (workdir / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    size_kb = final_path.stat().st_size // 1024
    log.ok(f"post-revision deck: {final_path}  ({size_kb} KB)")

    # ------------------------------------------------------------------
    # Stage 6 — deck critique
    # ------------------------------------------------------------------
    log.stage("Stage 6: deck critique")
    try:
        storyline = critique_deck_storyline(plan)
    except Exception as exc:  # noqa: BLE001
        log.warn(f"storyline critique skipped: {exc}")
        storyline = {"verdict": "SKIP", "issues": [], "reason": str(exc)}
    try:
        visual_consistency = critique_deck_visual(slide_paths, out_dir=workdir)
    except Exception as exc:  # noqa: BLE001
        log.warn(f"visual critique skipped: {exc}")
        visual_consistency = {"verdict": "SKIP", "issues": [], "reason": str(exc)}
    (workdir / "deck_critique.json").write_text(
        json.dumps({
            "storyline": storyline,
            "visual_consistency": visual_consistency,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.ok(f"deck critique saved -> {workdir / 'deck_critique.json'}")

    # ------------------------------------------------------------------
    # Stage 7 — gallery harvest (codegen path only)
    # ------------------------------------------------------------------
    if use_codegen and gallery is not None:
        try:
            critiques_path = workdir / "iter_1" / "critiques.json"
            saved = gallery.harvest_from_run(plan, critiques_path)
            if saved:
                log.ok(f"gallery: saved {saved} high-scoring slide(s) -> {gallery.path}")
        except Exception as exc:  # noqa: BLE001
            log.warn(f"gallery harvest skipped: {exc}")

    total_elapsed = time.time() - t0
    log.stage("Done")
    log.ok(f"total elapsed: {total_elapsed:.1f}s")
    log.ok(f"output: {final_path}")

    return final_path
