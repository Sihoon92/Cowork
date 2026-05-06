"""Print the codegen prompt that would be sent to the LLM for one slide.

Lets you eyeball / iterate on prompt design without burning LLM tokens.

Usage:
    PYTHONIOENCODING=utf-8 python scripts/dump_codegen_prompt.py PLAN_JSON SLIDE_NO
    PYTHONIOENCODING=utf-8 python scripts/dump_codegen_prompt.py PLAN_JSON SLIDE_NO --no-strategy
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.code_generator import build_codegen_prompt
from src.pipeline.codegen_path import (
    GUIDELINE_PATH, _build_slide_data, _intent_fallback_hint,
)


def main():
    ap = argparse.ArgumentParser(
        description="Dump the codegen prompt for one slide of a plan.json."
    )
    ap.add_argument("plan_json", help="Path to plan.json (workdir/plan.json).")
    ap.add_argument("slide_no", type=int, help="1-based slide_no to inspect.")
    ap.add_argument(
        "--no-strategy", action="store_true",
        help="Force the intent-derived fallback hint, ignoring any "
             "visual_strategy already on the slide.",
    )
    args = ap.parse_args()

    plan = json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
    deck_meta = plan["deck_meta"]
    slide = next(
        (s for s in plan["slides"] if int(s["slide_no"]) == args.slide_no),
        None,
    )
    if slide is None:
        print(f"ERROR: slide_no={args.slide_no} not in plan", file=sys.stderr)
        sys.exit(2)

    intent = slide.get("intent_label") or "general_facts"
    strategy = None if args.no_strategy else slide.get("visual_strategy")
    layout_hint = (
        (strategy or {}).get("layout_hint")
        if isinstance(strategy, dict) else None
    ) or _intent_fallback_hint(intent)

    pattern_guideline = GUIDELINE_PATH.read_text(encoding="utf-8")
    slide_data = _build_slide_data(deck_meta, slide)
    prompt = build_codegen_prompt(
        layout_hint=layout_hint,
        pattern_guideline=pattern_guideline,
        slide_data=slide_data,
    )

    print(prompt)


if __name__ == "__main__":
    main()
