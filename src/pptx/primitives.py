"""Layer 1 — Dumb executor primitives over python-pptx."""
from __future__ import annotations

from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from lxml import etree

_ALIGN = {
    "left": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
}


def _hex_to_rgb(hex_color: str) -> RGBColor:
    h = hex_color.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def set_bg(slide, color: str) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = _hex_to_rgb(color)


def add_text(
    slide,
    x: float, y: float, w: float, h: float,
    text: str,
    *,
    font_size: float = 14,
    bold: bool = False,
    italic: bool = False,
    color: str = "#000000",
    align: str = "left",
    font: str = "Pretendard",
    line_spacing: float = 1.2,
) -> None:
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    para = tf.paragraphs[0]
    para.alignment = _ALIGN.get(align, PP_ALIGN.LEFT)
    para.line_spacing = line_spacing
    run = para.add_run()
    run.text = text
    run.font.name = font
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = _hex_to_rgb(color)


def add_rect(
    slide,
    x: float, y: float, w: float, h: float,
    *,
    fill: str = "#FFFFFF",
    border_color: str | None = None,
    border_width: float = 0.0,
    rounded: bool = False,
) -> None:
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _hex_to_rgb(fill)
    if border_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = _hex_to_rgb(border_color)
        shape.line.width = Pt(border_width)
    # Strip default text frame contents to keep shape clean
    if shape.has_text_frame:
        shape.text_frame.text = ""


def add_line(
    slide,
    x1: float, y1: float, x2: float, y2: float,
    *,
    color: str = "#000000",
    width: float = 1.5,
) -> None:
    conn = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT,
        Inches(x1), Inches(y1), Inches(x2), Inches(y2),
    )
    conn.line.color.rgb = _hex_to_rgb(color)
    conn.line.width = Pt(width)


def add_arrow(
    slide,
    x1: float, y1: float, x2: float, y2: float,
    *,
    color: str = "#000000",
    width: float = 2.0,
) -> None:
    conn = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT,
        Inches(x1), Inches(y1), Inches(x2), Inches(y2),
    )
    conn.line.color.rgb = _hex_to_rgb(color)
    conn.line.width = Pt(width)
    ln = conn.line._get_or_add_ln()
    tail = etree.SubElement(
        ln,
        "{http://schemas.openxmlformats.org/drawingml/2006/main}tailEnd",
    )
    tail.set("type", "triangle")
    tail.set("w", "med")
    tail.set("len", "med")


def add_image(
    slide,
    x: float, y: float, w: float, h: float,
    image_path: str,
) -> None:
    slide.shapes.add_picture(image_path, Inches(x), Inches(y), Inches(w), Inches(h))
