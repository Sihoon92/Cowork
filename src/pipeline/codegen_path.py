"""Optional LLM-codegen rendering path (legacy Phase 3 style).

The recipe path (`render_slide` → primitives) is the safe default.
This module is opt-in via `--codegen` CLI flag or `COWORK_CODEGEN=1`.
For each body slide it asks the LLM to write python-pptx code grounded in
`visual_strategy.layout_hint` + `guidelines/design_guideline.md`, then
executes it in a subprocess via `code_runner`.

Failures are isolated per slide — on any error we fall back to the
deterministic renderer for that slide so the deck always builds.
"""
from __future__ import annotations

from pathlib import Path

from src.llm.client import DEFAULT_MODEL
from src.pipeline.code_generator import generate_slide_code
from src.pptx.code_runner import (
    CodeExecutionError, render_slide_with_retry,
)
from src.util import log

GUIDELINE_PATH = Path(__file__).resolve().parents[2] / "guidelines" / "design_guideline.md"

_FRAMING_INTENTS = frozenset({
    "deck_opening", "closing_thesis", "section_transition",
})


def _intent_fallback_hint(intent_label: str) -> str:
    """Generic layout hint when the planner did not produce a visual_strategy."""
    table = {
        "single_metric_emphasis":
            "헤드 상단 1줄. 본문 가운데 hero metric (값 72pt bold ACCENT, "
            "라벨 14pt body_text 아래). 우측 1/3에 narratives 2~3줄 16pt.",
        "multi_metric_dashboard":
            "본문 2x2 그리드. 각 셀에 metric (값 36pt bold ACCENT, 라벨 12pt). "
            "셀 간 0.3 gap.",
        "numeric_comparison":
            "본문 좌측 1/2 가로 막대 비교. 막대 길이 비례, 1위 ACCENT 색·1.2배 굵기. "
            "각 막대 우측에 값 라벨 14pt bold.",
        "two_dim_compare":
            "본문 2x2 매트릭스. 1행 col_headers ACCENT 배경 흰 글씨, "
            "1열 row_labels bold. 각 셀 bullets 12pt 좌정렬.",
        "before_after":
            "본문 좌우 50% 분할. 좌 As-Is(neutral 배경, 어두운 글씨), "
            "우 To-Be(ACCENT 배경, 흰 글씨). 중앙에 → 화살표 24pt.",
        "sequence_or_timeline":
            "본문 가로 chevron 3~5단. 번호 원형 ACCENT 배경. 아래 title 14pt bold + "
            "note 11pt body_text.",
        "quotation":
            "본문 가운데 큰 인용문 28pt italic. 하단에 — attribution 14pt body_text.",
        "parallel_compare":
            "본문 좌우 50% 분할. 각 헤더 pill (ACCENT) + bullets 14pt.",
        "general_facts":
            "본문 세로 bullet 리스트 4~6줄, 각 16pt body_text + bullet ACCENT.",
    }
    return table.get(
        intent_label,
        "본문 영역에 head_message 강조 + narratives 14pt bullet 리스트.",
    )


def _build_slide_data(deck_meta: dict, flat_slide: dict) -> dict:
    """Compose the runtime data dict the generated script will receive on stdin."""
    full = flat_slide.get("_full") or {}
    return {
        "slide_no": flat_slide["slide_no"],
        "head_message": flat_slide["head_message"],
        "section_id": flat_slide.get("section_id"),
        "intent_label": flat_slide.get("intent_label"),
        "content": full.get("content") or {},
        "deck_meta": deck_meta,
        "visual_strategy": flat_slide.get("visual_strategy"),
    }


def _save_code_artifact(code: str, code_dir: Path | None, slide_no: int,
                         tag: str) -> None:
    """Persist generated code to disk for post-mortem audit.

    `tag` distinguishes initial vs retry attempts (e.g. "v1", "v2_retry").
    Failures here are non-fatal — audit shouldn't break a working build.
    """
    if code_dir is None:
        return
    try:
        code_dir.mkdir(parents=True, exist_ok=True)
        (code_dir / f"slide_{slide_no:02d}_{tag}.py").write_text(
            code, encoding="utf-8",
        )
    except OSError as exc:
        log.warn(f"could not save codegen artifact slide {slide_no}: {exc}")


def render_via_codegen(
    deck_meta: dict,
    flat_slide: dict,
    out_path: Path,
    *,
    model: str = DEFAULT_MODEL,
    max_retries: int = 2,
    code_dir: Path | None = None,
) -> Path:
    """Generate + execute python-pptx code for one slide. Returns out_path on success.

    Args:
        code_dir: optional directory to persist generated code to. Each
            attempt writes `slide_<NN>_<tag>.py` so users can inspect
            what the LLM produced after the run.

    Raises CodeExecutionError if the script can't be made to run after retries.
    """
    intent = flat_slide.get("intent_label") or "general_facts"
    if intent in _FRAMING_INTENTS:
        raise CodeExecutionError(
            f"codegen path skipped for framing intent {intent!r}",
        )

    strategy = flat_slide.get("visual_strategy") or {}
    layout_hint = (
        strategy.get("layout_hint") if isinstance(strategy, dict) else None
    ) or _intent_fallback_hint(intent)

    pattern_guideline = GUIDELINE_PATH.read_text(encoding="utf-8")

    slide_no = flat_slide["slide_no"]
    slide_data = _build_slide_data(deck_meta, flat_slide)
    log.step(f"LLM call: codegen for slide {slide_no}")
    code = generate_slide_code(
        layout_hint=layout_hint,
        pattern_guideline=pattern_guideline,
        slide_data=slide_data,
        model=model,
    )
    _save_code_artifact(code, code_dir, slide_no, "v1")

    retry_counter = {"n": 1}

    def _fix_callback(prev_code: str, error: str, _data: dict) -> str:
        log.warn(
            f"slide {slide_no} codegen retry: {error[:160]}"
        )
        retry_hint = (
            f"{layout_hint}\n\nPREVIOUS ATTEMPT FAILED with this error:\n{error}\n"
            f"Fix the listed error and re-emit the COMPLETE script."
        )
        new_code = generate_slide_code(
            layout_hint=retry_hint,
            pattern_guideline=pattern_guideline,
            slide_data=slide_data,
            model=model,
        )
        retry_counter["n"] += 1
        _save_code_artifact(
            new_code, code_dir, slide_no, f"v{retry_counter['n']}_retry",
        )
        return new_code

    return render_slide_with_retry(
        code, slide_data, out_path,
        fix_callback=_fix_callback,
        max_retries=max_retries,
    )
