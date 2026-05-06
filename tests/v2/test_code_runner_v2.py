from pathlib import Path

from src.pipeline_v2.code_assembler import assemble_slide_module
from src.pipeline_v2.code_generator import execute_slide_body


GOOD_BODY = """
def build_slide(prs):
    slide = prs.slides[0]
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = BG
    bg.line.fill.background()
    tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.5),
                                  Inches(8), Inches(1))
    tb.text_frame.text = "Hello from v2"
"""


def test_execute_slide_body_writes_pptx(tmp_path: Path):
    out = tmp_path / "slide_01.pptx"
    execute_slide_body(GOOD_BODY, out, work_dir=tmp_path)
    assert out.exists() and out.stat().st_size > 0


BAD_BODY_FLOAT_EMU = """
def build_slide(prs):
    slide = prs.slides[0]
    # Float coords — without _patch_shapes this would emit float EMU
    slide.shapes.add_textbox(0.5 * 914400, 0.5 * 914400,
                             8.0 * 914400, 1.0 * 914400)
"""


def test_execute_slide_body_floats_survive_patch_shapes(tmp_path: Path):
    out = tmp_path / "slide_02.pptx"
    execute_slide_body(BAD_BODY_FLOAT_EMU, out, work_dir=tmp_path)
    assert out.exists()
