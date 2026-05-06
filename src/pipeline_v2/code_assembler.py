"""Assemble final slide module: preamble + LLM body + footer.

Footer adds the first slide, applies _patch_shapes, calls build_slide,
and saves to a fixed output path.
"""
from __future__ import annotations

from pathlib import Path

PREAMBLE_PATH = Path(__file__).resolve().parents[2] / "guidelines" / "v2" / "preamble.py"


_FOOTER_TEMPLATE = """

# --- v2 footer (auto-appended) ---
_OUT_PATH = r\"{out_path}\"

if __name__ == "__main__":
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _patch_shapes(slide)
    build_slide(prs)
    prs.save(_OUT_PATH)
"""


def assemble_slide_module(body: str, out_pptx: Path) -> str:
    """Compose ``preamble.py`` + LLM body + footer into a runnable module."""
    preamble = PREAMBLE_PATH.read_text(encoding="utf-8")
    footer = _FOOTER_TEMPLATE.format(out_path=str(out_pptx))
    return f"{preamble}\n\n# --- LLM body ---\n{body}\n{footer}\n"
