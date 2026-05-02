"""content.json -> plan.json via Ollama (Phases 2-1 and 2-2)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.llm.ollama_client import chat

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

_JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)


def parse_json_block(response: str):
    m = _JSON_FENCE_RE.search(response)
    if not m:
        raise ValueError("no ```json``` fence found in response")
    return json.loads(m.group(1))


def generate_outline(content: dict, *, model: str = "gemma4:e4b") -> list[dict]:
    template = (PROMPTS_DIR / "story_outline.txt").read_text(encoding="utf-8")
    prompt = template.format(content_json=json.dumps(content, ensure_ascii=False, indent=2))
    response = chat(prompt, model=model)
    parsed = parse_json_block(response)
    if not isinstance(parsed, list):
        raise ValueError(f"expected JSON array, got {type(parsed).__name__}")
    return parsed
