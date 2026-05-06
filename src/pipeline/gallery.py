"""Gallery store — persistence layer for high-scoring slides.

After each codegen run, slides whose visual critique is clean enough are
distilled into a small record (intent_label, approach, layout_hint, score)
and stored at `<repo>/gallery/<intent>.json`. On the next run the
`visual_strategy` prompt receives top-K examples for the same intent so
the LLM can imitate proven layouts and avoid repeating its own mistakes.

Scoring is derived from the per-slide visual critique (7 axes).
`score = ok_count` (0..7). We persist only slides with `score >= MIN_SCORE`.

The store is intentionally tiny and JSON-based so users can inspect/edit
it manually. Repository commits are up to the user; we ship a
`.gitignore` line that excludes the dir by default.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from src.util import log

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = REPO_ROOT / "gallery"

MIN_SCORE = 6   # 6/7 axes ok → "high score"
MAX_PER_INTENT = 12   # cap on disk to keep prompts small


class Gallery:
    """File-backed gallery of high-scoring slide visual_strategy records."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def default(cls) -> "Gallery":
        return cls(DEFAULT_DIR)

    @property
    def path(self) -> Path:
        return self.root

    # -- read --------------------------------------------------------------

    def _file_for(self, intent_label: str) -> Path:
        # intent_label is one of a small enum so it's safe as a filename.
        return self.root / f"{intent_label}.json"

    def _load(self, intent_label: str) -> list[dict]:
        path = self._file_for(intent_label)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warn(f"gallery: {path.name} unreadable: {exc}")
            return []
        if not isinstance(data, list):
            return []
        return data

    def examples_for(self, intent_label: str, k: int = 3) -> list[dict]:
        """Return up to k highest-scoring distinct-approach examples."""
        records = self._load(intent_label)
        records.sort(key=lambda r: r.get("score", 0), reverse=True)
        seen_approaches: set[str] = set()
        out: list[dict] = []
        for rec in records:
            approach = rec.get("approach", "")
            if approach in seen_approaches:
                continue
            seen_approaches.add(approach)
            out.append(rec)
            if len(out) >= k:
                break
        return out

    # -- write -------------------------------------------------------------

    def _save(self, intent_label: str, records: list[dict]) -> None:
        # Keep MAX_PER_INTENT highest-scoring records.
        records.sort(key=lambda r: r.get("score", 0), reverse=True)
        records = records[:MAX_PER_INTENT]
        path = self._file_for(intent_label)
        path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add(
        self,
        intent_label: str,
        *,
        approach: str,
        layout_hint: str,
        score: int,
        head_message: str = "",
        rationale: str = "",
    ) -> None:
        records = self._load(intent_label)
        records.append({
            "approach": approach,
            "layout_hint": layout_hint,
            "rationale": rationale,
            "head_message": head_message,
            "score": int(score),
        })
        self._save(intent_label, records)

    # -- harvest -----------------------------------------------------------

    def harvest_from_run(
        self,
        plan: dict,
        critiques_path: Path,
        *,
        min_score: int = MIN_SCORE,
    ) -> int:
        """Walk a finished plan + the iter_1 critiques.json and persist
        any slide whose score >= min_score AND that has a visual_strategy.

        Returns count of slides actually saved.
        """
        critiques_path = Path(critiques_path)
        if not critiques_path.exists():
            return 0
        try:
            payload = json.loads(critiques_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0
        critiques = payload.get("critiques") or []
        score_by_slide_no = {
            int(c["slide_no"]): _score_axes(c.get("axes") or [])
            for c in critiques
            if "slide_no" in c
        }

        saved = 0
        for slide in plan.get("slides", []):
            score = score_by_slide_no.get(int(slide.get("slide_no", -1)))
            if score is None or score < min_score:
                continue
            strategy = slide.get("visual_strategy")
            if not isinstance(strategy, dict):
                continue
            self.add(
                slide.get("intent_label", "general_facts"),
                approach=strategy.get("approach", ""),
                layout_hint=strategy.get("layout_hint", ""),
                rationale=strategy.get("rationale", ""),
                head_message=slide.get("head_message", ""),
                score=score,
            )
            saved += 1
        return saved


def _score_axes(axes: Iterable[dict]) -> int:
    """Count of axes with verdict='ok'. Range 0..7."""
    return sum(1 for a in axes if (a or {}).get("verdict") == "ok")
