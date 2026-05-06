"""Retry loop for slide code execution.

Calls Stage 2 once; on failure, asks the LLM to fix the traceback up to
``max_retries`` times. Returns the body that finally produced a .pptx.
"""
from __future__ import annotations

from pathlib import Path

from src.llm.client import chat
from src.pipeline_v2.code_generator import (
    SlideExecutionError, _strip_fences, execute_slide_body,
)
from src.pipeline_v2.prompts import load_prompt
from src.util import log


def execute_with_auto_fix(
    body: str, out_pptx: Path, *, work_dir: Path,
    design_guide_excerpt: str, max_retries: int = 2,
) -> tuple[Path, str]:
    """Execute, retry via LLM on failure. Returns (pptx_path, final_body)."""
    current_body = body
    for attempt in range(max_retries + 1):
        try:
            execute_slide_body(current_body, out_pptx, work_dir=work_dir)
            return out_pptx, current_body
        except SlideExecutionError as exc:
            if attempt == max_retries:
                raise
            log.warn(f"  slide exec failed (attempt {attempt+1}); auto-fixing")
            prompt = load_prompt(
                "code_auto_fix",
                prev_code=current_body,
                traceback=_tail(exc.traceback, 40),
                design_guide_excerpt=design_guide_excerpt,
            )
            current_body = _strip_fences(chat(prompt))
    raise RuntimeError("unreachable")


def _tail(text: str, lines: int) -> str:
    parts = text.splitlines()
    return "\n".join(parts[-lines:])
