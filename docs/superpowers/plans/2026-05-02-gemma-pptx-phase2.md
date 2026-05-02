# Phase 2 — Critique Loops & Quality Improvements

> Continuation of [`2026-05-02-gemma-pptx-pipeline.md`](2026-05-02-gemma-pptx-pipeline.md). MVP is shipped and produces a working `demo.pptx`. Phase 2 adds critique loops and reliability fixes surfaced by live testing.

**Goal:** Add critique/recovery layers that improve generated deck quality and reduce wasted LLM cycles.

**Priority order (highest ROI first):**

1. Stage 4.5 — AST pre-validation (catch broken code before subprocess timeout)
2. Stage 3 — Plan critique loop (5 axes including layout diversity)
3. Content-to-section mapping (per-slide facts, not all facts)
4. Stage 5-A — Text critique per slide
5. Stage 5-B — Visual critique (vision model)
6. Stage 6 — Deck integration critique

---

## Task P1: AST pre-validation in code_runner

**Files:**
- Modify: `src/pptx/code_runner.py`
- Modify: `tests/pptx/test_code_runner.py`

**Why:** When LLM generates syntactically broken code or references undefined names, the subprocess still spawns, runs for up to 30s, then fails. We can catch most of these in microseconds with `ast.parse` + a quick name-binding check.

### Steps

- [ ] Write test `test_run_slide_code_rejects_syntax_error` that passes `def add_slide(prs, data): pass\nfont_size=16, color=` (incomplete syntax) and expects `CodeExecutionError` with `"SyntaxError"` in message, raised in <1 second.
- [ ] Write test `test_run_slide_code_rejects_undefined_call` that passes code calling `undefined_func(slide)` and expects rejection in <1 second.
- [ ] Run tests, verify they fail (current code spawns subprocess and waits).
- [ ] Implement `_validate_code(code: str) -> None` in `code_runner.py`:
  - Try `ast.parse(code)` — on `SyntaxError`, raise `CodeExecutionError(f"SyntaxError: {e.msg} at line {e.lineno}")`.
  - Walk the AST to collect all `ast.Name` references (`Load` ctx) at module level and inside functions.
  - Build a known-names set: stdlib imports detected in code + names defined in code (`def`, assignments, function args) + the guaranteed preamble names (`add_text, add_rect, add_line, add_arrow, add_image, set_bg, Presentation, Inches, Pt, _json, _sys`) + Python builtins.
  - For any `Name` not in the known set, raise `CodeExecutionError(f"NameError likely: {name}")`. (Conservative: only flag names that are clearly undefined like `theme_color` typo, not generic stuff like `data`.)
  - Call `_validate_code(code)` after `inject_preamble` in `run_slide_code`.
- [ ] Run all code_runner tests, expect all pass + 2 new pass.
- [ ] Commit: `feat(code_runner): add AST pre-validation to short-circuit broken code`

---

## Task P2: Plan critique loop (Stage 3)

**Files:**
- Create: `prompts/plan_critique.txt`
- Create: `src/pipeline/critic.py`
- Create: `tests/pipeline/test_critic.py`
- Modify: `src/pipeline/builder.py`

**Why:** Catch flat narratives, weak head_messages, redundant slides, and layout monotony in plan.json before paying for slide rendering.

### Steps

- [ ] Create `prompts/plan_critique.txt` with 5-axis prompt:
  - **스토리 흐름** (1-5): head_message만 읽었을 때 논지가 이어지는가?
  - **메시지 강도** (1-5): head_message가 결론 문장인가?
  - **콘텐츠 균형** (1-5): 한 슬라이드에 정보 5개 초과 or 텍스트만 있는 슬라이드 연속 여부
  - **시각화 적합성** (1-5): layout_hint와 content가 맞는가?
  - **레이아웃 다양성** (1-5): 같은 layout_hint가 연속 또는 과반?
  - Output: JSON `{"scores": {axis: int}, "issues": [str], "patches": [{slide_no, field, new_value}], "verdict": "PASS"|"REVISE"}` in fenced block.
- [ ] Create `src/pipeline/critic.py`:
  - `critique_plan(plan: dict, model: str = DEFAULT_MODEL) -> dict` — call LLM, parse JSON.
  - `apply_patches(plan: dict, patches: list[dict]) -> dict` — apply patches by slide_no + field.
  - `revise_plan_until_pass(plan: dict, max_rounds: int = 3, model=...) -> dict` — loop critique → apply → re-critique until PASS or max rounds.
- [ ] Tests in `tests/pipeline/test_critic.py` (mock LLM):
  - `test_critique_plan_parses_scores_and_verdict`
  - `test_apply_patches_updates_head_message`
  - `test_revise_loop_stops_on_pass`
  - `test_revise_loop_gives_up_after_max`
- [ ] Wire into `builder.build_presentation` between `make_plan` and the slide loop:
  ```python
  plan = make_plan(content)
  plan = revise_plan_until_pass(plan, max_rounds=3)
  ```
- [ ] Commit: `feat(critic): add plan critique loop with 5 axes including layout diversity`

---

## Task P3: Per-slide section mapping

**Files:**
- Modify: `prompts/story_outline.txt`
- Modify: `src/pipeline/planner.py`
- Modify: `tests/pipeline/test_planner.py`

**Why:** Currently every slide gets ALL raw_facts in its detail prompt. With 10+ slides this wastes tokens and makes slides generic.

### Steps

- [ ] Modify `prompts/story_outline.txt` to require `section_id` per slide in the JSON output (referencing `content.sections[].id`).
- [ ] Modify `_section_facts_for(content, slide_no)` to look up the slide's `section_id` from the outline cache and return only that section's facts. (Need to thread the outline into the function.)
- [ ] Update `make_plan` to pass the outline-with-section-ids to `_section_facts_for`.
- [ ] Update tests to assert `section_id` is preserved through the pipeline.
- [ ] Commit: `feat(planner): map each slide to its source section instead of dumping all facts`

---

## Task P4: Per-slide text critique (Stage 5-A)

**Files:**
- Create: `prompts/text_critique.txt`
- Create: `src/pipeline/text_critic.py`
- Create: `tests/pipeline/test_text_critic.py`
- Modify: `src/pipeline/builder.py`

**Why:** Catch placeholder leftovers ("Lorem ipsum"), truncated headlines (...), wrong text vs plan, repeated words.

### Steps

- [ ] Create `prompts/text_critique.txt` — given the plan slide and extracted text, return JSON: `{"issues": [{"severity": "high|low", "msg": str}], "verdict": "PASS"|"FIX"}`
- [ ] Implement `extract_slide_text(pptx_path) -> list[str]` using python-pptx (read all text frames).
- [ ] Implement `critique_slide_text(slide_plan, slide_pptx_path) -> dict` — extract text, send to LLM with plan for comparison.
- [ ] On `FIX`, re-prompt code generator with critique findings appended to original prompt.
- [ ] Tests: extract test, critique-mocked test, fix-loop test.
- [ ] Wire into `builder` after each `render_slide_with_retry` (one round only — don't loop indefinitely).
- [ ] Commit: `feat(text_critic): add per-slide text critique with one fix attempt`

---

## Task P5: Visual critique (Stage 5-B)

**Files:**
- Modify: `requirements.txt` (or document pull command for vision model)
- Create: `src/pipeline/visual_critic.py`
- Create: `tests/pipeline/test_visual_critic.py`
- Modify: `src/pipeline/builder.py`

**Why:** Catch overflow, overlap, margin violations, low contrast — things LLM vision can see but text-only can't.

### Steps

- [ ] Document vision-model setup: `ollama pull qwen2.5vl:7b` (~6GB, fits 12GB VRAM).
- [ ] Add `chat_with_image(prompt, image_path, model)` to `src/llm/ollama_client.py` (POST to `/api/generate` with base64 image).
- [ ] Implement `pptx_to_image(pptx_path, out_dir) -> Path` using `soffice --headless --convert-to pdf` then `pdftoppm`. (May need to skip on machines without LibreOffice — wrap in availability check.)
- [ ] Implement `critique_slide_visual(slide_pptx_path, vision_model) -> dict` — convert to image, send to vision LLM with the 6-checkpoint prompt (overflow, overlap, margin, alignment, contrast, chart cropping).
- [ ] Tests: image-conversion fallback test, mocked vision-LLM test.
- [ ] Wire into `builder` after text critique. **One fix cycle only** — high/med findings trigger one regeneration; low findings ignored.
- [ ] Commit: `feat(visual_critic): add per-slide visual critique via vision LLM`

---

## Task P6: Deck integration critique (Stage 6)

**Files:**
- Create: `prompts/deck_storyline_critique.txt`
- Create: `prompts/deck_visual_critique.txt`
- Modify: `src/pipeline/critic.py`
- Modify: `src/pipeline/builder.py`

**Why:** After per-slide passes, verify the deck as a whole tells a story and looks consistent.

### Steps

- [ ] Implement `critique_deck_storyline(plan: dict) -> dict` — feed only `head_message`s to LLM, ask "does the narrative flow?".
- [ ] Implement `make_thumbnail_grid(slide_paths, out_path) -> Path` — combine slide images into a 2×N grid for vision LLM.
- [ ] Implement `critique_deck_visual(slide_paths, vision_model) -> dict` — feed grid to vision LLM, check font consistency, color palette consistency, layout monotony, hierarchy.
- [ ] If issues found, target ONLY the specific slide for regeneration (no full-deck rebuild).
- [ ] Tests with mocks.
- [ ] Wire into `builder` after merge, before final save.
- [ ] Commit: `feat(critic): add deck-level storyline and visual consistency critique`

---

## Stop Conditions

After each task: run `PYTHONIOENCODING=utf-8 python scripts/run_pipeline.py` end-to-end and visually inspect `output/demo.pptx`. If any task makes the deck WORSE (subjective), revert that task and reconsider.

Each task is independently revertable via `git revert`.
