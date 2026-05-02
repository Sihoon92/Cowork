"""Stage 3 — plan-level critique loop."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from src.llm.ollama_client import chat, DEFAULT_MODEL
from src.pipeline.planner import parse_json_block

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def critique_plan(plan: dict, *, model: str = DEFAULT_MODEL) -> dict:
    """Call LLM to critique the plan. Returns {scores, issues, patches, verdict}."""
    template = (PROMPTS_DIR / "plan_critique.txt").read_text(encoding="utf-8")
    prompt = template.format(plan_json=json.dumps(plan, ensure_ascii=False, indent=2))
    response = chat(prompt, model=model)
    parsed = parse_json_block(response)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object for critique")
    for required in ("scores", "issues", "patches", "verdict"):
        if required not in parsed:
            raise ValueError(f"critique missing key: {required}")
    return parsed


def apply_patches(plan: dict, patches: list[dict]) -> dict:
    """Return a NEW plan with patches applied. Patches with unknown slide_no are skipped."""
    new_plan = copy.deepcopy(plan)
    by_no = {s["slide_no"]: s for s in new_plan["slides"]}
    for patch in patches:
        target = by_no.get(patch.get("slide_no"))
        if target is None:
            continue
        field = patch.get("field")
        if field not in ("head_message", "layout_hint", "purpose"):
            continue
        target[field] = patch.get("new_value", target.get(field))
    return new_plan


def revise_plan_until_pass(
    plan: dict,
    *,
    max_rounds: int = 3,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Loop critique → apply patches → re-critique until PASS or max rounds."""
    current = plan
    for _ in range(max_rounds):
        result = critique_plan(current, model=model)
        if result["patches"]:
            current = apply_patches(current, result["patches"])
        if result["verdict"] == "PASS":
            return current
    return current
