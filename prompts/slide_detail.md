You expand a single slide outline into a structured RECIPE plan.

A *recipe* is a named slide layout pattern. You pick ONE recipe by name and
fill its data. You DO NOT decide geometry, zone counts, or coordinates —
the recipe compiler handles that.

================================================================================
## RECIPE CATALOG (pick exactly one by name)
================================================================================

{recipe_cards}

================================================================================
## CONTRACT
================================================================================

1. Pick ONE recipe by its snake_case name from the catalog.
2. The `data` keys MUST match the chosen recipe's data schema EXACTLY.
3. Slide 1 (`position_in_deck=first`) MUST use the `cover` recipe.
4. Last slide (`position_in_deck=last`) SHOULD use `thesis`.
5. Section divider slides (`position_in_deck=section_divider`) — for now use
   `single_bullets` with a 1-item summary, until a dedicated recipe exists.
6. For middle body slides, pick the recipe that fits the data shape.
   FIRST check if numbers are present in the raw_facts — visualize numbers
   instead of bullet-listing them:

   **Numeric data → visualization recipes (preferred when applicable)**
   - 1 dominant number with supporting context → `headline_metric`
     (ex: "92%가 도입", "ChatGPT 2개월 1억 명")
   - 3-4 parallel KPIs (no single dominant) → `kpi_dashboard_2x2`
     (ex: 시장 지표 4개를 한 슬라이드에)
   - 2-6 items being compared on one numeric axis → `bar_compare_h`
     (ex: "Threads 5일, ChatGPT 60일, TikTok 270일")

   **Text data → text recipes**
   - 1 idea → `single_bullets`
   - 2 parallel ideas (Pros/Cons, As-Is/To-Be) → `split_bullets`
   - 2 categories × 2 attributes → `matrix_2x2_compare`

7. **숫자 강제 시각화**: raw_facts 안에 숫자(%, 배, 일, 명, 억 등)가 하나라도
   있으면 metric 계열 recipe(`headline_metric` / `kpi_dashboard_2x2` /
   `bar_compare_h`) 중 하나를 **우선** 검토해야 한다.
   - 단일 압도 숫자 → `headline_metric`
   - 동등 숫자 4개 → `kpi_dashboard_2x2`
   - 동일 단위 비교 2~6개 → `bar_compare_h`

   숫자가 있는데도 텍스트 recipe를 골랐다면 `rationale`에 그 사유를
   "no-numeric-anchor: …" 형식으로 명시해야 한다 (예: 숫자가 단순 인용일 뿐
   주제가 아닌 경우). 사유 없이 텍스트 recipe를 고르면 거절된다.

================================================================================
## head_message 작성 기준 — 회의 보고서 톤 (명사형 개조식, 강제)
================================================================================

이 deck는 회의 보고서다. head_message는 슬라이드의 **소제목**.
**명사형 종결**이 표준. 5개 기준 모두 통과 필수.

1. **명사형 종결** — 의문형·동사 종결 절대 금지.
   ❌ "AI는 일을 재구성한다", "어떻게 대처해야 할 수 있을지"
   ✅ "AI 활용 직무 재구성 양상", "조직 차원 대응 방안"
   좋은 종결: 계획 / 방안 / 현황 / 사례 / 양상 / 분석 / 동향 / 결과

2. **구체적 보고 주제** — 막연 라벨 금지.
   ❌ "AI의 영향" / "도입률"
   ✅ "AI 일하는 방식 변화 분석" / "Fortune 500 도입 현황"

3. **단일 주제**. "와 / 그리고 / 및" 묶음 의심.

4. **25자 이하**.

5. **자연스러운 보고서 한국어**. 직역체 금지.

**중요**: outline의 head_message가 위 기준에 어긋나면 **반드시 다듬어서 출력**한다.
의미는 보존하면서 명사형으로 변환한다.

| 어긋난 outline | 다듬은 출력 |
|---|---|
| "AI는 일을 재구성한다" | "AI 활용 직무 재구성 양상" |
| "92%가 이미 도입했다" | "Fortune 500 도입률 92% 도달" |
| "어떻게 대처해야 할까" | "조직 대응 방안 제언" |
| "ChatGPT 2개월에 1억 명" | "ChatGPT 1억 MAU 달성 사례" |

================================================================================
## OUTPUT SHAPE — strict
================================================================================

Output ONLY a JSON object in a ```json ... ``` code block with EXACTLY these keys:

```json
{{
  "slide_no": <int>,
  "head_message": "<≤25자 명사형 종결, 회의 보고서 톤>",
  "sub_message": "<one supporting line, optional, can be null>",
  "intent": "<one phrase: comparison | summary | matrix-compare | cover | thesis | ...>",
  "rationale": "<one sentence: why this recipe for this content>",
  "recipe": "<recipe name from catalog>",
  "data": {{ ...recipe-specific... }}
}}
```

================================================================================
## WORKED EXAMPLES
================================================================================

### A — cover (slide 1)

```json
{{
  "slide_no": 1,
  "head_message": "AI 시대 — 변화의 한복판",
  "sub_message": null,
  "intent": "deck opening",
  "rationale": "표지 슬라이드는 cover recipe만 사용",
  "recipe": "cover",
  "data": {{
    "title": "AI 시대 — 변화의 한복판",
    "sub": "기회와 위기, 우리의 선택",
    "label": "Briefing",
    "meta": "2026.05"
  }}
}}
```

### B — headline metric (PREFER this over single_bullets when raw_facts has a dominant number)

```json
{{
  "slide_no": 4,
  "head_message": "Fortune 500 도입률 92% 도달",
  "sub_message": "도입 단계에서 운영 단계로 이동 중",
  "intent": "single dominant number with supporting context",
  "rationale": "92%라는 단일 압도 숫자 + 부연 3개 → headline_metric 적합",
  "recipe": "headline_metric",
  "data": {{
    "metric": {{
      "value": "92", "unit": "%",
      "label": "Fortune 500 생성형 AI 도입/검토",
      "trend": "+11pp YoY"
    }},
    "context_title": "배경",
    "context_items": [
      "도입 → 운영 단계로 빠르게 이동",
      "비도입 기업의 경쟁 압력 가중",
      "Capex보다 Opex 모델 채택 가속"
    ]
  }}
}}
```

### B' — single bullet body slide (only when no numeric anchor exists)

```json
{{
  "slide_no": 6,
  "head_message": "AI 활용 직무 재구성 양상",
  "sub_message": null,
  "intent": "qualitative conclusion supported by 3 facts",
  "rationale": "수치 anchor가 없어 텍스트 결론 + 근거 3개 구조",
  "recipe": "single_bullets",
  "data": {{
    "title": "재구성의 양상",
    "items": [
      "사라지는 일이 아닌 재구성되는 일",
      "AI 협업 비중이 직무 평가의 핵심",
      "신입 채용 평가에 AI 활용 능력 포함"
    ]
  }}
}}
```

### C — As-Is / To-Be split

```json
{{
  "slide_no": 8,
  "head_message": "사무 자동화 As-Is/To-Be 비교",
  "sub_message": null,
  "intent": "before/after comparison",
  "rationale": "As-Is와 To-Be를 좌우로 평행 비교",
  "recipe": "split_bullets",
  "data": {{
    "left":  {{"title": "As-Is", "items": ["보고서 수동 작성", "회의록 사후 정리"]}},
    "right": {{"title": "To-Be", "items": ["보고 템플릿 자동", "회의록 실시간 요약"]}},
    "ratio": "6_6"
  }}
}}
```

### D — 2×2 matrix

```json
{{
  "slide_no": 12,
  "head_message": "자동화 추진 우선순위 매트릭스",
  "sub_message": "현수준 vs 추진계획 — 영역별 격차",
  "intent": "two-dimension comparison matrix",
  "rationale": "두 영역 × 두 시점의 격차를 교차 비교",
  "recipe": "matrix_2x2_compare",
  "data": {{
    "col_headers": ["현수준", "추진계획"],
    "row_labels":  ["공장 자동화", "사무 자동화"],
    "cells": [
      [{{"primitive": "bullet_block", "data": {{"items": ["수동 검사", "분산 데이터"]}}}},
       {{"primitive": "bullet_block", "data": {{"items": ["비전 AI 검사", "통합 OEE"]}}}}],
      [{{"primitive": "bullet_block", "data": {{"items": ["문서 수동", "보고서 반복"]}}}},
       {{"primitive": "bullet_block", "data": {{"items": ["사내 RAG", "템플릿 자동"]}}}}]
    ]
  }}
}}
```

### E — closing thesis

```json
{{
  "slide_no": 20,
  "head_message": "전사 차원 대응 방향 제언",
  "sub_message": null,
  "intent": "closing thesis",
  "rationale": "마무리는 한 문장의 thesis",
  "recipe": "thesis",
  "data": {{
    "text": "AI는 도구다. 도메인 전문성이 차별점이 된다.",
    "attribution": "Strategy Team"
  }}
}}
```

================================================================================
## SLIDE OUTLINE (this slide)
================================================================================

- slide_no: {slide_no}
- purpose: {purpose}
- head_message: {head_message}
- position_in_deck: {slide_position}
- section_id: {section_id}

Recently used recipes (last few slides): {recent_recipes}
→ Prefer a recipe NOT in that list, unless content truly requires repetition.

================================================================================
## RELEVANT SECTION CONTENT (raw facts)
================================================================================

{section_facts}

================================================================================
## NOW PRODUCE THE JSON
================================================================================

Reply with ONLY the JSON object inside a ```json ... ``` code block.
