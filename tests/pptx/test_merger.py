from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from src.pptx.merger import merge_slides


def _make_one_slide(path: Path, text: str) -> Path:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    box.text_frame.text = text
    prs.save(path)
    return path


def test_merge_two_slides_into_one_deck(tmp_path):
    a = _make_one_slide(tmp_path / "a.pptx", "First")
    b = _make_one_slide(tmp_path / "b.pptx", "Second")
    out = tmp_path / "merged.pptx"
    merge_slides([a, b], out)
    final = Presentation(out)
    assert len(final.slides) == 2
    texts = []
    for sl in final.slides:
        for shp in sl.shapes:
            if shp.has_text_frame:
                texts.append(shp.text_frame.text)
    assert "First" in texts
    assert "Second" in texts


def test_merge_single_slide_passes_through(tmp_path):
    a = _make_one_slide(tmp_path / "a.pptx", "Only")
    out = tmp_path / "out.pptx"
    merge_slides([a], out)
    final = Presentation(out)
    assert len(final.slides) == 1


def test_merge_empty_list_raises(tmp_path):
    out = tmp_path / "out.pptx"
    try:
        merge_slides([], out)
    except ValueError:
        return
    raise AssertionError("expected ValueError on empty list")
