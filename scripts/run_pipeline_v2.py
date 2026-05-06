"""Run the v2 freeform-codegen pipeline.

Usage mirrors scripts/run_pipeline.py:
    python scripts/run_pipeline_v2.py
    python scripts/run_pipeline_v2.py data/ai_era.json
    python scripts/run_pipeline_v2.py data/ai_era.json output/ai_era_v2.pptx
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline_v2.builder import build_presentation_v2
from src.pipeline_v2.gallery import Gallery
from src.util import log


def _parse_args(root: Path) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="v2 freeform-codegen PPTX pipeline.")
    p.add_argument("content", nargs="?",
                   default=str(root / "data" / "sample_content.json"))
    p.add_argument("output", nargs="?", default=None)
    p.add_argument("--workdir", default=None)
    p.add_argument("--no-revision", action="store_true")
    p.add_argument("--no-gallery", action="store_true")
    p.add_argument("--max-iter", type=int, default=3)
    return p.parse_args()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    args = _parse_args(root)

    content_path = Path(args.content)
    if not content_path.is_absolute():
        content_path = (root / content_path).resolve()
    if not content_path.exists():
        print(f"ERROR: content not found: {content_path}", file=sys.stderr)
        sys.exit(1)

    stem = content_path.stem
    output_path = Path(args.output) if args.output else root / "output" / f"{stem}_v2.pptx"
    if not output_path.is_absolute():
        output_path = (root / output_path).resolve()
    workdir = Path(args.workdir) if args.workdir else output_path.parent / f"work_v2_{stem}"
    if not workdir.is_absolute():
        workdir = (root / workdir).resolve()

    log.info(f"v2 content: {content_path}")
    log.info(f"v2 output:  {output_path}")
    log.info(f"v2 workdir: {workdir}")

    content = json.loads(content_path.read_text(encoding="utf-8"))
    gallery = None if args.no_gallery else Gallery(root / "references" / "index.json")

    out = build_presentation_v2(
        content,
        output_path=output_path,
        workdir=workdir,
        gallery=gallery,
        enable_revision=not args.no_revision,
        enable_gallery=not args.no_gallery,
        max_iter=args.max_iter,
    )
    print(f"OK -> {out}")


if __name__ == "__main__":
    main()
