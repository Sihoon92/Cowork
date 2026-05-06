"""End-to-end builder test for the codegen-path branching.

Goal: prove that when `use_codegen=True` is passed to `build_presentation`,
the per-slide branch picks codegen first, and falls back to the recipe
path on codegen failure — without depending on a live LLM.

We mock everything that would otherwise hit the network or shell out:
    - `make_plan`            — returns a hand-rolled plan dict
    - `render_via_codegen`   — captures calls and selectively errors
    - `merge_slides`         — returns a stub path
    - `critique_deck_*`      — returns empty-issue stubs
    - `visual_revision_loop` — passthrough
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from src.pipeline import builder
from src.pptx.code_runner import CodeExecutionError


# ----------------------------------------------------------------------------
# fixtures
# ----------------------------------------------------------------------------

def _stub_plan() -> dict:
    deck_meta = {
        "title": "t",
        "theme": {
            "background": "#FFFFFF", "head_text": "#000",
            "head_rule": "#000", "body_text": "#000",
            "bullet": "#000", "accent": "#000",
            "primary": "#000", "neutral": "#FFF",
            "text_dark": "#000", "text_light": "#FFF",
        },
        "fonts": {"header": "F", "body": "F"},
        "slide_size": {"width_in": 13.333, "height_in": 7.5},
        "section_titles": {},
    }
    base_content = {
        "knowledge": {"metrics": [], "narratives": []},
        "key_takeaway": "k",
    }
    return {
        "deck_meta": deck_meta,
        "slides": [
            # body slide w/ visual_strategy → codegen-eligible
            {
                "slide_no": 1, "head_message": "h1",
                "intent_label": "general_facts",
                "section_id": None,
                "recipe": "single_bullets",
                "data": {"items": ["a"]},
                "visual_strategy": {
                    "approach": "v1", "layout_hint": "L1", "key_elements": [],
                },
                "_full": {"content": {"slide_no": 1, **base_content,
                                       "intent_label": "general_facts",
                                       "head_message": "h1"}},
            },
            # body slide that codegen will FAIL on → fallback to recipe
            {
                "slide_no": 2, "head_message": "h2",
                "intent_label": "general_facts",
                "section_id": None,
                "recipe": "single_bullets",
                "data": {"items": ["b"]},
                "visual_strategy": {
                    "approach": "v2", "layout_hint": "L2", "key_elements": [],
                },
                "_full": {"content": {"slide_no": 2, **base_content,
                                       "intent_label": "general_facts",
                                       "head_message": "h2"}},
            },
            # framing slide → never goes through codegen, no visual_strategy
            {
                "slide_no": 3, "head_message": "h3",
                "intent_label": "deck_opening",
                "section_id": None,
                "recipe": "cover",
                "data": {"title": "h3"},
                "visual_strategy": None,
                "_full": {"content": {"slide_no": 3, **base_content,
                                       "intent_label": "deck_opening",
                                       "head_message": "h3"}},
            },
        ],
    }


# ----------------------------------------------------------------------------
# tests
# ----------------------------------------------------------------------------

def test_use_codegen_branch_calls_codegen_then_falls_back_per_slide(
    tmp_path: Path, monkeypatch
):
    """Slide 1: codegen succeeds. Slide 2: codegen fails → recipe fallback.
    Slide 3: framing → recipe path directly (no codegen attempt)."""
    workdir = tmp_path / "wd"
    output = tmp_path / "out.pptx"

    # 1. Mock the planner: make_plan -> stub_plan; ignore with_visual_strategy.
    monkeypatch.setattr(
        builder, "make_plan",
        lambda content, **kw: _stub_plan(),
    )

    # 2. Mock the codegen entry point. Slide 1 succeeds (writes a tiny .pptx);
    #    slide 2 raises CodeExecutionError so the fallback kicks in.
    codegen_calls: list[int] = []

    def fake_codegen(deck_meta, flat_slide, out_path):
        slide_no = flat_slide["slide_no"]
        codegen_calls.append(slide_no)
        if slide_no == 1:
            # succeed — write a real one-slide pptx so size_kb logging works
            prs = Presentation()
            prs.slide_width = Inches(13.333)
            prs.slide_height = Inches(7.5)
            prs.slides.add_slide(prs.slide_layouts[6])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            prs.save(str(out_path))
            return out_path
        raise CodeExecutionError(f"forced failure on slide {slide_no}")

    # The codegen import inside build_presentation is lazy. We monkeypatch
    # the real module so the lazy import returns our stub.
    from src.pipeline import codegen_path
    monkeypatch.setattr(
        codegen_path, "render_via_codegen", fake_codegen,
    )

    # 3. Stub the merger so we don't need real powerpoint composition.
    def fake_merge(slide_paths, output_path):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"fake-pptx-bytes")
        return Path(output_path)

    monkeypatch.setattr(builder, "merge_slides", fake_merge)

    # 4. Stub the revision loop and deck critiques (they would need live
    #    LibreOffice / vision LLM to do real work).
    monkeypatch.setattr(
        builder, "visual_revision_loop",
        lambda plan, deck, paths, wd, **kw: (plan, deck, paths),
    )
    monkeypatch.setattr(
        builder, "critique_deck_storyline",
        lambda plan: {"verdict": "PASS", "issues": []},
    )
    monkeypatch.setattr(
        builder, "critique_deck_visual",
        lambda paths, out_dir: {"verdict": "PASS", "issues": []},
    )

    # ---- act ----
    out = builder.build_presentation(
        {"meta": {"title": "t"}, "sections": []},
        output_path=output, workdir=workdir,
        use_codegen=True,
    )

    # ---- assert ----
    assert out == output

    # Codegen was attempted for slides 1 and 2, NOT for the framing slide 3
    # (which has visual_strategy=None — guard in builder).
    assert codegen_calls == [1, 2], f"unexpected codegen call sequence: {codegen_calls}"

    # Slide 1 was written by the codegen stub — should be a real (tiny) pptx
    s1 = workdir / "slides" / "slide_01.pptx"
    assert s1.exists()
    Presentation(s1)  # parseable

    # Slide 2 was written by the recipe fallback (deterministic renderer).
    s2 = workdir / "slides" / "slide_02.pptx"
    assert s2.exists()
    Presentation(s2)

    # Slide 3 (framing) was rendered by the recipe path directly.
    s3 = workdir / "slides" / "slide_03.pptx"
    assert s3.exists()


def test_use_codegen_false_does_not_import_codegen_path(
    tmp_path: Path, monkeypatch
):
    """The recipe-only path must not pay the cost of importing codegen modules.

    We assert this indirectly: render_via_codegen never gets called even
    if available, because the `use_codegen` flag short-circuits the branch.
    """
    workdir = tmp_path / "wd"
    output = tmp_path / "out.pptx"

    monkeypatch.setattr(
        builder, "make_plan",
        lambda content, **kw: _stub_plan(),
    )
    monkeypatch.setattr(builder, "merge_slides",
        lambda paths, out_path: (Path(out_path).write_bytes(b"x"), Path(out_path))[1])
    monkeypatch.setattr(
        builder, "visual_revision_loop",
        lambda plan, deck, paths, wd, **kw: (plan, deck, paths),
    )
    monkeypatch.setattr(
        builder, "critique_deck_storyline",
        lambda plan: {"verdict": "PASS", "issues": []},
    )
    monkeypatch.setattr(
        builder, "critique_deck_visual",
        lambda paths, out_dir: {"verdict": "PASS", "issues": []},
    )

    # If codegen was reached, importing this stub would record it. Set it
    # AFTER the build to a sentinel so we can detect whether it was touched.
    from src.pipeline import codegen_path

    def explode(*a, **kw):  # pragma: no cover — should never be reached
        raise AssertionError("render_via_codegen called when use_codegen=False")

    monkeypatch.setattr(codegen_path, "render_via_codegen", explode)

    builder.build_presentation(
        {"meta": {"title": "t"}, "sections": []},
        output_path=output, workdir=workdir,
        use_codegen=False,
    )

    # If we reach here without the explode raising, the recipe-only path
    # never reached into codegen.
