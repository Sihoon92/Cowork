"""Stage 1a — structural outline only (no visual strategy).

See spec §4 (Stage 1a) and §5.5.
"""
from __future__ import annotations

import json

from src.llm.client import chat
from src.pipeline.planner import parse_json_block  # reuse v1 JSON repair
from src.pipeline_v2.prompts import load_prompt
from src.pipeline_v2.schemas import SlideOutline
from src.util import log


def generate_outline(content: dict) -> dict:
    """Return ``{"slides": [SlideOutline-shaped dicts]}``."""
    prompt = load_prompt(
        "outline_1a",
        content_json=json.dumps(content, ensure_ascii=False, indent=2),
    )
    log.stage("v2 Stage 1a: outline")
    raw = chat(prompt)
    data = parse_json_block(raw)
    if not isinstance(data, dict) or "slides" not in data:
        raise ValueError(f"outline_1a returned unexpected shape: {data!r}")

    # Validate each slide round-trips through the model.
    cleaned = []
    for s in data["slides"]:
        cleaned.append(SlideOutline.model_validate(s).model_dump(exclude_none=False))
    log.ok(f"outline: {len(cleaned)} slides")
    return {"slides": cleaned}
