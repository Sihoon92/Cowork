# Trouble: PPTX 파이프라인이 단일 슬라이드 렌더 실패로 전체 중단

- **일자**: 2026-05-02
- **영향 범위**: `scripts/run_pipeline.py` 전체. content.json → 최종 pptx 생성 워크플로우.
- **심각도**: high
- **상태**: resolved
- **관련 파일**: `src/pptx/code_runner.py`, `src/pipeline/builder.py`, `src/pipeline/critic.py`, `src/pipeline/visual_critic.py`

## 1. 문제 배경

`data/ai_era.json` 입력으로 7장짜리 발표자료 생성을 실행했다. 파이프라인은 (a) planner LLM이 슬라이드 개요/세부를 만들고, (b) critic LLM이 plan을 보정한 뒤, (c) 슬라이드별로 codegen LLM이 python-pptx 스크립트를 만들어 서브프로세스에서 실행, (d) 텍스트·비주얼 비평으로 보정, (e) merge 하는 구조다.

실행 결과 1·2·3·4번 슬라이드는 (재시도를 거쳐) 만들어졌지만 **slide 5에서 4회 모두 exit 1**이 나면서 `CodeExecutionError`가 위로 전파되어 파이프라인 전체가 죽었다. 이미 만들어진 1~4번 산출물도 merge되지 못해 사용자는 빈 결과만 받았다.

## 2. 증상 (What)

```text
[ 197.1s]   ! slide failed (attempt 1), asking LLM to fix: slide code exited with 1
[ 206.5s]   ! slide failed (attempt 2), asking LLM to fix: slide code exited with 1
[ 215.5s]   ! slide failed (attempt 3), asking LLM to fix: slide code exited with 1
Traceback (most recent call last):
  File "scripts\run_pipeline.py", line 74, in main
    out = build_presentation(content, output_path=output_path, workdir=workdir)
  File "src\pipeline\builder.py", line 157, in build_presentation
    render_slide_with_retry(...)
src.pptx.code_runner.CodeExecutionError: slide rendering failed after 3 retries
```

slide 3에서 한 번은 stderr에 명시적으로 다음 메시지가 떴다:

```text
undefined name likely: 'RGBColor' at line 19
```

추가 증상:
- Stage 3 plan critique가 3라운드 모두 `REVISE`로 PASS에 도달 못함 → 18초 낭비
- slide 3의 `layout_hint`가 critic에 의해 `'Icon Grid'` → `'Icon Grid with descriptions'`(가이드 사전에 없는 이름)로 바뀜 → `Bullet List`로 폴백
- visual critique는 `soffice/pdftoppm not found`로 매 슬라이드 SKIP

## 3. 근본 원인 (Why)

문제는 한 가지가 아니라 **여러 약점이 겹쳐 만든 캐스케이드 실패**였다.

1. **프리앰블이 부족함** (`src/pptx/code_runner.py:32-41`).
   서브프로세스에 자동 주입되는 import에 `Presentation, Inches, Pt, primitives 6종`만 들어 있어, LLM이 `RGBColor`, `MSO_SHAPE`, `PP_ALIGN` 같은 흔한 enum을 한 번이라도 import 안 하면 즉시 NameError → exit 1. AST 사전검증(`_validate_code`)이 잡아주지만 fix 루프가 같은 실수를 반복.

2. **fix 콜백에 traceback 정보가 부족** (`src/pptx/code_runner.py:273`).
   `_tail(stderr, 20)`로 마지막 20줄만 LLM에 전달. 실제 에러 종류·이름이 첫 줄에 있으면 잘려 나가 LLM은 무엇을 고쳐야 할지 모른 채 같은 코드를 또 생성.

3. **단일 슬라이드 실패가 deck 전체를 죽임** (`src/pipeline/builder.py:157`).
   `render_slide_with_retry`를 try/except 없이 호출. 한 슬라이드의 4회 시도가 모두 실패하면 예외가 그대로 위로 전파되어 이미 성공한 슬라이드까지 무용지물.

4. **critic이 가이드 사전에 없는 layout_hint를 만들어냄** (`src/pipeline/critic.py:36-48`).
   `apply_patches`가 `field` 화이트리스트만 검사하고 *값*은 검증하지 않음. critic이 자유롭게 `'Icon Grid with descriptions'` 같은 신조어를 만들어 패치하면 `resolve_pattern()`이 None을 돌려 `Bullet List`로 폴백 — codegen LLM은 의도(Icon Grid)와 다른 가이드를 받음.

5. **시각 비평 백엔드가 Windows에서 사용 불가** (`src/pipeline/visual_critic.py:16-26`).
   `soffice` + `pdftoppm` 둘 다 PATH에 있어야만 `pptx_to_image`가 동작. 사용자 환경에는 LibreOffice가 없어 visual critique가 늘 SKIP — Stage 5-B가 사실상 dead code.

## 4. 기술적 해결

| # | 변경 위치 | 변경 내용 | 효과 |
|---|---|---|---|
| 1 | `src/pptx/code_runner.py:23-46` | `_GUARANTEED_PREAMBLE`에 `RGBColor`, `MSO_SHAPE`, `PP_ALIGN`, `MSO_ANCHOR`, `Emu`, `Cm` import 추가. `_PREAMBLE_NAMES`도 동시에 갱신. | LLM이 import를 깜빡해도 NameError가 나지 않음. slide 3·5류 실패의 가장 흔한 원인 제거. |
| 2 | `src/pptx/code_runner.py` (`_error_excerpt` 추가, `render_slide_with_retry`에서 사용) | traceback의 **첫 비어있지 않은 줄 + 마지막 20줄**을 함께 fix 콜백에 전달. | LLM이 에러 클래스(NameError 등)와 위치를 모두 보고 정확히 수정할 확률↑. |
| 3 | `src/pipeline/builder.py` (`_write_placeholder_slide` 추가, render 호출부 try/except) | `CodeExecutionError`를 잡아 "Slide N: generation failed" placeholder pptx로 대체하고 다음 슬라이드로 진행. | 한 슬라이드 실패가 deck 전체를 죽이지 못함. 부분 산출물 보존. |
| 4 | `src/pipeline/critic.py` (`apply_patches`) | `field == "layout_hint"`일 때 `resolve_pattern()`으로 검증, fail 시 패치 거부 + warn. 통과 시 canonical 이름으로 정규화. | critic이 가이드 사전 밖 이름을 만들어내는 것을 차단. layout_hint와 codegen 가이드 일관성 보장. |
| 5 | `src/pipeline/visual_critic.py` 전면 개편 | `_pptx_to_image_powerpoint()`(pywin32 + COM) 백엔드 추가. 백엔드 우선순위: PowerPoint → soffice → SKIP. `conversion_tools_available()`이 둘 중 하나라도 있으면 True. | Windows + PowerPoint 환경에서 visual critique가 비로소 동작. soffice 의존 제거. |

핵심 diff (Fix 1·2):

```diff
 _PREAMBLE_NAMES = frozenset({
-    "Presentation", "Inches", "Pt",
+    "Presentation", "Inches", "Pt", "Emu", "Cm",
+    "RGBColor",
+    "MSO_SHAPE", "PP_ALIGN", "MSO_ANCHOR",
     "add_text", "add_rect", "add_line", "add_arrow", "add_image", "set_bg",
     ...
 })

 _GUARANTEED_PREAMBLE = '''# --- guaranteed imports (injected) ---
 from pptx import Presentation
-from pptx.util import Inches, Pt
+from pptx.util import Inches, Pt, Emu, Cm
+from pptx.dml.color import RGBColor
+from pptx.enum.shapes import MSO_SHAPE
+from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
 ...
```

## 5. 검증

격리된 sanity check를 실행해 5가지 변경이 모두 의도대로 동작함을 확인:

```text
imports OK
powerpoint available: True
soffice available: False
any backend: True
---excerpt---
Traceback (most recent call last):
...
  ...lots of frames...
NameError: name RGBColor is not defined
---end---
rejected bad patch: True
canonicalized patch: Icon Grid
preamble symbols OK
```

placeholder 슬라이드 생성도 정상 (28 KB pptx 산출).

전체 파이프라인 재실행으로 end-to-end 검증은 사용자가 수행 예정 (`scripts/run_pipeline.py data/ai_era.json`).

## 6. 재발 방지 / 후속 조치

- [ ] `data/ai_era.json` 전체 파이프라인 재실행 후 결과 확인
- [ ] codegen 프롬프트에 "주입된 import 목록"을 명시하여 LLM이 재정의하지 않도록 가이드 보강
- [ ] plan critique가 항상 REVISE만 내는 문제는 별도 트러블로 추적 (PASS 도달 가능한 임계 조정 또는 max_rounds=2 단축)
- [ ] CI 환경(Linux)에서 PowerPoint COM 미사용 시 soffice 설치 가이드를 README에 추가

## 7. 참고

- `guidelines/design_guideline.md` — 33개 슬라이드 패턴 정식 명단 (critic 검증의 ground truth)
- `src/pipeline/guideline_loader.py:resolve_pattern` — 패턴 이름 정규화 함수
- 관련 커밋: (생성 후 추가)
