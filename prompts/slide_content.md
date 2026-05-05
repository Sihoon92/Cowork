You are a senior analyst preparing a single slide for an executive briefing.

Run TWO PHASES in order in your head, then emit ONE JSON object.

================================================================================
## PHASE 1 — So-what Interrogation
================================================================================

Pretend a skeptical executive is in the room. After you state any fact they
will fire back "그래서 뭐?" — you cannot answer with truisms. Generate at
least TWO Q&A pairs from these three categories:

- WHY        이 사실이 왜 중요한가? 함의는?
- HOW_MUCH   영향의 규모·범위·비교 대상은?
- WHAT_NEXT  의사결정·행동에 무엇을 시사하는가?

For each Q&A:
- evidence: list of raw_facts indices (e.g. ["raw[0]", "raw[2]"]) you pulled
  the answer from. If you cannot ground the answer in raw_facts, leave
  evidence as [] and put a brief "근거 부족 — ..." note in answer.
- feeds: which slide element this answer flows into. Choose from
  head_message / key_takeaway / metric.comparison / narratives / quotes.

REJECT truisms. "AI가 중요하다", "빠르게 도입해야 한다" are forbidden.
Every answer must contain a specific comparison, mechanism, or number.

================================================================================
## PHASE 2 — Compose slide content (driven by PHASE 1 answers)
================================================================================

Using the so-what answers as your raw material, fill these fields:

### intent_label (single category — pick exactly ONE)

| intent_label             | use when                                                   |
|--------------------------|------------------------------------------------------------|
| deck_opening             | This is slide 1 (cover).                                   |
| closing_thesis           | This is the last slide (sums up the whole deck).           |
| section_transition       | This slide marks a new section opening.                    |
| single_metric_emphasis   | One dominant number is the headline; rest is supporting.   |
| multi_metric_dashboard   | Exactly 4 parallel KPIs of comparable importance.          |
| numeric_comparison       | 2-6 items being compared on one numeric axis (same unit).  |
| two_dim_compare          | Two categories (cols) × two attributes (rows). 2x2 cells.  |
| before_after             | A transformation: As-Is → To-Be.                           |
| sequence_or_timeline     | 3-5 steps/phases in time order.                            |
| quotation                | A single quote is the centerpiece.                         |
| parallel_compare         | Two parallel ideas (Pros/Cons, A/B), text-heavy.           |
| general_facts            | Several text facts, no single dominant number. Default.    |

If the raw_facts contain numbers, prefer a metric-related intent
(single_metric_emphasis / multi_metric_dashboard / numeric_comparison) over
text-based intents.

### head_message — Standalone meaningful (CRITICAL)

The headline must STAND ALONE. A reader who only sees the headline must get
the slide's conclusion. If "그래서 뭐?" is a natural reaction, it's wrong.

5 hard rules (all must pass):

1. Standalone — contains at least 2 of [subject, specific fact/number,
   implication]. Examples:
   - GOOD: "ChatGPT, 2개월 만에 1억 사용자 — 역대 최단"
   - GOOD: "Fortune 500의 92%가 이미 생성형 AI 도입"
   - GOOD: "AI 격차가 신입 채용 차별 요인으로 부상"
   - BAD:  "AI의 영향" (label only)
   - BAD:  "ChatGPT 1억 사용자 달성 사례" ("그래서 뭐?")
   - BAD:  "AI는 어떻게 변화시키는가" (question form)
2. One topic only. No "와/그리고/및" joining two subjects.
3. No question form. Do NOT end with `?` or `~까/~는가/~할까`.
4. One line. Roughly ≤30 Korean chars / ≤80 English chars.
5. Korean reads naturally (no 직역체).

Set head_derivation to indicate which so_what answers you wove in,
e.g. "so_what[0]+[1]".

### key_takeaway — Different layer from head_message

- head_message = the FACT/CONCLUSION that goes in the slide header.
- key_takeaway = the INSIGHT/ACTION the audience walks away with.

If they would be 70%+ similar in wording, rewrite the takeaway. The takeaway
typically draws from a WHAT_NEXT answer (or the implication of WHY).

Set key_takeaway_derivation to indicate which so_what answer it came from.

### knowledge — Universal facts + intent-specific structures

Universal fields:
- metrics: list of objects with value/unit/label/sub_label?/trend?/comparison?
- narratives: list of objects with text/sub?
- quotes: list of objects with text/attribution?/context?

Plus, depending on intent_label, fill the matching structured field:

| intent_label             | required structured field         |
|--------------------------|-----------------------------------|
| two_dim_compare          | knowledge.matrix                  |
| before_after             | knowledge.transformation          |
| sequence_or_timeline     | knowledge.timeline                |
| (others)                 | none — universal fields only      |

Metric format rules (for every entry in knowledge.metrics):
- value is ALWAYS a string ("1.5억", "92", "5.2배" all fine)
- label ≤25 chars, no question form, no trailing punctuation
- trend (optional) MUST contain a sign or direction word
  (e.g. "+11pp YoY", "역대 최단", "5배 증가"). Otherwise omit it.
- comparison (optional): a comparative phrase like "Threads 5일 vs 60일"

Matrix structured shape (when intent_label = two_dim_compare):
- col_headers: array of exactly 2 strings
- row_labels:  array of exactly 2 strings
- cells: 2x2 array; each cell has `bullets` array of strings

Transformation structured shape (when intent_label = before_after):
- as_is: object with title + items
- to_be: object with title + items
- arrow_label: optional short string

Timeline structured shape (when intent_label = sequence_or_timeline):
- nodes: array of 3-5 objects, each with when + title + note?

================================================================================
## OUTPUT — strict JSON shape
================================================================================

Output ONLY a JSON object inside a ```json ... ``` code block. NO prose.

```json
{{
  "slide_no": <int>,
  "section_id": "<id or null>",
  "intent_label": "<one of the categories above>",
  "so_what": [
    {{"type": "WHY", "question": "...", "answer": "...",
      "evidence": ["raw[0]"], "feeds": ["head_message"]}},
    {{"type": "HOW_MUCH", "question": "...", "answer": "...",
      "evidence": ["raw[1]"], "feeds": ["metric.comparison"]}}
  ],
  "head_message": "<one-line standalone, 명사구 또는 짧은 서술>",
  "head_derivation": "so_what[0]+[1]",
  "key_takeaway": "<청중이 가져갈 insight/action>",
  "key_takeaway_derivation": "so_what[0]",
  "knowledge": {{
    "metrics": [],
    "narratives": [],
    "quotes": [],
    "matrix": null,
    "transformation": null,
    "timeline": null
  }}
}}
```

================================================================================
## WORKED EXAMPLES
================================================================================

### Example A — single_metric_emphasis

Input outline:
- slide_no: 2, section_id: scale, head_draft: "ChatGPT 1억 사용자 달성"
- raw_facts:
  [0] ChatGPT 출시 2개월 만에 월간 활성 사용자 1억 명 돌파 (역대 가장 빠른 속도)
  [1] Threads 5일, TikTok 9개월
  [2] OpenAI 단일 진입점 효과
  [3] 엔터프라이즈 전환 가속

```json
{{
  "slide_no": 2,
  "section_id": "scale",
  "intent_label": "single_metric_emphasis",
  "so_what": [
    {{"type": "WHY",
      "question": "1억 사용자가 왜 중요한가?",
      "answer": "단일 자연어 인터페이스가 채택 마찰을 사라지게 했음 — 인터넷 시대 어떤 서비스보다 빠른 보급",
      "evidence": ["raw[0]", "raw[2]"],
      "feeds": ["head_message", "key_takeaway"]}},
    {{"type": "HOW_MUCH",
      "question": "다른 서비스와 비교하면 얼마나 빠른가?",
      "answer": "Threads 5일은 outlier(기존 사용자풀). TikTok 9개월·Instagram 2.5년 대비 4~10배 빠름",
      "evidence": ["raw[1]"],
      "feeds": ["metric.comparison"]}}
  ],
  "head_message": "ChatGPT, 2개월 만에 1억 사용자 — 역대 최단",
  "head_derivation": "so_what[0]+[1]",
  "key_takeaway": "AI 채택 속도가 인터넷 시대를 능가 — 대응 지연 = 격차",
  "key_takeaway_derivation": "so_what[0]",
  "knowledge": {{
    "metrics": [
      {{"value": "1억", "unit": "명", "label": "MAU 도달까지 60일",
        "sub_label": "2023.01 기준", "trend": "역대 최단",
        "comparison": "Threads 5일·TikTok 9개월 vs ChatGPT 60일"}}
    ],
    "narratives": [
      {{"text": "OpenAI 단일 진입점 효과"}},
      {{"text": "엔터프라이즈 전환 가속"}}
    ],
    "quotes": []
  }}
}}
```

### Example B — two_dim_compare

```json
{{
  "slide_no": 5,
  "section_id": "action",
  "intent_label": "two_dim_compare",
  "so_what": [
    {{"type": "WHY",
      "question": "왜 두 차원으로 비교해야 하는가?",
      "answer": "영역별 As-Is 격차가 추진 우선순위를 결정함",
      "evidence": ["raw[0]", "raw[2]"],
      "feeds": ["head_message"]}},
    {{"type": "WHAT_NEXT",
      "question": "어디부터 시작?",
      "answer": "사무 자동화 격차가 작아 quick win — 공장은 R&D 동반",
      "evidence": ["raw[3]"],
      "feeds": ["key_takeaway"]}}
  ],
  "head_message": "자동화 추진 — 영역별 격차로 우선순위 결정",
  "head_derivation": "so_what[0]",
  "key_takeaway": "사무 quick win → 공장 R&D 동반 단계적 확산",
  "key_takeaway_derivation": "so_what[1]",
  "knowledge": {{
    "metrics": [], "narratives": [], "quotes": [],
    "matrix": {{
      "col_headers": ["현수준", "추진계획"],
      "row_labels":  ["공장 자동화", "사무 자동화"],
      "cells": [
        [{{"bullets": ["수동 검사 의존", "데이터 분산"]}},
         {{"bullets": ["비전 AI 검사", "통합 OEE"]}}],
        [{{"bullets": ["보고서 수동", "검색 비효율"]}},
         {{"bullets": ["사내 RAG", "템플릿 자동"]}}]
      ]
    }}
  }}
}}
```

### Example C — before_after

```json
{{
  "slide_no": 8,
  "section_id": "action",
  "intent_label": "before_after",
  "so_what": [
    {{"type": "WHY",
      "question": "사무 자동화가 왜 시급한가?",
      "answer": "수작업 시간이 핵심 직무 능력으로 재할당 가능",
      "evidence": ["raw[1]"], "feeds": ["head_message"]}},
    {{"type": "WHAT_NEXT",
      "question": "전환 단계는?",
      "answer": "RAG·템플릿부터 점진적 도입",
      "evidence": ["raw[2]"], "feeds": ["key_takeaway"]}}
  ],
  "head_message": "사무 자동화 — 수동에서 자동 워크플로로 전환",
  "head_derivation": "so_what[0]",
  "key_takeaway": "RAG·템플릿 PoC → 전사 확산 순으로",
  "key_takeaway_derivation": "so_what[1]",
  "knowledge": {{
    "metrics": [], "narratives": [], "quotes": [],
    "transformation": {{
      "as_is": {{"title": "As-Is", "items": ["보고서 수동 작성", "회의록 사후 정리", "문서 검색 비효율"]}},
      "to_be": {{"title": "To-Be", "items": ["보고 템플릿 자동", "회의록 실시간 요약", "사내 RAG 챗봇"]}},
      "arrow_label": "AI 도입"
    }}
  }}
}}
```

================================================================================
## SLIDE OUTLINE (this slide)
================================================================================

- slide_no: {slide_no}
- section_id: {section_id}
- head_draft (you may rewrite): {head_draft}
- position_in_deck: {slide_position}
- recently used intents (last few slides): {recent_intents}
  → prefer an intent NOT in this list unless the content truly demands repetition

================================================================================
## RAW FACTS (your source material)
================================================================================

{section_facts}

================================================================================
## NOW PRODUCE THE JSON
================================================================================

Reply with ONLY the JSON object inside a ```json ... ``` block. No prose.
