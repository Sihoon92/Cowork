# v2 Design Guide for LLM-generated python-pptx code

You will write the body of `def build_slide(prs):`. The framework
prepends a preamble that gives you all imports and design tokens, and
appends a footer that creates the first slide and calls
`_patch_shapes(slide)` for you. You do NOT write imports, slide creation,
or `prs.save`.

## Canvas
- Size: `SLIDE_W` × `SLIDE_H` (13.333 × 7.5 in, 16:9).
- Safe area: leave at least 0.4 in (`Inches(0.4)`) padding on all edges.

## Color tokens (use these — never hardcode hex)
`PRIMARY` `ACCENT` `INK` `MUTED` `BG` `SURFACE`

## Typography tokens (use these — never hardcode pt)
`FONT_HEAD` `FONT_BODY`
`SIZE_HEAD` (36) `SIZE_SUB` (20) `SIZE_BODY` (14) `SIZE_CAP` (11)

For headline emphasis larger than `SIZE_HEAD`, use `Pt(48)` etc. directly.

## Recipe snippets (illustrative; not mandatory)

### Headline strip

```python
def build_slide(prs):
    slide = prs.slides[0]
    # Background
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = BG; bg.line.fill.background()
    # Headline strip (top 1/4)
    strip = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                    0, 0, SLIDE_W, SLIDE_H // 4)
    strip.fill.solid(); strip.fill.fore_color.rgb = PRIMARY
    strip.line.fill.background()
```

### 1×3 cards with center emphasis (1.4×)

```python
pad = Inches(0.4)
content_top = SLIDE_H // 4 + Inches(0.3)
content_h = SLIDE_H - content_top - Inches(0.6)
# Ratios [1, 1.4, 1] — total 3.4
total = SLIDE_W - pad * 2
unit = total // 34
widths = [unit * 10, unit * 14, unit * 10]
gap = (total - sum(widths)) // 2
x = pad
for i, w in enumerate(widths):
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                   x, content_top, w, content_h)
    card.fill.solid()
    card.fill.fore_color.rgb = ACCENT if i == 1 else SURFACE
    x += w + gap
```

### Chart + side text card with connector

```python
# 1. Render donut PNG via matplotlib in-memory.
import io
fig, ax = plt.subplots(figsize=(4, 4), dpi=150)
ax.pie([60, 25, 15], wedgeprops={"width": 0.35})
ax.set(aspect="equal")
buf = io.BytesIO(); fig.savefig(buf, format="png", bbox_inches="tight"); plt.close(fig)
buf.seek(0)
chart_x, chart_y, chart_w, chart_h = Inches(0.6), Inches(1.5), Inches(5), Inches(5)
slide.shapes.add_picture(buf, chart_x, chart_y, chart_w, chart_h)
# 2. Side text card.
card_x, card_y = Inches(7), Inches(2)
card_w, card_h = Inches(5.7), Inches(3.5)
slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, card_x, card_y, card_w, card_h)
# 3. Connector from donut center to card left edge.
center_x = chart_x + chart_w // 2
center_y = chart_y + chart_h // 2
slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                            center_x, center_y, card_x, card_y + card_h // 2)
```

## Anti-patterns (NEVER do these)

- ❌ Hardcoded magic coordinates like `Inches(2.34)`. Compute from
  `SLIDE_W` / `SLIDE_H` and the padding budget.
- ❌ Hex literals like `RGBColor(0xAB, 0xCD, 0xEF)`. Use the tokens.
- ❌ External file paths (`open("foo.png")`). Generate everything inline
  with matplotlib + `io.BytesIO`.
- ❌ Hardcoded font names like `"Arial"`. Use `FONT_HEAD` / `FONT_BODY`.
- ❌ Adding new `import` statements. Everything you need is in the preamble.
- ❌ Calling `prs.save(...)` or `prs.slides.add_slide(...)`. The footer does it.

## Output

Reply with ONLY the body of `def build_slide(prs):` and any helper
functions you need. No prose, no markdown fences.
