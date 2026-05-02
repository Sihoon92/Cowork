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


@lru_cache(maxsize=1)
def _build_alias_index() -> dict[str, str]:
    """Return a lowercase-normalised alias map: normalised_alias -> canonical_name.

    For every canonical name in the pattern index we register:
    - the canonical name itself (normalised)
    - the raw heading from the guideline (normalised), which may include a
      parenthetical subtitle, e.g. "stat 강조 (big number)" -> "Stat 강조"
    """
    doc = _read_doc()
    matches = list(_HEADING_RE.finditer(doc))
    alias_map: dict[str, str] = {}

    for m in matches:
        raw = m.group(1).strip()
        canonical = re.sub(r"\s*\(.+\)\s*$", "", raw).strip()

        # Register the canonical name as an alias of itself
        alias_map[canonical.lower()] = canonical
        # Register the raw heading (with parenthetical) as an alias
        alias_map[raw.lower()] = canonical

    return alias_map


def _strip_parens(text: str) -> str:
    """Remove a trailing parenthetical group, e.g. 'Cover (표지)' -> 'Cover'."""
    return re.sub(r"\s*\(.+\)\s*$", "", text).strip()


def resolve_pattern(name: str) -> str | None:
    """Case-insensitive, whitespace-tolerant, parenthetical-tolerant lookup.

    Returns the canonical pattern name if found, else None.
    """
    alias_map = _build_alias_index()
    # 1. Exact (normalised) match against all aliases
    normalised = name.strip().lower()
    if normalised in alias_map:
        return alias_map[normalised]

    # 2. Strip parenthetical from the input and try again
    stripped = _strip_parens(name.strip()).lower()
    if stripped in alias_map:
        return alias_map[stripped]

    return None


def get_pattern_section(name: str) -> str:
    canonical = resolve_pattern(name)
    if canonical is None:
        raise KeyError(f"unknown pattern: {name!r}")
    idx = load_pattern_index()
    return idx[canonical]


def get_pattern_summary_cards() -> list[str]:
    """Return one-liner cards: 'Name — when one-liner' for every pattern."""
    idx = load_pattern_index()
    cards: list[str] = []
    for name, body in idx.items():
        m = re.search(r"-\s*\*\*언제\*\*:\s*(.+)", body)
        when = m.group(1).strip() if m else ""
        cards.append(f"{name} — {when}")
    return cards
