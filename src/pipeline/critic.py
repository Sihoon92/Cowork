"""Stage 6 — deck-level critique (storyline + visual consistency).

Per-slide critique was retired with the recipe migration: pydantic schema
validation in the planner now catches the structural defects the old per-slide
critic was reactively patching. Deck-level checks remain because they need
cross-slide context the planner doesn't have.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from src.llm.client import chat, chat_with_image, DEFAULT_MODEL, VISION_MODEL
from src.pipeline.planner import parse_json_block
from src.util import log

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


# ---------------------------------------------------------------------------
# Storyline critique — operates on text only (head_messages)
# ---------------------------------------------------------------------------

def critique_deck_storyline(plan: dict, *, model: str = DEFAULT_MODEL) -> dict:
    """Feed head_messages of all slides to LLM. Return {issues, verdict}."""
    log.step("LLM call: deck storyline critique")
    head_lines = "\n".join(
        f"{s['slide_no']}. {s['head_message']}"
        for s in plan.get("slides", [])
    )
    template = (PROMPTS_DIR / "deck_storyline_critique.md").read_text(encoding="utf-8")
    prompt = template.format(head_messages=head_lines)
    response = chat(prompt, model=model)
    parsed = parse_json_block(response)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object for storyline critique")
    parsed.setdefault("issues", [])
    parsed.setdefault("verdict", "PASS")
    log.info(f"storyline verdict={parsed['verdict']} issues={len(parsed['issues'])}")
    return parsed


# ---------------------------------------------------------------------------
# Visual critique — needs LibreOffice/soffice to convert pptx → png
# ---------------------------------------------------------------------------

def _conversion_tools_available() -> bool:
    """LibreOffice (soffice) is required to convert pptx → png for the grid."""
    return shutil.which("soffice") is not None or shutil.which("libreoffice") is not None


def _pptx_to_image(pptx_path: Path, out_dir: Path) -> "Path | None":
    """Convert one .pptx to a .png in out_dir; returns the image path or None."""
    bin_name = shutil.which("soffice") or shutil.which("libreoffice")
    if bin_name is None:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [bin_name, "--headless", "--convert-to", "png",
             "--outdir", str(out_dir), str(pptx_path)],
            check=True, capture_output=True, timeout=60,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    candidate = out_dir / f"{pptx_path.stem}.png"
    return candidate if candidate.exists() else None


def make_thumbnail_grid(
    slide_paths: list[Path], out_path: Path, *, cols: int = 2,
) -> "Path | None":
    """Combine per-slide pptx images into a grid JPEG.

    Returns None if conversion tools or Pillow are unavailable.
    """
    if not _conversion_tools_available():
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
        img = _pptx_to_image(sp, img_dir)
        if img is not None:
            images.append(img)
    if not images:
        return None

    pil_imgs = [Image.open(p) for p in images]
    target_w = pil_imgs[0].width // 2
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
    prompt = (PROMPTS_DIR / "deck_visual_critique.md").read_text(encoding="utf-8")
    response = chat_with_image(prompt, str(grid), model=model)
    parsed = parse_json_block(response)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object for deck visual critique")
    parsed.setdefault("issues", [])
    parsed.setdefault("verdict", "PASS")
    return parsed
