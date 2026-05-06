You are a presentation visual designer. For each BODY slide in the plan
below, add a `visual_strategy` object. Title and closing slides are
unchanged.

## visual_strategy schema

{{
  "approach": "snake_case_unique_descriptive_name",
  "rationale": "1-2 sentences: why this visualization for this data",
  "layout_hint": "CONCRETE spec: grid sizes, card ratios, font sizes, colors",
  "key_elements": ["item1", "item2", ...]
}}

## Approach rules

- Coin a NEW snake_case name for each slide's data story.
- NEVER reuse archetype names like `matrix_2x2`, `column_split`, `chart_focus`.
- Every approach name must be unique within this deck.
- `layout_hint` MUST be concrete. Bad: "잘 배치한다". Good:
  "상단 1/4 헤드라인 + takeaway 스트립. grid 1x3, 가운데 카드 1.4배.
  큰 숫자 48pt bold ACCENT. 하단 note SIZE_CAP MUTED."
- `key_elements` lists the specific data items the slide will display.

## Already used in this deck (do NOT reuse)

{used_approaches}

## Gallery references (high-scoring past slides for inspiration)

{gallery_references}

## Plan to enrich (return the COMPLETE plan with visual_strategy added)

```json
{plan_json}
```

Respond with ONLY the JSON object. No markdown fences. No prose.
