# Phase 1 — 3-tier 헤더 시스템

날짜: 2026-05-04
상태: 구현 완료
관련 코드: `src/pptx/primitives.py`, `src/pptx/renderer.py`, `src/pipeline/planner.py`

## 무엇을 바꿨는가

`apply_master`가 그리던 2-tier 헤더(28pt head_message + 18pt sub_message)를
3-tier로 재구성:

| Tier | 출처 | 폰트 | 의미 |
|------|------|------|------|
| 1 | `content.sections[i].topic` (deck-level) | 28pt bold | 섹션 정체성 |
| — | — | 1.5pt accent rule | 시각적 분리 |
| 2 | LLM의 `head_message` (slide-level) | 18pt bold ■ | 슬라이드 결론 |
| 3 | LLM의 `sub_message` (slide-level, 옵션) | 16pt - | 보조 설명 |

## 왜 이렇게 해야 했는가

### 문제 1 — 의미 계층의 혼선

기존 구조에서 `head_message`가 28pt로 가장 크게 그려졌다. 그런데 사용자가
디자인한 reference 슬라이드를 분석해 보면 28pt 자리는 **섹션 제목**(deck 전체에
걸쳐 동일 섹션이면 같은 문구)이고, 슬라이드별 메시지는 18pt ■ 위치였다.

즉 `head_message`라는 이름은 같은데, **2-tier 구현에서는 슬라이드별 메시지가
섹션 제목 자리에 박혀 있었다.** 이는 다음 두 모순을 낳는다:

1. 한 섹션의 슬라이드 5장이 모두 다른 28pt 텍스트로 시작 → deck 톤 무너짐
2. LLM은 매 슬라이드마다 28pt에 들어갈 적당한 문구를 새로 만들어야 함 → 의미 중복

### 문제 2 — 일관성 보장 불가능

섹션 제목을 슬라이드마다 LLM이 결정하면, 같은 섹션 안에서도 표현이 흔들린다
(예: "변화의 규모" vs "AI의 규모와 속도"). 이걸 후처리로 통일하려면 섹션별
canonical 문자열 합의 로직이 또 필요하다 — 비용 대비 효과 ↓.

### 대안과 그 한계

| 대안 | 왜 안 되는가 |
|---|---|
| **A. LLM에게 "섹션 제목 톤을 일관되게" 지시** | 규모가 큰 deck에서 LLM이 기억력 한계로 어김. 검증 불가능. |
| **B. content.json의 section.topic을 그대로 사용하되, head_message에 prepend** | 28pt + 18pt가 한 줄에 묶임. 시각적 위계 깨짐. |
| **C. 별도 layout 변수로 master 자체를 PPT layout에 넣기** | python-pptx의 layout 슬라이드 placeholder 동작이 복잡·취약. 동적 텍스트 주입에 부적합. |
| **D. 본 설계 — apply_master가 데이터로 받아 그리기** | 코드 레벨에서 결정론적. content.json이 단일 진실. |

D를 선택한 이유: **3-tier 분리가 "deck-level vs slide-level" 책임 경계와 정확히
일치**하기 때문이다. tier 1은 콘텐츠 작성자(content.json)가 한 번만 정하면 끝.
tier 2/3은 LLM의 슬라이드별 책임. apply_master는 둘을 받아 결정론적으로 그릴 뿐.

## 데이터 흐름

```mermaid
flowchart LR
    A[content.json] -->|sections[].topic| B[derive_deck_meta]
    B -->|section_titles map| C[deck_meta]
    C --> D[render_slide]
    E[planner LLM] -->|head_message + sub_message| F[slide plan]
    F --> D
    D -->|section_id lookup| G[apply_master]
    C --> G
    G -->|tier 1 28pt| H[(slide)]
    G -->|tier 2 18pt| H
    G -->|tier 3 16pt| H
```

## 구현 핵심

### `derive_deck_meta` 확장 (planner.py)

```python
section_titles = {sec["id"]: sec.get("topic") or "" for sec in content["sections"] if sec.get("id")}
deck_meta["section_titles"] = section_titles
```

deck 레벨에서 한 번만 만든다. 슬라이드 렌더 시점에는 lookup만.

### `apply_master` 시그니처 (primitives.py)

```python
def apply_master(slide, deck_meta, *,
                 head_message: str,
                 section_title: str | None = None,
                 sub_message: str | None = None,
                 ...) -> Rect:
```

- `section_title=None`이면 tier 1을 건너뛰고 head_message는 그 자리(승격 X).
  → section_id가 없는 슬라이드도 깨지지 않음.

### `render_slide` 매개 (renderer.py)

```python
section_titles = deck_meta.get("section_titles") or {}
section_title = section_titles.get(plan.get("section_id"))
apply_master(..., section_title=section_title, ...)
```

LLM 출력에는 손대지 않는다. 매개는 100% 코드 책임.

## 예상 효과

| 효과 | 메커니즘 |
|---|---|
| **deck 톤 일관성** | 같은 섹션의 모든 슬라이드가 28pt에서 동일 문자열 → 시각 톤 자동 정렬 |
| **LLM 토큰 절약** | LLM이 매 슬라이드마다 섹션 제목을 재생성할 필요 없음 |
| **content.json이 단일 진실** | 섹션 제목 변경 = content.json 한 줄 수정 |
| **슬라이드 헤더의 정보 밀도 ↑** | 청중이 헤더만 봐도 "어떤 섹션의 어떤 결론인가"를 0.5초에 파악 |

## 알려진 제한

- `full_canvas` 슬라이드(cover/thesis 등)는 apply_master를 거치지 않음 → 3-tier
  헤더가 그려지지 않는다. 의도된 동작 (cover는 별도 톤).
- 사용자가 sub_message를 안 주면 tier 3은 비고, body 영역이 그만큼 위로 확장.
  → 의도된 가변 레이아웃.

## 검증

- `tests/test_renderer.py`: 4개 테스트 모두 통과.
- `data/sample_zone_plan.json`: section_titles 추가 후 slide 2~5에서 3-tier 확인.
