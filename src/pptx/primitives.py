"""Layer 1 — primitives + relative-positioning toolkit.

Three positioning tools are exposed:

- ``Rect`` is a coordinate container. ``apply_master`` returns one (the body
  zone). Slicing it via ``rect.col(...)`` / ``rect.row(...)`` produces
  sub-Rects (Grid).
- ``Stack`` lays out N items in a row or column with constant gap.
- Every placed shape becomes an ``Anchor`` (or wraps a ``Rect``) and exposes
  9 anchor points (TL/TC/TR/ML/MC/MR/BL/BC/BR) so subsequent calls can
  position relative to it.

LLM-facing helpers (apply_master, add_card, add_metric, add_pill, add_quote,
add_step_box, place, Stack) avoid raw (x, y) math.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Tuple, Union

from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from lxml import etree

# ---------------------------------------------------------------------------
# Slide geometry constants (mirrors guidelines/layout_grid.md)
# ---------------------------------------------------------------------------

SLIDE_W = 13.333
SLIDE_H = 7.5
MARGIN = 0.6
HEADER_Y = 0.4
HEADER_H = 1.1            # 0.4 → 1.5
BODY_Y = 1.6
BODY_H = 5.1              # 1.6 → 6.7
FOOTER_Y = 6.8
FOOTER_H = 0.4            # 6.8 → 7.2
GUTTER = 0.2              # gap between Grid columns
COLS = 12

_ALIGN = {
    "left": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
}


def _hex_to_rgb(hex_color: str) -> RGBColor:
    h = hex_color.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _warn_unknown(fn_name: str, extra: dict) -> None:
    """Emit a stderr warning for unrecognised kwargs without crashing."""
    if not extra:
        return
    import sys
    keys = ", ".join(sorted(extra.keys()))
    print(f"[primitives] {fn_name}: ignoring unknown kwargs: {keys}", file=sys.stderr)


def _theme(deck_meta: dict, key: str, default: str = "#000000") -> str:
    """Resolve a theme color by role, with sensible fallbacks for old schemas."""
    theme = deck_meta.get("theme", {})
    if key in theme:
        return theme[key]
    legacy_map = {
        "background": "neutral",
        "head_text": "text_dark",
        "head_rule": "primary",
        "body_text": "text_dark",
        "bullet": "primary",
        "accent": "accent",
    }
    legacy_key = legacy_map.get(key)
    if legacy_key and legacy_key in theme:
        return theme[legacy_key]
    return default


# ---------------------------------------------------------------------------
# Rect — coordinate container, supports Grid slicing
# ---------------------------------------------------------------------------

AnchorName = Literal[
    "TL", "TC", "TR",
    "ML", "MC", "MR",
    "BL", "BC", "BR",
]


@dataclass(frozen=True)
class Rect:
    """Immutable rectangle in inches. The Grid root is body-relative."""
    x: float
    y: float
    w: float
    h: float

    # Convenience -----------------------------------------------------------

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    # python-pptx-style aliases (commonly attempted by LLM)
    @property
    def left(self) -> float:
        return self.x

    @property
    def top(self) -> float:
        return self.y

    @property
    def width(self) -> float:
        return self.w

    @property
    def height(self) -> float:
        return self.h

    def anchor_point(self, name: AnchorName) -> Tuple[float, float]:
        v, h = name[0], name[1]
        ax = {"L": self.x, "C": self.cx, "R": self.right}[h]
        ay = {"T": self.y, "M": self.cy, "B": self.bottom}[v]
        return ax, ay

    def inset(self, padding: float) -> "Rect":
        return Rect(
            self.x + padding,
            self.y + padding,
            max(0.0, self.w - 2 * padding),
            max(0.0, self.h - 2 * padding),
        )

    # Grid slicing ----------------------------------------------------------

    def col(self, start: int, *, span: int = 1) -> "Rect":
        """Return a sub-Rect spanning `span` columns starting at `start` (1-based)."""
        if not (1 <= start <= COLS) or span < 1 or start + span - 1 > COLS:
            raise ValueError(f"col(start={start}, span={span}) out of 1..{COLS}")
        col_w = (self.w - GUTTER * (COLS - 1)) / COLS
        x0 = self.x + (start - 1) * (col_w + GUTTER)
        w = col_w * span + GUTTER * (span - 1)
        return Rect(x0, self.y, w, self.h)

    def row(self, start: int, *, span: int = 1, total: int = 2) -> "Rect":
        """Slice vertically into `total` equal rows; pick rows [start, start+span)."""
        if not (1 <= start <= total) or span < 1 or start + span - 1 > total:
            raise ValueError(f"row(start={start}, span={span}, total={total}) invalid")
        row_h = (self.h - GUTTER * (total - 1)) / total
        y0 = self.y + (start - 1) * (row_h + GUTTER)
        h = row_h * span + GUTTER * (span - 1)
        return Rect(self.x, y0, self.w, h)


# ---------------------------------------------------------------------------
# Grid — explicit row/col splits with span support. Used by recipe compilers.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Grid:
    """A rectangular grid carved from a container Rect.

    `row_heights` and `col_widths` are interpreted as RELATIVE WEIGHTS — they
    are normalized to sum to (container.h - row gutters) and (container.w -
    col gutters) respectively. So `row_heights=[1, 2]` makes row 1 take 1/3
    of the available height and row 2 take 2/3.

    `cell(r, c, rspan=1, cspan=1)` returns the Rect spanning from (r, c) to
    (r+rspan-1, c+cspan-1), inclusive of intermediate gutters. Indices are
    0-based to match Python list conventions.
    """
    container: "Rect"
    row_heights: tuple
    col_widths: tuple
    gutter: float = 0.1

    @property
    def n_rows(self) -> int:
        return len(self.row_heights)

    @property
    def n_cols(self) -> int:
        return len(self.col_widths)

    def _row_extents(self) -> list:
        avail = self.container.h - self.gutter * max(0, self.n_rows - 1)
        if avail < 0:
            avail = 0.0
        total = sum(self.row_heights) or 1.0
        extents: list = []
        cursor = self.container.y
        for i, w in enumerate(self.row_heights):
            h = avail * (w / total)
            extents.append((cursor, h))
            cursor += h + self.gutter
        return extents

    def _col_extents(self) -> list:
        avail = self.container.w - self.gutter * max(0, self.n_cols - 1)
        if avail < 0:
            avail = 0.0
        total = sum(self.col_widths) or 1.0
        extents: list = []
        cursor = self.container.x
        for i, w in enumerate(self.col_widths):
            cw = avail * (w / total)
            extents.append((cursor, cw))
            cursor += cw + self.gutter
        return extents

    def cell(self, r: int, c: int, *, rspan: int = 1, cspan: int = 1) -> "Rect":
        if not (0 <= r < self.n_rows) or not (0 <= c < self.n_cols):
            raise ValueError(
                f"cell({r},{c}) out of grid {self.n_rows}x{self.n_cols}"
            )
        if rspan < 1 or cspan < 1:
            raise ValueError(f"span must be >=1, got rspan={rspan} cspan={cspan}")
        if r + rspan > self.n_rows or c + cspan > self.n_cols:
            raise ValueError(
                f"cell({r},{c}, rspan={rspan}, cspan={cspan}) overflows grid "
                f"{self.n_rows}x{self.n_cols}"
            )
        rows = self._row_extents()
        cols = self._col_extents()
        y0, _ = rows[r]
        y1_origin, y1_h = rows[r + rspan - 1]
        x0, _ = cols[c]
        x1_origin, x1_w = cols[c + cspan - 1]
        h = (y1_origin + y1_h) - y0
        w = (x1_origin + x1_w) - x0
        return Rect(x0, y0, w, h)


# ---------------------------------------------------------------------------
# AnchorRef — wraps a placed shape so it exposes 9 anchor points
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AnchorRef:
    """A placed shape's anchor surface. Carries its bounding Rect."""
    rect: Rect
    shape: object = None  # underlying pptx shape (optional)

    def anchor_point(self, name: AnchorName) -> Tuple[float, float]:
        return self.rect.anchor_point(name)


AnchorTarget = Union[Rect, AnchorRef]


def _rect_of(target: AnchorTarget) -> Rect:
    return target.rect if isinstance(target, AnchorRef) else target


def _resolve_relative(
    *,
    relative_to: AnchorTarget,
    their_anchor: AnchorName,
    my_anchor: AnchorName,
    gap: Tuple[float, float],
    w: float,
    h: float,
) -> Rect:
    """Compute the Rect for a new shape attached to an existing anchor."""
    px, py = _rect_of(relative_to).anchor_point(their_anchor)
    px += gap[0]
    py += gap[1]
    # offset within the new shape so my_anchor lands on (px, py)
    v, hp = my_anchor[0], my_anchor[1]
    ox = {"L": 0.0, "C": w / 2, "R": w}[hp]
    oy = {"T": 0.0, "M": h / 2, "B": h}[v]
    return Rect(px - ox, py - oy, w, h)


def _resolve_anchor_in_rect(
    container: Rect, anchor: AnchorName, w: float, h: float,
) -> Rect:
    """Place a w×h rect inside a container at one of its 9 anchor points."""
    cx, cy = container.anchor_point(anchor)
    v, hp = anchor[0], anchor[1]
    ox = {"L": 0.0, "C": w / 2, "R": w}[hp]
    oy = {"T": 0.0, "M": h / 2, "B": h}[v]
    return Rect(cx - ox, cy - oy, w, h)


# ---------------------------------------------------------------------------
# Low-level primitives (now return AnchorRef)
# ---------------------------------------------------------------------------

def set_bg(slide, color: str, **_extra) -> None:
    if _extra:
        _warn_unknown("set_bg", _extra)
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = _hex_to_rgb(color)


def add_text(
    slide,
    *args,
    text: str = None,
    font_size: float = 14,
    bold: bool = False,
    italic: bool = False,
    color: str = "#1C2833",
    align: str = "left",
    valign: str = "top",  # "top" | "middle" | "bottom"
    font: str = "Pretendard",
    line_spacing: float = 1.3,
    rect=None,
    relative_to: AnchorTarget = None,
    their_anchor: AnchorName = "BC",
    my_anchor: AnchorName = "TC",
    gap: Tuple[float, float] = (0.0, 0.2),
    w: float = None,
    h: float = None,
    **_extra,
) -> AnchorRef:
    """Add a text box. Three call styles supported:

    - Legacy positional:  add_text(slide, x, y, w, h, text, ...)
    - Rect-based:         add_text(slide, text="...", rect=some_rect, ...)
    - Anchor-relative:    add_text(slide, text="...", relative_to=other,
                                   their_anchor="BC", my_anchor="TC", w=4, h=0.6)
    """
    if _extra:
        _warn_unknown("add_text", _extra)
    rect = _coerce_rect("add_text", args, rect, relative_to,
                        their_anchor, my_anchor, gap, w, h)
    if text is None:
        # legacy positional: text often appears at index 4 of args after numeric (x,y,w,h)
        nums_seen = 0
        text = ""
        for a in args:
            if isinstance(a, (int, float)):
                nums_seen += 1
                continue
            if nums_seen >= 4 and isinstance(a, str):
                text = a
                break
        if not text and len(args) >= 5 and isinstance(args[4], str):
            text = args[4]

    box = slide.shapes.add_textbox(
        Inches(rect.x), Inches(rect.y), Inches(rect.w), Inches(rect.h),
    )
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.05)
    tf.margin_right = Inches(0.05)
    tf.margin_top = Inches(0.02)
    tf.margin_bottom = Inches(0.02)
    # Vertical anchoring: top (default) / middle / bottom
    try:
        if valign == "middle":
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        elif valign == "bottom":
            tf.vertical_anchor = MSO_ANCHOR.BOTTOM
    except (AttributeError, ValueError):
        pass
    # Let PowerPoint shrink the font when content overflows the box. This
    # rescues Korean wrap cases where character width pushes text past the
    # zone, even after our per-block character truncation.
    try:
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    except (AttributeError, ValueError):
        pass
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
    return AnchorRef(rect=rect, shape=box)


def add_rect(
    slide,
    *args,
    fill: str | None = "#FFFFFF",
    border_color: str | None = None,
    border_width: float = 0.0,
    rounded: bool = False,
    shadow: bool = False,
    rect=None,
    relative_to: AnchorTarget = None,
    their_anchor: AnchorName = "BC",
    my_anchor: AnchorName = "TC",
    gap: Tuple[float, float] = (0.0, 0.0),
    w: float = None,
    h: float = None,
    **_extra,
) -> AnchorRef:
    """Add a rectangle. Same call styles as add_text."""
    if _extra:
        _warn_unknown("add_rect", _extra)
    rect = _coerce_rect("add_rect", args, rect, relative_to,
                        their_anchor, my_anchor, gap, w, h)
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(
        shape_type, Inches(rect.x), Inches(rect.y), Inches(rect.w), Inches(rect.h),
    )
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = _hex_to_rgb(fill)
    if border_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = _hex_to_rgb(border_color)
        shape.line.width = Pt(max(0.5, border_width))
    if not shadow:
        _disable_shadow(shape)
    if shape.has_text_frame:
        shape.text_frame.text = ""
    return AnchorRef(rect=rect, shape=shape)


def _resolve_endpoint(end) -> Tuple[float, float]:
    """Resolve a from_/to_ endpoint into (x, y).

    Accepts:
    - (Rect|AnchorRef, "anchor_name")
    - (x, y) raw coordinate pair
    - Rect|AnchorRef alone — defaults to MC anchor
    """
    if isinstance(end, (Rect, AnchorRef)):
        return _rect_of(end).anchor_point("MC")
    if isinstance(end, tuple) and len(end) == 2:
        a, b = end
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return float(a), float(b)
        if isinstance(a, (Rect, AnchorRef)) and isinstance(b, str):
            return _rect_of(a).anchor_point(b)
    raise TypeError(f"unrecognised endpoint: {end!r}")


def add_line(
    slide,
    *args,
    color: str = "#1C2833",
    width: float = 1.0,
    from_=None,
    to_=None,
    **_extra,
) -> AnchorRef:
    """Straight line. Either (x1, y1, x2, y2) positional or from_/to_ anchors."""
    if _extra:
        _warn_unknown("add_line", _extra)
    if from_ is not None and to_ is not None:
        x1, y1 = _resolve_endpoint(from_)
        x2, y2 = _resolve_endpoint(to_)
    elif len(args) >= 4:
        x1, y1, x2, y2 = args[:4]
    else:
        raise TypeError("add_line requires either (x1,y1,x2,y2) or from_/to_")
    conn = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2),
    )
    conn.line.color.rgb = _hex_to_rgb(color)
    conn.line.width = Pt(width)
    rect = Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
    return AnchorRef(rect=rect, shape=conn)


def add_arrow(
    slide,
    *args,
    color: str = "#1C2833",
    width: float = 2.0,
    from_=None,
    to_=None,
    **_extra,
) -> AnchorRef:
    """Straight arrow. Either positional (x1,y1,x2,y2) or from_/to_ anchors."""
    if _extra:
        _warn_unknown("add_arrow", _extra)
    if from_ is not None and to_ is not None:
        x1, y1 = _resolve_endpoint(from_)
        x2, y2 = _resolve_endpoint(to_)
    elif len(args) >= 4:
        x1, y1, x2, y2 = args[:4]
    else:
        raise TypeError("add_arrow requires either (x1,y1,x2,y2) or from_/to_")
    conn = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2),
    )
    conn.line.color.rgb = _hex_to_rgb(color)
    conn.line.width = Pt(width)
    ln = conn.line._get_or_add_ln()
    tail = etree.SubElement(
        ln, "{http://schemas.openxmlformats.org/drawingml/2006/main}tailEnd",
    )
    tail.set("type", "triangle")
    tail.set("w", "med")
    tail.set("len", "med")
    rect = Rect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
    return AnchorRef(rect=rect, shape=conn)


def add_image(slide, *args, image_path: str = None,
              rect=None, w: float = None, h: float = None, **_extra) -> AnchorRef:
    if _extra:
        _warn_unknown("add_image", _extra)
    if rect is None:
        if len(args) >= 5:
            x, y, w_, h_, image_path = args[:5]
            rect = Rect(x, y, w_, h_)
        else:
            raise TypeError("add_image requires rect or (x,y,w,h,image_path)")
    if isinstance(rect, tuple):
        rect = Rect(*rect)
    pic = slide.shapes.add_picture(
        image_path, Inches(rect.x), Inches(rect.y),
        Inches(rect.w), Inches(rect.h),
    )
    return AnchorRef(rect=rect, shape=pic)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _coerce_rect(
    fn_name: str,
    args: tuple,
    rect,
    relative_to: AnchorTarget | None,
    their_anchor: AnchorName,
    my_anchor: AnchorName,
    gap: Tuple[float, float],
    w: float | None,
    h: float | None,
) -> Rect:
    """Resolve the Rect from any of the supported call styles.

    Accepts tolerant inputs:
    - Rect / AnchorRef (uses .rect)
    - 4-tuple (x, y, w, h)
    - dict with x/y/w/h or left/top/width/height
    """
    if rect is not None:
        if isinstance(rect, Rect):
            return rect
        if isinstance(rect, AnchorRef):
            return rect.rect
        if isinstance(rect, tuple) and len(rect) == 4:
            return Rect(*rect)
        if isinstance(rect, dict):
            if {"x", "y", "w", "h"} <= rect.keys():
                return Rect(rect["x"], rect["y"], rect["w"], rect["h"])
            if {"left", "top", "width", "height"} <= rect.keys():
                return Rect(rect["left"], rect["top"], rect["width"], rect["height"])
        raise TypeError(f"{fn_name}: rect must be Rect, AnchorRef, 4-tuple, or dict")
    if relative_to is not None:
        if w is None or h is None:
            raise TypeError(f"{fn_name}: relative_to requires w and h")
        return _resolve_relative(
            relative_to=relative_to, their_anchor=their_anchor,
            my_anchor=my_anchor, gap=gap, w=w, h=h,
        )
    # Legacy positional: try (slide, x, y, w, h, [text]) — args excludes slide already
    # but LLM sometimes passes (slide, deck_meta, x, y, w, h). Skip non-numeric leading args.
    nums = [a for a in args if isinstance(a, (int, float))]
    if len(nums) >= 4:
        return Rect(nums[0], nums[1], nums[2], nums[3])
    raise TypeError(f"{fn_name}: provide either rect, relative_to+w+h, or (x,y,w,h)")


def _disable_shadow(shape) -> None:
    """Remove the default theme shadow from a shape."""
    sp_pr = shape.fill._xPr  # spPr element
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    effect_lst = sp_pr.find(f"{{{ns_a}}}effectLst")
    if effect_lst is None:
        etree.SubElement(sp_pr, f"{{{ns_a}}}effectLst")


def _enable_soft_shadow(shape, *, blur_pt: int = 8, alpha_pct: int = 20) -> None:
    sp_pr = shape.fill._xPr
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    # Remove existing effectLst
    for child in sp_pr.findall(f"{{{ns_a}}}effectLst"):
        sp_pr.remove(child)
    effect_lst = etree.SubElement(sp_pr, f"{{{ns_a}}}effectLst")
    outer = etree.SubElement(effect_lst, f"{{{ns_a}}}outerShdw")
    outer.set("blurRad", str(int(blur_pt * 12700)))   # EMU per pt = 12700
    outer.set("dist", "0")
    outer.set("dir", "5400000")
    outer.set("rotWithShape", "0")
    color = etree.SubElement(outer, f"{{{ns_a}}}srgbClr")
    color.set("val", "000000")
    alpha = etree.SubElement(color, f"{{{ns_a}}}alpha")
    alpha.set("val", str(int(alpha_pct * 1000)))


# ---------------------------------------------------------------------------
# apply_master — paints header (title + blue rule) + footer, returns body Rect
# ---------------------------------------------------------------------------

def apply_master(
    slide,
    deck_meta: dict,
    *,
    head_message: str,
    section_title: str | None = None,
    sub_message: str | None = None,
    page_no: int | None = None,
    section_id: str | None = None,
) -> Rect:
    """Paint deck-wide header/footer. Return the Body Rect for content.

    Three-tier header (top → bottom):
      Tier 1  section_title  28pt bold   (deck-level — section.topic)
      ----    1.5pt accent rule
      Tier 2  ■ head_message 18pt bold   (slide-level — LLM)
      Tier 3  - sub_message  16pt        (slide-level optional — LLM)

    When section_title is empty/None, Tier 1 is skipped and head_message stays
    where it is (no promotion). This keeps the deck tone consistent for slides
    without a section assignment.
    """
    bg = _theme(deck_meta, "background", "#FFFFFF")
    head_text_color = _theme(deck_meta, "head_text", "#1C2833")
    rule_color = _theme(deck_meta, "head_rule", "#065A82")
    body_text_color = _theme(deck_meta, "body_text", "#1C2833")
    bullet_color = _theme(deck_meta, "bullet", "#065A82")
    fonts = deck_meta.get("fonts", {})
    head_font = fonts.get("header", "Pretendard")
    body_font = fonts.get("body", "Pretendard")

    set_bg(slide, bg)

    title_w = SLIDE_W - 2 * MARGIN
    cursor_y = HEADER_Y  # 0.4

    # Tier 1 — section title (28pt bold)
    if section_title:
        add_text(
            slide,
            rect=Rect(MARGIN, cursor_y, title_w, 0.55),
            text=section_title,
            font_size=28, bold=True, color=head_text_color,
            align="left", font=head_font, line_spacing=1.1,
        )
        cursor_y += 0.6

    # 1.5pt accent rule
    rule_y = cursor_y + 0.05
    add_line(
        slide,
        MARGIN, rule_y, MARGIN + title_w, rule_y,
        color=rule_color, width=1.5,
    )
    cursor_y = rule_y + 0.1

    # Tier 2 — head_message (18pt bold). ■ glyph is accent-colored, the
    # message text itself is the dark head_text color so the message reads
    # as the slide's headline (not as a colored decorative line).
    if head_message:
        box = slide.shapes.add_textbox(
            Inches(MARGIN), Inches(cursor_y), Inches(title_w), Inches(0.42),
        )
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.0)
        tf.margin_right = Inches(0.0)
        tf.margin_top = Inches(0.02)
        tf.margin_bottom = Inches(0.02)
        try:
            tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        except (AttributeError, ValueError):
            pass
        para = tf.paragraphs[0]
        para.alignment = PP_ALIGN.LEFT
        para.line_spacing = 1.2

        bullet_run = para.add_run()
        bullet_run.text = "■ "
        bullet_run.font.name = head_font
        bullet_run.font.size = Pt(18)
        bullet_run.font.bold = True
        bullet_run.font.color.rgb = _hex_to_rgb(bullet_color)

        text_run = para.add_run()
        text_run.text = head_message
        text_run.font.name = head_font
        text_run.font.size = Pt(18)
        text_run.font.bold = True
        text_run.font.color.rgb = _hex_to_rgb(head_text_color)
        cursor_y += 0.5

    # Tier 3 — sub_message (16pt -)
    if sub_message:
        add_text(
            slide,
            rect=Rect(MARGIN, cursor_y, title_w, 0.4),
            text=f"- {sub_message}",
            font_size=16, color=body_text_color,
            align="left", font=body_font, line_spacing=1.25,
        )
        cursor_y += 0.45

    # Footer (page number only — section_id is intentionally NOT shown;
    # section identity is communicated via the 28pt section_title at the top)
    if page_no is not None:
        add_text(
            slide,
            rect=Rect(SLIDE_W - MARGIN - 1.0, FOOTER_Y, 1.0, FOOTER_H),
            text=str(page_no),
            font_size=10, color=body_text_color, font=body_font, align="right",
        )

    body_top = cursor_y + 0.15
    body_h = FOOTER_Y - body_top - 0.15
    return Rect(MARGIN, body_top, SLIDE_W - 2 * MARGIN, body_h)


# ---------------------------------------------------------------------------
# Stack — 1D auto-layout
# ---------------------------------------------------------------------------

class Stack:
    """Auto-layout helper. Place items along one axis with constant gap."""

    def __init__(
        self,
        container: Rect,
        *,
        direction: Literal["vertical", "horizontal"] = "vertical",
        gap: float = 0.3,
        align: Literal["start", "center", "end"] = "start",
        wrap: bool = False,
    ):
        self.container = container
        self.direction = direction
        self.gap = gap
        self.align = align
        self.wrap = wrap
        self._cursor = 0.0
        self._row_max = 0.0  # for horizontal wrap
        self._row_origin = 0.0  # for horizontal wrap

    # Layout maths ----------------------------------------------------------

    def _next_rect(self, w: float, h: float) -> Rect:
        c = self.container
        if self.direction == "vertical":
            x = c.x
            if self.align == "center":
                x = c.x + (c.w - w) / 2
            elif self.align == "end":
                x = c.right - w
            y = c.y + self._cursor
            self._cursor += h + self.gap
            return Rect(x, y, w, h)
        # horizontal
        if self.wrap and self._cursor + w > c.w:
            self._row_origin += self._row_max + self.gap
            self._cursor = 0.0
            self._row_max = 0.0
        x = c.x + self._cursor
        y = c.y + self._row_origin
        if self.align == "center":
            y = c.y + self._row_origin + max(0.0, (c.h - h) / 2)
        elif self.align == "end":
            y = c.bottom - h
        self._cursor += w + self.gap
        self._row_max = max(self._row_max, h)
        return Rect(x, y, w, h)

    # Items -----------------------------------------------------------------

    def add_text(self, slide, text: str, *, h: float = 0.5, **kwargs) -> AnchorRef:
        c = self.container
        w = kwargs.pop("w", c.w if self.direction == "vertical" else 4.0)
        rect = self._next_rect(w, h)
        return add_text(slide, rect=rect, text=text, **kwargs)

    def add_rect(self, slide, *, w: float, h: float, **kwargs) -> AnchorRef:
        rect = self._next_rect(w, h)
        return add_rect(slide, rect=rect, **kwargs)

    def add_card(self, slide, deck_meta: dict, *, w: float | None = None, h: float = 1.2,
                 title: str | None = None, body: str | None = None, **kw) -> AnchorRef:
        c = self.container
        if w is None:
            w = c.w if self.direction == "vertical" else 3.5
        rect = self._next_rect(w, h)
        return add_card(slide, deck_meta, rect=rect, title=title, body=body, **kw)

    def add_metric(self, slide, deck_meta: dict, *, w: float = 3.0, h: float = 2.0,
                   value: str, label: str, **kw) -> AnchorRef:
        rect = self._next_rect(w, h)
        return add_metric(slide, deck_meta, rect=rect, value=value, label=label, **kw)

    def add_step_box(self, slide, deck_meta: dict, *, w: float = 2.5, h: float = 1.4,
                     number: int, title: str, body: str | None = None) -> AnchorRef:
        rect = self._next_rect(w, h)
        return add_step_box(slide, deck_meta, rect=rect,
                            number=number, title=title, body=body)


# ---------------------------------------------------------------------------
# place — anchor-based placement inside a Rect
# ---------------------------------------------------------------------------

def place(container, *, anchor: AnchorName, w: float, h: float, **_extra) -> Rect:
    """Return a Rect of size (w, h) anchored inside container.

    `container` may be a Rect, an AnchorRef, or a slide-like object — for the
    latter we fall back to the full canvas (13.333 x 7.5 in).
    """
    if _extra:
        _warn_unknown("place", _extra)
    if isinstance(container, Rect):
        return _resolve_anchor_in_rect(container, anchor, w, h)
    if isinstance(container, AnchorRef):
        return _resolve_anchor_in_rect(container.rect, anchor, w, h)
    # assume slide-like → full canvas
    canvas = Rect(0, 0, SLIDE_W, SLIDE_H)
    return _resolve_anchor_in_rect(canvas, anchor, w, h)


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

def add_card(
    slide, deck_meta: dict, *,
    rect=None,
    title: str | None = None,
    body: str | None = None,
    padding: float = 0.3,
    fill: str | None = None,
    border: str | None = "#E0E0E0",
    shadow: bool = True,
    relative_to: AnchorTarget = None,
    their_anchor: AnchorName = "BC",
    my_anchor: AnchorName = "TC",
    gap: Tuple[float, float] = (0.0, 0.2),
    w: float = None,
    h: float = None,
    **_extra,
) -> AnchorRef:
    """White card with optional title (■-bulleted, 18pt bold) and body (16pt)."""
    if _extra:
        _warn_unknown("add_card", _extra)
    rect = _coerce_rect("add_card", (), rect, relative_to,
                        their_anchor, my_anchor, gap, w, h)
    fill = fill or _theme(deck_meta, "background", "#FFFFFF")
    head_color = _theme(deck_meta, "head_text", "#1C2833")
    body_color = _theme(deck_meta, "body_text", "#1C2833")
    bullet_color = _theme(deck_meta, "bullet", "#065A82")

    card = add_rect(
        slide, rect=rect, fill=fill, border_color=border, border_width=0.75,
        rounded=True, shadow=False,
    )
    if shadow and card.shape is not None:
        try:
            _enable_soft_shadow(card.shape, blur_pt=8, alpha_pct=20)
        except Exception:
            pass

    inner = rect.inset(padding)
    cursor_y = inner.y
    if title:
        add_text(
            slide,
            rect=Rect(inner.x, cursor_y, inner.w, 0.42),
            text=f"■ {title}",
            font_size=18, bold=True, color=bullet_color,
            align="left", line_spacing=1.2,
        )
        cursor_y += 0.5
    if body:
        body_h = max(0.4, inner.bottom - cursor_y)
        add_text(
            slide,
            rect=Rect(inner.x, cursor_y, inner.w, body_h),
            text=body,
            font_size=16, color=body_color, align="left", line_spacing=1.35,
        )
    return card


def add_metric(
    slide, deck_meta: dict, *,
    rect,
    value: str,
    label: str,
    unit: str | None = None,
    trend: str | None = None,
    **_extra,
) -> AnchorRef:
    if _extra:
        _warn_unknown("add_metric", _extra)
    if isinstance(rect, tuple):
        rect = Rect(*rect)
    if isinstance(rect, AnchorRef):
        rect = rect.rect
    accent = _theme(deck_meta, "accent", "#21295C")
    body_color = _theme(deck_meta, "body_text", "#1C2833")
    card = add_card(slide, deck_meta, rect=rect, padding=0.3)

    inner = rect.inset(0.3)
    value_h = min(1.4, inner.h * 0.6)
    value_text = f"{value} {unit}" if unit else value
    add_text(
        slide,
        rect=Rect(inner.x, inner.y, inner.w, value_h),
        text=value_text,
        font_size=44, bold=True, color=accent, align="left", line_spacing=1.0,
    )
    add_text(
        slide,
        rect=Rect(inner.x, inner.y + value_h + 0.05, inner.w, 0.4),
        text=label,
        font_size=14, color=body_color, align="left", line_spacing=1.2,
    )
    if trend:
        # small pill at top-right
        pill_w, pill_h = 0.9, 0.35
        pill_rect = Rect(inner.right - pill_w, inner.y, pill_w, pill_h)
        add_pill(slide, deck_meta, rect=pill_rect, text=trend)
    return card


def add_pill(
    slide, deck_meta: dict, *,
    rect,
    text: str,
    fill: str | None = None,
    text_color: str | None = None,
    **_extra,
) -> AnchorRef:
    if _extra:
        _warn_unknown("add_pill", _extra)
    if isinstance(rect, tuple):
        rect = Rect(*rect)
    if isinstance(rect, AnchorRef):
        rect = rect.rect
    fill = fill or _theme(deck_meta, "accent", "#21295C")
    text_color = text_color or _theme(deck_meta, "background", "#FFFFFF")
    pill = add_rect(slide, rect=rect, fill=fill, rounded=True, border_color=None)
    add_text(
        slide, rect=rect, text=text,
        font_size=12, bold=True, color=text_color, align="center",
        line_spacing=1.0,
    )
    return pill


def add_quote(
    slide, deck_meta: dict, *,
    rect,
    text: str,
    attribution: str | None = None,
    **_extra,
) -> AnchorRef:
    if _extra:
        _warn_unknown("add_quote", _extra)
    if isinstance(rect, tuple):
        rect = Rect(*rect)
    if isinstance(rect, AnchorRef):
        rect = rect.rect
    accent = _theme(deck_meta, "accent", "#21295C")
    body_color = _theme(deck_meta, "body_text", "#1C2833")

    bar_w = 0.08
    add_rect(
        slide,
        rect=Rect(rect.x, rect.y, bar_w, rect.h),
        fill=accent, border_color=None,
    )
    body_x = rect.x + bar_w + 0.3
    body_w = rect.right - body_x
    body_h = rect.h - (0.5 if attribution else 0.0)
    quote_ref = add_text(
        slide,
        rect=Rect(body_x, rect.y, body_w, body_h),
        text=text,
        font_size=20, italic=True, color=body_color, align="left",
        line_spacing=1.4,
    )
    if attribution:
        add_text(
            slide,
            rect=Rect(body_x, rect.bottom - 0.4, body_w, 0.4),
            text=f"— {attribution}",
            font_size=14, color=body_color, align="left",
        )
    return quote_ref


def add_step_box(
    slide, deck_meta: dict, *,
    rect,
    number: int,
    title: str,
    body: str | None = None,
    **_extra,
) -> AnchorRef:
    if _extra:
        _warn_unknown("add_step_box", _extra)
    if isinstance(rect, tuple):
        rect = Rect(*rect)
    if isinstance(rect, AnchorRef):
        rect = rect.rect
    accent = _theme(deck_meta, "accent", "#21295C")
    bg = _theme(deck_meta, "background", "#FFFFFF")
    head_color = _theme(deck_meta, "head_text", "#1C2833")
    body_color = _theme(deck_meta, "body_text", "#1C2833")

    card = add_card(slide, deck_meta, rect=rect, padding=0.3)

    # number circle (half-overhanging TL)
    d = 0.5
    circle_rect = Rect(rect.x - d / 3, rect.y - d / 3, d, d)
    circle_shape = slide.shapes.add_shape(
        MSO_SHAPE.OVAL,
        Inches(circle_rect.x), Inches(circle_rect.y),
        Inches(circle_rect.w), Inches(circle_rect.h),
    )
    circle_shape.fill.solid()
    circle_shape.fill.fore_color.rgb = _hex_to_rgb(accent)
    circle_shape.line.fill.background()
    circle_shape.text_frame.text = ""
    add_text(
        slide,
        rect=circle_rect,
        text=str(number),
        font_size=14, bold=True, color=bg, align="center", line_spacing=1.0,
    )

    inner = rect.inset(0.3)
    title_y = inner.y + 0.15  # leave room for circle overhang
    add_text(
        slide,
        rect=Rect(inner.x + 0.2, title_y, inner.w - 0.2, 0.4),
        text=title,
        font_size=18, bold=True, color=head_color, align="left",
        line_spacing=1.2,
    )
    if body:
        add_text(
            slide,
            rect=Rect(inner.x + 0.2, title_y + 0.45,
                      inner.w - 0.2, max(0.3, inner.bottom - (title_y + 0.45))),
            text=body,
            font_size=14, color=body_color, align="left", line_spacing=1.3,
        )
    return card


# ---------------------------------------------------------------------------
# Recipe-era primitives — small, single-purpose visual atoms
# ---------------------------------------------------------------------------

def draw_header_strip(slide, rect: Rect, data: dict, deck_meta: dict) -> AnchorRef:
    """Solid navy strip with white centered text.

    Marks "this region is one category". Use as column header in matrices,
    side header in side-by-side comparisons.

    data: {"text": str}
    """
    fill = _theme(deck_meta, "accent", "#1F497D")
    text_color = _theme(deck_meta, "background", "#FFFFFF")
    add_rect(slide, rect=rect, fill=fill, border_color=None, rounded=False, shadow=False)
    add_text(
        slide, rect=rect, text=str(data.get("text", "")),
        font_size=14, bold=True, color=text_color, align="center", valign="middle",
        line_spacing=1.0,
    )
    return AnchorRef(rect=rect)


def draw_label_card(slide, rect: Rect, data: dict, deck_meta: dict) -> AnchorRef:
    """Pale grey card with thin border and dark centered text.

    Row/group label inside a matrix or grid. Visually quiet — distinguishes
    label from content without competing for attention.

    data: {"text": str}
    """
    body_color = _theme(deck_meta, "head_text", "#1C2833")
    add_rect(
        slide, rect=rect,
        fill="#F2F2F2", border_color="#D9D9D9", border_width=0.75,
        rounded=False, shadow=False,
    )
    add_text(
        slide, rect=rect, text=str(data.get("text", "")),
        font_size=14, bold=True, color=body_color, align="center", valign="middle",
        line_spacing=1.2,
    )
    return AnchorRef(rect=rect)


def draw_bullet_block(slide, rect: Rect, data: dict, deck_meta: dict) -> AnchorRef:
    """Plain (no fill, no border) bulleted text block.

    Body content of a matrix cell or any zone. ALL items live in a single
    text frame (one paragraph per item) so wrapping/spacing is handled by
    PowerPoint, not by per-item Rect math.

    data: {"title": str | None, "items": [str, ...]}
    """
    body_color = _theme(deck_meta, "body_text", "#1C2833")
    bullet_color = _theme(deck_meta, "bullet", "#065A82")

    pad = 0.12
    inner = rect.inset(pad)
    cursor_y = inner.y

    title = data.get("title")
    if title:
        add_text(
            slide,
            rect=Rect(inner.x, cursor_y, inner.w, 0.32),
            text=str(title),
            font_size=12, bold=True, color=bullet_color, align="left",
            line_spacing=1.1,
        )
        cursor_y += 0.35

    items = data.get("items") or []
    if not items:
        return AnchorRef(rect=rect)

    remaining_h = max(0.2, inner.bottom - cursor_y)
    box = slide.shapes.add_textbox(
        Inches(inner.x), Inches(cursor_y), Inches(inner.w), Inches(remaining_h),
    )
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.05)
    tf.margin_right = Inches(0.05)
    tf.margin_top = Inches(0.02)
    tf.margin_bottom = Inches(0.02)
    try:
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    except (AttributeError, ValueError):
        pass

    for i, item in enumerate(items):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = PP_ALIGN.LEFT
        para.line_spacing = 1.4
        # Small space-after between items so the block breathes
        try:
            para.space_after = Pt(4)
        except (AttributeError, ValueError):
            pass
        run = para.add_run()
        run.text = f"■ {item}"
        run.font.name = "Pretendard"
        run.font.size = Pt(12)
        run.font.color.rgb = _hex_to_rgb(body_color)
    return AnchorRef(rect=rect)


def draw_cover_card(slide, rect: Rect, data: dict, deck_meta: dict) -> AnchorRef:
    """Full-canvas cover layout: accent strip + title + sub + label/meta line.

    data: {"title": str, "sub": str | None, "label": str | None, "meta": str | None}
    """
    bg = _theme(deck_meta, "background", "#FFFFFF")
    accent = _theme(deck_meta, "accent", "#1F497D")
    head = _theme(deck_meta, "head_text", "#1C2833")
    body_color = _theme(deck_meta, "body_text", "#1C2833")

    set_bg(slide, bg)

    # Left accent bar (full height, narrow)
    bar_w = 0.35
    add_rect(slide, rect=Rect(rect.x, rect.y, bar_w, rect.h),
             fill=accent, border_color=None, rounded=False, shadow=False)

    inner_x = rect.x + bar_w + 0.6
    inner_w = rect.right - inner_x - 0.4

    # Vertical centering: title at ~38%, sub at ~50%, label at ~75%
    title_y = rect.y + rect.h * 0.32
    add_text(slide, rect=Rect(inner_x, title_y, inner_w, 1.4),
             text=str(data.get("title", "")),
             font_size=44, bold=True, color=head, align="left",
             line_spacing=1.1)

    sub = data.get("sub")
    if sub:
        add_text(slide, rect=Rect(inner_x, title_y + 1.5, inner_w, 0.8),
                 text=str(sub),
                 font_size=22, color=body_color, align="left", line_spacing=1.3)

    label = data.get("label")
    meta = data.get("meta")
    if label or meta:
        bits = " · ".join(b for b in [label, meta] if b)
        add_text(slide, rect=Rect(inner_x, rect.bottom - 0.7, inner_w, 0.4),
                 text=bits,
                 font_size=12, color=accent, bold=True, align="left",
                 line_spacing=1.0)
    return AnchorRef(rect=rect)


def draw_thesis_card(slide, rect: Rect, data: dict, deck_meta: dict) -> AnchorRef:
    """Full-canvas closing thesis: huge centered statement + small attribution.

    data: {"text": str, "attribution": str | None}
    """
    bg = _theme(deck_meta, "background", "#FFFFFF")
    head = _theme(deck_meta, "head_text", "#1C2833")
    accent = _theme(deck_meta, "accent", "#1F497D")
    body_color = _theme(deck_meta, "body_text", "#1C2833")

    set_bg(slide, bg)

    # Top quote-mark accent
    mark_h = 0.6
    add_text(slide, rect=Rect(rect.cx - 0.6, rect.y + rect.h * 0.18, 1.2, mark_h),
             text="“",
             font_size=72, bold=True, color=accent, align="center",
             line_spacing=1.0)

    # Main thesis (centered, large)
    text_y = rect.y + rect.h * 0.32
    text_h = rect.h * 0.4
    add_text(slide, rect=Rect(rect.x + 1.0, text_y, rect.w - 2.0, text_h),
             text=str(data.get("text", "")),
             font_size=36, bold=True, color=head, align="center",
             line_spacing=1.3)

    attr = data.get("attribution")
    if attr:
        add_text(slide, rect=Rect(rect.x, rect.bottom - 0.9, rect.w, 0.4),
                 text=f"— {attr}",
                 font_size=14, color=body_color, align="center", line_spacing=1.0)
    return AnchorRef(rect=rect)


def draw_big_number(slide, rect: Rect, data: dict, deck_meta: dict) -> AnchorRef:
    """Hero number primitive — one big numeric value + small label below.

    Use as the dominant visual element on a metric-focused slide. The number
    eats most of the rect; label sits at the bottom in body color.

    data: {"value": str, "unit": str | None, "label": str | None,
           "trend": str | None}
    """
    accent = _theme(deck_meta, "accent", "#1F497D")
    body = _theme(deck_meta, "body_text", "#1C2833")

    inner = rect.inset(0.15)
    value = str(data.get("value", ""))
    unit = data.get("unit")
    label = data.get("label")
    trend = data.get("trend")

    # Reserve bottom 25% for label, rest for the number
    label_h = 0.6 if label else 0.0
    number_h = max(0.6, inner.h - label_h - 0.05)

    # Big number: scale font roughly to rect height. ~70% of number_h in pt.
    # Cap at 96pt to avoid over-large rendering on huge zones.
    pt = max(36, min(96, int(number_h * 60)))

    value_text = f"{value}{unit}" if unit else value
    add_text(
        slide,
        rect=Rect(inner.x, inner.y, inner.w, number_h),
        text=value_text,
        font_size=pt, bold=True, color=accent,
        align="left", valign="middle", line_spacing=1.0,
    )

    if trend:
        add_text(
            slide,
            rect=Rect(inner.right - 1.2, inner.y, 1.2, 0.4),
            text=str(trend),
            font_size=12, bold=True, color=accent,
            align="right", valign="top", line_spacing=1.0,
        )

    if label:
        add_text(
            slide,
            rect=Rect(inner.x, inner.y + number_h, inner.w, label_h),
            text=str(label),
            font_size=14, color=body,
            align="left", valign="top", line_spacing=1.2,
        )
    return AnchorRef(rect=rect)


def draw_progress_bar(slide, rect: Rect, data: dict, deck_meta: dict) -> AnchorRef:
    """Horizontal progress bar — track + fill + percent label.

    Use to express "X% of Y" or single-axis progress. Label appears on the
    right of the bar; full title (if any) sits above.

    data: {"percent": float (0-100), "label": str | None, "title": str | None}
    """
    accent = _theme(deck_meta, "accent", "#1F497D")
    body = _theme(deck_meta, "body_text", "#1C2833")

    pct = float(data.get("percent", 0))
    pct = max(0.0, min(100.0, pct))
    title = data.get("title")
    label = data.get("label") or f"{pct:.0f}%"

    inner = rect.inset(0.1)
    cursor_y = inner.y

    if title:
        add_text(
            slide,
            rect=Rect(inner.x, cursor_y, inner.w, 0.4),
            text=str(title),
            font_size=14, bold=True, color=body, align="left",
            valign="middle", line_spacing=1.1,
        )
        cursor_y += 0.45

    # Bar geometry
    bar_h = 0.3
    bar_y = cursor_y + max(0.0, (inner.bottom - cursor_y - bar_h) / 2)
    label_w = 0.9
    track_w = max(0.5, inner.w - label_w - 0.15)

    # Track (light grey)
    add_rect(
        slide,
        rect=Rect(inner.x, bar_y, track_w, bar_h),
        fill="#E8EBEE", border_color=None, rounded=True, shadow=False,
    )
    # Fill
    fill_w = track_w * (pct / 100.0)
    if fill_w > 0.05:
        add_rect(
            slide,
            rect=Rect(inner.x, bar_y, fill_w, bar_h),
            fill=accent, border_color=None, rounded=True, shadow=False,
        )
    # Label (right of bar)
    add_text(
        slide,
        rect=Rect(inner.x + track_w + 0.1, bar_y - 0.05, label_w, bar_h + 0.1),
        text=label,
        font_size=14, bold=True, color=accent, align="left",
        valign="middle", line_spacing=1.0,
    )
    return AnchorRef(rect=rect)


def draw_bar_compare(slide, rect: Rect, data: dict, deck_meta: dict) -> AnchorRef:
    """Horizontal bar chart for 2-6 items.

    Each row is one item: name on left, bar in the middle scaled to max value,
    numeric value on the right. Pure shape rendering — no python-pptx Chart.

    data: {
      "title": str | None,
      "items": [
        {"name": "Threads",  "value": 5,    "unit": "일"},
        {"name": "ChatGPT",  "value": 60,   "unit": "일"},
        ...
      ]
    }
    """
    accent = _theme(deck_meta, "accent", "#1F497D")
    body = _theme(deck_meta, "body_text", "#1C2833")

    items = data.get("items") or []
    if not items:
        return AnchorRef(rect=rect)
    if len(items) > 6:
        items = items[:6]

    inner = rect.inset(0.12)
    cursor_y = inner.y

    title = data.get("title")
    if title:
        add_text(
            slide,
            rect=Rect(inner.x, cursor_y, inner.w, 0.4),
            text=str(title),
            font_size=14, bold=True, color=body, align="left",
            valign="middle", line_spacing=1.1,
        )
        cursor_y += 0.5

    # Find max numeric value for scaling
    def _num(v) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    max_val = max((_num(it.get("value")) for it in items), default=0.0)
    if max_val <= 0:
        max_val = 1.0

    # Layout per row
    row_h = max(0.32, (inner.bottom - cursor_y) / len(items) - 0.08)
    name_w = 2.2
    value_w = 1.2
    track_x = inner.x + name_w + 0.15
    track_w = max(0.5, inner.right - track_x - value_w - 0.15)

    for it in items:
        name = str(it.get("name", ""))
        v = _num(it.get("value"))
        unit = it.get("unit") or ""
        # Name (left)
        add_text(
            slide,
            rect=Rect(inner.x, cursor_y, name_w, row_h),
            text=name,
            font_size=12, color=body, align="right",
            valign="middle", line_spacing=1.0,
        )
        # Bar (middle)
        bar_w_ratio = v / max_val if max_val else 0.0
        fill_w = max(0.05, track_w * bar_w_ratio) if v > 0 else 0.0
        bar_h = max(0.2, row_h * 0.55)
        bar_y = cursor_y + (row_h - bar_h) / 2
        # Track
        add_rect(
            slide,
            rect=Rect(track_x, bar_y, track_w, bar_h),
            fill="#EEF1F4", border_color=None, rounded=False, shadow=False,
        )
        # Fill
        if fill_w > 0:
            add_rect(
                slide,
                rect=Rect(track_x, bar_y, fill_w, bar_h),
                fill=accent, border_color=None, rounded=False, shadow=False,
            )
        # Value (right)
        value_text = f"{int(v) if v.is_integer() else v}{unit}"
        add_text(
            slide,
            rect=Rect(inner.right - value_w, cursor_y, value_w, row_h),
            text=value_text,
            font_size=12, bold=True, color=accent, align="left",
            valign="middle", line_spacing=1.0,
        )
        cursor_y += row_h + 0.08
    return AnchorRef(rect=rect)


def draw_arrow_transform(slide, rect: Rect, data: dict, deck_meta: dict) -> AnchorRef:
    """Big horizontal arrow used as the connector between As-Is and To-Be cards.

    data: {"label": str | None}  — short label sits above the arrow if present.
    """
    accent = _theme(deck_meta, "accent", "#1F497D")
    body = _theme(deck_meta, "body_text", "#1C2833")

    label = data.get("label")
    label_h = 0.4 if label else 0.0
    arrow_y = rect.y + label_h + (rect.h - label_h) / 2

    if label:
        add_text(
            slide,
            rect=Rect(rect.x, rect.y, rect.w, label_h),
            text=str(label),
            font_size=12, bold=True, color=body,
            align="center", valign="middle", line_spacing=1.0,
        )

    # Use add_arrow with explicit endpoints
    pad = 0.15
    add_arrow(
        slide,
        rect.x + pad, arrow_y,
        rect.right - pad, arrow_y,
        color=accent, width=4.0,
    )
    return AnchorRef(rect=rect)


def draw_section_band(slide, rect: Rect, data: dict, deck_meta: dict) -> AnchorRef:
    """Full-canvas section divider — large numeral + section title on accent band.

    data: {"number": str, "title": str, "sub": str | None}
    """
    bg = _theme(deck_meta, "background", "#FFFFFF")
    accent = _theme(deck_meta, "accent", "#1F497D")
    head = _theme(deck_meta, "head_text", "#1C2833")

    set_bg(slide, bg)

    # Left accent band
    band_w = rect.w * 0.35
    add_rect(slide, rect=Rect(rect.x, rect.y, band_w, rect.h),
             fill=accent, border_color=None, rounded=False, shadow=False)

    # Large numeral on the band
    number = str(data.get("number", ""))
    if number:
        add_text(
            slide, rect=Rect(rect.x, rect.cy - 1.5, band_w, 3.0),
            text=number,
            font_size=140, bold=True, color="#FFFFFF",
            align="center", valign="middle", line_spacing=1.0,
        )

    # Title + sub on the right
    text_x = rect.x + band_w + 0.6
    text_w = rect.right - text_x - 0.4

    title = str(data.get("title", ""))
    add_text(
        slide, rect=Rect(text_x, rect.cy - 0.8, text_w, 1.2),
        text=title,
        font_size=36, bold=True, color=head,
        align="left", valign="middle", line_spacing=1.1,
    )

    sub = data.get("sub")
    if sub:
        add_text(
            slide, rect=Rect(text_x, rect.cy + 0.3, text_w, 0.6),
            text=str(sub),
            font_size=18, color=head,
            align="left", valign="top", line_spacing=1.2,
        )
    return AnchorRef(rect=rect)


def draw_pull_quote(slide, rect: Rect, data: dict, deck_meta: dict) -> AnchorRef:
    """Large pull quote with leading quote mark + attribution.

    data: {"text": str, "attribution": str | None, "context": str | None}
    """
    accent = _theme(deck_meta, "accent", "#1F497D")
    body = _theme(deck_meta, "body_text", "#1C2833")

    text = str(data.get("text", ""))
    attribution = data.get("attribution")
    context = data.get("context")

    inner = rect.inset(0.2)

    # Leading huge quote mark (left-aligned, top)
    mark_w, mark_h = 1.0, 1.2
    add_text(
        slide, rect=Rect(inner.x, inner.y, mark_w, mark_h),
        text="“",
        font_size=96, bold=True, color=accent,
        align="left", valign="top", line_spacing=1.0,
    )

    # Quote text
    body_x = inner.x + mark_w + 0.1
    body_w = inner.right - body_x
    quote_h = inner.h - (1.0 if attribution or context else 0.3)
    add_text(
        slide, rect=Rect(body_x, inner.y + 0.2, body_w, quote_h),
        text=text,
        font_size=24, italic=True, color=body,
        align="left", valign="top", line_spacing=1.4,
    )

    # Attribution / context
    bottom_y = inner.bottom - 0.7
    if attribution:
        add_text(
            slide, rect=Rect(body_x, bottom_y, body_w, 0.4),
            text=f"— {attribution}",
            font_size=14, bold=True, color=body,
            align="left", valign="middle", line_spacing=1.0,
        )
        bottom_y += 0.32
    if context:
        add_text(
            slide, rect=Rect(body_x, bottom_y, body_w, 0.35),
            text=str(context),
            font_size=11, color=body,
            align="left", valign="middle", line_spacing=1.0,
        )
    return AnchorRef(rect=rect)


def draw_timeline_node(slide, rect: Rect, data: dict, deck_meta: dict) -> AnchorRef:
    """One node in a horizontal timeline — circle marker + when/title/note stack.

    data: {"when": str, "title": str, "note": str | None}
    """
    accent = _theme(deck_meta, "accent", "#1F497D")
    body = _theme(deck_meta, "body_text", "#1C2833")

    # Marker circle at the top of rect, centered horizontally
    d = 0.35
    cx = rect.cx
    circle_y = rect.y + 0.1
    circle_shape = slide.shapes.add_shape(
        MSO_SHAPE.OVAL,
        Inches(cx - d / 2), Inches(circle_y), Inches(d), Inches(d),
    )
    circle_shape.fill.solid()
    circle_shape.fill.fore_color.rgb = _hex_to_rgb(accent)
    circle_shape.line.fill.background()
    if circle_shape.has_text_frame:
        circle_shape.text_frame.text = ""

    # When (date / phase) — bold below the marker
    when = str(data.get("when", ""))
    add_text(
        slide, rect=Rect(rect.x, circle_y + d + 0.05, rect.w, 0.35),
        text=when,
        font_size=12, bold=True, color=accent,
        align="center", valign="top", line_spacing=1.0,
    )

    # Title — primary content
    title = str(data.get("title", ""))
    add_text(
        slide, rect=Rect(rect.x, circle_y + d + 0.45, rect.w, 0.5),
        text=title,
        font_size=14, bold=True, color=body,
        align="center", valign="top", line_spacing=1.1,
    )

    # Note — tertiary
    note = data.get("note")
    if note:
        add_text(
            slide,
            rect=Rect(rect.x, circle_y + d + 1.0, rect.w,
                      max(0.4, rect.bottom - (circle_y + d + 1.0))),
            text=str(note),
            font_size=11, color=body,
            align="center", valign="top", line_spacing=1.3,
        )
    return AnchorRef(rect=rect)


def draw_timeline_connector(slide, rect: Rect, data: dict, deck_meta: dict) -> AnchorRef:
    """Thin horizontal line connecting timeline nodes."""
    color = _theme(deck_meta, "accent", "#1F497D")
    y = rect.y + 0.275  # align with the node circle's vertical center (offset 0.1 + d/2 = 0.275)
    add_line(slide, rect.x, y, rect.right, y, color=color, width=2.0)
    return AnchorRef(rect=rect)


PRIMITIVES: dict = {
    "header_strip":        draw_header_strip,
    "label_card":          draw_label_card,
    "bullet_block":        draw_bullet_block,
    "cover_card":          draw_cover_card,
    "thesis_card":         draw_thesis_card,
    "big_number":          draw_big_number,
    "progress_bar":        draw_progress_bar,
    "bar_compare":         draw_bar_compare,
    "arrow_transform":     draw_arrow_transform,
    "section_band":        draw_section_band,
    "pull_quote":          draw_pull_quote,
    "timeline_node":       draw_timeline_node,
    "timeline_connector":  draw_timeline_connector,
}
