"""Run the full pipeline against data/sample_content.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.builder import build_presentation


def main():
    root = Path(__file__).resolve().parents[1]
    content_path = root / "data" / "sample_content.json"
    output_path = root / "output" / "demo.pptx"
    workdir = root / "output" / "work"

    content = json.loads(content_path.read_text(encoding="utf-8"))
    out = build_presentation(content, output_path=output_path, workdir=workdir)
    print(f"OK -> {out}")


if __name__ == "__main__":
    main()
