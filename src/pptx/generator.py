"""JSON 기반 PPTX 생성기."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN


# ── 상수 ────────────────────────────────────────────────────────────────────
SLIDE_WIDTH = Inches(13.33)
SLIDE_HEIGHT = Inches(7.5)

ALIGN_MAP = {
    "left": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
}


# ── 헬퍼 ────────────────────────────────────────────────────────────────────
def _hex_to_rgb(hex_color: str) -> RGBColor:
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return RGBColor(r, g, b)


def _apply_text_style(run, style: dict[str, Any]) -> None:
    if "bold" in style:
        run.font.bold = style["bold"]
    if "italic" in style:
        run.font.italic = style["italic"]
    if "font_size" in style:
        run.font.size = Pt(style["font_size"])
    if "color" in style:
        run.font.color.rgb = _hex_to_rgb(style["color"])


def _add_textbox(slide, box: dict[str, Any]) -> None:
    left = Inches(box["left"])
    top = Inches(box["top"])
    width = Inches(box["width"])
    height = Inches(box["height"])

    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True

    lines: list[dict] = box.get("lines", [])
    for i, line in enumerate(lines):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        align = line.get("align", "left")
        para.alignment = ALIGN_MAP.get(align, PP_ALIGN.LEFT)

        run = para.add_run()
        run.text = line.get("text", "")
        _apply_text_style(run, line)


def _add_background(slide, bg: dict[str, Any], prs: Presentation) -> None:
    """단색 배경을 슬라이드 전체에 채운다."""
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = _hex_to_rgb(bg["color"])


# ── 메인 ────────────────────────────────────────────────────────────────────
def build_from_json(data: dict | str | Path, output_path: str | Path) -> Path:
    """
    JSON 데이터를 받아 PPTX 파일을 생성한다.

    Parameters
    ----------
    data : dict | str | Path
        프레젠테이션 JSON (딕셔너리 또는 파일 경로)
    output_path : str | Path
        저장할 .pptx 경로

    Returns
    -------
    Path
        생성된 파일의 절대 경로
    """
    if isinstance(data, (str, Path)):
        data = json.loads(Path(data).read_text(encoding="utf-8"))

    prs = Presentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT

    blank_layout = prs.slide_layouts[6]  # 완전 빈 레이아웃

    for slide_data in data.get("slides", []):
        slide = prs.slides.add_slide(blank_layout)

        if bg := slide_data.get("background"):
            _add_background(slide, bg, prs)

        for box in slide_data.get("textboxes", []):
            _add_textbox(slide, box)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(output_path)
    return output_path.resolve()
