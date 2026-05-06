"""Stage 2 — generate per-slide python-pptx code via LLM and execute it.

The actual subprocess execution is handled by ``execute_slide_body``,
which is also reused by the auto-fix and revision loops.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from src.llm.client import chat
from src.pipeline_v2.code_assembler import (
    PREAMBLE_PATH, assemble_slide_module,
)
from src.pipeline_v2.prompts import load_prompt
from src.util import log


class SlideExecutionError(RuntimeError):
    def __init__(self, message: str, *, traceback: str, code: str):
        super().__init__(message)
        self.traceback = traceback
        self.code = code


def execute_slide_body(body: str, out_pptx: Path, *, work_dir: Path) -> Path:
    """Assemble body into a runnable module and execute in a subprocess."""
    work_dir.mkdir(parents=True, exist_ok=True)
    module_path = work_dir / f"{out_pptx.stem}.py"
    module = assemble_slide_module(body, out_pptx)
    module_path.write_text(module, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True, text=True,
        env={"PYTHONIOENCODING": "utf-8", **_env_passthrough()},
    )
    if proc.returncode != 0 or not out_pptx.exists():
        raise SlideExecutionError(
            f"slide module failed (rc={proc.returncode})",
            traceback=proc.stderr or proc.stdout,
            code=body,
        )
    return out_pptx


def _env_passthrough() -> dict:
    keep = ("PATH", "SYSTEMROOT", "USERPROFILE", "TEMP", "TMP",
            "PYTHONPATH", "VIRTUAL_ENV")
    return {k: os.environ[k] for k in keep if k in os.environ}


def generate_slide_body(slide_plan: dict, *, design_guide: str,
                        preamble_excerpt: str) -> str:
    """Single LLM call. Returns code body only."""
    prompt = load_prompt(
        "code_generation",
        slide_plan_json=json.dumps(slide_plan, ensure_ascii=False, indent=2),
        design_guide=design_guide,
        preamble_excerpt=preamble_excerpt,
    )
    log.info(f"  generating code for slide {slide_plan.get('index')}")
    raw = chat(prompt)
    return _strip_fences(raw)


def _strip_fences(text: str) -> str:
    """Remove ```python ... ``` fences if the LLM ignored instructions."""
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        # drop opening fence
        if lines[0].startswith("```"):
            lines = lines[1:]
        # drop closing fence
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines)
    return t
