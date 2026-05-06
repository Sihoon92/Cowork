"""Retry loop for slide code execution.

Calls Stage 2 once; on failure, asks the LLM to fix the traceback up to
``max_retries`` times. Each retry receives the FULL history of prior
failed attempts so the model can recognise repeating-mistake patterns
instead of re-emitting the same bad idiom with cosmetic tweaks.
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
    design_guide_excerpt: str, max_retries: int = 5,
) -> tuple[Path, str]:
    """Execute, retry via LLM on failure. Returns (pptx_path, final_body)."""
    current_body = body
    history: list[tuple[str, str]] = []  # [(failed_code, traceback), ...]
    for attempt in range(max_retries + 1):
        try:
            execute_slide_body(current_body, out_pptx, work_dir=work_dir)
            return out_pptx, current_body
        except SlideExecutionError as exc:
            history.append((current_body, _tail(exc.traceback, 40)))
            if attempt == max_retries:
                raise
            log.warn(f"  slide exec failed (attempt {attempt+1}); auto-fixing")
            prompt = load_prompt(
                "code_auto_fix",
                prev_code=current_body,
                traceback=_tail(exc.traceback, 40),
                design_guide_excerpt=design_guide_excerpt,
                history_block=_format_history(history),
            )
            current_body = _strip_fences(chat(prompt))
    raise RuntimeError("unreachable")


def _tail(text: str, lines: int) -> str:
    parts = text.splitlines()
    return "\n".join(parts[-lines:])


def _format_history(history: list[tuple[str, str]]) -> str:
    """Render all prior failed attempts so the LLM sees recurring patterns."""
    if len(history) <= 1:
        return "(this is the first failure — no prior attempts)"
    out = []
    # Skip the last entry: it is shown as `prev_code` / `traceback` already.
    for i, (_code, tb) in enumerate(history[:-1], start=1):
        out.append(f"### Attempt {i} — failed with:\n```\n{tb}\n```")
    out.append(
        "If the current traceback is the SAME CLASS of error as any of the "
        "above, your previous fix did not address the root cause. Try a "
        "structurally different approach (e.g. remove the failing call "
        "entirely and replace its visual purpose with shapes + text)."
    )
    return "\n\n".join(out)
