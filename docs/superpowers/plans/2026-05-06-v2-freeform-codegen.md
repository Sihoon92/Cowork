# v2 Freeform Codegen Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a second PPTX generation pipeline (v2) that runs alongside the v1 recipe pipeline. v2 generates python-pptx code per slide via LLM, executes each in a subprocess, refines via 3-axis vision critique, and learns by accumulating high-scoring slides in `references/index.json`.

**Architecture:** Two-phase planning (1a structure, 1b visual strategy with gallery injection) → per-slide LLM code generation prepended with a fixed preamble → subprocess execution with auto-fix retries → merge → vision-LLM critique loop with partial revise → deck critique → gallery persistence. v1 in `src/pipeline/` is read-only; v2 lives entirely in `src/pipeline_v2/`, `prompts/v2/`, `guidelines/v2/`, and `scripts/run_pipeline_v2.py`.

**Tech Stack:** Python 3.12, python-pptx 1.0.2, pydantic, matplotlib (Agg), Ollama or OpenAI-compatible LLM via `src/llm/client.py` (already supports `chat` and `chat_with_image`), pytest with `live` marker for LLM tests.

**Spec:** `docs/superpowers/specs/2026-05-06-v2-freeform-codegen-design.md`

---

## File Structure

**New files (created by this plan):**

```
src/pipeline_v2/
  __init__.py
  schemas.py                # pydantic models (Task 1)
  gallery.py                # JSON store + lookup (Task 2)
  outline.py                # Stage 1a (Task 4)
  visual_strategy.py        # Stage 1b (Task 5)
  code_assembler.py         # preamble + body + footer composition (Task 6)
  code_generator.py         # Stage 2 LLM call (Task 7)
  auto_fix.py               # Stage 3 retry loop (Task 7)
  revision_loop.py          # Stage 5 (Task 9)
  builder.py                # orchestrator (Task 10)

guidelines/v2/
  preamble.py               # imports, tokens, _patch_shapes (Task 6)
  design_guide.md           # raw python-pptx recipes & anti-patterns (Task 7)

prompts/v2/
  outline_1a.md             # (Task 4)
  visual_strategy_1b.md     # (Task 5)
  code_generation.md        # (Task 7)
  code_auto_fix.md          # (Task 7)
  slide_critique_3axis.md   # (Task 9)
  code_revision.md          # (Task 9)

references/
  .gitkeep                  # gallery initialized lazily by Task 2

scripts/
  run_pipeline_v2.py        # entry point (Task 10)

tests/v2/
  __init__.py
  test_schemas.py           # (Task 1)
  test_gallery.py           # (Task 2)
  test_preamble.py          # (Task 6)
  test_code_assembler.py    # (Task 6)
  test_code_runner_v2.py    # (Task 7) — fixed body, real subprocess
  test_outline.py           # (Task 4) — live
  test_visual_strategy.py   # (Task 5) — live
  test_pipeline_v2.py       # (Task 10) — live, end-to-end
```

**Reused without modification:** `src/llm/client.py` (`chat`, `chat_with_image`), `src/pptx/code_runner.py` (`run_slide_code`, `CodeExecutionError`), `src/pptx/merger.py` (`merge_slides`), `src/pptx/capture.py` (`screenshot_deck`), `src/pipeline/critic.py` (`critique_deck_storyline`, `critique_deck_visual`).

---

## Task 1: Schemas

**Files:**
- Create: `src/pipeline_v2/__init__.py`
- Create: `src/pipeline_v2/schemas.py`
- Create: `tests/v2/__init__.py`
- Create: `tests/v2/test_schemas.py`

- [ ] **Step 1: Create empty package markers**

```python
# src/pipeline_v2/__init__.py
"""v2 freeform-codegen pipeline. See docs/superpowers/specs/2026-05-06-v2-freeform-codegen-design.md."""
```

```python
# tests/v2/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/v2/test_schemas.py
import pytest
from pydantic import ValidationError

from src.pipeline_v2.schemas import (
    SlideOutline, VisualStrategy, SlidePlanV2,
    CritiqueIssue, SlideCritique, GalleryEntry,
)


def test_slide_outline_title_minimal():
    s = SlideOutline(index=1, kind="title", subtitle="hello")
    assert s.kind == "title"
    assert s.content_structure is None


def test_slide_outline_body_requires_kind_value():
    s = SlideOutline(index=2, kind="body", headline="h",
                     takeaway="t", content_structure="comparison")
    assert s.content_structure == "comparison"


def test_slide_outline_invalid_kind():
    with pytest.raises(ValidationError):
        SlideOutline(index=1, kind="bogus")


def test_visual_strategy_requires_all_fields():
    vs = VisualStrategy(approach="two_card_compare",
                        rationale="A vs B is the simplest contrast",
                        layout_hint="grid 1x2, equal",
                        key_elements=["a", "b"])
    assert vs.approach == "two_card_compare"


def test_slide_plan_v2_body_with_strategy():
    p = SlidePlanV2(
        index=2, kind="body", headline="h", takeaway="t",
        content_structure="metric",
        visual_strategy=VisualStrategy(
            approach="big_number_with_caption",
            rationale="single hero metric",
            layout_hint="centered 96pt + caption",
            key_elements=["value"]),
    )
    assert p.visual_strategy.approach == "big_number_with_caption"


def test_critique_issue_and_critique():
    issue = CritiqueIssue(
        location="3rd card bottom note",
        root_cause="card width includes padding",
        code_hint="card_w = (SLIDE_W - 4*pad)//3",
    )
    c = SlideCritique(score_strategy=8, score_visual=6, score_content=9,
                      issues=[issue], verdict="REVISE")
    assert min(c.score_strategy, c.score_visual, c.score_content) == 6


def test_critique_score_range_validation():
    with pytest.raises(ValidationError):
        SlideCritique(score_strategy=11, score_visual=5, score_content=5,
                      issues=[], verdict="KEEP")


def test_gallery_entry_round_trip():
    g = GalleryEntry(
        deck_id="work_v2_demo", slide_no=3, category="comparison",
        approach="horizontal_metric_cards_dominant_emphasis",
        rationale="emphasize winner",
        layout_hint="grid 1x3, center 1.4x",
        key_elements=["a", "b", "c"],
        scores={"strategy": 9, "visual": 8, "content": 9},
        quality_score=8.0,
        code_snippet="    set_bg(slide, BG)\n",
        created_at="2026-05-06T14:23:11",
    )
    assert g.quality_score == 8.0
    assert g.model_dump()["category"] == "comparison"
```

- [ ] **Step 3: Run test to verify it fails**

```
PYTHONIOENCODING=utf-8 pytest tests/v2/test_schemas.py -v
```
Expected: FAIL with `ModuleNotFoundError: src.pipeline_v2.schemas`.

- [ ] **Step 4: Implement schemas**

```python
# src/pipeline_v2/schemas.py
"""Pydantic models for the v2 pipeline.

See docs/superpowers/specs/2026-05-06-v2-freeform-codegen-design.md §5.4.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, conint


CONTENT_STRUCTURES = Literal[
    "comparison", "process", "hierarchy", "matrix", "metric",
    "narrative", "enumeration", "timeline", "system", "other",
]


class SlideOutline(BaseModel):
    index: int
    kind: Literal["title", "body", "closing"]
    headline: str = ""
    takeaway: str = ""
    subtitle: str = ""
    implication: str = ""
    content_structure: Optional[CONTENT_STRUCTURES] = None


class VisualStrategy(BaseModel):
    approach: str            # snake_case, unique within deck
    rationale: str
    layout_hint: str
    key_elements: list[str]


class SlidePlanV2(SlideOutline):
    visual_strategy: Optional[VisualStrategy] = None


class CritiqueIssue(BaseModel):
    location: str
    root_cause: str
    code_hint: str


class SlideCritique(BaseModel):
    score_strategy: conint(ge=0, le=10)  # type: ignore[valid-type]
    score_visual: conint(ge=0, le=10)    # type: ignore[valid-type]
    score_content: conint(ge=0, le=10)   # type: ignore[valid-type]
    issues: list[CritiqueIssue] = Field(default_factory=list)
    verdict: Literal["KEEP", "REVISE", "REGENERATE"]

    @property
    def min_score(self) -> int:
        return min(self.score_strategy, self.score_visual, self.score_content)


class GalleryEntry(BaseModel):
    deck_id: str
    slide_no: int
    category: str            # = content_structure
    approach: str
    rationale: str
    layout_hint: str
    key_elements: list[str]
    scores: dict[str, int]
    quality_score: float
    code_snippet: str
    created_at: str          # ISO 8601
```

- [ ] **Step 5: Run test to verify it passes**

```
PYTHONIOENCODING=utf-8 pytest tests/v2/test_schemas.py -v
```
Expected: 8 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline_v2/__init__.py src/pipeline_v2/schemas.py tests/v2/__init__.py tests/v2/test_schemas.py
git commit -m "feat(v2): pydantic schemas for outline, plan, critique, gallery"
```

---

## Task 2: Gallery store

**Files:**
- Create: `src/pipeline_v2/gallery.py`
- Create: `references/.gitkeep`
- Create: `tests/v2/test_gallery.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/v2/test_gallery.py
from pathlib import Path

from src.pipeline_v2.gallery import Gallery
from src.pipeline_v2.schemas import GalleryEntry


def _entry(deck="d1", slide_no=1, category="comparison",
           approach="a1", quality=8.0):
    return GalleryEntry(
        deck_id=deck, slide_no=slide_no, category=category,
        approach=approach, rationale="r", layout_hint="hint",
        key_elements=["x"],
        scores={"strategy": int(quality), "visual": int(quality), "content": int(quality)},
        quality_score=quality,
        code_snippet="pass",
        created_at="2026-05-06T00:00:00",
    )


def test_gallery_append_and_load(tmp_path: Path):
    g = Gallery(tmp_path / "index.json")
    g.append(_entry())
    g2 = Gallery(tmp_path / "index.json")
    assert len(g2.all()) == 1
    assert g2.all()[0].approach == "a1"


def test_gallery_dedup_keeps_higher_score(tmp_path: Path):
    g = Gallery(tmp_path / "index.json")
    g.append(_entry(quality=7.5))
    g.append(_entry(quality=9.0))
    rows = g.all()
    assert len(rows) == 1
    assert rows[0].quality_score == 9.0


def test_gallery_top_k_per_category(tmp_path: Path):
    g = Gallery(tmp_path / "index.json")
    for i, q in enumerate([7.0, 9.0, 8.5, 6.0]):
        g.append(_entry(slide_no=i, approach=f"a{i}", quality=q))
    g.append(_entry(slide_no=99, category="metric",
                    approach="m1", quality=10.0))
    refs = g.top_k(category="comparison", k=2)
    assert [r.quality_score for r in refs] == [9.0, 8.5]


def test_gallery_pruning_per_category(tmp_path: Path):
    g = Gallery(tmp_path / "index.json", per_category_cap=3)
    for i in range(5):
        g.append(_entry(slide_no=i, approach=f"a{i}",
                        quality=7.0 + i * 0.1))
    rows = [r for r in g.all() if r.category == "comparison"]
    assert len(rows) == 3
    # Oldest pruned: a0, a1 dropped (lowest quality + oldest)
    approaches = {r.approach for r in rows}
    assert "a0" not in approaches
```

- [ ] **Step 2: Run test to verify it fails**

```
PYTHONIOENCODING=utf-8 pytest tests/v2/test_gallery.py -v
```
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement Gallery**

```python
# src/pipeline_v2/gallery.py
"""Persistent gallery of high-scoring slides for cross-deck learning.

See spec §5.8.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.pipeline_v2.schemas import GalleryEntry


class Gallery:
    """JSON-backed gallery. Appends with dedup + per-category cap pruning."""

    def __init__(self, path: Path, per_category_cap: int = 20):
        self.path = Path(path)
        self.per_category_cap = per_category_cap
        self._entries: list[GalleryEntry] = self._load()

    # -- I/O ----------------------------------------------------------
    def _load(self) -> list[GalleryEntry]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [GalleryEntry.model_validate(r) for r in raw]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [e.model_dump() for e in self._entries]
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # -- queries ------------------------------------------------------
    def all(self) -> list[GalleryEntry]:
        return list(self._entries)

    def top_k(self, *, category: str, k: int = 2) -> list[GalleryEntry]:
        cands = [e for e in self._entries if e.category == category]
        cands.sort(key=lambda e: e.quality_score, reverse=True)
        return cands[:k]

    # -- mutation -----------------------------------------------------
    def append(self, entry: GalleryEntry) -> None:
        # Dedup on (deck_id, slide_no): keep higher quality_score.
        for i, e in enumerate(self._entries):
            if e.deck_id == entry.deck_id and e.slide_no == entry.slide_no:
                if entry.quality_score > e.quality_score:
                    self._entries[i] = entry
                self._prune_category(entry.category)
                self._save()
                return
        self._entries.append(entry)
        self._prune_category(entry.category)
        self._save()

    def _prune_category(self, category: str) -> None:
        cat = [e for e in self._entries if e.category == category]
        if len(cat) <= self.per_category_cap:
            return
        # Sort by (quality_score desc, created_at desc) and keep top N
        cat.sort(key=lambda e: (e.quality_score, e.created_at), reverse=True)
        keep = set(id(e) for e in cat[: self.per_category_cap])
        self._entries = [
            e for e in self._entries
            if e.category != category or id(e) in keep
        ]
```

- [ ] **Step 4: Create the references directory marker**

```
# references/.gitkeep
```

(empty file — keeps the dir in git before any gallery is written)

- [ ] **Step 5: Run test to verify it passes**

```
PYTHONIOENCODING=utf-8 pytest tests/v2/test_gallery.py -v
```
Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline_v2/gallery.py references/.gitkeep tests/v2/test_gallery.py
git commit -m "feat(v2): persistent gallery store with dedup and category pruning"
```

---

## Task 3: Prompt loading helper

**Files:**
- Create: `src/pipeline_v2/prompts.py`
- Create: `tests/v2/test_prompts.py`

A tiny helper that loads `prompts/v2/<name>.md` and substitutes `{placeholder}` tokens. Prompts files themselves are written in the milestones that use them.

- [ ] **Step 1: Write the failing test**

```python
# tests/v2/test_prompts.py
from pathlib import Path
from src.pipeline_v2.prompts import load_prompt


def test_load_prompt_substitutes(tmp_path: Path, monkeypatch):
    prompts = tmp_path / "prompts" / "v2"
    prompts.mkdir(parents=True)
    (prompts / "demo.md").write_text("Hello {name}!", encoding="utf-8")
    monkeypatch.setattr("src.pipeline_v2.prompts.PROMPTS_DIR", prompts)
    out = load_prompt("demo", name="world")
    assert out == "Hello world!"


def test_load_prompt_missing_placeholder_raises(tmp_path: Path, monkeypatch):
    prompts = tmp_path / "prompts" / "v2"
    prompts.mkdir(parents=True)
    (prompts / "demo.md").write_text("Hi {name} {age}", encoding="utf-8")
    monkeypatch.setattr("src.pipeline_v2.prompts.PROMPTS_DIR", prompts)
    import pytest
    with pytest.raises(KeyError):
        load_prompt("demo", name="x")  # 'age' missing
```

- [ ] **Step 2: Run test to verify it fails**

```
PYTHONIOENCODING=utf-8 pytest tests/v2/test_prompts.py -v
```
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# src/pipeline_v2/prompts.py
"""Prompt loader for v2.

Templates live in ``prompts/v2/<name>.md`` and use ``{placeholder}`` syntax.
``str.format_map`` is used so missing keys raise KeyError loudly.
"""
from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts" / "v2"


class _StrictMap(dict):
    def __missing__(self, key):  # noqa: D401
        raise KeyError(f"missing prompt placeholder: {{{key}}}")


def load_prompt(name: str, **values: object) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    template = path.read_text(encoding="utf-8")
    return template.format_map(_StrictMap(values))
```

- [ ] **Step 4: Run test to verify it passes**

```
PYTHONIOENCODING=utf-8 pytest tests/v2/test_prompts.py -v
```
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline_v2/prompts.py tests/v2/test_prompts.py
git commit -m "feat(v2): strict prompt template loader for prompts/v2/*"
```

---

## Task 4: Stage 1a — outline

**Files:**
- Create: `prompts/v2/outline_1a.md`
- Create: `src/pipeline_v2/outline.py`
- Create: `tests/v2/test_outline.py`

- [ ] **Step 1: Write the prompt template**

```markdown
<!-- prompts/v2/outline_1a.md -->
You are a presentation content analyst. Given an insight report, produce a
slide outline as JSON — structure only, no visual design yet.

## Schema (return EXACTLY this shape, no extra keys)

{{
  "slides": [
    {{"index": 1, "kind": "title", "headline": "...", "subtitle": "..."}},
    {{"index": 2, "kind": "body", "headline": "...", "takeaway": "...",
      "implication": "", "content_structure": "comparison"}},
    {{"index": N, "kind": "closing", "headline": "...", "subtitle": "..."}}
  ]
}}

`content_structure` must be exactly one of:
comparison | process | hierarchy | matrix | metric | narrative |
enumeration | timeline | system | other

## Rules

- index 1 must be `kind: title`; the last slide must be `kind: closing`.
- At least 2 body slides between them.
- title/closing slides: only `index`, `kind`, `headline`, `subtitle`.
- body slides: omit `subtitle`. `implication` may be empty string.
- Do NOT add a `visual_strategy` field — that is Phase 1b.
- Respond with ONLY the JSON object. No markdown fences, no prose.

## Input

```json
{content_json}
```
```

(Note: the literal `{{` / `}}` in the schema example escape the braces so
`str.format` only consumes `{content_json}`.)

- [ ] **Step 2: Write the failing test**

```python
# tests/v2/test_outline.py
import json
import pytest

from src.pipeline_v2.outline import generate_outline


pytestmark = pytest.mark.live


def test_outline_smoke():
    content = {
        "meta": {"title": "AI in 2026"},
        "sections": [
            {"heading": "Today", "body": "GPT-class models everywhere."},
            {"heading": "Action", "body": "Pilot, measure, expand."},
        ],
    }
    out = generate_outline(content)
    assert out["slides"][0]["kind"] == "title"
    assert out["slides"][-1]["kind"] == "closing"
    bodies = [s for s in out["slides"] if s["kind"] == "body"]
    assert len(bodies) >= 2
    for s in bodies:
        assert s["content_structure"] in {
            "comparison","process","hierarchy","matrix","metric",
            "narrative","enumeration","timeline","system","other",
        }
```

- [ ] **Step 3: Run test to verify it fails**

```
PYTHONIOENCODING=utf-8 pytest tests/v2/test_outline.py -v -m live
```
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 4: Implement**

```python
# src/pipeline_v2/outline.py
"""Stage 1a — structural outline only (no visual strategy).

See spec §4 (Stage 1a) and §5.5.
"""
from __future__ import annotations

import json

from src.llm.client import chat
from src.pipeline.planner import parse_json_block  # reuse v1 JSON repair
from src.pipeline_v2.prompts import load_prompt
from src.pipeline_v2.schemas import SlideOutline
from src.util import log


def generate_outline(content: dict) -> dict:
    """Return ``{"slides": [SlideOutline-shaped dicts]}``."""
    prompt = load_prompt(
        "outline_1a",
        content_json=json.dumps(content, ensure_ascii=False, indent=2),
    )
    log.stage("v2 Stage 1a: outline")
    raw = chat(prompt)
    data = parse_json_block(raw)
    if not isinstance(data, dict) or "slides" not in data:
        raise ValueError(f"outline_1a returned unexpected shape: {data!r}")

    # Validate each slide round-trips through the model.
    cleaned = []
    for s in data["slides"]:
        cleaned.append(SlideOutline.model_validate(s).model_dump(exclude_none=False))
    log.ok(f"outline: {len(cleaned)} slides")
    return {"slides": cleaned}
```

- [ ] **Step 5: Run test to verify it passes**

```
PYTHONIOENCODING=utf-8 pytest tests/v2/test_outline.py -v -m live
```
Expected: PASS (requires running LLM — Ollama or configured `LLM_PROVIDER`).

- [ ] **Step 6: Commit**

```bash
git add prompts/v2/outline_1a.md src/pipeline_v2/outline.py tests/v2/test_outline.py
git commit -m "feat(v2): Stage 1a structural outline LLM call"
```

---

## Task 5: Stage 1b — visual strategy with gallery injection

**Files:**
- Create: `prompts/v2/visual_strategy_1b.md`
- Create: `src/pipeline_v2/visual_strategy.py`
- Create: `tests/v2/test_visual_strategy.py`

- [ ] **Step 1: Write the prompt template**

```markdown
<!-- prompts/v2/visual_strategy_1b.md -->
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
```

- [ ] **Step 2: Write the failing test**

```python
# tests/v2/test_visual_strategy.py
import pytest
from pathlib import Path

from src.pipeline_v2.gallery import Gallery
from src.pipeline_v2.visual_strategy import (
    add_visual_strategy, _format_gallery_refs, _format_used_approaches,
)


def test_format_used_approaches_empty():
    assert _format_used_approaches([]).strip() == "(none yet)"


def test_format_used_approaches_some():
    out = _format_used_approaches(["a_b", "c_d"])
    assert "- a_b" in out and "- c_d" in out


def test_format_gallery_refs_empty(tmp_path: Path):
    g = Gallery(tmp_path / "index.json")
    out = _format_gallery_refs(g, categories={"comparison", "metric"})
    assert "(no references" in out


@pytest.mark.live
def test_add_visual_strategy_smoke():
    plan = {"slides": [
        {"index": 1, "kind": "title", "headline": "Hello", "subtitle": "Sub"},
        {"index": 2, "kind": "body", "headline": "A vs B",
         "takeaway": "B wins on cost", "implication": "",
         "content_structure": "comparison"},
        {"index": 3, "kind": "closing", "headline": "Thanks", "subtitle": "Q&A"},
    ]}
    out = add_visual_strategy(plan, gallery=None)
    body = [s for s in out["slides"] if s["kind"] == "body"][0]
    vs = body["visual_strategy"]
    assert vs["approach"]
    assert vs["layout_hint"]
    assert isinstance(vs["key_elements"], list) and vs["key_elements"]
```

- [ ] **Step 3: Run test to verify it fails**

```
PYTHONIOENCODING=utf-8 pytest tests/v2/test_visual_strategy.py -v
```
Expected: FAIL.

- [ ] **Step 4: Implement**

```python
# src/pipeline_v2/visual_strategy.py
"""Stage 1b — add visual_strategy to body slides; inject gallery references.

See spec §4 (Stage 1b) and §5.8 (gallery lookup).
"""
from __future__ import annotations

import json
from typing import Optional

from src.llm.client import chat
from src.pipeline.planner import parse_json_block
from src.pipeline_v2.gallery import Gallery
from src.pipeline_v2.prompts import load_prompt
from src.pipeline_v2.schemas import SlidePlanV2
from src.util import log

K_PER_CATEGORY = 2
SNIPPET_LINES = 30


def _format_used_approaches(used: list[str]) -> str:
    if not used:
        return "(none yet)"
    return "\n".join(f"- {a}" for a in used)


def _format_gallery_refs(
    gallery: Optional[Gallery], *, categories: set[str]
) -> str:
    if gallery is None or not categories:
        return "(no references available)"
    chunks = []
    for cat in sorted(categories):
        refs = gallery.top_k(category=cat, k=K_PER_CATEGORY)
        if not refs:
            continue
        chunks.append(f"### content_structure = {cat}")
        for r in refs:
            snippet = "\n".join(r.code_snippet.splitlines()[:SNIPPET_LINES])
            chunks.append(
                f"- score={r.quality_score:.1f}  approach: `{r.approach}`\n"
                f"  layout_hint: {r.layout_hint}\n"
                f"  code_snippet (first {SNIPPET_LINES} lines):\n"
                f"  ```python\n{snippet}\n  ```"
            )
    return "\n".join(chunks) if chunks else "(no references for these categories)"


def add_visual_strategy(plan: dict, *, gallery: Optional[Gallery]) -> dict:
    """Return plan with `visual_strategy` populated on body slides."""
    log.stage("v2 Stage 1b: visual strategy")
    body_categories = {
        s["content_structure"] for s in plan["slides"]
        if s["kind"] == "body" and s.get("content_structure")
    }
    prompt = load_prompt(
        "visual_strategy_1b",
        plan_json=json.dumps(plan, ensure_ascii=False, indent=2),
        used_approaches=_format_used_approaches([]),  # first call: empty
        gallery_references=_format_gallery_refs(gallery, categories=body_categories),
    )
    raw = chat(prompt)
    data = parse_json_block(raw)
    if not isinstance(data, dict) or "slides" not in data:
        raise ValueError(f"visual_strategy_1b returned unexpected shape: {data!r}")

    # Validate every slide.
    cleaned = []
    used = set()
    for s in data["slides"]:
        valid = SlidePlanV2.model_validate(s)
        if valid.kind == "body" and valid.visual_strategy:
            if valid.visual_strategy.approach in used:
                raise ValueError(
                    f"duplicate approach within deck: {valid.visual_strategy.approach!r}"
                )
            used.add(valid.visual_strategy.approach)
        cleaned.append(valid.model_dump(exclude_none=False))
    log.ok(
        f"visual_strategy: {sum(1 for s in cleaned if s['kind']=='body')} body slides"
    )
    return {"slides": cleaned}
```

- [ ] **Step 5: Run unit tests + live smoke**

```
PYTHONIOENCODING=utf-8 pytest tests/v2/test_visual_strategy.py -v
```
Expected: 3 unit PASS, 1 live PASS.

- [ ] **Step 6: Commit**

```bash
git add prompts/v2/visual_strategy_1b.md src/pipeline_v2/visual_strategy.py tests/v2/test_visual_strategy.py
git commit -m "feat(v2): Stage 1b visual_strategy with gallery injection"
```

---

## Task 6: Preamble + code assembler

**Files:**
- Create: `guidelines/v2/preamble.py`
- Create: `src/pipeline_v2/code_assembler.py`
- Create: `tests/v2/test_preamble.py`
- Create: `tests/v2/test_code_assembler.py`

- [ ] **Step 1: Write the preamble**

```python
# guidelines/v2/preamble.py
"""Prepended to every LLM-generated slide module. Provides imports,
design tokens, and a defense layer (`_patch_shapes`) against the
float-EMU bug python-pptx silently passes through.

The footer (added by code_assembler.py) calls _patch_shapes(slide)
before invoking build_slide(prs), so the LLM cannot disable the defense.
"""
from __future__ import annotations

import math
from pathlib import Path

# python-pptx
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE

# matplotlib (Agg backend; Korean-capable font fallback)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = ["Pretendard", "Malgun Gothic", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

# Color tokens
PRIMARY = RGBColor(0x1F, 0x36, 0x5C)
ACCENT  = RGBColor(0xE8, 0x6A, 0x33)
INK     = RGBColor(0x1A, 0x1A, 0x1A)
MUTED   = RGBColor(0x77, 0x77, 0x77)
BG      = RGBColor(0xFF, 0xFF, 0xFF)
SURFACE = RGBColor(0xF4, 0xF6, 0xFA)

# Typography tokens
FONT_HEAD = "Pretendard"
FONT_BODY = "Pretendard"
SIZE_HEAD = Pt(36)
SIZE_SUB  = Pt(20)
SIZE_BODY = Pt(14)
SIZE_CAP  = Pt(11)

# Canvas (16:9)
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def _coerce_int_args(fn):
    def wrapper(*args, **kwargs):
        new_args = tuple(int(a) if isinstance(a, float) else a for a in args)
        new_kwargs = {
            k: (int(v) if isinstance(v, float) else v) for k, v in kwargs.items()
        }
        return fn(*new_args, **new_kwargs)
    wrapper.__wrapped__ = fn
    return wrapper


def _patch_shapes(slide):
    """Replace add_* methods on slide.shapes to coerce floats to ints.

    Safe to call multiple times — checks for prior wrapping.
    """
    for name in ("add_textbox", "add_shape", "add_connector",
                 "add_picture", "add_chart", "add_table"):
        orig = getattr(slide.shapes, name, None)
        if orig is None or hasattr(orig, "__wrapped__"):
            continue
        setattr(slide.shapes, name, _coerce_int_args(orig))
    return slide
```

- [ ] **Step 2: Write the failing preamble test**

```python
# tests/v2/test_preamble.py
from pathlib import Path
import subprocess
import sys
import textwrap

PREAMBLE_PATH = Path(__file__).resolve().parents[2] / "guidelines" / "v2" / "preamble.py"


def test_preamble_imports_clean(tmp_path: Path):
    """The preamble must execute on its own without errors."""
    out = tmp_path / "x.py"
    out.write_text(PREAMBLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(out)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_patch_shapes_casts_floats(tmp_path: Path):
    code = PREAMBLE_PATH.read_text(encoding="utf-8") + textwrap.dedent("""
        prs = Presentation()
        prs.slide_width = SLIDE_W
        prs.slide_height = SLIDE_H
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        _patch_shapes(slide)
        # All four positional args are floats — the patch must cast them.
        slide.shapes.add_textbox(Inches(1.0).emu * 1.0,
                                 Inches(1.0).emu * 1.0,
                                 Inches(2.0).emu * 1.0,
                                 Inches(1.0).emu * 1.0)
        out = r"{out_pptx}"
        prs.save(out)
    """)
    pptx = tmp_path / "out.pptx"
    script = tmp_path / "run.py"
    script.write_text(code.replace("{out_pptx}", str(pptx)), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(script)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert pptx.exists() and pptx.stat().st_size > 0
```

- [ ] **Step 3: Run preamble test (must fail until preamble created — already done in Step 1)**

```
PYTHONIOENCODING=utf-8 pytest tests/v2/test_preamble.py -v
```
Expected: 2 PASS (file already exists from Step 1).

- [ ] **Step 4: Write the failing assembler test**

```python
# tests/v2/test_code_assembler.py
from pathlib import Path

from src.pipeline_v2.code_assembler import assemble_slide_module


def test_assemble_includes_preamble_body_footer(tmp_path: Path):
    body = "def build_slide(prs):\n    slide = prs.slides[0]\n    pass\n"
    out_pptx = tmp_path / "out.pptx"
    code = assemble_slide_module(body, out_pptx)
    assert "from pptx import Presentation" in code      # preamble
    assert "def build_slide(prs):" in code              # body
    assert "_patch_shapes(slide)" in code               # footer
    assert str(out_pptx) in code                        # footer save path


def test_assemble_strips_main_block_in_body(tmp_path: Path):
    body = (
        "def build_slide(prs):\n    pass\n\n"
        "if __name__ == '__main__':\n    print('ignore')\n"
    )
    code = assemble_slide_module(body, tmp_path / "x.pptx")
    # The LLM's __main__ block is preserved as-is; our footer comes after.
    # Verify the footer is the LAST __main__ block.
    assert code.rstrip().endswith("prs.save(_OUT_PATH)")
```

- [ ] **Step 5: Run test to verify it fails**

```
PYTHONIOENCODING=utf-8 pytest tests/v2/test_code_assembler.py -v
```
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 6: Implement assembler**

```python
# src/pipeline_v2/code_assembler.py
"""Assemble final slide module: preamble + LLM body + footer.

Footer adds the first slide, applies _patch_shapes, calls build_slide,
and saves to a fixed output path.
"""
from __future__ import annotations

from pathlib import Path

PREAMBLE_PATH = Path(__file__).resolve().parents[2] / "guidelines" / "v2" / "preamble.py"


_FOOTER_TEMPLATE = """

# --- v2 footer (auto-appended) ---
_OUT_PATH = r\"{out_path}\"

if __name__ == "__main__":
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _patch_shapes(slide)
    build_slide(prs)
    prs.save(_OUT_PATH)
"""


def assemble_slide_module(body: str, out_pptx: Path) -> str:
    """Compose ``preamble.py`` + LLM body + footer into a runnable module."""
    preamble = PREAMBLE_PATH.read_text(encoding="utf-8")
    footer = _FOOTER_TEMPLATE.format(out_path=str(out_pptx))
    return f"{preamble}\n\n# --- LLM body ---\n{body}\n{footer}\n"
```

- [ ] **Step 7: Run all Task 6 tests**

```
PYTHONIOENCODING=utf-8 pytest tests/v2/test_preamble.py tests/v2/test_code_assembler.py -v
```
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add guidelines/v2/preamble.py src/pipeline_v2/code_assembler.py tests/v2/test_preamble.py tests/v2/test_code_assembler.py
git commit -m "feat(v2): preamble with float-EMU defense + slide module assembler"
```

---

## Task 7: Stage 2 — code generation + auto-fix

**Files:**
- Create: `guidelines/v2/design_guide.md`
- Create: `prompts/v2/code_generation.md`
- Create: `prompts/v2/code_auto_fix.md`
- Create: `src/pipeline_v2/code_generator.py`
- Create: `src/pipeline_v2/auto_fix.py`
- Create: `tests/v2/test_code_runner_v2.py`

- [ ] **Step 1: Write the design guide**

```markdown
<!-- guidelines/v2/design_guide.md -->
# v2 Design Guide for LLM-generated python-pptx code

You will write the body of `def build_slide(prs):`. The framework
prepends a preamble that gives you all imports and design tokens, and
appends a footer that creates the first slide and calls
`_patch_shapes(slide)` for you. You do NOT write imports, slide creation,
or `prs.save`.

## Canvas
- Size: `SLIDE_W` × `SLIDE_H` (13.333 × 7.5 in, 16:9).
- Safe area: leave at least 0.4 in (`Inches(0.4)`) padding on all edges.

## Color tokens (use these — never hardcode hex)
`PRIMARY` `ACCENT` `INK` `MUTED` `BG` `SURFACE`

## Typography tokens (use these — never hardcode pt)
`FONT_HEAD` `FONT_BODY`
`SIZE_HEAD` (36) `SIZE_SUB` (20) `SIZE_BODY` (14) `SIZE_CAP` (11)

For headline emphasis larger than `SIZE_HEAD`, use `Pt(48)` etc. directly.

## Recipe snippets (illustrative; not mandatory)

### Headline strip

```python
def build_slide(prs):
    slide = prs.slides[0]
    # Background
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = BG; bg.line.fill.background()
    # Headline strip (top 1/4)
    strip = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                    0, 0, SLIDE_W, SLIDE_H // 4)
    strip.fill.solid(); strip.fill.fore_color.rgb = PRIMARY
    strip.line.fill.background()
```

### 1×3 cards with center emphasis (1.4×)

```python
pad = Inches(0.4)
content_top = SLIDE_H // 4 + Inches(0.3)
content_h = SLIDE_H - content_top - Inches(0.6)
# Ratios [1, 1.4, 1] — total 3.4
total = SLIDE_W - pad * 2
unit = total // 34
widths = [unit * 10, unit * 14, unit * 10]
gap = (total - sum(widths)) // 2
x = pad
for i, w in enumerate(widths):
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                   x, content_top, w, content_h)
    card.fill.solid()
    card.fill.fore_color.rgb = ACCENT if i == 1 else SURFACE
    x += w + gap
```

### Chart + side text card with connector

```python
# 1. Render donut PNG via matplotlib in-memory.
import io
fig, ax = plt.subplots(figsize=(4, 4), dpi=150)
ax.pie([60, 25, 15], wedgeprops={"width": 0.35})
ax.set(aspect="equal")
buf = io.BytesIO(); fig.savefig(buf, format="png", bbox_inches="tight"); plt.close(fig)
buf.seek(0)
chart_x, chart_y, chart_w, chart_h = Inches(0.6), Inches(1.5), Inches(5), Inches(5)
slide.shapes.add_picture(buf, chart_x, chart_y, chart_w, chart_h)
# 2. Side text card.
card_x, card_y = Inches(7), Inches(2)
card_w, card_h = Inches(5.7), Inches(3.5)
slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, card_x, card_y, card_w, card_h)
# 3. Connector from donut center to card left edge.
center_x = chart_x + chart_w // 2
center_y = chart_y + chart_h // 2
slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                            center_x, center_y, card_x, card_y + card_h // 2)
```

## Anti-patterns (NEVER do these)

- ❌ Hardcoded magic coordinates like `Inches(2.34)`. Compute from
  `SLIDE_W` / `SLIDE_H` and the padding budget.
- ❌ Hex literals like `RGBColor(0xAB, 0xCD, 0xEF)`. Use the tokens.
- ❌ External file paths (`open("foo.png")`). Generate everything inline
  with matplotlib + `io.BytesIO`.
- ❌ Hardcoded font names like `"Arial"`. Use `FONT_HEAD` / `FONT_BODY`.
- ❌ Adding new `import` statements. Everything you need is in the preamble.
- ❌ Calling `prs.save(...)` or `prs.slides.add_slide(...)`. The footer does it.

## Output

Reply with ONLY the body of `def build_slide(prs):` and any helper
functions you need. No prose, no markdown fences.
```

- [ ] **Step 2: Write the code-generation prompt**

```markdown
<!-- prompts/v2/code_generation.md -->
You are a senior visual designer who writes python-pptx code.

Generate the body of `def build_slide(prs):` for the slide below.
Strictly follow the design guide.

## Slide plan

```json
{slide_plan_json}
```

## Design guide

{design_guide}

## Available preamble (already imported — do not re-import)

```python
{preamble_excerpt}
```

Reply with ONLY Python code: the `def build_slide(prs):` definition
and any helpers. No fences, no explanations.
```

- [ ] **Step 3: Write the auto-fix prompt**

```markdown
<!-- prompts/v2/code_auto_fix.md -->
Your previous slide code raised an error during execution.

## Previous code

```python
{prev_code}
```

## Traceback

```
{traceback}
```

## Design guide reminders

{design_guide_excerpt}

Fix the bug. Do NOT add new imports. Do NOT call `prs.save`. Reply with
ONLY the corrected `def build_slide(prs):` body and helpers. No fences,
no prose.
```

- [ ] **Step 4: Write the failing runner test (uses a fixed body, not LLM)**

```python
# tests/v2/test_code_runner_v2.py
from pathlib import Path

from src.pipeline_v2.code_assembler import assemble_slide_module
from src.pipeline_v2.code_generator import execute_slide_body


GOOD_BODY = """
def build_slide(prs):
    slide = prs.slides[0]
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = BG
    bg.line.fill.background()
    tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.5),
                                  Inches(8), Inches(1))
    tb.text_frame.text = "Hello from v2"
"""


def test_execute_slide_body_writes_pptx(tmp_path: Path):
    out = tmp_path / "slide_01.pptx"
    execute_slide_body(GOOD_BODY, out, work_dir=tmp_path)
    assert out.exists() and out.stat().st_size > 0


BAD_BODY_FLOAT_EMU = """
def build_slide(prs):
    slide = prs.slides[0]
    # Float coords — without _patch_shapes this would emit float EMU
    slide.shapes.add_textbox(0.5 * 914400, 0.5 * 914400,
                             8.0 * 914400, 1.0 * 914400)
"""


def test_execute_slide_body_floats_survive_patch_shapes(tmp_path: Path):
    out = tmp_path / "slide_02.pptx"
    execute_slide_body(BAD_BODY_FLOAT_EMU, out, work_dir=tmp_path)
    assert out.exists()
```

- [ ] **Step 5: Run test to verify it fails**

```
PYTHONIOENCODING=utf-8 pytest tests/v2/test_code_runner_v2.py -v
```
Expected: FAIL `ModuleNotFoundError: src.pipeline_v2.code_generator`.

- [ ] **Step 6: Implement code_generator (executor + LLM call)**

```python
# src/pipeline_v2/code_generator.py
"""Stage 2 — generate per-slide python-pptx code via LLM and execute it.

The actual subprocess execution is handled by ``execute_slide_body``,
which is also reused by the auto-fix and revision loops.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.llm.client import chat
from src.pipeline_v2.code_assembler import (
    PREAMBLE_PATH, assemble_slide_module,
)
from src.pipeline_v2.prompts import load_prompt
from src.util import log


class SlideExecutionError(RuntimeError):
    def __init__(self, message: str, *, traceback: str, code: str):
        super().__init__(message)
        self.traceback = traceback
        self.code = code


def execute_slide_body(body: str, out_pptx: Path, *, work_dir: Path) -> Path:
    """Assemble body into a runnable module and execute in a subprocess."""
    work_dir.mkdir(parents=True, exist_ok=True)
    module_path = work_dir / f"{out_pptx.stem}.py"
    module = assemble_slide_module(body, out_pptx)
    module_path.write_text(module, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(module_path)],
        capture_output=True, text=True,
        env={"PYTHONIOENCODING": "utf-8", **_env_passthrough()},
    )
    if proc.returncode != 0 or not out_pptx.exists():
        raise SlideExecutionError(
            f"slide module failed (rc={proc.returncode})",
            traceback=proc.stderr or proc.stdout,
            code=body,
        )
    return out_pptx


def _env_passthrough() -> dict:
    import os
    keep = ("PATH", "SYSTEMROOT", "USERPROFILE", "TEMP", "TMP",
            "PYTHONPATH", "VIRTUAL_ENV")
    return {k: os.environ[k] for k in keep if k in os.environ}


def generate_slide_body(slide_plan: dict, *, design_guide: str,
                        preamble_excerpt: str) -> str:
    """Single LLM call. Returns code body only."""
    prompt = load_prompt(
        "code_generation",
        slide_plan_json=json.dumps(slide_plan, ensure_ascii=False, indent=2),
        design_guide=design_guide,
        preamble_excerpt=preamble_excerpt,
    )
    log.info(f"  generating code for slide {slide_plan.get('index')}")
    raw = chat(prompt)
    return _strip_fences(raw)


def _strip_fences(text: str) -> str:
    """Remove ```python ... ``` fences if the LLM ignored instructions."""
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        # drop opening fence
        if lines[0].startswith("```"):
            lines = lines[1:]
        # drop closing fence
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines)
    return t
```

- [ ] **Step 7: Implement auto_fix**

```python
# src/pipeline_v2/auto_fix.py
"""Retry loop for slide code execution.

Calls Stage 2 once; on failure, asks the LLM to fix the traceback up to
``max_retries`` times. Returns the body that finally produced a .pptx.
"""
from __future__ import annotations

from pathlib import Path

from src.llm.client import chat
from src.pipeline_v2.code_generator import (
    SlideExecutionError, _strip_fences, execute_slide_body,
)
from src.pipeline_v2.prompts import load_prompt
from src.util import log


def execute_with_auto_fix(
    body: str, out_pptx: Path, *, work_dir: Path,
    design_guide_excerpt: str, max_retries: int = 2,
) -> tuple[Path, str]:
    """Execute, retry via LLM on failure. Returns (pptx_path, final_body)."""
    current_body = body
    for attempt in range(max_retries + 1):
        try:
            execute_slide_body(current_body, out_pptx, work_dir=work_dir)
            return out_pptx, current_body
        except SlideExecutionError as exc:
            if attempt == max_retries:
                raise
            log.warn(f"  slide exec failed (attempt {attempt+1}); auto-fixing")
            prompt = load_prompt(
                "code_auto_fix",
                prev_code=current_body,
                traceback=_tail(exc.traceback, 40),
                design_guide_excerpt=design_guide_excerpt,
            )
            current_body = _strip_fences(chat(prompt))
    raise RuntimeError("unreachable")


def _tail(text: str, lines: int) -> str:
    parts = text.splitlines()
    return "\n".join(parts[-lines:])
```

- [ ] **Step 8: Run runner tests**

```
PYTHONIOENCODING=utf-8 pytest tests/v2/test_code_runner_v2.py -v
```
Expected: 2 PASS.

- [ ] **Step 9: Commit**

```bash
git add guidelines/v2/design_guide.md prompts/v2/code_generation.md prompts/v2/code_auto_fix.md src/pipeline_v2/code_generator.py src/pipeline_v2/auto_fix.py tests/v2/test_code_runner_v2.py
git commit -m "feat(v2): Stage 2 codegen + auto-fix subprocess execution"
```

---

## Task 8: Stage 4 wiring — first end-to-end (no critique yet)

**Files:**
- Modify: `src/pipeline_v2/builder.py` (create initial version)
- Create: `scripts/run_pipeline_v2.py`

This task wires Stages 1a, 1b, 2, 3, 4 into the smallest end-to-end runner so we can verify a full deck before adding revision and gallery.

- [ ] **Step 1: Implement initial builder**

```python
# src/pipeline_v2/builder.py
"""Stage 0–4 orchestrator. Stages 5–7 are added in later tasks.

See spec §4.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from src.pipeline_v2.auto_fix import execute_with_auto_fix
from src.pipeline_v2.code_assembler import PREAMBLE_PATH
from src.pipeline_v2.code_generator import generate_slide_body
from src.pipeline_v2.outline import generate_outline
from src.pipeline_v2.visual_strategy import add_visual_strategy
from src.pipeline_v2.gallery import Gallery
from src.pptx.merger import merge_slides
from src.util import log


GUIDELINES_DIR = Path(__file__).resolve().parents[2] / "guidelines" / "v2"


def build_presentation_v2(
    content: dict,
    *,
    output_path: Path,
    workdir: Path,
    gallery: Optional[Gallery] = None,
    enable_revision: bool = True,
    enable_gallery: bool = True,
    max_iter: int = 3,
) -> Path:
    t0 = time.time()
    output_path = Path(output_path)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    slides_dir = workdir / "slides"; slides_dir.mkdir(exist_ok=True)
    code_dir = workdir / "slide_codes"; code_dir.mkdir(exist_ok=True)

    # Stage 1a + 1b
    outline = generate_outline(content)
    (workdir / "outline.json").write_text(
        json.dumps(outline, ensure_ascii=False, indent=2), encoding="utf-8")

    plan = add_visual_strategy(
        outline,
        gallery=gallery if (enable_gallery and gallery is not None) else None,
    )
    (workdir / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    # Stage 2 + 3 (per-slide LLM codegen + auto-fix execution)
    design_guide = (GUIDELINES_DIR / "design_guide.md").read_text(encoding="utf-8")
    preamble_text = PREAMBLE_PATH.read_text(encoding="utf-8")

    slide_paths: list[Path] = []
    for s in plan["slides"]:
        idx = s["index"]
        log.stage(f"v2 Stage 2/3: slide {idx} ({s['kind']})")
        body = generate_slide_body(
            s, design_guide=design_guide, preamble_excerpt=preamble_text)
        out_pptx = slides_dir / f"slide_{idx:02d}.pptx"
        try:
            execute_with_auto_fix(
                body, out_pptx, work_dir=code_dir,
                design_guide_excerpt=design_guide[:2000],
            )
        except Exception as exc:  # noqa: BLE001
            log.warn(f"slide {idx} failed after retries: {exc}; placeholder used")
            _write_blank_slide(out_pptx, reason=str(exc))
        slide_paths.append(out_pptx)

    # Stage 4 — merge
    log.stage("v2 Stage 4: merge")
    merge_slides(slide_paths, output_path)
    log.ok(f"-> {output_path}  ({output_path.stat().st_size // 1024} KB)")

    # Stages 5–7 added in Tasks 9 & 10
    log.ok(f"v2 done in {time.time() - t0:.1f}s")
    return output_path


def _write_blank_slide(out_pptx: Path, *, reason: str) -> None:
    """Last-resort fallback so merge does not break."""
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(11), Inches(2))
    tb.text_frame.text = f"slide failed: {reason[:200]}"
    out_pptx.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_pptx))
```

- [ ] **Step 2: Implement runner**

```python
# scripts/run_pipeline_v2.py
"""Run the v2 freeform-codegen pipeline.

Usage mirrors scripts/run_pipeline.py:
    python scripts/run_pipeline_v2.py
    python scripts/run_pipeline_v2.py data/ai_era.json
    python scripts/run_pipeline_v2.py data/ai_era.json output/ai_era_v2.pptx
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline_v2.builder import build_presentation_v2
from src.pipeline_v2.gallery import Gallery
from src.util import log


def _parse_args(root: Path) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="v2 freeform-codegen PPTX pipeline.")
    p.add_argument("content", nargs="?",
                   default=str(root / "data" / "sample_content.json"))
    p.add_argument("output", nargs="?", default=None)
    p.add_argument("--workdir", default=None)
    p.add_argument("--no-revision", action="store_true")
    p.add_argument("--no-gallery", action="store_true")
    p.add_argument("--max-iter", type=int, default=3)
    return p.parse_args()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    args = _parse_args(root)

    content_path = Path(args.content)
    if not content_path.is_absolute():
        content_path = (root / content_path).resolve()
    if not content_path.exists():
        print(f"ERROR: content not found: {content_path}", file=sys.stderr)
        sys.exit(1)

    stem = content_path.stem
    output_path = Path(args.output) if args.output else root / "output" / f"{stem}_v2.pptx"
    if not output_path.is_absolute():
        output_path = (root / output_path).resolve()
    workdir = Path(args.workdir) if args.workdir else output_path.parent / f"work_v2_{stem}"
    if not workdir.is_absolute():
        workdir = (root / workdir).resolve()

    log.info(f"v2 content: {content_path}")
    log.info(f"v2 output:  {output_path}")
    log.info(f"v2 workdir: {workdir}")

    content = json.loads(content_path.read_text(encoding="utf-8"))
    gallery = None if args.no_gallery else Gallery(root / "references" / "index.json")

    out = build_presentation_v2(
        content,
        output_path=output_path,
        workdir=workdir,
        gallery=gallery,
        enable_revision=not args.no_revision,
        enable_gallery=not args.no_gallery,
        max_iter=args.max_iter,
    )
    print(f"OK -> {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run end-to-end smoke (live)**

```
PYTHONIOENCODING=utf-8 python scripts/run_pipeline_v2.py data/sample_content.json --no-revision --no-gallery
```
Expected: produces `output/sample_content_v2.pptx`. Open it manually and verify slides render.

- [ ] **Step 4: Commit**

```bash
git add src/pipeline_v2/builder.py scripts/run_pipeline_v2.py
git commit -m "feat(v2): minimal end-to-end builder (Stages 1a/1b/2/3/4) + runner"
```

---

## Task 9: Stage 5 — visual revision loop

**Files:**
- Create: `prompts/v2/slide_critique_3axis.md`
- Create: `prompts/v2/code_revision.md`
- Create: `src/pipeline_v2/revision_loop.py`
- Modify: `src/pipeline_v2/builder.py` (insert Stage 5 call)

- [ ] **Step 1: Write the critique prompt**

```markdown
<!-- prompts/v2/slide_critique_3axis.md -->
You are a presentation quality critic. Examine the rendered slide image
and score it against its plan.

## Scoring rubric (0–10 each)

- **score_strategy** — fidelity to `visual_strategy.layout_hint`.
  9–10 exact; 7–8 mostly right; 4–6 partial; 0–3 wrong layout.
- **score_visual** — alignment, spacing, color, hierarchy, readability.
  9–10 polished; 7–8 clean; 4–6 awkward; 0–3 broken/overlapping.
- **score_content** — text quality, message clarity, fit with layout.
  9–10 impactful; 7–8 clear; 4–6 flat; 0–3 truncated/typos.

## issues[] — each issue MUST follow this format

- `location`: pinpoint, e.g. "3rd card bottom note clipped 8px right".
  Do NOT say "text overlaps somewhere".
- `root_cause`: ONE sentence explaining why.
- `code_hint`: function- or parameter-level fix, e.g.
  "card_w = (SLIDE_W - 4*pad)//3".

## verdict — exactly one of: KEEP | REVISE | REGENERATE

Return ONLY this JSON shape:

{{
  "score_strategy": <int 0-10>,
  "score_visual": <int 0-10>,
  "score_content": <int 0-10>,
  "issues": [
    {{"location": "...", "root_cause": "...", "code_hint": "..."}}
  ],
  "verdict": "KEEP" | "REVISE" | "REGENERATE"
}}

## Plan

```json
{slide_plan_json}
```
```

- [ ] **Step 2: Write the revision prompt**

```markdown
<!-- prompts/v2/code_revision.md -->
You are revising slide code based on a visual critique.

## Slide plan

```json
{slide_plan_json}
```

## Critique

```json
{critique_json}
```

## Previous code

```python
{prev_code}
```

Apply fixes from the `issues` `code_hint` fields. Do NOT re-import. Do NOT
call `prs.save`. Reply with ONLY the corrected `def build_slide(prs):`
body and helpers. No fences, no prose.
```

- [ ] **Step 3: Implement revision_loop**

```python
# src/pipeline_v2/revision_loop.py
"""Stage 5 — per-slide visual revision loop.

For each slide, capture PNG → 3-axis critique → if min(scores) < 7 and
verdict != KEEP, ask LLM to revise the code, re-execute (with one
auto-fix retry on failure), and re-capture. Bail out early if no slide
was revised in an iteration.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.llm.client import chat, chat_with_image
from src.pipeline.planner import parse_json_block
from src.pipeline_v2.auto_fix import execute_with_auto_fix
from src.pipeline_v2.code_generator import _strip_fences
from src.pipeline_v2.prompts import load_prompt
from src.pipeline_v2.schemas import SlideCritique
from src.pptx.capture import screenshot_deck
from src.util import log

REVISE_THRESHOLD = 7


def _capture_slide(pptx_path: Path, out_dir: Path) -> Path:
    """Capture a single-slide deck to PNG. Returns the PNG path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pngs = screenshot_deck(pptx_path, out_dir)
    if not pngs:
        raise RuntimeError(f"capture produced no PNG for {pptx_path}")
    return pngs[0]


def _critique_slide(png: Path, slide_plan: dict) -> SlideCritique:
    prompt = load_prompt(
        "slide_critique_3axis",
        slide_plan_json=json.dumps(slide_plan, ensure_ascii=False, indent=2),
    )
    raw = chat_with_image(prompt, str(png))
    data = parse_json_block(raw)
    return SlideCritique.model_validate(data)


def _revise_code(slide_plan: dict, critique: SlideCritique, prev_code: str) -> str:
    prompt = load_prompt(
        "code_revision",
        slide_plan_json=json.dumps(slide_plan, ensure_ascii=False, indent=2),
        critique_json=critique.model_dump_json(indent=2),
        prev_code=prev_code,
    )
    return _strip_fences(chat(prompt))


def visual_revision_loop_v2(
    plan: dict,
    slide_paths: list[Path],
    slide_bodies: list[str],
    *,
    workdir: Path,
    design_guide_excerpt: str,
    max_iterations: int = 3,
) -> tuple[list[Path], list[str], list[SlideCritique]]:
    """Returns (final slide paths, final bodies, final critiques).

    ``slide_paths`` and ``slide_bodies`` are aligned to ``plan['slides']``.
    """
    code_dir = workdir / "slide_codes"
    captures_dir = workdir / "captures"
    crit_dir = workdir / "critiques"
    crit_dir.mkdir(parents=True, exist_ok=True)

    last_critiques: list[SlideCritique | None] = [None] * len(slide_paths)

    for it in range(1, max_iterations + 1):
        any_revised = False
        log.stage(f"v2 Stage 5: revision iter {it}")

        for n, (slide_path, body) in enumerate(zip(slide_paths, slide_bodies)):
            slide_plan = plan["slides"][n]
            png = _capture_slide(slide_path, captures_dir / f"iter{it}")

            try:
                crit = _critique_slide(png, slide_plan)
            except Exception as exc:  # noqa: BLE001
                log.warn(f"  slide {n+1}: critique failed ({exc}); skipping")
                continue
            (crit_dir / f"slide_{n+1:02d}_iter{it}.json").write_text(
                crit.model_dump_json(indent=2), encoding="utf-8")
            last_critiques[n] = crit

            if crit.verdict == "KEEP" or crit.min_score >= REVISE_THRESHOLD:
                continue

            log.info(f"  slide {n+1}: revising "
                     f"(strategy={crit.score_strategy} visual={crit.score_visual} "
                     f"content={crit.score_content})")
            try:
                new_body = _revise_code(slide_plan, crit, body)
                execute_with_auto_fix(
                    new_body, slide_path, work_dir=code_dir,
                    design_guide_excerpt=design_guide_excerpt, max_retries=1,
                )
                slide_bodies[n] = new_body
                # snapshot history
                hist = code_dir / f"{slide_path.stem}.iter{it}.py"
                hist.write_text(new_body, encoding="utf-8")
                any_revised = True
            except Exception as exc:  # noqa: BLE001
                log.warn(f"  slide {n+1} revision failed ({exc}); keeping previous")

        if not any_revised:
            log.ok(f"  no revisions in iter {it}; stopping")
            break

    return slide_paths, slide_bodies, [c for c in last_critiques if c is not None]
```

- [ ] **Step 4: Wire Stage 5 into builder**

Edit `src/pipeline_v2/builder.py` — after the merge step, insert:

```python
    # Stage 5 — visual revision loop
    final_critiques: list = []
    if enable_revision:
        try:
            from src.pipeline_v2.revision_loop import visual_revision_loop_v2
            slide_paths, slide_bodies, final_critiques = visual_revision_loop_v2(
                plan, slide_paths, slide_bodies,
                workdir=workdir,
                design_guide_excerpt=design_guide[:2000],
                max_iterations=max_iter,
            )
            merge_slides(slide_paths, output_path)
            log.ok(f"post-revision deck: {output_path}")
        except Exception as exc:  # noqa: BLE001
            log.warn(f"v2 revision loop crashed: {exc}; keeping pre-revision deck")
```

Also collect ``slide_bodies: list[str] = []`` during the Stage 2/3 loop and
append the *successful* body each iteration (the body returned by
``execute_with_auto_fix`` — modify the loop to capture it; on failure,
append an empty string so indexing stays aligned).

Concretely, in the existing loop, replace the try/except around
``execute_with_auto_fix`` with:

```python
        try:
            _, final_body = execute_with_auto_fix(
                body, out_pptx, work_dir=code_dir,
                design_guide_excerpt=design_guide[:2000],
            )
            slide_bodies.append(final_body)
        except Exception as exc:  # noqa: BLE001
            log.warn(f"slide {idx} failed after retries: {exc}; placeholder used")
            _write_blank_slide(out_pptx, reason=str(exc))
            slide_bodies.append("")  # keep alignment
        slide_paths.append(out_pptx)
```

Add ``slide_bodies: list[str] = []`` initialization above the loop.

Also add ``final_critiques`` to the function's return value if downstream
needs it; for now keep it in a local for Task 10's gallery step (we will
re-read critiques from disk).

- [ ] **Step 5: Live smoke (with revision)**

```
PYTHONIOENCODING=utf-8 python scripts/run_pipeline_v2.py data/sample_content.json --no-gallery --max-iter 1
```
Expected: produces an `output/.../sample_content_v2.pptx` plus
`workdir/critiques/*.json` and `workdir/captures/iter1/*.png`.

- [ ] **Step 6: Commit**

```bash
git add prompts/v2/slide_critique_3axis.md prompts/v2/code_revision.md src/pipeline_v2/revision_loop.py src/pipeline_v2/builder.py
git commit -m "feat(v2): Stage 5 vision-LLM critique + per-slide revision loop"
```

---

## Task 10: Stages 6 + 7 — deck critique and gallery persistence

**Files:**
- Modify: `src/pipeline_v2/builder.py` (add Stages 6, 7)
- Create: `tests/v2/test_pipeline_v2.py`

- [ ] **Step 1: Add Stage 6 + 7 to builder**

Insert at the end of `build_presentation_v2`, just before the final `log.ok`:

```python
    # Stage 6 — deck-level critique (reuse v1 critic)
    log.stage("v2 Stage 6: deck critique")
    from src.pipeline.critic import critique_deck_storyline, critique_deck_visual
    try:
        storyline = critique_deck_storyline(plan)
    except Exception as exc:  # noqa: BLE001
        log.warn(f"storyline critique skipped: {exc}")
        storyline = {"verdict": "SKIP", "reason": str(exc)}
    try:
        visual_consistency = critique_deck_visual(slide_paths, out_dir=workdir)
    except Exception as exc:  # noqa: BLE001
        log.warn(f"visual critique skipped: {exc}")
        visual_consistency = {"verdict": "SKIP", "reason": str(exc)}
    (workdir / "deck_critique.json").write_text(
        json.dumps({"storyline": storyline,
                    "visual_consistency": visual_consistency},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Stage 7 — gallery append (only if enabled and we have critiques)
    if enable_gallery and gallery is not None and final_critiques:
        from datetime import datetime
        from src.pipeline_v2.schemas import GalleryEntry
        log.stage("v2 Stage 7: gallery append")
        deck_id = workdir.name
        appended = 0
        for n, crit in enumerate(final_critiques):
            slide_plan = plan["slides"][n]
            if slide_plan["kind"] != "body":
                continue
            vs = slide_plan.get("visual_strategy") or {}
            cat = slide_plan.get("content_structure")
            if not cat or crit.min_score < 8 or not slide_bodies[n]:
                continue
            entry = GalleryEntry(
                deck_id=deck_id,
                slide_no=slide_plan["index"],
                category=cat,
                approach=vs.get("approach", "(unknown)"),
                rationale=vs.get("rationale", ""),
                layout_hint=vs.get("layout_hint", ""),
                key_elements=vs.get("key_elements", []),
                scores={
                    "strategy": crit.score_strategy,
                    "visual": crit.score_visual,
                    "content": crit.score_content,
                },
                quality_score=float(crit.min_score),
                code_snippet=slide_bodies[n],
                created_at=datetime.utcnow().isoformat(timespec="seconds"),
            )
            gallery.append(entry)
            appended += 1
        log.ok(f"gallery: appended {appended} entries")
```

- [ ] **Step 2: Write a tiny end-to-end live test**

```python
# tests/v2/test_pipeline_v2.py
import json
import pytest
from pathlib import Path

from src.pipeline_v2.builder import build_presentation_v2
from src.pipeline_v2.gallery import Gallery


pytestmark = pytest.mark.live


def test_pipeline_v2_end_to_end(tmp_path: Path):
    content = {
        "meta": {"title": "Tiny v2 smoke"},
        "sections": [
            {"heading": "A vs B", "body": "A is fast; B is cheap."},
            {"heading": "Action", "body": "Pilot A this quarter."},
        ],
    }
    out = tmp_path / "smoke_v2.pptx"
    workdir = tmp_path / "work"
    gallery = Gallery(tmp_path / "gallery.json")
    result = build_presentation_v2(
        content,
        output_path=out,
        workdir=workdir,
        gallery=gallery,
        enable_revision=False,
        enable_gallery=False,
        max_iter=1,
    )
    assert result.exists() and result.stat().st_size > 0
    assert (workdir / "outline.json").exists()
    assert (workdir / "plan.json").exists()
    plan = json.loads((workdir / "plan.json").read_text(encoding="utf-8"))
    assert plan["slides"][0]["kind"] == "title"
    assert plan["slides"][-1]["kind"] == "closing"
```

- [ ] **Step 3: Run end-to-end (no LLM live test in CI; manual)**

```
PYTHONIOENCODING=utf-8 pytest tests/v2/test_pipeline_v2.py -v -m live
```
Expected: PASS.

For a full live run including revision + gallery:

```
PYTHONIOENCODING=utf-8 python scripts/run_pipeline_v2.py data/sample_content.json
```
Expected: `output/sample_content_v2.pptx` + populated
`output/work_v2_sample_content/{outline,plan,deck_critique,critiques/*}.json`
+ possibly new entries in `references/index.json`.

- [ ] **Step 4: Commit**

```bash
git add src/pipeline_v2/builder.py tests/v2/test_pipeline_v2.py
git commit -m "feat(v2): Stages 6 (deck critique) + 7 (gallery persist)"
```

---

## Task 11: README and comparison docs

**Files:**
- Modify: `README.md` (append v2 section)
- Create: `docs/v2-comparison.md`

- [ ] **Step 1: Append v2 section to README**

Add the following at the end of `README.md`:

```markdown
## v2 — Freeform Codegen Pipeline

A second pipeline that lives alongside the v1 recipe pipeline. v2 generates
python-pptx code per slide via LLM, executes each in a subprocess, and
refines via vision-LLM critique. See
`docs/superpowers/specs/2026-05-06-v2-freeform-codegen-design.md`.

```bash
# Side-by-side run on the same input:
PYTHONIOENCODING=utf-8 python scripts/run_pipeline.py    data/sample_content.json
PYTHONIOENCODING=utf-8 python scripts/run_pipeline_v2.py data/sample_content.json

# Outputs:
# output/sample_content.pptx       (v1)
# output/sample_content_v2.pptx    (v2)

# v2 flags:
python scripts/run_pipeline_v2.py data/foo.json --no-revision   # baseline
python scripts/run_pipeline_v2.py data/foo.json --no-gallery    # no learning
python scripts/run_pipeline_v2.py data/foo.json --max-iter 1    # cheap revision
```
```

- [ ] **Step 2: Write a short comparison doc**

```markdown
<!-- docs/v2-comparison.md -->
# v1 vs v2 — what to look for

| What | v1 (recipe) | v2 (freeform codegen) |
|---|---|---|
| Layout source | `src/pipeline/recipes_*.py` registry | LLM coins per slide |
| Render | deterministic compile | subprocess-executed Python |
| Plan | one LLM pass | two LLM passes (1a + 1b) |
| Revision | recipe data patch | code patch from PNG critique |
| Learning | none | `references/index.json` gallery |
| Free-form shapes | no (primitives only) | yes (raw `add_connector` etc.) |

Run both on the same input and compare:

- `output/<stem>.pptx` vs `output/<stem>_v2.pptx`
- `output/work_<stem>/plan.json` vs `output/work_v2_<stem>/plan.json`
- v2 only: `output/work_v2_<stem>/slide_codes/` and `captures/` and `critiques/`

Re-run v2 several times on a small set of decks to seed the gallery, then
re-run a fresh deck — Phase 1b should now pull in similar high-scoring
approaches.
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/v2-comparison.md
git commit -m "docs(v2): README section + v1/v2 comparison guide"
```

---

## Self-review

**Spec coverage** — checked each numbered section of the spec against tasks:

- §3 differences table → described in Task 11 comparison doc ✅
- §4 Stage 0–7 pipeline → Tasks 4 (1a), 5 (1b), 7 (2/3), 8 (4), 9 (5), 10 (6/7) ✅
- §5.1 directory layout → matches Tasks 1–10 ✅
- §5.2 reused v1 assets → imported (not modified) in Tasks 4, 5, 8, 9, 10 ✅
- §5.3 LLM-facing code surface → Tasks 6 (preamble + assembler) and 7 (design guide) ✅
- §5.4 schemas → Task 1 ✅
- §5.5 prompts (6 files) → Tasks 4, 5, 7, 9 ✅
- §5.6 critique scoring rubric → encoded in Task 9 prompt ✅
- §5.7 revision policy (min<7, KEEP, one revise per iter, bail-out) → Task 9 implementation ✅
- §5.8 gallery (≥8 threshold, dedup, top-K, K=2, cap=20, oldest pruning) → Tasks 2 + 10 ✅
- §5.9 workdir layout → produced by Tasks 8, 9, 10 ✅
- §6 runner CLI + flags → Task 8 ✅
- §7 testing matrix → Tasks 1, 2, 4, 5, 6, 7, 10 cover all rows ✅
- §8 milestones → mapped to Tasks 1–10 (M1=Tasks 1–5, M2=6–7, M3=8, M4=9, M5+M6=10, M7=11) ✅
- §9 risks → preamble defenses (Task 6), Korean fonts (Task 6), `_patch_shapes` (Task 6), gallery cap (Task 2), vision skip (Task 9 try/except) ✅
- §10 open questions:
  - "vision call interface" → confirmed `chat_with_image` exists in `src/llm/client.py:56`; resolved.
  - "auto_fix and code_revision share prompt?" → kept split; documented.
  - "gallery stores body or full file?" → body only; encoded in Task 10 (`code_snippet=slide_bodies[n]`).

**Placeholder scan**: no TBD/TODO/"add appropriate handling" patterns. All steps with code show the code. Exact paths everywhere.

**Type consistency**:
- `SlideCritique.min_score` is a property (Task 1); used in Task 9 (`crit.min_score`) and Task 10 (`crit.min_score`) — consistent ✅
- `Gallery.append` / `Gallery.top_k` signatures match Task 5's call (`gallery.top_k(category=cat, k=K_PER_CATEGORY)`) and Task 10's call (`gallery.append(entry)`) ✅
- `execute_with_auto_fix(body, out, *, work_dir, design_guide_excerpt, max_retries)` — Task 7 defines, Tasks 8, 9 call with same kwargs ✅
- `execute_slide_body` signature: `(body, out_pptx, *, work_dir)` — defined Task 7, used Task 7 tests ✅
- `SlideExecutionError(message, *, traceback, code)` — defined Task 7, caught Task 7 (auto_fix) ✅
- `assemble_slide_module(body, out_pptx)` — defined Task 6, called Task 7 ✅
