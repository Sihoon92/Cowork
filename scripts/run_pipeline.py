"""Run the full pipeline.

Usage:
    python scripts/run_pipeline.py                         # uses data/sample_content.json
    python scripts/run_pipeline.py data/ai_era.json        # default output: output/<stem>.pptx
    python scripts/run_pipeline.py data/ai_era.json output/my.pptx
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.builder import build_presentation
from src.util import log


def _parse_args(root: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a .pptx from a content.json via local LLM.")
    parser.add_argument(
        "content",
        nargs="?",
        default=str(root / "data" / "sample_content.json"),
        help="Path to content.json (default: data/sample_content.json)",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Path to output .pptx (default: output/<content-stem>.pptx)",
    )
    parser.add_argument(
        "--workdir",
        default=None,
        help="Workdir for plan/slides/critique artifacts (default: <output-parent>/work_<stem>)",
    )
    parser.add_argument(
        "--codegen",
        action="store_true",
        help="Use the LLM-codegen path (Phase 3 style) instead of fixed recipes. "
             "Adds a per-slide visual_strategy LLM call and runs generated "
             "python-pptx code in a subprocess. Falls back to recipes per-slide on failure.",
    )
    return parser.parse_args()


def main():
    root = Path(__file__).resolve().parents[1]
    args = _parse_args(root)

    content_path = Path(args.content)
    if not content_path.is_absolute():
        content_path = (root / content_path).resolve() if not content_path.exists() else content_path.resolve()
    if not content_path.exists():
        print(f"ERROR: content file not found: {content_path}", file=sys.stderr)
        sys.exit(1)

    stem = content_path.stem
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = (root / output_path).resolve()
    else:
        output_path = root / "output" / f"{stem}.pptx"

    if args.workdir:
        workdir = Path(args.workdir)
        if not workdir.is_absolute():
            workdir = (root / workdir).resolve()
    else:
        workdir = output_path.parent / f"work_{stem}"

    log.info(f"content: {content_path}")
    log.info(f"output:  {output_path}")
    log.info(f"workdir: {workdir}")

    content = json.loads(content_path.read_text(encoding="utf-8"))
    out = build_presentation(
        content,
        output_path=output_path,
        workdir=workdir,
        use_codegen=args.codegen,
    )
    print(f"OK -> {out}")

    log.stage("Done")
    log.ok(f"output: {out}")
    log.info(f"workdir: {workdir}")


if __name__ == "__main__":
    main()
