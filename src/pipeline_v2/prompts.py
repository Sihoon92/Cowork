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


def load_prompt(name: str, /, **values: object) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    template = path.read_text(encoding="utf-8")
    return template.format_map(_StrictMap(values))
