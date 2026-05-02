"""Parse guidelines/design_guideline.md into pattern sections for prompts."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

GUIDELINE_PATH = Path(__file__).resolve().parents[2] / "guidelines" / "design_guideline.md"

# Pattern headings are level-3 (### Name). Section ends at next ### or ## or EOF.
_HEADING_RE = re.compile(r"^### (.+?)\s*$", re.MULTILINE)


@lru_cache(maxsize=1)
def _read_doc() -> str:
    return GUIDELINE_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_pattern_index() -> dict[str, str]:
    """Return {pattern_name: full_section_text} for every level-3 heading."""
    doc = _read_doc()
    matches = list(_HEADING_RE.finditer(doc))
    index: dict[str, str] = {}
    for i, m in enumerate(matches):
        raw = m.group(1).strip()
        # Strip parenthetical subtitles like "(Big Number)" or "(표지)" so the
        # primary name is used as the key: "Stat 강조 (Big Number)" → "Stat 강조"
        name = re.sub(r"\s*\(.+\)\s*$", "", raw).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(doc)
        # Stop early if a level-2 heading appears between
        body = doc[start:end]
        sub_h2 = re.search(r"^## ", body, re.MULTILINE)
        if sub_h2:
            body = body[: sub_h2.start()]
        index[name] = body.strip()
    return index


def get_pattern_section(name: str) -> str:
    idx = load_pattern_index()
    if name not in idx:
        raise KeyError(f"unknown pattern: {name!r}")
    return idx[name]


def get_pattern_summary_cards() -> list[str]:
    """Return one-liner cards: 'Name — when one-liner' for every pattern."""
    idx = load_pattern_index()
    cards: list[str] = []
    for name, body in idx.items():
        m = re.search(r"-\s*\*\*언제\*\*:\s*(.+)", body)
        when = m.group(1).strip() if m else ""
        cards.append(f"{name} — {when}")
    return cards
