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
