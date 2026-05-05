"""Parse guideline catalogs for prompt injection.

Recipe-era loader: only the design_guideline.md pattern index survives,
since composition/block catalogs were retired with the recipe migration.
The pattern index is currently unused by the planner but kept reachable for
future tooling that may want to surface design vocabulary to the LLM.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

GUIDELINES_DIR = Path(__file__).resolve().parents[2] / "guidelines"
GUIDELINE_PATH = GUIDELINES_DIR / "design_guideline.md"

# Pattern headings are level-3 (### Name). Section ends at next ### or ## or EOF.
_HEADING_RE = re.compile(r"^### (.+?)\s*$", re.MULTILINE)


@lru_cache(maxsize=1)
def _read_doc() -> str:
    if not GUIDELINE_PATH.exists():
        return ""
    return GUIDELINE_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_pattern_index() -> dict[str, str]:
    """Return {pattern_name: full_section_text} for every level-3 heading."""
    doc = _read_doc()
    if not doc:
        return {}
    matches = list(_HEADING_RE.finditer(doc))
    index: dict[str, str] = {}
    for i, m in enumerate(matches):
        raw = m.group(1).strip()
        # Strip parenthetical subtitles like "(Big Number)" → "Stat 강조"
        name = re.sub(r"\s*\(.+\)\s*$", "", raw).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(doc)
        body = doc[start:end]
        sub_h2 = re.search(r"^## ", body, re.MULTILINE)
        if sub_h2:
            body = body[: sub_h2.start()]
        index[name] = body.strip()
    return index


def get_pattern_section(name: str) -> str:
    """Look up a design guideline pattern by name."""
    idx = load_pattern_index()
    if name not in idx:
        raise KeyError(f"unknown pattern: {name!r}")
    return idx[name]
