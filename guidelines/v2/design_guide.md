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
`FONT_HEAD` `FONT_BODY` — string font names.
`SIZE_HEAD` `SIZE_SUB` `SIZE_BODY` `SIZE_CAP` — these are ALREADY
`Pt(...)` instances (Pt(36), Pt(20), Pt(14), Pt(11)). Assign them
**directly** to `font.size`. Do NOT wrap them in `Pt(...)` again.

```python
# ✅ correct
r.font.size = SIZE_HEAD
# ❌ wrong — double-wrap explodes the value 12700×, raising
#    ValueError: value must be in range 100 to 400000 inclusive
r.font.size = Pt(SIZE_HEAD)
```

For headline emphasis larger than `SIZE_HEAD`, use `Pt(48)` etc. directly
on a literal int.

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

## Forbidden — these crash the slide. Hard rules, not style suggestions.

If you find yourself about to write any of these, STOP and pick a
different approach. The retry loop will not save you — these errors
have no "fix the filename" or "fix the index" workaround. The whole
idiom is wrong for this environment.

### F1. NEVER pass a string filepath to `add_picture`
The slide_codes directory ships with **zero image assets on disk**.
Any filepath string — including made-up names like `"diagram.png"`,
`"path_to_chart.png"`, `"icon.svg"` — raises `FileNotFoundError`.

```python
# ❌ WRONG — guaranteed FileNotFoundError, no matter what string you pick
slide.shapes.add_picture("diagram.png", x, y, w, h)
slide.shapes.add_picture("path_to_code_generation_diagram.png", x, y, w, h)

# ✅ ONLY acceptable form: in-memory BytesIO from matplotlib
import io
fig, ax = plt.subplots(figsize=(4, 4), dpi=150); ax.pie([60, 40])
buf = io.BytesIO(); fig.savefig(buf, format="png"); plt.close(fig); buf.seek(0)
slide.shapes.add_picture(buf, x, y, w, h)
```

If you cannot generate the visual with matplotlib, **drop the picture
entirely** and represent the idea with shapes + text.

### F2. NEVER use `slide.placeholders` or `slide.shapes.title`
The footer creates the slide via `prs.slide_layouts[6]` (BLANK layout).
A blank slide has **no placeholders at all**. Any access — including
`slide.placeholders[0]`, `slide.placeholders[1]`, `slide.shapes.title` —
raises `KeyError: 'no placeholder on this slide with idx == N'`.

```python
# ❌ WRONG — guaranteed KeyError on a blank layout
title = slide.placeholders[1]; title.text = "Hello"
slide.shapes.title.text = "Hello"

# ✅ Add a textbox shape directly
tb = slide.shapes.add_textbox(left, top, width, height)
tf = tb.text_frame; tf.word_wrap = True
r = tf.paragraphs[0].add_run(); r.text = "Hello"
r.font.name = FONT_HEAD; r.font.size = Pt(SIZE_HEAD); r.font.color.rgb = INK
```

### F3. NEVER add a second slide or call `prs.save(...)`
The footer already created `prs.slides[0]` and will save the file at
the end. Calling `prs.slides.add_slide(...)` or `prs.save(...)` yourself
corrupts the output.

### F4. NEVER add new `import` statements
Everything you need (`Pt`, `Inches`, `RGBColor`, `MSO_SHAPE`,
`MSO_CONNECTOR`, `plt`, `io`, color/typography tokens) is already in
the preamble. A new import usually means you are reaching for a feature
that is not supported in this environment.

### F5. NEVER wrap `SIZE_*` tokens in `Pt(...)`
`SIZE_HEAD`, `SIZE_SUB`, `SIZE_BODY`, `SIZE_CAP` are already `Pt(...)`
instances. Wrapping them again multiplies the value by 12700 and
raises `ValueError: value must be in range 100 to 400000 inclusive`.

```python
# ❌ WRONG — guaranteed ValueError
r.font.size = Pt(SIZE_HEAD)
# ✅ correct
r.font.size = SIZE_HEAD
```

### F6. NEVER hardcode design constants
- ❌ `RGBColor(0xAB, 0xCD, 0xEF)` → use `PRIMARY` / `ACCENT` / `INK` / `MUTED` / `BG` / `SURFACE`.
- ❌ `Pt(13)` for body copy → use `SIZE_HEAD` / `SIZE_SUB` / `SIZE_BODY` / `SIZE_CAP`.
- ❌ `"Arial"`, `"Helvetica"` → use `FONT_HEAD` / `FONT_BODY`.
- ❌ `Inches(2.34)` magic positions → derive from `SLIDE_W`, `SLIDE_H`, and a padding budget.

## Output

Reply with ONLY the body of `def build_slide(prs):` and any helper
functions you need. No prose, no markdown fences.
