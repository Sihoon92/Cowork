"""Merge multiple single-slide .pptx files into one presentation.

python-pptx has no public slide-copy API. We deep-copy the slide part XML and
re-link relationships into a destination presentation.
"""
from __future__ import annotations

import copy
from pathlib import Path

from pptx import Presentation
from pptx.oxml.ns import qn


def _copy_slide(dest_prs, source_slide) -> None:
    """Append a copy of source_slide into dest_prs."""
    blank_layout = dest_prs.slide_layouts[6]
    new_slide = dest_prs.slides.add_slide(blank_layout)

    # Drop default placeholders that came from the layout
    for shp in list(new_slide.shapes):
        sp = shp._element
        sp.getparent().remove(sp)

    # Deep-copy each shape from the source
    src_spTree = source_slide.shapes._spTree
    dst_spTree = new_slide.shapes._spTree
    for child in src_spTree.iterchildren():
        tag = child.tag
        # Skip non-shape bookkeeping elements that the layout already provides
        if tag.endswith("}nvGrpSpPr") or tag.endswith("}grpSpPr"):
            continue
        dst_spTree.append(copy.deepcopy(child))

    # Copy slide background fill if present
    src_bg = source_slide._element.find(qn("p:cSld") + "/" + qn("p:bg"))
    if src_bg is not None:
        dst_cSld = new_slide._element.find(qn("p:cSld"))
        for existing in dst_cSld.findall(qn("p:bg")):
            dst_cSld.remove(existing)
        dst_cSld.insert(0, copy.deepcopy(src_bg))


def merge_slides(slide_paths: list[Path], output_path: Path) -> Path:
    if not slide_paths:
        raise ValueError("merge_slides: slide_paths is empty")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Start from a fresh blank deck so dimensions/theme are consistent
    first = Presentation(slide_paths[0])
    final = Presentation()
    final.slide_width = first.slide_width
    final.slide_height = first.slide_height

    for path in slide_paths:
        src = Presentation(path)
        for sl in src.slides:
            _copy_slide(final, sl)

    final.save(output_path)
    return output_path
