# Component Library

High-level building blocks. **Prefer components over raw `add_rect`/`add_text`** —
they enforce the deck's visual tone (white card, soft shadow, square bullet, etc.)
without the LLM having to decide colors/sizes every time.

All components honor `data["deck_meta"]["theme"]` automatically. Coordinates
flow from Grid / Stack / Anchor — components only need a `Rect` (or a parent
to attach to via Anchor).

---

## Card — generic content container

White rectangle with a subtle border and shadow, optional title bar.

```python
add_card(rect, *, title=None, body=None,
         padding=0.3, fill="background", border="#E0E0E0", shadow=True)
```

- Default fill: `theme.background` (white)
- Border: 1pt `#E0E0E0`, corner radius 0.08 in
- Shadow: soft drop shadow (offset 0, blur 8, alpha 20%)
- Title (if given): 18pt bold `theme.head_text`, square bullet `■` prefix
- Body (if given): 16pt `theme.body_text`, line spacing 1.3

Returns the Card shape so it can be used as an Anchor reference.

---

## Metric — big number + label

For Stat 강조 / KPI Dashboard / Progress.

```python
add_metric(rect, *, value, label, unit=None, trend=None)
```

- `value`: 56pt bold `theme.accent`
- `unit`: 24pt regular `theme.body_text`, baseline-aligned with value
- `label`: 14pt `theme.body_text`, below value
- `trend`: optional "+12%" pill, accent-coloured, top-right of rect
- Wraps internally in a Card unless rect is already a Card

---

## Pill — short label / tag

```python
add_pill(rect, *, text, fill="accent", text_color="background")
```

- Rounded fully (radius = h/2)
- Padding: 0.15 horizontal, 0.06 vertical
- Font: 12pt bold, `theme.background` text on `theme.accent` fill

---

## Quote — pull quote / testimonial

```python
add_quote(rect, *, text, attribution=None)
```

- Left edge: 6pt vertical bar, `theme.accent`, full height of rect
- Body: 20pt italic `theme.body_text`, line spacing 1.4, padded 0.4 from bar
- Attribution (if given): 14pt regular `theme.body_text` with leading "— "

---

## StepBox — one step in a process

For Flow / Timeline / Customer Journey / Cycle.

```python
add_step_box(rect, *, number, title, body=None)
```

- Card with a small number circle (0.5 in diameter, `theme.accent` fill,
  `theme.background` text) anchored at TL with gap (-0.15, -0.15) so it
  half-overhangs the corner
- Title: 18pt bold `theme.head_text`
- Body (optional): 14pt `theme.body_text`

---

## When the LLM should pick which

| Need | Component |
|---|---|
| Generic content box | **Card** |
| Show a single number prominently | **Metric** |
| Tag / category / status label | **Pill** |
| Customer testimonial / call-out quote | **Quote** |
| Numbered step in a process | **StepBox** |

If none fit, fall back to a plain `add_text` inside a Card-styled rect.
**Do not** mix Card + manual `add_rect` for the same purpose — pick one.

---

## Pattern → recommended components

These are defaults. The LLM may deviate only with reason.

| Pattern | Default components |
|---|---|
| Cover | Plain `add_text` (no master) |
| Section Divider | Plain `add_text` (no master) |
| Bullet List | `Card` per bullet, stacked vertically |
| Stat 강조 (Big Number) | `Metric` × 1–3 in Grid |
| KPI Dashboard | `Metric` × 3–4 in Grid |
| 3-Column Cards | `Card` × 3 in Grid |
| 3-Card Highlights | `Card` × 3 in Grid |
| Featured Callout | `Card` (large, accent border) + `Pill` |
| Icon Grid | `Card` × N in horizontal Stack with wrap |
| Pros & Cons | `Card` × 2 in Grid (col 1–6 / 7–12) |
| Matrix 비교 | `Card` cells in Grid |
| Comparison Table | `Card` cells in Grid |
| Timeline | `StepBox` × N in horizontal Stack |
| Flow 다이어그램 | `StepBox` × N + Anchor arrows |
| Cycle / Loop | `StepBox` × N + Anchor arrows in a ring |
| Funnel | `Card` × N in vertical Stack with shrinking widths |
| As-Is / To-Be | `Card` × 2 in Grid + central Anchor arrow |
| Spectrum | `Card` × 2 endpoints + central label |
| Pyramid | `Card` × N stacked, widths shrinking upward |
| Hub & Spoke | `Card` (centre, MC anchor) + `Card` × N anchored around |
| 인용 (Quote) | `Quote` × 1 |
| Big Statement | Plain `add_text` (large), centred |
| Problem-Solution-Benefit | `Card` × 3 in Grid |
| Headline + Image | Plain `add_text` + `add_image` in Grid |
| Photo + Caption | `add_image` + `Card` (caption) Anchor below |

Patterns not listed: use Grid + Card by default.
