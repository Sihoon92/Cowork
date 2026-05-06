# v2 Freeform Codegen Pipeline — Design

**Date**: 2026-05-06
**Status**: Draft (awaiting user review)
**Coexists with**: v1 recipe pipeline in `src/pipeline/` (unchanged)
**Related**: `2026-05-02-gemma-pptx-pipeline-design.md`

---

## 1. Goal

Build a second PPTX generation pipeline (v2) that runs alongside the current
recipe-based pipeline (v1). v2 trades v1's deterministic, recipe-bounded
rendering for **fully LLM-generated python-pptx code per slide**, driven by an
explicit two-phase plan (structure → visual strategy) and improved over time
through a persistent gallery of high-scoring slides.

Both pipelines must remain runnable from the same `data/sample_content.json`
fixtures so a user can compare outputs side by side.

## 2. Non-goals

- Rewriting or deprecating v1. Not a single line of `src/pipeline/`,
  `src/pptx/primitives.py`, `src/pptx/renderer.py`, existing `prompts/`, or
  existing `guidelines/` is touched.
- Building an automated v1-vs-v2 diff/scoring report. v2 just produces parallel
  artifacts in a `_v2`-suffixed location; comparison is manual for now.
- Cross-deck style transfer beyond what `references/index.json` provides.

## 3. Differences vs v1 (summary)

| Axis | v1 (recipe pipeline) | v2 (freeform codegen) |
|---|---|---|
| Layout source | Fixed recipe registry (~11 named recipes) | LLM coins a fresh `snake_case approach` per slide |
| Render | Deterministic compile of `PrimitiveSpec` list | LLM writes python-pptx code; subprocess execution |
| Plan stages | Single LLM call (outline + recipe + slot fill) | Two LLM calls (1a structure, 1b visual strategy) |
| Layout hint | Implicit (recipe is the hint) | Explicit free-form spec text in `layout_hint` |
| Revision | Patch recipe data → recompile | Vision-LLM critique on PNG → patch the code |
| Critique axes | Single deck-level pass | Per-slide 3-axis (strategy/visual/content) + deck-level |
| Cumulative learning | None | Gallery (`references/index.json`) — slides scoring ≥8 are saved and reinjected into future Phase 1b prompts |
| Failure mode | pydantic validation error | runtime error → auto-fix retry (max 2) |
| Free-form shapes (e.g. connector callouts) | Not supported | Supported (raw `slide.shapes.add_connector(...)`) |

## 4. Pipeline

```
Stage 0   load content.json
Stage 1a  outline LLM            → outline.json
            kind / headline / takeaway / content_structure only
Stage 1b  visual_strategy LLM    → plan.json
            adds approach / rationale / layout_hint / key_elements per body slide
            inputs include (a) approaches already used in this deck,
                           (b) gallery references for this content_structure
Stage 2   per-slide code-generation LLM
            input:  plan[N] + design_guide_v2.md + preamble.py text
            output: body of `def build_slide(prs): ...`
Stage 3   per-slide subprocess execution → slides/slide_NN.pptx
            failure → auto_fix LLM (max 2 retries)
Stage 4   merge slides → output_v2.pptx                      (reuse src/pptx/merger.py)
Stage 5   visual revision loop (max 3 iterations)
            for each slide:
              capture PNG → 3-axis critique LLM
              min(scores) < 7 and verdict != KEEP
                → revise_code LLM (PNG + prev code + critique + plan)
                → re-execute (with auto_fix on failure)
                → re-capture
            bail out early if no slide was revised in an iteration
Stage 6   deck-level critique (storyline + visual consistency)  (reuse v1 critic)
Stage 7   gallery append: for each slide where min(scores) ≥ 8,
            append a GalleryEntry to references/index.json
```

## 5. Architecture

### 5.1 Directory layout

```
src/
  pipeline/                       # v1, unchanged
  pipeline_v2/                    # NEW
    __init__.py
    builder.py                    # build_presentation_v2(content, output, workdir, opts)
    outline.py                    # Stage 1a
    visual_strategy.py            # Stage 1b (gallery injection)
    code_generator.py             # Stage 2 (LLM call + assemble final .py)
    auto_fix.py                   # Stage 3 retry loop
    revision_loop.py              # Stage 5 (3-axis)
    gallery.py                    # Stage 7 persistence + Stage 1b lookup
    schemas.py                    # SlideOutline, VisualStrategy, SlidePlanV2,
                                  # SlideCritique, GalleryEntry
prompts/v2/
  outline_1a.md
  visual_strategy_1b.md
  code_generation.md
  code_auto_fix.md
  slide_critique_3axis.md
  code_revision.md
guidelines/v2/
  design_guide.md                 # raw python-pptx recipes / anti-patterns / tokens
  preamble.py                     # imports + tokens + _patch_shapes — prepended to LLM code
references/
  index.json                      # gallery (git-tracked)
scripts/
  run_pipeline_v2.py              # NEW entry point
tests/v2/
  test_preamble.py
  test_schemas.py
  test_gallery.py
  test_code_runner_v2.py
  test_outline.py                 # live
  test_pipeline_v2.py             # live
```

### 5.2 Reused v1 assets (import only, no edits)

- `src/llm/client.py` — text chat; vision call may need a thin extension
  (added in a v2-only module if v1 does not already expose one).
- `src/pptx/merger.py` — `merge_slides(...)`.
- `src/pptx/capture.py` — `.pptx` → `.png` rendering.
- `src/pipeline/critic.py` — `critique_deck_storyline`, `critique_deck_visual`.
- `src/pptx/code_runner.py` — subprocess + retry skeleton; `pipeline_v2`
  may wrap it but not modify it.

### 5.3 LLM-facing code surface

LLM output is **only** the body of `def build_slide(prs):`. The runner
assembles a final file as:

```
[guidelines/v2/preamble.py contents]   # prepended verbatim
[LLM-generated body]                   # def build_slide(prs): ...
[footer]                               # adds first slide, calls _patch_shapes(slide),
                                       # invokes build_slide(prs), prs.save(out_path)
```

`preamble.py` provides:

- python-pptx imports (`Presentation`, `Inches`, `Pt`, `Emu`, `RGBColor`,
  `MSO_SHAPE`, `MSO_CONNECTOR`, `PP_ALIGN`, `MSO_ANCHOR`,
  `CategoryChartData`, `XL_CHART_TYPE`).
- `matplotlib` configured with `Agg` backend and Korean-capable font fallback
  (`["Pretendard", "Malgun Gothic", "sans-serif"]`).
- Color tokens: `PRIMARY`, `ACCENT`, `INK`, `MUTED`, `BG`, `SURFACE`.
- Typography tokens: `FONT_HEAD`, `FONT_BODY`, `SIZE_HEAD`, `SIZE_SUB`,
  `SIZE_BODY`, `SIZE_CAP`.
- Canvas constants: `SLIDE_W`, `SLIDE_H` (16:9, 13.333 × 7.5 in EMU).
- `_patch_shapes(slide)`: monkeypatches `slide.shapes.add_textbox`,
  `add_shape`, `add_connector`, `add_picture`, `add_chart`, `add_table` to
  coerce all positional/keyword `float` args to `int` — defends against the
  float-EMU bug python-pptx silently passes through but PowerPoint rejects.

The footer always calls `_patch_shapes` on the slide before invoking
`build_slide`, so the LLM cannot forget to enable the defense.

`design_guide.md` (≈6–8 KB) covers: canvas / safe area, color tokens,
typography scale, sample recipe snippets (headline strip; 1×3 cards with
center emphasis; chart + side text card + connector; left→right
transformation; horizontal timeline), and explicit anti-patterns
(no `Inches(2.34)`-style magic coordinates, no hex literals, no external
file paths, no font-name literals).

### 5.4 Schemas

```python
class SlideOutline(BaseModel):
    index: int
    kind: Literal["title", "body", "closing"]
    headline: str = ""
    takeaway: str = ""
    subtitle: str = ""           # title/closing only
    implication: str = ""        # body, optional
    content_structure: Optional[Literal[
        "comparison","process","hierarchy","matrix","metric",
        "narrative","enumeration","timeline","system","other",
    ]] = None                    # body only

class VisualStrategy(BaseModel):
    approach: str                # snake_case, unique within deck
    rationale: str
    layout_hint: str             # free-form spec sentence(s)
    key_elements: list[str]

class SlidePlanV2(SlideOutline):
    visual_strategy: Optional[VisualStrategy] = None  # body slides only

class CritiqueIssue(BaseModel):
    location: str                # e.g. "3rd card bottom note"
    root_cause: str              # one sentence
    code_hint: str               # function/parameter-level fix

class SlideCritique(BaseModel):
    score_strategy: int          # 0-10 — fidelity to layout_hint
    score_visual: int            # 0-10 — alignment, spacing, color, hierarchy
    score_content: int           # 0-10 — text quality, message clarity
    issues: list[CritiqueIssue]
    verdict: Literal["KEEP", "REVISE", "REGENERATE"]

class GalleryEntry(BaseModel):
    deck_id: str                 # workdir name
    slide_no: int
    category: str                # = content_structure
    approach: str
    rationale: str
    layout_hint: str
    key_elements: list[str]
    scores: dict[str, int]
    quality_score: float         # = min(scores)
    code_snippet: str            # body of build_slide, verbatim
    created_at: str              # ISO 8601
```

### 5.5 Prompts (`prompts/v2/`)

Markdown files with `{placeholder}` substitution, matching the existing
`prompts/` convention.

| Prompt | Inputs | Output |
|---|---|---|
| `outline_1a.md` | `content.json` | `{"slides":[{index, kind, headline, takeaway, content_structure?}]}` |
| `visual_strategy_1b.md` | outline + used-approaches list + gallery refs grouped by content_structure | full plan with `visual_strategy` per body slide |
| `code_generation.md` | `plan[N]` + full `design_guide.md` + full `preamble.py` text | body of `build_slide(prs)` |
| `code_auto_fix.md` | previous code + traceback + design_guide excerpt | revised body |
| `slide_critique_3axis.md` | slide PNG + `plan[N]` | `SlideCritique` JSON |
| `code_revision.md` | PNG + previous code + critique JSON + `plan[N]` | revised body |

### 5.6 Critique scoring rubric (encoded in `slide_critique_3axis.md`)

| Axis | What it measures | 0-3 | 4-6 | 7-8 | 9-10 |
|---|---|---|---|---|---|
| strategy | Match between `layout_hint` spec and rendered PNG | wrong layout | partial | mostly right | exact |
| visual | Alignment, spacing, readability, color, hierarchy | broken / overlap | awkward | clean | polished |
| content | Text quality, message clarity, fit with layout | truncated / typos | flat | clear | impactful |

`issues` MUST follow the v1-described rules:

- **Locate**: "3rd card bottom note clipped 8px right" — not "text overlaps".
- **Root cause**: one sentence.
- **Code hint**: function/parameter level, not "fix it".

### 5.7 Revision loop policy

- A slide is revised only if `min(scores) < 7` AND `verdict != "KEEP"`.
- A slide is revised at most once per iteration (no inner loop on the same slide).
- An iteration that revises nothing terminates the loop early.
- `max_iterations` defaults to 3.
- `code_revision` failures fall back to `auto_fix` once before the slide is
  declared unrevisable for this iteration; the previous slide is then kept.

### 5.8 Gallery

- Append after Stage 6, using the **final** critique scores.
- Threshold: `min(scores) >= 8`.
- File: `references/index.json` at repo root, JSON list, git-tracked.
- Dedup: `(deck_id, slide_no)` pair; on collision, keep the higher
  `quality_score`.
- Pruning: per-category cap of 20 entries, oldest first by `created_at`.
- Stage 1b lookup: top-K per category (default K=2) by `quality_score`,
  injected as a "## Gallery references" section in the 1b prompt with
  `approach`, `layout_hint`, and the first ~30 lines of `code_snippet`.

### 5.9 Workdir layout

```
workdir/
  outline.json
  plan.json
  slide_codes/
    slide_01.py  slide_02.py ...           # final
    slide_01.iter0.py  slide_01.iter1.py ...
  slides/
    slide_01.pptx ...
  captures/
    slide_01_iter0.png  slide_01_final.png ...
  critiques/
    slide_01_iter0.json  ...
    deck_storyline.json
    deck_visual.json
  output_v2.pptx
```

## 6. Runner

`scripts/run_pipeline_v2.py` mirrors `scripts/run_pipeline.py`:

```bash
PYTHONIOENCODING=utf-8 python scripts/run_pipeline_v2.py
PYTHONIOENCODING=utf-8 python scripts/run_pipeline_v2.py data/ai_era.json
PYTHONIOENCODING=utf-8 python scripts/run_pipeline_v2.py data/ai_era.json output/ai_era_v2.pptx
```

Defaults:

- output: `output/<stem>_v2.pptx`
- workdir: `output/work_v2_<stem>/`
- gallery: `references/index.json`

Optional flags:

- `--no-revision` — skip Stage 5 (baseline measurement of one-shot generation).
- `--no-gallery` — skip both Stage 7 persist and Stage 1b injection.
- `--max-iter N` — Stage 5 iteration cap.
- `--seed N` — passed to LLM provider when supported.

## 7. Testing

Follows existing `pytest -m "not live"` / `-m live` split.

| Test | Marker |
|---|---|
| `test_preamble.py` — preamble parses and execs; `_patch_shapes` casts floats | unit |
| `test_schemas.py` — pydantic valid/invalid | unit |
| `test_gallery.py` — append, dedup, top-K, pruning | unit |
| `test_code_runner_v2.py` — preamble + fixed body assembled and executed in subprocess | unit |
| `test_outline.py` — Stage 1a returns schema-valid JSON | live |
| `test_pipeline_v2.py` — small end-to-end run on a 3-slide fixture | live |

## 8. Milestones

1. **M1 — skeleton**: `pipeline_v2/{schemas,builder}.py` + `run_pipeline_v2.py`,
   Stages 1a/1b only; Stage 2 stubs an empty slide.
2. **M2 — codegen**: `design_guide.md` + `preamble.py` + `code_generation.md`
   + Stage 2 + auto_fix.
3. **M3 — merge**: Stage 4 wired to `merger.py`; first end-to-end deck.
4. **M4 — revision**: critique_3axis + revision_loop + Stage 5.
5. **M5 — deck critique**: Stage 6 wired to v1 `critic.py`.
6. **M6 — gallery**: `gallery.py` + Stage 7 + Stage 1b injection.
7. **M7 — polish**: tests, README v2 section, comparison guide.

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| First run has empty gallery → 1b injection has no effect | Intended; after M6 land, run on 3–4 sample decks and commit a seed `references/index.json` |
| LLM re-imports modules → `NameError` or shadowed defenses | Preamble provides every needed import; auto_fix prompt says "no new imports — use preamble" |
| Float-EMU errors recur | `_patch_shapes` is invoked by the footer, not the LLM; defense is unconditional |
| matplotlib lacks Korean font in subprocess | preamble sets `plt.rcParams["font.family"]` with fallback chain |
| Vision LLM unavailable for current provider | If `LLM_VISION_MODEL` empty, Stage 5 logs warn and skips; Stage 7 still runs (uses whatever scores exist or marks slides ineligible) |
| `references/index.json` grows unbounded | Per-category cap (20) + oldest pruning |
| Comparing v1 and v2 needs the same input twice | Both runners take identical positional CLI args; output paths differ only by `_v2` suffix |

## 10. Open questions (deferred, not blocking M1)

- Should auto_fix and code_revision share a single code-edit prompt, or stay split?
- Should the gallery store the full assembled slide file or just the `build_slide` body? (current plan: body only — preamble is a moving target)
- Vision call interface: is there an existing `chat_with_image` in `src/llm/client.py`? If not, where does it live? (verify in M2)
