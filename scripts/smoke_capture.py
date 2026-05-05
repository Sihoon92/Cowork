"""Smoke test for slide screenshot capture.

Run on the target machine (especially the corporate PC running NASCA) to
verify that PowerPoint COM + PrintWindow API work end-to-end. If this
script produces N PNG files for an N-slide deck, the capture path is
viable for the visual revision loop.

Usage:
    PYTHONIOENCODING=utf-8 python scripts/smoke_capture.py [pptx_path]

If pptx_path is omitted, the script picks the most recent .pptx in
output/, falling back to data/sample_presentation.json -> generated deck.

Exit codes:
    0  success — N PNGs written under output/_smoke_capture/
    1  capture failed (NASCA block, missing PowerPoint, etc.)
    2  no input pptx available
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Make `src` importable when running this file directly.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pptx.capture import CaptureError, screenshot_deck


def _resolve_input(arg: str | None) -> Path | None:
    if arg:
        p = Path(arg).resolve()
        return p if p.exists() else None

    out_dir = ROOT / "output"
    if out_dir.exists():
        candidates = sorted(out_dir.glob("*.pptx"), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            return candidates[0]
    return None


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    pptx = _resolve_input(arg)
    if pptx is None:
        print("[smoke_capture] no input pptx — pass a path or generate one in output/", flush=True)
        return 2

    out_dir = ROOT / "output" / "_smoke_capture"
    print(f"[smoke_capture] input:  {pptx}", flush=True)
    print(f"[smoke_capture] output: {out_dir}", flush=True)

    t0 = time.time()
    try:
        paths = screenshot_deck(pptx, out_dir)
    except CaptureError as exc:
        print(f"[smoke_capture] FAILED: {exc}", flush=True)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"[smoke_capture] UNEXPECTED FAILURE: {type(exc).__name__}: {exc}", flush=True)
        return 1

    elapsed = time.time() - t0
    print(f"[smoke_capture] OK — {len(paths)} slides in {elapsed:.1f}s", flush=True)
    for p in paths:
        size_kb = p.stat().st_size // 1024
        print(f"  {p.name}  {size_kb} KB", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
