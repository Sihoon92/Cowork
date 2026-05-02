"""Stage 5-B — per-slide visual critique via vision LLM."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from src.llm.ollama_client import chat_with_image, VISION_MODEL
from src.pipeline.planner import parse_json_block
from src.util import log

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def conversion_tools_available() -> bool:
    """True iff both `soffice` and `pdftoppm` are on PATH."""
    return bool(shutil.which("soffice")) and bool(shutil.which("pdftoppm"))


def pptx_to_image(pptx_path: str | Path, out_dir: str | Path) -> Path | None:
    """Convert a single-slide pptx to a JPEG. Return Path or None if tools unavailable."""
    if not conversion_tools_available():
        print("[visual_critic] soffice/pdftoppm not found — skipping visual critique",
              file=sys.stderr)
        return None

    pptx_path = Path(pptx_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: pptx -> pdf (libreoffice writes to current dir or --outdir)
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf",
         "--outdir", str(out_dir), str(pptx_path)],
        check=True, capture_output=True, timeout=60,
    )
    pdf_path = out_dir / (pptx_path.stem + ".pdf")
    if not pdf_path.exists():
        return None

    # Step 2: pdf -> jpeg
    out_prefix = out_dir / pptx_path.stem
    subprocess.run(
        ["pdftoppm", "-jpeg", "-r", "150", str(pdf_path), str(out_prefix)],
        check=True, capture_output=True, timeout=30,
    )
    # pdftoppm names output `prefix-1.jpg`, `prefix-2.jpg`, ...
    candidates = sorted(out_dir.glob(pptx_path.stem + "-*.jpg"))
    return candidates[0] if candidates else None


def critique_slide_visual(
    slide_pptx_path: str | Path,
    *,
    out_dir: str | Path | None = None,
    model: str = VISION_MODEL,
) -> dict:
    """Convert slide to image and ask vision LLM for defects.

    Returns {"verdict": "PASS"|"FIX"|"SKIP", "issues": [...], "reason"?: str}
    """
    slide_pptx_path = Path(slide_pptx_path)
    if out_dir is None:
        out_dir = slide_pptx_path.parent / "img"
    image_path = pptx_to_image(slide_pptx_path, out_dir)
    if image_path is None:
        log.warn("visual SKIP -- soffice/pdftoppm missing, skipping visual critique")
        return {"verdict": "SKIP", "issues": [], "reason": "image conversion unavailable"}

    log.step("LLM call: visual critique")
    prompt = (PROMPTS_DIR / "visual_critique.txt").read_text(encoding="utf-8")
    response = chat_with_image(prompt, str(image_path), model=model)
    parsed = parse_json_block(response)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object for visual critique")
    parsed.setdefault("issues", [])
    parsed.setdefault("verdict", "PASS")
    log.info(f"visual verdict={parsed['verdict']} issues={len(parsed['issues'])}")
    return parsed
