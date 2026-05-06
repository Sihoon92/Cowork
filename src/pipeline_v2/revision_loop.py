"""Stage 5 — per-slide visual revision loop.

For each slide, capture PNG → 3-axis critique → if min(scores) < 7 and
verdict != KEEP, ask LLM to revise the code, re-execute (with one
auto-fix retry on failure), and re-capture. Bail out early if no slide
was revised in an iteration.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.llm.client import chat, chat_with_image
from src.pipeline.planner import parse_json_block
from src.pipeline_v2.auto_fix import execute_with_auto_fix
from src.pipeline_v2.code_generator import _strip_fences
from src.pipeline_v2.prompts import load_prompt
from src.pipeline_v2.schemas import SlideCritique
from src.pptx.capture import screenshot_deck
from src.util import log

REVISE_THRESHOLD = 7


def _capture_slide(pptx_path: Path, out_dir: Path) -> Path:
    """Capture a single-slide deck to PNG. Returns the PNG path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pngs = screenshot_deck(pptx_path, out_dir)
    if not pngs:
        raise RuntimeError(f"capture produced no PNG for {pptx_path}")
    return pngs[0]


def _critique_slide(png: Path, slide_plan: dict) -> SlideCritique:
    prompt = load_prompt(
        "slide_critique_3axis",
        slide_plan_json=json.dumps(slide_plan, ensure_ascii=False, indent=2),
    )
    raw = chat_with_image(prompt, str(png))
    data = parse_json_block(raw)
    return SlideCritique.model_validate(data)


def _revise_code(slide_plan: dict, critique: SlideCritique, prev_code: str) -> str:
    prompt = load_prompt(
        "code_revision",
        slide_plan_json=json.dumps(slide_plan, ensure_ascii=False, indent=2),
        critique_json=critique.model_dump_json(indent=2),
        prev_code=prev_code,
    )
    return _strip_fences(chat(prompt))


def visual_revision_loop_v2(
    plan: dict,
    slide_paths: list[Path],
    slide_bodies: list[str],
    *,
    workdir: Path,
    design_guide_excerpt: str,
    max_iterations: int = 3,
) -> tuple[list[Path], list[str], list[SlideCritique]]:
    """Returns (final slide paths, final bodies, final critiques).

    ``slide_paths`` and ``slide_bodies`` are aligned to ``plan['slides']``.
    """
    code_dir = workdir / "slide_codes"
    captures_dir = workdir / "captures"
    crit_dir = workdir / "critiques"
    crit_dir.mkdir(parents=True, exist_ok=True)

    last_critiques: list[SlideCritique | None] = [None] * len(slide_paths)

    for it in range(1, max_iterations + 1):
        any_revised = False
        log.stage(f"v2 Stage 5: revision iter {it}")

        for n, (slide_path, body) in enumerate(zip(slide_paths, slide_bodies)):
            slide_plan = plan["slides"][n]
            png = _capture_slide(slide_path, captures_dir / f"iter{it}")

            try:
                crit = _critique_slide(png, slide_plan)
            except Exception as exc:  # noqa: BLE001
                log.warn(f"  slide {n+1}: critique failed ({exc}); skipping")
                continue
            (crit_dir / f"slide_{n+1:02d}_iter{it}.json").write_text(
                crit.model_dump_json(indent=2), encoding="utf-8")
            last_critiques[n] = crit

            if crit.verdict == "KEEP" or crit.min_score >= REVISE_THRESHOLD:
                continue

            log.info(f"  slide {n+1}: revising "
                     f"(strategy={crit.score_strategy} visual={crit.score_visual} "
                     f"content={crit.score_content})")
            try:
                new_body = _revise_code(slide_plan, crit, body)
                execute_with_auto_fix(
                    new_body, slide_path, work_dir=code_dir,
                    design_guide_excerpt=design_guide_excerpt, max_retries=1,
                )
                slide_bodies[n] = new_body
                # snapshot history
                hist = code_dir / f"{slide_path.stem}.iter{it}.py"
                hist.write_text(new_body, encoding="utf-8")
                any_revised = True
            except Exception as exc:  # noqa: BLE001
                log.warn(f"  slide {n+1} revision failed ({exc}); keeping previous")

        if not any_revised:
            log.ok(f"  no revisions in iter {it}; stopping")
            break

    return slide_paths, slide_bodies, [c for c in last_critiques if c is not None]
