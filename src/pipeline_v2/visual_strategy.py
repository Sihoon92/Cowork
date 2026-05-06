"""Stage 1b — add visual_strategy to body slides; inject gallery references.

See spec §4 (Stage 1b) and §5.8 (gallery lookup).
"""
from __future__ import annotations

import json
from typing import Optional

from src.llm.client import chat
from src.pipeline.planner import parse_json_block
from src.pipeline_v2.gallery import Gallery
from src.pipeline_v2.prompts import load_prompt
from src.pipeline_v2.schemas import SlidePlanV2
from src.util import log

K_PER_CATEGORY = 2
SNIPPET_LINES = 30


def _format_used_approaches(used: list[str]) -> str:
    if not used:
        return "(none yet)"
    return "\n".join(f"- {a}" for a in used)


def _format_gallery_refs(
    gallery: Optional[Gallery], *, categories: set[str]
) -> str:
    if gallery is None or not categories:
        return "(no references available)"
    chunks = []
    for cat in sorted(categories):
        refs = gallery.top_k(category=cat, k=K_PER_CATEGORY)
        if not refs:
            continue
        chunks.append(f"### content_structure = {cat}")
        for r in refs:
            snippet = "\n".join(r.code_snippet.splitlines()[:SNIPPET_LINES])
            chunks.append(
                f"- score={r.quality_score:.1f}  approach: `{r.approach}`\n"
                f"  layout_hint: {r.layout_hint}\n"
                f"  code_snippet (first {SNIPPET_LINES} lines):\n"
                f"  ```python\n{snippet}\n  ```"
            )
    return "\n".join(chunks) if chunks else "(no references for these categories)"


def add_visual_strategy(plan: dict, *, gallery: Optional[Gallery]) -> dict:
    """Return plan with `visual_strategy` populated on body slides."""
    log.stage("v2 Stage 1b: visual strategy")
    body_categories = {
        s["content_structure"] for s in plan["slides"]
        if s["kind"] == "body" and s.get("content_structure")
    }
    prompt = load_prompt(
        "visual_strategy_1b",
        plan_json=json.dumps(plan, ensure_ascii=False, indent=2),
        used_approaches=_format_used_approaches([]),  # first call: empty
        gallery_references=_format_gallery_refs(gallery, categories=body_categories),
    )
    raw = chat(prompt)
    data = parse_json_block(raw)
    if not isinstance(data, dict) or "slides" not in data:
        raise ValueError(f"visual_strategy_1b returned unexpected shape: {data!r}")

    # Validate every slide.
    cleaned = []
    used = set()
    for s in data["slides"]:
        valid = SlidePlanV2.model_validate(s)
        if valid.kind == "body" and valid.visual_strategy:
            if valid.visual_strategy.approach in used:
                raise ValueError(
                    f"duplicate approach within deck: {valid.visual_strategy.approach!r}"
                )
            used.add(valid.visual_strategy.approach)
        cleaned.append(valid.model_dump(exclude_none=False))
    log.ok(
        f"visual_strategy: {sum(1 for s in cleaned if s['kind']=='body')} body slides"
    )
    return {"slides": cleaned}
