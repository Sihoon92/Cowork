"""Per-slide visual critique via vision LLM.

Input:  slide PNG (from src.pptx.capture) + plan slice (slide_no, intent_label,
        head_message, key_takeaway).
Output: SlideCritique with 7 axes evaluated.

Used by the visual revision loop (Phase D) to decide whether a slide needs
patching. The LLM does NOT propose plan patches here — that's the patcher's
job. Critic only diagnoses; patcher prescribes.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.llm.ollama_client import VISION_MODEL, chat_with_image
from src.pipeline.planner import parse_json_block
from src.pipeline.schemas import SlideCritique, VISUAL_AXIS_CODES
from src.util import log

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def _empty_axes_payload(slide_no: int, reason: str) -> dict:
    """Build a SlideCritique-shaped dict with all axes ok/low.

    Used when the LLM call fails entirely — we still return a stable
    7-axis structure so the revision loop can carry on.
    """
    return {
        "slide_no": slide_no,
        "axes": [
            {"code": code, "verdict": "ok", "severity": "low",
             "msg": f"(critic skipped: {reason})", "suggestion": ""}
            for code in VISUAL_AXIS_CODES
        ],
        "summary": f"critic skipped: {reason}",
    }


def critique_slide(
    image_path: Path,
    slide_plan: dict,
    *,
    model: str = VISION_MODEL,
    max_retries: int = 1,
) -> SlideCritique:
    """Run the visual critic on a single slide.

    Args:
        image_path: PNG screenshot from capture.screenshot_deck.
        slide_plan: flattened slide plan (must contain slide_no,
            intent_label, head_message, key_takeaway/sub_message).
        model: vision-capable Ollama model.
        max_retries: extra attempts if the LLM output won't parse / validate.

    Returns:
        SlideCritique. Always returns a populated 7-axis result — on
        unrecoverable failure the axes are filled with neutral ok/low
        and the summary explains the skip.
    """
    slide_no = int(slide_plan["slide_no"])
    log.step(f"LLM call: visual critic for slide {slide_no}")

    template = (PROMPTS_DIR / "slide_visual_critic.md").read_text(encoding="utf-8")
    prompt = template.format(
        slide_no=slide_no,
        intent_label=slide_plan.get("intent_label", "?"),
        head_message=slide_plan.get("head_message", ""),
        key_takeaway=slide_plan.get("sub_message")
            or slide_plan.get("key_takeaway", ""),
    )

    last_err: str | None = None
    for attempt in range(max_retries + 1):
        try:
            response = chat_with_image(prompt, str(image_path), model=model)
        except Exception as exc:  # noqa: BLE001
            last_err = f"vision LLM call failed: {exc}"
            log.warn(f"slide {slide_no} critic attempt {attempt + 1}: {last_err}")
            continue

        try:
            parsed = parse_json_block(response)
        except ValueError as exc:
            last_err = f"JSON parse failed: {exc}"
            log.warn(f"slide {slide_no} critic attempt {attempt + 1}: {last_err}")
            continue

        if not isinstance(parsed, dict):
            last_err = "response was not a JSON object"
            continue

        # Force slide_no to match the plan (LLMs sometimes echo back wrong int)
        parsed["slide_no"] = slide_no

        try:
            critique = SlideCritique.model_validate(parsed)
        except Exception as exc:  # noqa: BLE001
            last_err = f"schema invalid: {exc}"
            log.warn(f"slide {slide_no} critic attempt {attempt + 1}: {last_err}")
            continue

        return critique

    log.warn(
        f"slide {slide_no} critic unrecoverable after {max_retries + 1} "
        f"attempts: {last_err}; returning neutral critique"
    )
    return SlideCritique.model_validate(_empty_axes_payload(slide_no, last_err or "unknown"))


def critique_slides(
    image_paths: list[Path],
    slide_plans: list[dict],
    *,
    model: str = VISION_MODEL,
) -> list[SlideCritique]:
    """Sequential per-slide critique. Order matches input.

    Parallelization deferred — vision LLM calls are heavy and Ollama serves
    them serially anyway under default config.
    """
    if len(image_paths) != len(slide_plans):
        raise ValueError(
            f"image_paths ({len(image_paths)}) and slide_plans "
            f"({len(slide_plans)}) length mismatch"
        )
    out: list[SlideCritique] = []
    for img, plan in zip(image_paths, slide_plans):
        out.append(critique_slide(img, plan, model=model))
    return out


def summarize_critiques(critiques: list[SlideCritique]) -> dict:
    """Aggregate stats useful for revision-loop decisions.

    Returns:
        {
          "total_slides": int,
          "fail_count": int,         # axes with verdict=fail
          "warn_count": int,
          "by_axis": { code: {"fail": n, "warn": n} },
          "needs_revision": [slide_no, ...]   # severity >= medium and not ok
        }
    """
    by_axis: dict[str, dict[str, int]] = {
        code: {"fail": 0, "warn": 0} for code in VISUAL_AXIS_CODES
    }
    fail_count = 0
    warn_count = 0
    needs: list[int] = []
    for c in critiques:
        if c.fail_or_warn_axes(min_severity="medium"):
            needs.append(c.slide_no)
        for a in c.axes:
            if a.verdict == "fail":
                by_axis[a.code]["fail"] += 1
                fail_count += 1
            elif a.verdict == "warn":
                by_axis[a.code]["warn"] += 1
                warn_count += 1
    return {
        "total_slides": len(critiques),
        "fail_count": fail_count,
        "warn_count": warn_count,
        "by_axis": by_axis,
        "needs_revision": needs,
    }


def dump_critiques(critiques: list[SlideCritique], out_path: Path) -> Path:
    """Persist critiques to JSON for debugging / iter_N audit trail."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summarize_critiques(critiques),
        "critiques": [c.model_dump() for c in critiques],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return out_path
