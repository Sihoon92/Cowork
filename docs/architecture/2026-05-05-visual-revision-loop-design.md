# Visual Revision Loop — 설계 결정 기록

작성일: 2026-05-05
상태: 설계 확정 → Phase A 구현 진입

## 1. 배경

기존 파이프라인은 deck-level critique(storyline + visual grid)을 정보 표시용으로만 수행했다. 슬라이드 단위로 "비주얼 결함을 보고 plan을 고치는" 루프가 없어 다음 결함이 그대로 출력에 남았다:

- 텍스트 박스 overflow / 잘림
- 도형·텍스트 겹침
- 위계 역전 (sub_message가 head보다 두드러짐)
- head_message가 시각요소와 grounding 안 됨

per-slide 비평·수정 루프를 추가해 위 결함을 자동 교정한다.

## 2. 결정사항 요약

| 분기 | 선택 | 근거 |
|---|---|---|
| 캡처 시점 | merge 후 final deck 일괄 | COM 기동 1회로 비용 절감 |
| 캡처 방식 | **실제 스크린샷 (PrintWindow API)** | NASCA 보안 프로그램이 `Slide.Export` 차단 가능. PrintWindow는 다른 레이어라 통과 기대 |
| PowerPoint 모드 | 슬라이드쇼 (`SlideShowSettings.Run`) | 발표 시 보이는 픽셀 그대로 = 비평 기준 명확 |
| 수정 방식 | plan 패치 → re-render | 결정론적 렌더 단계 보존, 의미 레이어만 변경 |
| 최대 반복 | 3 | 시간보다 품질 우선 |
| 비평 단위 | per-slide (이번 단계는 직렬) | 안정화 후 병렬 검토 |
| Critic 프롬프트 | 7축 체크리스트 | 자유 비평은 truism 양산 |
| Patcher 스코프 | 화이트리스트 6 op | LLM 환각이 plan을 직접 깨뜨리지 않도록 차단 |
| Stagnation 처리 | 마지막 iter는 가장 가벼운 패치만 | 무한 반복·후퇴 방지 |
| 산출물 저장 | 모든 iter PNG·critique·patch 디스크 보관 | 디버깅 + 사용자 검증 |

## 3. 파이프라인 변경

```
... 기존 Stage 1~4 (merge) ...
   ↓
[Stage 5 NEW] visual_revision_loop  (max 3 iterations)
   ┌─────────────────────────────────────────────────────────┐
   │ for iteration in 1..3:                                  │
   │   5a. screenshot_all(merged_pptx) → list[PNG]           │
   │   5b. for each (slide_no, png):                         │
   │         critic = LLM_visual_critic(png, plan[slide_no]) │
   │   5c. issues = aggregate(critics)                       │
   │   5d. if all severity < medium: BREAK                   │
   │   5e. patcher = LLM_plan_patcher(issues, plan)          │
   │   5f. plan = apply_patch(plan, patcher.changes)         │
   │   5g. for each changed slide:                           │
   │         re-render that single slide_NN.pptx             │
   │   5h. re-merge → new merged_pptx                        │
   └─────────────────────────────────────────────────────────┘
   ↓
[Stage 6] deck-level critique (storyline + 최종 visual)
```

## 4. 비평 7축 (per-slide critic 프롬프트)

| 코드 | 축 | 판정 기준 |
|---|---|---|
| `overflow` | 텍스트가 박스 경계 침범/잘림 | 절대 허용 안 함 |
| `collision` | 도형·텍스트 겹침 | 절대 허용 안 함 |
| `alignment` | 정렬 일관성 | 동일 위계는 동일 정렬 |
| `whitespace` | 한쪽 쏠림 / 거대 빈 공간 | 시각적 균형 |
| `hierarchy` | head > sub > body 위계 | head가 가장 두드러져야 |
| `readability` | 대비·폰트 크기 | 본문 ≥14pt, 충분한 대비 |
| `data_grounding` | head 주장과 시각요소 부합 | 차트 방향이 head와 반대면 fail |

각 축별 출력: `{verdict: ok|warn|fail, severity: low|medium|high, msg, suggestion}`

## 5. Patcher op 화이트리스트

| op | 의미 | 영향 |
|---|---|---|
| `shorten_head` | head_message 더 짧게 (new_text) | overflow |
| `truncate_bullets` | bullets/narratives 개수 줄이기 (keep) | overflow, whitespace |
| `change_intent` | intent_label 변경 → selector가 다른 recipe 선택 | 시각화 자체 변경 |
| `drop_metric` | metrics 배열에서 1개 제거 (index) | 4-metric dashboard 과밀 |
| `swap_emphasis` | 강조 metric 교체 | hero number 변경 |
| `rewrite_takeaway` | key_takeaway 재작성 (new_text) | data_grounding 약함 |

**금지**: font_size/color/position 같은 픽셀 단위 패치 — recipe layer 책임. plan은 의미 레벨만 건드림.

**적용 후 검증**: deterministic checks (checks.py) 재실행. 실패한 op는 롤백, 다른 op는 살림.

## 6. 추상화 레이어와 다양성

```
Layer 1: raw_facts (자유 텍스트, 무한)
Layer 2: 자유 텍스트 필드 (head/takeaway/narratives/quotes ...) ← LLM 자유
Layer 3: intent_label (12 화이트리스트) ← 1차 좁아짐
Layer 4: recipe (intent에 1:1 매핑) ← 2차 좁아짐
Layer 5: data (recipe 요구 구조)
Layer 6: primitive (Rect/add_text/set_bg) ← 픽셀 단위 고정
```

| 다양성 종류 | 결정 위치 | 현재 수준 |
|---|---|---|
| 의미적 (메시지·인사이트) | Layer 2 | 거의 무한 |
| 구조적 (레이아웃·차트) | Layer 3~4 | 12종 |
| 시각적 (색·여백) | Layer 6 | 매우 한정 |

**Patcher는 Layer 3~4 안에서만 작동** — 천장은 그대로, 그 밑에서 안전한 변형만. 다양성 손실 없음.

다양성 확장이 필요할 때 손댈 곳:
- 톤 다양화 → Layer 2 프롬프트
- 레이아웃 추가 → Layer 3~4 (recipe 신규)
- 색 팔레트 → Layer 6 / theme 분리

## 7. 단계별 구현 계획

### Phase A — 캡처 인프라 (LLM 무관, 가장 위험)
- `src/pptx/capture.py`: `screenshot_deck(pptx_path, out_dir, *, wait_per_slide=1.0) -> list[Path]`
- `scripts/smoke_capture.py`: 회사 PC에서 NASCA 통과 단독 검증
- fallback: PrintWindow 실패 시 mss, 둘 다 실패면 명시적 에러

### Phase B — Per-slide visual critic
- `prompts/slide_visual_critic.md`: 7축 체크리스트
- `src/pipeline/slide_critic.py`: PNG + plan slice → critique
- pydantic `SlideCritique`

### Phase C — Plan patcher
- `prompts/plan_patcher.md`: 6 op 화이트리스트 강제
- `src/pipeline/patcher.py`: critique → ops → `apply_patch(plan, ops)`
- 적용 후 deterministic check 재실행, 실패 op 롤백

### Phase D — Revision loop 통합
- `builder.py` Stage 5 자리
- `workdir/iter_N/` 디렉터리에 PNG·critique·patch 보관
- 종료: severity 모두 low or max=3 도달 or stagnation
- 부분 re-render + re-merge

### Phase E — 안전망
- `try/finally`로 PowerPoint 인스턴스 누수 방지
- 같은 시간에 다른 deck 빌드 동시 방지 (lockfile)
- 캡처 1장당 timeout (10초), placeholder PNG 대체

## 8. 미해결·확인 필요

- NASCA가 PrintWindow도 차단할 가능성 → 회사 PC smoke test 필수
- 듀얼 모니터 환경에서 슬라이드쇼가 어느 모니터에 뜨는지 제어 필요할 수 있음
- 캡처 해상도 (모니터 종속) → vision LLM 입력 적합성
