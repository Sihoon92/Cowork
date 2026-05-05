# Phase 3a — Grid + Recipe Engine

날짜: 2026-05-04
상태: 진행 중
연관: `docs/architecture/2026-05-04-phase1-three-tier-header.md`,
      `docs/architecture/2026-05-04-outline-robustness.md`

## 목표

`split_x_y` enum composition + `Block` enum 모델을 폐기하고, **grid + primitive +
recipe** 3계층 모델로 교체. Clean break — 호환 레이어 없음.

LLM은 의미층(`recipe` 이름 + `data`)에서만 사고. zone 좌표·primitive 배치·
grid 산수는 컴파일러가 처리.

## 동기 (요약)

| 현재 시스템의 결함 | 새 모델이 해결하는 방식 |
|---|---|
| LLM이 zone 개수를 결정 → `expects 2 zones, got 4` 빈발 | recipe가 zone 수를 강제 |
| 행 분할 빈약 (`split_tb_3_4` 1개) | grid는 임의 행/열 표현 |
| 시각 어휘 부족 (block은 코어스, 합성 불가) | primitive 단위로 분해, recipe로 합성 |
| 새 레이아웃 추가 시 코드 + 가이드 + 카드 + 카탈로그 동시 수정 | recipe 파일 1개만 추가 |

## 단계 분리

### Stage 1 — 엔진 골격 (현재)

산출물:
- `src/pptx/primitives.py`: `Grid` 클래스
- `src/pipeline/recipes.py` (신규): `RECIPES` 레지스트리, `PrimitiveSpec`
  dataclass, recipe 컴파일 함수 시그니처 정의
- `tests/test_grid.py` (신규): Grid 셀 배치, span, gutter 단위 테스트

성공 기준: Grid 단위 테스트 통과. recipe 0개여도 import 깨지지 않음.

### Stage 2 — 첫 recipe end-to-end (LLM 미관여)

산출물:
- `src/pptx/primitives.py`에 draw 함수 3개:
  - `draw_header_strip(slide, rect, data, theme)` — navy fill + white text 띠
  - `draw_label_card(slide, rect, data, theme)` — 옅은 회색 fill + border + 가운데 텍스트
  - `draw_bullet_block(slide, rect, data, theme)` — plain ■ 글머리 + 1.5 line height
- `src/pipeline/recipes.py`에 `matrix_2x2_compare` recipe:
  - 데이터 모델 (pydantic): col_headers[2], row_labels[2], cells[2][2]{bullets[]}
  - 컴파일 함수: data → list[PrimitiveSpec]
- `src/pptx/renderer.py`: `render_slide_recipe(prs, deck_meta, plan)` 추가
  (기존 `render_slide`는 유지, 별도 함수)
- `tests/test_matrix_recipe.py` (신규): 하드코드 데이터로 사용자 reference
  슬라이드와 시각적으로 동일한 PPTX 생성

성공 기준: 사용자 매트릭스 reference와 톤·배치가 일치하는 PPTX가 LLM 없이 생성됨.

### Stage 3 — planner/prompt를 recipe 모드로 전환

산출물:
- `src/pipeline/schemas.py`에 `SlideRecipe` 모델 (recipe + data + intent
  + rationale_short + section_id + sub_message)
- `prompts/slide_detail.md` 전면 재작성 — recipe 카탈로그 + 데이터 schema 안내,
  composition/block/zone 어휘 모두 제거
- `src/pipeline/guideline_loader.py`에 `get_recipe_cards()` 추가
- `guidelines/recipes.md` (신규): recipe당 visual recipe / 언제 쓰는가 / 안 쓰는가 /
  효과 / reference JSON 경로
- `guidelines/primitives.md` (신규, 같은 형식)
- `src/pipeline/planner.py`의 `generate_slide_detail`을 recipe 출력으로 교체
- `src/pptx/renderer.py`의 `render_deck`이 recipe-aware 함수 호출

성공 기준: `scripts/run_pipeline.py data/ai_era.json`이 끝까지 실행되어
matrix recipe가 1장 이상 deck에 들어간 PPTX 산출.

### Stage 4 — 옛 시스템 제거 (clean break)

산출물:
- 삭제: `src/pptx/compositions.py`, `src/pptx/blocks.py`,
  `src/pipeline/zone_geometry.py` 중 zone-기반 로직, `src/pipeline/visual_patcher.py`의
  composition 의존부
- 갱신: `SlideDetail` 모델 제거 또는 deprecated 표시, 옛 outline schema 영향 없음
- 갱신: `tests/test_renderer.py` — 옛 zone-plan 테스트 → recipe-plan 테스트로 교체
- 갱신: `guidelines/compositions.md`, `guidelines/blocks.md` 제거 또는 history로 이동
- 갱신: `data/sample_zone_plan.json` → `data/sample_recipe_plan.json`로 교체

성공 기준: grep으로 `composition`, `BLOCKS`, `BlockName` 잔존 0건 (의도한 history 외).

### Stage 5 (Phase A) — primitive·recipe 카탈로그 확장

Stage 4까지 끝난 상태에서, 사용자 협업으로 reference 슬라이드를 1~2장씩 추가하며
primitive와 recipe를 점진적으로 늘림. 우선순위:

1. As-Is/To-Be 화살표 → primitive: `arrow`, recipe: `transformation_lr`
2. Big Number 강조 → primitive: `big_number`, recipe: `headline_metric`
3. Section Divider → primitive: `section_number`, recipe: `section_divider_strip`
4. Quote → primitive: `quote_mark`, `attribution_line`, recipe: `pull_quote`
5. Timeline → primitive: `timeline_node`, `connector_line`, recipe: `timeline_horizontal`

각 추가는 (primitive draw 함수) + (primitive 카드 .md) + (recipe 컴파일러) +
(recipe 카드 .md) + (reference JSON) + (단위 테스트) 5종 셋트.

## 의존성 그래프

```
Stage 1 (엔진 골격)
   │
   ├─→ Stage 2 (첫 recipe end-to-end)
   │      │
   │      └─→ Stage 3 (planner/prompt 전환)
   │             │
   │             └─→ Stage 4 (옛 시스템 제거)
   │                    │
   │                    └─→ Stage 5 (카탈로그 확장)
```

각 stage는 다음 stage가 시작되기 전 자체 검증을 통과해야 함.

## 핵심 설계 결정

### 결정 1 — recipe와 primitive를 분리된 레지스트리로 둔다

대안: recipe와 primitive를 한 레지스트리에 섞기.
거부 이유: 둘은 다른 추상 수준. recipe는 LLM이 선택, primitive는 LLM이 (cell-level
선택만) 한다. 같은 슬롯에 두면 LLM이 recipe 자리에 primitive를 직접 넣으려는
실수가 빈발함.

### 결정 2 — recipe 컴파일러는 PrimitiveSpec 리스트를 반환한다

대안: 컴파일러가 직접 slide에 그림.
거부 이유: 단위 테스트 어려움. PrimitiveSpec 리스트로 분리하면 (a) 컴파일 결과를
직렬화·assert 가능, (b) 다른 렌더 백엔드(예: 미리보기 이미지)로 재사용 가능.

### 결정 3 — Cell-level primitive 선택을 LLM에 위임 (사용자 결정)

각 cell에 들어갈 primitive 후보를 recipe가 제시하고, LLM이 그 중 하나를 고른다.
data 스키마는 primitive별로 다름.

```json
{
  "recipe": "matrix_2x2_compare",
  "data": {
    "col_headers": ["A", "B"],
    "row_labels":  ["X", "Y"],
    "cells": [
      [{"primitive": "bullet_block", "data": {...}},
       {"primitive": "metric",       "data": {...}}],
      [...]
    ]
  }
}
```

복잡도 ↑이지만 자유도 확보. recipe 카드에 "이 cell의 primitive 후보" 명시 필수.

### 결정 4 — Clean break, 호환 레이어 없음 (사용자 결정)

기존 deck 재생성 가능성을 포기. 이행 비용 vs 코드 단순성에서 후자 선택.

## 트레이드오프

| 항목 | 비용 | 가치 |
|---|---|---|
| Recipe 카탈로그를 사람이 정의해야 함 | 새 레이아웃 = 코드 추가 작업 | LLM 출력 검증·일관성 확보 |
| Cell-level primitive 선택 | 프롬프트 길이 ↑, 검증 룰 ↑ | recipe 1개로 N가지 변형 흡수 |
| Clean break | 기존 ai_era 결과 재현성 0 | 코드/문서 단순성 |
| LLM이 recipe·primitive 두 어휘를 알아야 함 | 프롬프트 길이 ↑ | 단어 기반 검증 가능 (좌표 산수 회피) |

## 위험 / 미정 사항

- **Cell-level primitive 검증**: recipe별로 cell이 받을 수 있는 primitive
  화이트리스트를 어떻게 표현할지 — Stage 3에서 결정.
- **단일 cell 내부에 여러 primitive 합성**: 예) cell 안에 header + bullets.
  Stage 2에서는 1 cell = 1 primitive로 단순화. Stage 5 어딘가에서 sub-recipe
  개념이 필요할 수 있음.
- **빈 cell 처리**: 매트릭스의 한 칸이 의도적으로 비어있어야 할 때. 빈 칸을
  visual placeholder로 그릴지, 무시할지 — 첫 recipe 작성 시 결정.

## 검증 체크포인트

- Stage 1 후: `python tests/test_grid.py` 통과
- Stage 2 후: `python tests/test_matrix_recipe.py` → 사용자 reference와
  육안으로 동일한 PPTX
- Stage 3 후: `scripts/run_pipeline.py data/ai_era.json` 끝까지 실행, deck에
  matrix recipe 1장 이상 포함
- Stage 4 후: `git grep -E "compositions|BLOCKS|BlockName"` → 의도된 history 외 0건
- Stage 5 후: 사용자 reference 슬라이드 5장이 deck에 분포

## 작업 순서 (이번 세션)

1. ✅ 본 계획 문서 작성
2. → Stage 1 시작 (Grid 클래스 + recipe 엔진 골격)
3. Stage 2까지 진행하고 사용자 확인 받기 (LLM 없이 매트릭스 reproduce 시점)
4. Stage 3 이후는 별도 세션에서 — 변경량이 크고 review 분기점이 필요
