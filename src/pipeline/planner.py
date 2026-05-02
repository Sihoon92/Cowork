"""content.json -> plan.json via Ollama (Phases 2-1 and 2-2)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.llm.ollama_client import chat, DEFAULT_MODEL
from src.pipeline.guideline_loader import get_pattern_summary_cards
from src.util import log

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

_JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)


def parse_json_block(response: str):
    m = _JSON_FENCE_RE.search(response)
    if not m:
        raise ValueError("no ```json``` fence found in response")
    return json.loads(m.group(1))


_RETRY_SUFFIX = (
    "\n\nYour previous response was not a valid ```json``` code block. "
    "Reply with ONLY the JSON in a fenced block."
)


def _call_llm_with_json_retry(prompt: str, model: str, max_retries: int = 2):
    """Call chat() and parse JSON, retrying up to max_retries times on ValueError."""
    last_error: ValueError | None = None
    current_prompt = prompt
    for attempt in range(max_retries + 1):
        response = chat(current_prompt, model=model)
        try:
            return parse_json_block(response)
        except ValueError as exc:
            last_error = exc
            if attempt < max_retries:
                log.warn(f"JSON parse failed (attempt {attempt + 1}), retrying")
                current_prompt = prompt + _RETRY_SUFFIX
    raise last_error  # type: ignore[misc]


def generate_outline(content: dict, *, model: str = DEFAULT_MODEL) -> list[dict]:
    log.step("LLM call: outline")
    template = (PROMPTS_DIR / "story_outline.txt").read_text(encoding="utf-8")
    prompt = template.format(content_json=json.dumps(content, ensure_ascii=False, indent=2))
    parsed = _call_llm_with_json_retry(prompt, model=model)
    if not isinstance(parsed, list):
        raise ValueError(f"expected JSON array, got {type(parsed).__name__}")
    log.ok(f"got {len(parsed)} slides in outline")
    return parsed


_DEFAULT_THEME = {
    "primary": "#065A82",
    "accent": "#21295C",
    "neutral": "#F2F2F2",
    "text_dark": "#1C2833",
    "text_light": "#FFFFFF",
}

_DEFAULT_FONTS = {
    "header": "Pretendard Bold",
    "body": "Pretendard",
}


def derive_deck_meta(content: dict) -> dict:
    return {
        "title": content.get("meta", {}).get("title", ""),
        "theme": dict(_DEFAULT_THEME),
        "fonts": dict(_DEFAULT_FONTS),
        "slide_size": {"width_in": 13.333, "height_in": 7.5},
    }


def _section_facts_for(content: dict, section_id: str | None) -> list[str]:
    """Return raw_facts for the given section_id. Empty list if section_id is None or unknown."""
    if section_id is None:
        return []
    for sec in content.get("sections", []):
        if sec.get("id") == section_id:
            return list(sec.get("raw_facts", []))
    return []


def generate_slide_detail(
    outline: dict,
    section_facts: list[str],
    *,
    model: str = DEFAULT_MODEL,
) -> dict:
    log.step(f"LLM call: detail for slide {outline['slide_no']}")
    template = (PROMPTS_DIR / "slide_detail.txt").read_text(encoding="utf-8")
    cards = "\n".join(f"- {c}" for c in get_pattern_summary_cards())
    prompt = template.format(
        pattern_cards=cards,
        slide_no=outline["slide_no"],
        purpose=outline["purpose"],
        head_message=outline["head_message"],
        section_facts="\n".join(f"- {f}" for f in section_facts),
    )
    parsed = _call_llm_with_json_retry(prompt, model=model)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object for slide detail")
    for required in ("slide_no", "purpose", "head_message", "layout_hint", "content"):
        if required not in parsed:
            raise ValueError(f"slide detail missing key: {required}")
    parsed["section_id"] = outline.get("section_id")
    return parsed


def make_plan(content: dict, *, model: str = DEFAULT_MODEL) -> dict:
    outline = generate_outline(content, model=model)
    slides: list[dict] = []
    for o in outline:
        facts = _section_facts_for(content, o.get("section_id"))
        detail = generate_slide_detail(o, facts, model=model)
        slides.append(detail)
    return {
        "deck_meta": derive_deck_meta(content),
        "slides": slides,
    }
