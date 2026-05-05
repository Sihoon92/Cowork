# Layout Grid & Positioning System

This document defines the **deck-wide spatial contract** every slide must follow,
and the **three positioning tools** the LLM uses instead of raw coordinates.

> Goal: the LLM never writes raw `(x, y)` numbers. It says either
> "place this in column 1–6" (Grid), "stack these vertically with gap 0.3"
> (Stack), or "attach this caption below that image" (Anchor).

---

## 1. Slide Geometry (constant for every slide)

- Slide size: **13.333 × 7.5 in** (16:9)
- Safe margins: **0.6 in** on all four sides
- Three vertical zones:

| Zone | y range | Use |
|---|---|---|
| **Header** | 0.4 – 1.5 | Title (28pt bold) + thin blue rule under it |
| **Body**   | 1.6 – 6.7 | All content goes here |
| **Footer** | 6.8 – 7.2 | Page number (right) + section_id (left) |

Cover / Section Divider slides skip the master and own the full canvas.

The `apply_master(slide, deck_meta, head_message, sub_message=None)` helper
paints Header + Footer automatically and returns the **Body Rect** that
content should be placed inside.

---

## 2. The Three Positioning Tools

The LLM picks **one** primary tool per slide based on the layout pattern.
See `design_guideline.md` for the recommended tool per pattern.

### 2.1 Grid (12-column, body-relative)

Use when the slide divides into clear columns/rows.

```python
left  = body.col(1, span=6)      # columns 1-6  → left half
right = body.col(7, span=6)      # columns 7-12 → right half

# Two-row split inside the left half:
top_left = left.row(1, span=1)
bot_left = left.row(2, span=1)
```

- Columns: 12 equal columns inside Body, gutter 0.2 in
- Rows: declared via `.row(start, span)` after a column slice; default 1 row
- Returned object is a `Rect` you pass to other primitives or wrap with Stack/Anchor

### 2.2 Stack (1D auto-layout)

Use when the same shape repeats N times in a line.

```python
stack = Stack(body, direction="vertical", gap=0.3, align="center")
for point in data["content"]["points"]:
    stack.add_card(title=point["title"], body=point["body"])

# horizontal stack with wrap:
row = Stack(body, direction="horizontal", gap=0.4, wrap=True)
for icon in icons:
    row.add(icon)
```

- `direction`: `"vertical"` | `"horizontal"`
- `gap`: spacing between items in inches
- `align`: `"start"` | `"center"` | `"end"` along the cross-axis
- `wrap`: only for horizontal — wrap to next row when overflowing the rect width
- Each `add_*` returns the placed shape so it can be used as an Anchor reference

### 2.3 Anchor (shape → shape chaining)

Use when one shape's position depends on another shape (callouts, arrows,
captions, hub-and-spoke).

Every placed shape exposes 9 anchor points:

```
TL  TC  TR
ML  MC  MR
BL  BC  BR
```

```python
hero = add_card(body, anchor="MC", w=4, h=2.5, title="Hero")

# Caption sits 0.3 in below hero, horizontally centred:
caption = add_text(
    relative_to=hero,
    their_anchor="BC",
    my_anchor="TC",
    gap=(0, 0.3),
    text="…",
    style="sub",
)

# Arrow connecting two cards:
add_arrow(from_=(boxA, "MR"), to_=(boxB, "ML"))
```

Rules:
- `relative_to` may be the body Rect or any previously placed shape
- Chains may be N-deep (B → A, C → B, D → C …) but cycles are forbidden
- `gap=(dx, dy)` in inches; both can be negative
- For lines/arrows, `from_` and `to_` may both be anchor tuples

---

## 3. When to use which

| Pattern shape | Tool |
|---|---|
| One big focal element | **Anchor** ("MC" of body) |
| List of N similar items in a line | **Stack** |
| Slide split into named regions | **Grid** |
| Free-form diagram with arrows | **Anchor** chains |
| Mixed (e.g. 2-column with stacked items inside each column) | **Grid → Stack** nesting |

Do not mix tools without nesting — never compute a coordinate from one tool's
output and pass it as a raw number to another. Always pass the returned `Rect`
or shape reference.

---

## 4. Hard rules (the validator will reject violations)

1. No raw `(x, y, w, h)` numbers in slide code — use Grid / Stack / Anchor.
2. All text fits inside the Body rect returned by `apply_master`.
3. Theme colors are referenced by **role** (`background`, `head_text`,
   `head_rule`, `body_text`, `bullet`, `accent`), never hard-coded.
4. Header (title + blue rule) is painted by `apply_master`, not by the slide.
5. The slide's own code never calls `set_bg` — `apply_master` handles it.

Exceptions: Cover and Section Divider slides skip rule 4 and 5.
