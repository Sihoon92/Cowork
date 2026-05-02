from pptx import Presentation
from pptx.util import Inches
from pptx.enum.shapes import MSO_SHAPE_TYPE

from src.pptx.primitives import _hex_to_rgb, set_bg, add_text


def _new_slide():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    return prs, slide


def test_hex_to_rgb_uppercase():
    rgb = _hex_to_rgb("#FF8800")
    assert (rgb[0], rgb[1], rgb[2]) == (255, 136, 0)


def test_hex_to_rgb_no_hash():
    rgb = _hex_to_rgb("00FF00")
    assert (rgb[0], rgb[1], rgb[2]) == (0, 255, 0)


def test_set_bg_paints_slide():
    prs, slide = _new_slide()
    set_bg(slide, "#1C2833")
    fill = slide.background.fill
    assert fill.type is not None
    assert (fill.fore_color.rgb[0], fill.fore_color.rgb[1], fill.fore_color.rgb[2]) == (0x1C, 0x28, 0x33)


def test_add_text_creates_textbox_with_content():
    prs, slide = _new_slide()
    add_text(slide, x=1.0, y=2.0, w=5.0, h=1.0, text="Hello", font_size=20, bold=True, color="#FF0000")
    textboxes = [s for s in slide.shapes if s.has_text_frame]
    assert len(textboxes) == 1
    tf = textboxes[0].text_frame
    run = tf.paragraphs[0].runs[0]
    assert run.text == "Hello"
    assert run.font.bold is True
    assert run.font.size.pt == 20
    assert (run.font.color.rgb[0], run.font.color.rgb[1], run.font.color.rgb[2]) == (255, 0, 0)


def test_add_text_alignment_center():
    prs, slide = _new_slide()
    add_text(slide, x=0, y=0, w=10, h=1, text="X", align="center")
    tb = [s for s in slide.shapes if s.has_text_frame][0]
    from pptx.enum.text import PP_ALIGN
    assert tb.text_frame.paragraphs[0].alignment == PP_ALIGN.CENTER


from src.pptx.primitives import add_rect


def test_add_rect_with_fill():
    prs, slide = _new_slide()
    add_rect(slide, x=1, y=1, w=2, h=1, fill="#065A82")
    rects = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE]
    assert len(rects) == 1
    fc = rects[0].fill.fore_color.rgb
    assert (fc[0], fc[1], fc[2]) == (0x06, 0x5A, 0x82)


def test_add_rect_with_border():
    prs, slide = _new_slide()
    add_rect(slide, x=0, y=0, w=1, h=1, fill="#FFFFFF", border_color="#000000", border_width=2.0)
    rect = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE][0]
    assert rect.line.color.rgb is not None


def test_add_rect_rounded():
    prs, slide = _new_slide()
    add_rect(slide, x=0, y=0, w=1, h=1, fill="#FF0000", rounded=True)
    rect = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE][0]
    from pptx.enum.shapes import MSO_SHAPE
    assert rect.auto_shape_type == MSO_SHAPE.ROUNDED_RECTANGLE


from src.pptx.primitives import add_line, add_arrow


def test_add_line_creates_connector():
    prs, slide = _new_slide()
    add_line(slide, x1=1, y1=1, x2=5, y2=3, color="#FF0000", width=2.0)
    lines = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.LINE]
    assert len(lines) == 1


def test_add_arrow_creates_arrow_connector():
    prs, slide = _new_slide()
    add_arrow(slide, x1=0, y1=0, x2=4, y2=0, color="#000000")
    # Arrow is a connector with end-arrow head; we just verify a shape was added
    assert len(slide.shapes) == 1


from pathlib import Path
from src.pptx.primitives import add_image


def test_add_image_inserts_picture():
    prs, slide = _new_slide()
    fixture = Path(__file__).parent / "fixtures" / "dot.png"
    add_image(slide, x=1, y=1, w=2, h=2, image_path=str(fixture))
    pictures = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert len(pictures) == 1
