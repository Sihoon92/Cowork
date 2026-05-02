"""Stage 3 — plan-level critique loop, and Stage 6 — deck-level critique."""
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


# ---------------------------------------------------------------------------
# Stage 6: deck-level critique
# ---------------------------------------------------------------------------

from src.pipeline.visual_critic import (  # noqa: E402
    conversion_tools_available,
    pptx_to_image,
)
from src.llm.ollama_client import chat_with_image, VISION_MODEL  # noqa: E402


def critique_deck_storyline(plan: dict, *, model: str = DEFAULT_MODEL) -> dict:
    """Feed head_messages of all slides to LLM. Return {issues, verdict}."""
    head_lines = "\n".join(
        f"{s['slide_no']}. {s['head_message']}"
        for s in plan.get("slides", [])
    )
    template = (PROMPTS_DIR / "deck_storyline_critique.txt").read_text(encoding="utf-8")
    prompt = template.format(head_messages=head_lines)
    response = chat(prompt, model=model)
    parsed = parse_json_block(response)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object for storyline critique")
    parsed.setdefault("issues", [])
    parsed.setdefault("verdict", "PASS")
    return parsed


def make_thumbnail_grid(slide_paths: list[Path], out_path: Path, *, cols: int = 2) -> "Path | None":
    """Combine per-slide pptx images into a grid JPEG.

    Returns None if image conversion tools are not available or no slides could be converted.
    Requires Pillow.
    """
    if not conversion_tools_available():
        return None
    try:
        from PIL import Image
    except ImportError:
        return None

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img_dir = out_path.parent / "deck_imgs"
    img_dir.mkdir(exist_ok=True)

    images: list[Path] = []
    for sp in slide_paths:
        img = pptx_to_image(sp, img_dir)
        if img is not None:
            images.append(img)
    if not images:
        return None

    pil_imgs = [Image.open(p) for p in images]
    # Normalize sizes — scale to first image's width
    target_w = pil_imgs[0].width // 2  # downscale to keep grid manageable
    resized = []
    for im in pil_imgs:
        ratio = target_w / im.width
        resized.append(im.resize((target_w, int(im.height * ratio))))

    rows = (len(resized) + cols - 1) // cols
    cell_w = max(im.width for im in resized)
    cell_h = max(im.height for im in resized)
    grid = Image.new("RGB", (cell_w * cols, cell_h * rows), "white")
    for i, im in enumerate(resized):
        r, c = divmod(i, cols)
        grid.paste(im, (c * cell_w, r * cell_h))
    grid.save(out_path, "JPEG", quality=80)
    return out_path


def critique_deck_visual(
    slide_paths: list[Path],
    *,
    out_dir: "Path | None" = None,
    model: str = VISION_MODEL,
) -> dict:
    """Build thumbnail grid and ask vision LLM about deck-wide consistency."""
    if out_dir is None:
        out_dir = slide_paths[0].parent
    grid = make_thumbnail_grid(slide_paths, out_dir / "deck_grid.jpg")
    if grid is None:
        return {"verdict": "SKIP", "issues": [], "reason": "tools or Pillow unavailable"}
    prompt = (PROMPTS_DIR / "deck_visual_critique.txt").read_text(encoding="utf-8")
    response = chat_with_image(prompt, str(grid), model=model)
    parsed = parse_json_block(response)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object for deck visual critique")
    parsed.setdefault("issues", [])
    parsed.setdefault("verdict", "PASS")
    return parsed
