"""End-to-end orchestrator: content.json -> output.pptx."""
from __future__ import annotations

import json
from pathlib import Path

from src.pipeline.planner import make_plan
from src.pipeline.code_generator import generate_slide_code
from src.pipeline.guideline_loader import get_pattern_section, resolve_pattern
from src.pptx.code_runner import render_slide_with_retry
from src.pptx.merger import merge_slides

_FALLBACK_PATTERN = "Bullet List"


def _safe_get_pattern_section(layout_hint: str) -> tuple[str, str]:
    """Return (resolved_layout_hint, pattern_guideline), falling back to Bullet List."""
    canonical = resolve_pattern(layout_hint)
    if canonical is None:
        print(
            f"WARNING: layout_hint {layout_hint!r} did not resolve to any known pattern; "
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
    output_path = Path(output_path)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    slides_dir = workdir / "slides"
    slides_dir.mkdir(exist_ok=True)

    plan = make_plan(content)
    (workdir / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    slide_paths: list[Path] = []
    for slide_plan in plan["slides"]:
        layout_hint = slide_plan["layout_hint"]
        layout_hint, pattern_guideline = _safe_get_pattern_section(layout_hint)
        slide_data = {**slide_plan, "deck_meta": plan["deck_meta"]}
        code = generate_slide_code(
            layout_hint=layout_hint,
            pattern_guideline=pattern_guideline,
            slide_data=slide_data,
        )
        out = slides_dir / f"slide_{slide_plan['slide_no']:02d}.pptx"
        render_slide_with_retry(
            code,
            slide_data,
            out,
            fix_callback=_fix_callback_factory(layout_hint, slide_data),
            max_retries=3,
        )
        slide_paths.append(out)

    return merge_slides(slide_paths, output_path)
