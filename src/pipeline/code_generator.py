"""Phase 4 — generate slide python code from a single slide plan via LLM."""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.llm.ollama_client import chat, DEFAULT_MODEL

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "code_generation.txt"

_FENCE_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)


def extract_code_block(response: str) -> str:
    """Return the contents of the first ```python ...``` fence, or raw response if none."""
    m = _FENCE_RE.search(response)
    if m:
        return m.group(1)
    return response


def build_codegen_prompt(
    *,
    layout_hint: str,
    pattern_guideline: str,
    slide_data: dict,
) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(
        layout_hint=layout_hint,
        pattern_guideline=pattern_guideline,
        slide_data_json=json.dumps(slide_data, ensure_ascii=False, indent=2),
    )


def generate_slide_code(
    *,
    layout_hint: str,
    pattern_guideline: str,
    slide_data: dict,
    model: str = DEFAULT_MODEL,
) -> str:
    prompt = build_codegen_prompt(
        layout_hint=layout_hint,
        pattern_guideline=pattern_guideline,
        slide_data=slide_data,
    )
    response = chat(prompt, model=model)
    return extract_code_block(response)
