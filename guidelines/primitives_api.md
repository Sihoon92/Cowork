# Primitives API Reference

Layer 1 dumb-executor functions exposed at `src.pptx.primitives`.

All coordinates and dimensions are in **inches**. Slide is **13.333 × 7.5** inches (16:9).
All colors are uppercase 6-digit hex with leading `#` (e.g., `#1C2833`).

## Functions

### `set_bg(slide, color)`
Paint slide background with a solid color.
- `color`: hex string

### `add_text(slide, x, y, w, h, text, *, font_size=14, bold=False, italic=False, color="#000000", align="left", font="Pretendard", line_spacing=1.2)`
Insert a text box at `(x, y)` with size `(w, h)`.
- `align` ∈ {`"left"`, `"center"`, `"right"`}
- For Korean text prefer `font="Pretendard"` or `"Malgun Gothic"`.

### `add_rect(slide, x, y, w, h, *, fill="#FFFFFF", border_color=None, border_width=0.0, rounded=False)`
Insert a rectangle (or rounded rectangle).
- `border_color=None` means no border.

### `add_line(slide, x1, y1, x2, y2, *, color="#000000", width=1.5)`
Insert a straight line connector.

### `add_arrow(slide, x1, y1, x2, y2, *, color="#000000", width=2.0)`
Insert a straight line with an end-arrow head (triangle).

### `add_image(slide, x, y, w, h, image_path)`
Insert a picture from disk at `(x, y)` with size `(w, h)`.

## Required Slide Code Skeleton

```python
from pptx import Presentation
from pptx.util import Inches
from src.pptx.primitives import (
    add_text, add_rect, add_line, add_arrow, add_image, set_bg,
)
import json, sys


def add_slide(prs: Presentation, data: dict) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    # Compose using primitives only.


if __name__ == "__main__":
    data = json.loads(sys.stdin.read())
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    add_slide(prs, data)
    prs.save(sys.argv[1])
```

## Constraints (for code generation)

- Only the imports shown above are allowed.
- No file I/O other than reading stdin and writing `sys.argv[1]`.
- All text and numbers must come from the `data` dict; no hardcoded content.
- Colors and fonts come from `data["deck_meta"]["theme"]` and `data["deck_meta"]["fonts"]`.
- Keep all content within `0.4` inch margin from slide edges.
