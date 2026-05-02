# Gemma → PPTX 자동 생성 파이프라인 설계

**Date**: 2026-05-02
**Project**: CoWork
**Scope**: MVP (Stages 1–4)

---

## 1. 배경

CoWork 시스템의 첫 번째 기능으로 **로컬 LLM(Ollama gemma4:e4b)을 활용한 PPTX 자동 생성 파이프라인**을 구축한다. 사용자가 `content.json`(원본 콘텐츠)을 입력하면, Gemma가 슬라이드 설계도(`plan.json`)를 만들고, 슬라이드별 python-pptx 코드를 생성·실행하여 최종 `.pptx` 파일을 출력한다.

---

## 2. 설계 원칙

### 2.1 Brain–Executor 분리
LLM은 **계획·코드 생성·수정**만 담당한다. 실제 PPTX 바이너리 조작은 격리된 subprocess가 수행한다.

### 2.2 2-Tier JSON 구조
콘텐츠와 디자인 의도를 분리한다.
- **Tier 1 (`content.json`)**: 사용자/시스템이 입력하는 원본. 디자인 정보 없음.
- **Tier 2 (`plan.json`)**: Gemma가 생성하는 슬라이드 설계도. 모든 의사결정이 응축됨.

### 2.3 Primitives + Guideline 접근
고정된 layout 카탈로그 대신:
- **Primitives**: `add_rect`, `add_text`, `add_line`, `add_arrow` 등 최소 도구
- **Guideline**: 상황별 권장 구성 패턴 (33개) 마크다운 문서
- Gemma가 가이드라인을 참고해 primitives를 자유롭게 조합

### 2.4 슬라이드별 독립 생성
전체 PPT를 한 번에 생성하지 않는다. 슬라이드별로 독립 코드 → 개별 .pptx → 최종 머지. 한 슬라이드 실패가 전체를 망가뜨리지 않게.

### 2.5 반자유 + 시그니처 고정
Gemma는 python-pptx 코드를 직접 생성하지만, 함수 시그니처(`add_slide(prs, data)`)와 사용 가능한 primitives는 강제한다.

### 2.6 MVP는 직선 파이프라인
비평 루프(3·5·6단계)는 MVP에서 제외. 작동하는 것을 먼저 만든 후 품질 루프 추가.

---

## 3. 전체 파이프라인

```
┌─────────────────────┐
│   content.json      │  ← 사용자 입력
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Phase 2-1          │  Gemma 호출
│  Story Outline      │  → [{slide_no, purpose, head_message}, ...]
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Phase 2-2          │  Gemma × N슬라이드 (병렬)
│  Slide Detail       │  → 각 슬라이드 layout_hint, content
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  plan.json          │  최종 슬라이드 설계도
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Phase 4            │  슬라이드별 Gemma 호출
│  Code Generation    │  → add_slide(prs, data) 코드 N개
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Subprocess Execute │  격리 실행, 에러 시 max 3회 재시도
│  + Error Recovery   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Merge Slides       │  슬라이드별 .pptx → 단일 .pptx
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   output.pptx       │
└─────────────────────┘
```

---

## 4. 모듈 구조

```
CoWork/
├── src/
│   ├── llm/
│   │   └── ollama_client.py       # 기존 — Ollama REST API 래퍼
│   ├── pptx/
│   │   ├── primitives.py          # NEW — Layer 1 도구
│   │   ├── generator.py           # 기존 — JSON→PPTX (호환 유지)
│   │   ├── code_runner.py         # NEW — subprocess 실행 + 에러 복구
│   │   └── merger.py              # NEW — 슬라이드별 .pptx 머지
│   └── pipeline/
│       ├── planner.py             # NEW — content.json → plan.json
│       ├── code_generator.py      # NEW — plan.json → 슬라이드 코드
│       └── builder.py             # NEW — 전체 파이프라인 오케스트레이터
├── guidelines/
│   ├── design_guideline.md        # NEW — 33개 패턴 상세 설명
│   └── primitives_api.md          # NEW — Primitives API 레퍼런스
├── prompts/
│   ├── story_outline.txt          # NEW — Phase 2-1 프롬프트 템플릿
│   ├── slide_detail.txt           # NEW — Phase 2-2 프롬프트 템플릿
│   └── code_generation.txt        # NEW — Phase 4 프롬프트 템플릿
├── data/
│   ├── sample_presentation.json   # 기존
│   └── sample_content.json        # NEW — content.json 예시
├── tests/
│   ├── test_ollama.py             # 기존
│   ├── test_pptx.py               # 기존
│   ├── test_primitives.py         # NEW
│   ├── test_planner.py            # NEW
│   ├── test_code_runner.py        # NEW
│   └── test_e2e.py                # NEW — 전체 파이프라인 통합
└── output/
```

---

## 5. 데이터 스키마

### 5.1 `content.json` (사용자 입력)

```json
{
  "meta": {
    "title": "Q3 코팅 공정 개선 보고",
    "audience": "팀장급",
    "tone": "데이터 중심, 결론부터",
    "duration_min": 10,
    "language": "ko"
  },
  "sections": [
    {
      "id": "s1",
      "topic": "현황 진단",
      "raw_facts": [
        "8월 불량률 2.3%, 7월 대비 +0.8%p",
        "주요 원인: 도공기 #3 두께 편차"
      ]
    }
  ]
}
```

**필드 정의**:
- `meta.title`: 발표 제목 (필수)
- `meta.audience`: 청중 (선택, 톤 결정에 영향)
- `meta.tone`: 발표 어조 (선택)
- `meta.language`: 출력 언어 (`ko` | `en`)
- `sections[].id`: 섹션 식별자
- `sections[].topic`: 섹션 주제
- `sections[].raw_facts`: 원본 사실 목록

### 5.2 `plan.json` (Gemma 생성)

```json
{
  "deck_meta": {
    "title": "Q3 코팅 공정 개선 보고",
    "theme": {
      "primary": "#065A82",
      "accent": "#21295C",
      "neutral": "#F2F2F2",
      "text_dark": "#1C2833",
      "text_light": "#FFFFFF"
    },
    "fonts": {
      "header": "Pretendard Bold",
      "body": "Pretendard"
    },
    "slide_size": { "width_in": 13.333, "height_in": 7.5 }
  },
  "slides": [
    {
      "slide_no": 1,
      "purpose": "발표 시작, 청중 주목",
      "head_message": "Q3 코팅 공정 개선 보고",
      "layout_hint": "Cover",
      "content": {
        "title": "Q3 코팅 공정 개선 보고",
        "subtitle": "2025-10 / 품질팀"
      }
    },
    {
      "slide_no": 3,
      "purpose": "현황의 심각성을 숫자로 각인",
      "head_message": "8월 불량률 2.3% — 분기 목표의 1.5배",
      "layout_hint": "Stat 강조",
      "content": {
        "stats": [
          { "value": "2.3%", "label": "불량률", "delta": "▲0.8%p" },
          { "value": "67%",  "label": "두께 편차 기인" }
        ],
        "context": "도공기 #3에서 편차 집중 발생"
      }
    }
  ]
}
```

**필드 정의**:
- `deck_meta.theme`: 전 슬라이드 공통 색상 팔레트
- `slides[].purpose`: 이 슬라이드의 존재 이유 (한 줄, 못 쓰면 슬라이드 제거)
- `slides[].head_message`: 결론 문장 25자 내외 (주제 라벨 X)
- `slides[].layout_hint`: 33개 가이드라인 패턴 중 하나의 이름
- `slides[].content`: layout_hint에 따라 구조가 달라지는 자유 형식 dict

### 5.3 슬라이드 코드 시그니처

```python
# Gemma가 생성해야 하는 형식
from pptx import Presentation
from pptx.util import Inches, Pt
from src.pptx.primitives import (
    add_rect, add_text, add_line, add_arrow, add_image, set_bg
)

def add_slide(prs: Presentation, data: dict) -> None:
    """단일 슬라이드를 prs에 추가."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout
    # Gemma가 자유롭게 primitives 조합
    set_bg(slide, "#FFFFFF")
    add_text(slide, x=0.5, y=0.5, w=12.3, h=0.8,
             text=data["head_message"],
             font_size=28, bold=True, color="#1C2833")
    # ...

if __name__ == "__main__":
    import json, sys
    data = json.loads(sys.stdin.read())
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    add_slide(prs, data)
    prs.save(sys.argv[1])
```

---

## 6. 컴포넌트 상세

### 6.1 `primitives.py` — Layer 1 (Dumb Executor)

python-pptx 위에 얇게 래핑한 도구 함수들. 좌표 단위는 **인치(Inches)**. 모든 함수는 `slide` 객체를 첫 인자로 받음.

```python
def add_text(slide, x, y, w, h, text, *,
             font_size=14, bold=False, italic=False,
             color="#000000", align="left", font="Pretendard",
             line_spacing=1.2): ...

def add_rect(slide, x, y, w, h, *,
             fill="#FFFFFF", border_color=None, border_width=0,
             rounded=False): ...

def add_line(slide, x1, y1, x2, y2, *,
             color="#000000", width=1.5): ...

def add_arrow(slide, x1, y1, x2, y2, *,
              color="#000000", width=2.0,
              head_size=0.15): ...

def add_image(slide, x, y, w, h, image_path): ...

def set_bg(slide, color): ...
```

**책임 범위**:
- 좌표·색상·폰트 변환만
- 비즈니스 로직 없음 (어떤 layout인지 모름)
- python-pptx 외 의존성 금지

### 6.2 `planner.py` — Phase 2

`content.json` → `plan.json` 변환. 두 단계 LLM 호출.

```python
def make_plan(content: dict) -> dict:
    """전체 plan.json 생성."""
    outline = generate_outline(content)              # Phase 2-1
    slides = []
    for slide_outline in outline:
        section = find_section(content, slide_outline)
        detail = generate_slide_detail(slide_outline, section)  # Phase 2-2
        slides.append(detail)
    return {
        "deck_meta": derive_deck_meta(content),
        "slides": slides
    }
```

**Phase 2-1 (story outline)**:
- 입력: `content.json` 전체
- 출력: `[{slide_no, purpose, head_message}]` 목록
- 프롬프트: "도입-본론-결론" 평면 구조 금지, BLUF, head_message는 결론 문장

**Phase 2-2 (slide detail)**:
- 입력: 단일 outline + 관련 섹션 + **가이드라인 전체 33패턴 요약 카드** (각 패턴: 이름·언제 1줄)
- 출력: `layout_hint` (33개 중 정확히 하나의 이름), `content` (선택한 layout에 적합한 dict)
- 프롬프트: 가이드라인 카드를 모두 보여주고 가장 적합한 것 1개 선택. content는 해당 패턴 설명에 맞춰 구성

**deck_meta 결정 책임**:
- `deck_meta.theme`(색상)·`deck_meta.fonts`는 Phase 2-1에서 함께 결정
- 입력 `content.meta.tone`을 참고 (예: "데이터 중심" → 차분한 블루 계열, "활기차게" → 따뜻한 색)

**MVP 단순화**:
- Phase 2-2의 슬라이드별 호출은 **순차 실행** (전체 다이어그램의 "병렬"은 향후 확장 시점, MVP 아님)
- 실패 시 단순 재시도(max 2회)
- LLM 응답 JSON 파싱 실패 시 raw text 보존하고 에러 raise

### 6.3 `code_generator.py` — Phase 4 (코드 생성)

각 슬라이드에 대해 Gemma를 호출해 python 코드 생성.

```python
def generate_slide_code(slide_plan: dict, deck_meta: dict,
                        guideline: str, primitives_api: str) -> str:
    """단일 슬라이드의 python-pptx 코드 문자열 반환."""
    prompt = build_prompt(
        slide_plan=slide_plan,
        deck_meta=deck_meta,
        guideline=guideline,           # 해당 layout_hint 부분만 추출
        primitives_api=primitives_api,
        signature_template=SIGNATURE_TEMPLATE
    )
    response = ollama_client.chat(prompt)
    code = extract_code_block(response)
    return code
```

**프롬프트 템플릿 핵심 제약**:
1. 시그니처 정확히 일치: `def add_slide(prs: Presentation, data: dict) -> None:`
2. python-pptx + src.pptx.primitives만 import
3. 좌표는 Inches() 단위, 슬라이드 13.333 × 7.5
4. data 딕셔너리에서 텍스트·수치 읽기 (하드코딩 금지)
5. 색상·폰트는 deck_meta에서 받기
6. 에러 시 부분 패치 금지 → 전체 코드 재생성

### 6.4 `code_runner.py` — Subprocess 실행 + 에러 복구

**책임**:
- LLM이 생성한 코드를 격리된 subprocess로 실행
- 실패 시 traceback을 LLM에 전달, 코드 재생성 요청 (max 3회)
- 실행 성공 시 출력 .pptx 경로 반환

```python
def render_slide(code: str, slide_data: dict, output_path: Path,
                 max_retries: int = 3) -> Path:
    """코드를 subprocess로 실행. 실패 시 LLM에 재요청."""
    for attempt in range(max_retries):
        result = subprocess.run(
            [sys.executable, "-"],
            input=code.encode("utf-8"),
            capture_output=True,
            timeout=30,
            env=isolated_env(),
        )
        if result.returncode == 0 and output_path.exists():
            return output_path

        # 실패 → LLM에 컨텍스트 주입 후 재생성 요청
        traceback_tail = extract_traceback_tail(result.stderr)
        code = llm_fix_code(
            original_code=code,
            traceback=traceback_tail,
            slide_plan=slide_data
        )
    raise RuntimeError(f"Slide {slide_data['slide_no']} 생성 실패 (after {max_retries} retries)")
```

**격리 환경**:
- `subprocess.run`에 timeout=30s 강제
- 환경 변수 최소화 (`PYTHONPATH`만 통과)
- 출력 디렉토리는 절대경로로 명시
- stdin으로 코드 주입, sys.argv[1]로 출력 경로 전달

### 6.5 `merger.py` — 슬라이드 머지

```python
def merge_slides(slide_pptx_paths: list[Path], output_path: Path) -> Path:
    """N개의 단일 슬라이드 .pptx → 하나로 합침."""
    final = Presentation(slide_pptx_paths[0])
    for path in slide_pptx_paths[1:]:
        copy_first_slide(final, Presentation(path))
    final.save(output_path)
    return output_path
```

**구현 노트**:
- python-pptx에는 슬라이드 복사 native API가 없음
- MVP 1차 구현: XML 레벨 복사 함수 자체 구현 (`copy_first_slide`) — 외부 의존성 없음
- 머지 실패 시 fallback: 첫 슬라이드만 살린 prs를 base로 삼고, 나머지 슬라이드는 각 .pptx의 `slide1.xml`을 직접 ZIP 조작으로 삽입

### 6.6 `builder.py` — 오케스트레이터

```python
def build_presentation(content_path: Path, output_path: Path) -> Path:
    content = load_json(content_path)
    plan = make_plan(content)
    save_json(plan, "output/plan.json")  # 디버깅용

    slide_paths = []
    for slide_plan in plan["slides"]:
        code = generate_slide_code(slide_plan, plan["deck_meta"],
                                    guideline, primitives_api)
        slide_path = Path(f"output/slides/slide_{slide_plan['slide_no']}.pptx")
        render_slide(code, slide_plan, slide_path)
        slide_paths.append(slide_path)

    return merge_slides(slide_paths, output_path)
```

---

## 7. Guideline 패턴 (33개)

전체 가이드라인은 `guidelines/design_guideline.md`로 저장. 8개 카테고리.

### A. 수치·데이터 표현 (6)
Stat 강조 · Chart 슬라이드 · KPI Dashboard · Trend+Annotation · Progress Bar · Top Ranking

### B. 비교·대조 (6)
Matrix 비교 · As-Is/To-Be · 2×2 Quadrant · Pros & Cons · 3-Column Cards · Spectrum

### C. 프로세스·흐름 (6)
Flow 다이어그램 · Cycle/Loop · Funnel · Swim Lane · Decision Tree · Force Field

### D. 시간·일정 (3)
추진계획 로드맵 · Timeline · Customer Journey

### E. 구조·관계 (6)
피라미드 · Venn 다이어그램 · Concentric Circles · Org Chart · Hub & Spoke · Iceberg

### F. 메시지 전달 (6)
Cover · 인용 · Big Statement · Problem-Solution-Benefit · Section Divider · Headline+Image

### G. 콘텐츠 밀도 (6)
Bullet List · Icon Grid · 3-Card Highlights · Featured Callout · Photo+Caption · Comparison Table

### H. 메타·구조 (6)
Agenda · Summary · Next Steps · Q&A · Thank You · Reference

각 패턴 설명 형식 (3섹션):
- **언제**: 사용 상황
- **구성**: 배치 방법, primitives 조합 방식
- **주의**: 자주 하는 실수

---

## 8. 테스트 전략

### 8.1 단위 테스트
- `test_primitives.py`: 각 primitive가 올바른 위치에 도형/텍스트를 생성하는지
- `test_planner.py`: content.json 입력 → plan.json 구조 검증 (LLM 모킹)
- `test_code_runner.py`: 정상 코드/에러 코드 모두 처리하는지

### 8.2 통합 테스트
- `test_e2e.py`: `data/sample_content.json` → 최종 PPTX 생성, 슬라이드 수·크기 검증
- 첫 MVP 기준: 3슬라이드짜리 입력 → 30초 내 생성 성공

### 8.3 Smoke 테스트 (수동)
실제 LibreOffice/PowerPoint로 열어서 결함 시각 확인. (자동 비주얼 비평은 5단계 추가 후)

---

## 9. 개발 순서 (MVP 구현)

| 단계 | 산출물 | 검증 |
|------|--------|------|
| 1 | `primitives.py` + 단위 테스트 | 6개 primitive 모두 동작 |
| 2 | `code_runner.py` (subprocess + retry) | 정상/에러 코드 모두 처리 |
| 3 | 수동 작성한 코드 → `render_slide` 1슬라이드 생성 | PPTX 파일 정상 생성 |
| 4 | `merger.py` | 2개 .pptx → 1개로 합쳐짐 |
| 5 | `guidelines/design_guideline.md` 작성 (3~5개 패턴 우선) | LLM이 참조 가능한 형식 |
| 6 | `code_generator.py` + 프롬프트 | 1슬라이드 코드 생성 성공 |
| 7 | `planner.py` (Phase 2-1, 2-2) | content → plan 변환 성공 |
| 8 | `builder.py` 오케스트레이션 + e2e 테스트 | 3슬라이드 전체 생성 |

각 단계에서 동작하면 commit. 다음 단계로 진행.

---

## 10. 알려진 위험

| 위험 | 완화 |
|------|------|
| gemma4:e4b가 python-pptx 코드 생성을 신뢰성 있게 못할 수 있음 | 시그니처 고정 + 좁은 primitives + 에러 복구 루프(3회) |
| 코드 실행 보안 (악성 코드 가능성) | subprocess 격리, timeout 30s, 환경변수 최소화 |
| 슬라이드 머지 — python-pptx native API 없음 | XML 레벨 복사 함수 자체 구현 |
| LLM JSON 출력 파싱 실패 | code block 추출 정규식 + 재시도 |
| 한글 폰트 — Pretendard 등 시스템에 없을 수 있음 | 기본값 fallback (Malgun Gothic, Arial) |
| Windows cp949 인코딩 | 모든 subprocess `PYTHONIOENCODING=utf-8` 강제 |

---

## 11. MVP 이후 (참고)

- **5-A 텍스트 비평**: PPTX 텍스트 추출 → LLM이 오타·불일치 검토
- **5-B 비주얼 비평**: PPTX → PDF → PNG → vision 모델 검토 (vision 모델 도입 필요)
- **3단계 플랜 비평**: plan.json 4축 점수화
- **6단계 통합 비평**: 슬라이드 그리드 시각 일관성 검증
- **차트 객체 지원**: `add_chart` primitive (현재는 사각형 조합으로 표현)
- **이미지 자동 생성**: 외부 이미지 API 또는 로컬 SD 연동

---

## 12. 결정 요약

| 결정사항 | 선택 |
|---------|------|
| 코드 생성 방식 | Gemma가 python-pptx 코드 직접 생성 |
| Layout 제어 | 카탈로그 enum 없음, Primitives + Guideline |
| 함수 시그니처 | 고정 (`add_slide(prs, data)`) |
| Guideline 형식 | 상세형 (언제 / 구성 / 주의) |
| 패턴 수 | 33개, 8 카테고리 |
| 슬라이드 생성 | 슬라이드별 독립 → 머지 |
| 비평 루프 | MVP 제외 (5·6단계는 추후) |
| LLM 모델 | Ollama gemma4:e4b (로컬) |
| 실행 환경 | subprocess 격리, timeout 30s |
