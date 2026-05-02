"""End-to-end orchestrator: content.json -> output.pptx."""
from __future__ import annotations

import json
import time
from pathlib import Path

from src.pipeline.planner import make_plan
from src.pipeline.critic import revise_plan_until_pass, critique_deck_storyline, critique_deck_visual
from src.pipeline.code_generator import generate_slide_code, build_codegen_prompt, extract_code_block
from src.pipeline.guideline_loader import get_pattern_section, resolve_pattern
from src.pipeline.text_critic import critique_slide_text
from src.pipeline.visual_critic import critique_slide_visual
from src.pptx.code_runner import render_slide_with_retry
from src.pptx.merger import merge_slides
from src.util import log

_FALLBACK_PATTERN = "Bullet List"


def _safe_get_pattern_section(layout_hint: str) -> tuple[str, str]:
    """Return (resolved_layout_hint, pattern_guideline), falling back to Bullet List."""
    canonical = resolve_pattern(layout_hint)
    if canonical is None:
        log.warn(
            f"layout_hint {layout_hint!r} did not resolve to any known pattern; "
            f"falling back to {_FALLBACK_PATTERN!r}"
        )
        canonical = _FALLBACK_PATTERN
    return canonical, get_pattern_section(canonical)


def _fix_callback_factory(layout_hint: str, slide_data: dict):
    _, pattern_guideline = _safe_get_pattern_section(layout_hint)

    def fix(original_code: str, traceback: str, _slide_data: dict) -> str:
        from src.pipeline.code_generator import build_codegen_prompt, extract_code_block
        from src.llm.ollama_client import chat

        base = build_codegen_prompt(
            layout_hint=layout_hint,
            pattern_guideline=pattern_guideline,
            slide_data=slide_data,
        )
        prompt = (
            base
            + "\n\nThe previous code failed with this error. Regenerate the FULL script (no partial patches):\n"
            + traceback
            + "\n\nPrevious code:\n```python\n"
            + original_code
            + "\n```\n"
        )
        return extract_code_block(chat(prompt))

    return fix


def build_presentation(
    content: dict,
    *,
    output_path: Path,
    workdir: Path,
) -> Path:
    t0 = time.time()
    output_path = Path(output_path)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    slides_dir = workdir / "slides"
    slides_dir.mkdir(exist_ok=True)

    # -------------------------------------------------------------------------
    # Stage 1: load content info
    # -------------------------------------------------------------------------
    log.stage("Stage 1: load content")
    meta = content.get("meta", {})
    sections = content.get("sections", [])
    log.info(f"title: {meta.get('title', '(no title)')!r}")
    log.info(f"sections: {len(sections)}")

    # -------------------------------------------------------------------------
    # Stage 2: planner
    # -------------------------------------------------------------------------
    log.stage("Stage 2: planner")
    plan_raw = make_plan(content)
    (workdir / "plan_raw.json").write_text(
        json.dumps(plan_raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.ok(f"raw plan: {len(plan_raw['slides'])} slides")
    for s in plan_raw["slides"]:
        log.info(
            f"  slide {s['slide_no']:02d}  layout={s.get('layout_hint','?')!r}"
            f"  msg={s.get('head_message','')[:60]!r}"
        )

    # -------------------------------------------------------------------------
    # Stage 3: plan critique
    # -------------------------------------------------------------------------
    log.stage("Stage 3: plan critique")
    plan = revise_plan_until_pass(plan_raw, max_rounds=3)
    (workdir / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Log any fields that changed vs plan_raw
    patched_slides = []
    raw_by_no = {s["slide_no"]: s for s in plan_raw["slides"]}
    for s in plan["slides"]:
        raw = raw_by_no.get(s["slide_no"], {})
        changed = [k for k in ("head_message", "layout_hint", "purpose") if s.get(k) != raw.get(k)]
        if changed:
            patched_slides.append((s["slide_no"], changed))
    if patched_slides:
        for sno, fields in patched_slides:
            log.info(f"  slide {sno:02d} patched fields: {fields}")
    else:
        log.ok("no patches applied — plan passed as-is")

    # -------------------------------------------------------------------------
    # Stage 4: per-slide code generation + render
    # -------------------------------------------------------------------------
    total = len(plan["slides"])
    slide_paths: list[Path] = []

    for idx, slide_plan in enumerate(plan["slides"], start=1):
        slide_no = slide_plan["slide_no"]
        layout_hint_raw = slide_plan["layout_hint"]
        head_msg = slide_plan.get("head_message", "")

        log.stage(f"Stage 4: slide {idx}/{total} — layout={layout_hint_raw!r}")
        log.info(f"slide_no={slide_no}  head_message={head_msg[:70]!r}")

        layout_hint, pattern_guideline = _safe_get_pattern_section(layout_hint_raw)
        if layout_hint != layout_hint_raw:
            log.warn(f"layout_hint resolved: {layout_hint_raw!r} -> {layout_hint!r}")

        slide_data = {**slide_plan, "deck_meta": plan["deck_meta"]}

        # --- code generation ---
        log.step("generating code")
        t_gen = time.time()
        code = generate_slide_code(
            layout_hint=layout_hint,
            pattern_guideline=pattern_guideline,
            slide_data=slide_data,
        )
        log.info(f"code: {len(code)} chars  ({time.time() - t_gen:.1f}s)")
        log.detail(code, max_lines=8)

        # Save generated code to disk
        code_path = slides_dir / f"slide_{slide_no:02d}_code.py"
        code_path.write_text(code, encoding="utf-8")
        log.info(f"code saved -> {code_path.name}")

        # --- subprocess render ---
        log.step("running subprocess")
        out = slides_dir / f"slide_{slide_plan['slide_no']:02d}.pptx"
        t_render = time.time()
        render_slide_with_retry(
            code,
            slide_data,
            out,
            fix_callback=_fix_callback_factory(layout_hint, slide_data),
            max_retries=3,
        )
        size_kb = out.stat().st_size // 1024
        log.ok(f"slide_{slide_no:02d}.pptx  {size_kb} KB  ({time.time() - t_render:.1f}s)")
        slide_paths.append(out)

        # --- Stage 5-A: text critique ---
        log.step("text critique")
        critique = critique_slide_text(slide_plan, out)
        t_verdict = critique["verdict"]
        t_issues = critique.get("issues", [])
        log.info(f"verdict={t_verdict}  issues={len(t_issues)}")
        if t_issues:
            preview = "\n".join(
                f"  [{i.get('severity','?')}] {i.get('msg','')}"
                for i in t_issues[:2]
            )
            log.detail(preview, max_lines=4)

        if t_verdict == "FIX":
            issues_text = "\n".join(f"- {i['msg']}" for i in t_issues)
            fix_prompt = (
                f"The previous slide had these text issues:\n{issues_text}\n"
                f"Regenerate the FULL python script fixing them. Do not add new content."
            )
            _, pattern_guideline_fix = _safe_get_pattern_section(layout_hint)
            base = build_codegen_prompt(
                layout_hint=layout_hint,
                pattern_guideline=pattern_guideline_fix,
                slide_data=slide_data,
            )
            from src.llm.ollama_client import chat as _chat
            fixed_code = extract_code_block(_chat(base + "\n\n" + fix_prompt))
            try:
                render_slide_with_retry(
                    fixed_code,
                    slide_data,
                    out,
                    fix_callback=_fix_callback_factory(layout_hint, slide_data),
                    max_retries=1,
                )
                log.ok("text fix applied")
            except Exception as exc:
                log.warn(f"text fix failed, keeping original: {exc}")

        # Save text critique JSON
        critique_path = slides_dir / f"slide_{slide_no:02d}_text_critique.json"
        critique_path.write_text(
            json.dumps(critique, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # --- Stage 5-B: visual critique ---
        log.step("visual critique")
        v_critique = critique_slide_visual(out)
        v_verdict = v_critique["verdict"]
        v_issues = v_critique.get("issues", [])
        if v_verdict == "SKIP":
            log.warn(f"visual SKIP -- {v_critique.get('reason', 'unavailable')}")
        else:
            log.info(f"verdict={v_verdict}  issues={len(v_issues)}")
            if v_issues:
                preview = "\n".join(
                    f"  [{i.get('severity','?')}] {i.get('msg','')}"
                    for i in v_issues[:2]
                )
                log.detail(preview, max_lines=4)

        if v_verdict == "FIX":
            issues_text = "\n".join(f"- {i['msg']}" for i in v_issues)
            fix_prompt = (
                f"The previous slide had these visual defects:\n{issues_text}\n"
                f"Regenerate the FULL python script fixing them. Keep all coordinates within "
                f"0.4 inch margin from slide edges. Do not let text or shapes overlap."
            )
            base = build_codegen_prompt(
                layout_hint=layout_hint,
                pattern_guideline=pattern_guideline,
                slide_data=slide_data,
            )
            from src.llm.ollama_client import chat as _chat
            fixed = extract_code_block(_chat(base + "\n\n" + fix_prompt))
            try:
                render_slide_with_retry(
                    fixed, slide_data, out,
                    fix_callback=_fix_callback_factory(layout_hint, slide_data),
                    max_retries=1,
                )
                log.ok("visual fix applied")
            except Exception as exc:
                log.warn(f"visual fix failed, keeping original: {exc}")

        # Save visual critique JSON
        v_critique_path = slides_dir / f"slide_{slide_no:02d}_visual_critique.json"
        v_critique_path.write_text(
            json.dumps(v_critique, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # -------------------------------------------------------------------------
    # Stage Final: merge
    # -------------------------------------------------------------------------
    log.stage("Stage Final: merge")
    final_path = merge_slides(slide_paths, output_path)
    size_kb = final_path.stat().st_size // 1024
    log.ok(f"-> {final_path}  ({size_kb} KB)")

    # -------------------------------------------------------------------------
    # Stage 6: deck critique
    # -------------------------------------------------------------------------
    log.stage("Stage 6: deck critique")
    storyline = critique_deck_storyline(plan)
    visual_consistency = critique_deck_visual(slide_paths, out_dir=workdir)
    (workdir / "deck_critique.json").write_text(
        json.dumps({
            "storyline": storyline,
            "visual_consistency": visual_consistency,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.ok(f"deck critique saved -> {workdir / 'deck_critique.json'}")

    total_elapsed = time.time() - t0
    log.stage("Done")
    log.ok(f"total elapsed: {total_elapsed:.1f}s")
    log.ok(f"output: {final_path}")

    return final_path
