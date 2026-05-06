"""Survey a finished pipeline workdir and report the codegen path's behavior.

Walks `<workdir>/`:
  - plan.json            → which slides have a visual_strategy (approach diversity)
  - codegen/slide_NN_*.py → which slides actually went through codegen, retry count
  - iter_1/critiques.json → per-slide visual scores (ok-axis count out of 7)
  - gallery/<intent>.json → what was harvested into the persistent store

Prints a single table the user can scan quickly to see:
  - was codegen tried for this slide?
  - did it succeed on first try, retry, or fall back to recipe?
  - what score did the visual critic give it?
  - did this slide make the gallery cut?

Usage:
    PYTHONIOENCODING=utf-8 python scripts/inspect_codegen_run.py <workdir>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.gallery import DEFAULT_DIR as GALLERY_DEFAULT_DIR


_ARTIFACT_RE = re.compile(r"^slide_(\d+)_v(\d+)(?:_(\w+))?\.py$")


def _scan_codegen_dir(code_dir: Path) -> dict[int, list[str]]:
    """Return {slide_no: [tag1, tag2, ...]} where tag is e.g. 'v1', 'v2_retry'."""
    out: dict[int, list[str]] = {}
    if not code_dir.exists():
        return out
    for f in sorted(code_dir.glob("slide_*.py")):
        m = _ARTIFACT_RE.match(f.name)
        if not m:
            continue
        slide_no = int(m.group(1))
        tag = f"v{m.group(2)}" + (f"_{m.group(3)}" if m.group(3) else "")
        out.setdefault(slide_no, []).append(tag)
    return out


def _score_axes(axes: list[dict]) -> int:
    return sum(1 for a in axes if (a or {}).get("verdict") == "ok")


def _load_critique_scores(critiques_path: Path) -> dict[int, int]:
    if not critiques_path.exists():
        return {}
    try:
        payload = json.loads(critiques_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        int(c["slide_no"]): _score_axes(c.get("axes") or [])
        for c in (payload.get("critiques") or [])
        if "slide_no" in c
    }


def _load_gallery(gallery_dir: Path) -> dict[str, list[str]]:
    """Return {intent_label: [approach1, approach2, ...]} for harvested slides."""
    out: dict[str, list[str]] = {}
    if not gallery_dir.exists():
        return out
    for f in sorted(gallery_dir.glob("*.json")):
        try:
            records = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(records, list):
            out[f.stem] = [r.get("approach", "?") for r in records]
    return out


def _approach_for(slide: dict) -> str:
    vs = slide.get("visual_strategy") or {}
    if isinstance(vs, dict):
        return vs.get("approach") or "(none)"
    return "(none)"


def _verdict_for(slide_no: int, attempts: list[str]) -> str:
    """Codegen behavior in one short label: skipped / clean / retried / fallback."""
    if not attempts:
        return "skipped"
    has_retry = any("retry" in t for t in attempts)
    if has_retry:
        return f"retried×{len(attempts) - 1}"
    return "clean"


def main():
    ap = argparse.ArgumentParser(
        description="Inspect a finished pipeline workdir for codegen-path behavior."
    )
    ap.add_argument("workdir", help="Path to a pipeline workdir.")
    ap.add_argument(
        "--gallery", default=None,
        help="Override gallery dir (default: <repo>/gallery).",
    )
    args = ap.parse_args()

    workdir = Path(args.workdir).resolve()
    if not workdir.exists():
        print(f"ERROR: workdir not found: {workdir}", file=sys.stderr)
        sys.exit(2)

    plan_path = workdir / "plan.json"
    if not plan_path.exists():
        print(f"ERROR: plan.json not in {workdir}", file=sys.stderr)
        sys.exit(2)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    code_attempts = _scan_codegen_dir(workdir / "codegen")
    scores = _load_critique_scores(workdir / "iter_1" / "critiques.json")
    gallery_dir = Path(args.gallery) if args.gallery else GALLERY_DEFAULT_DIR
    gallery = _load_gallery(gallery_dir)

    # --- Report ---
    slides = plan.get("slides", [])
    print(f"Workdir: {workdir}")
    print(f"Gallery: {gallery_dir}")
    print(f"Total slides: {len(slides)}\n")

    header = f"{'#':>3}  {'intent':<24}  {'approach':<32}  {'codegen':<13}  {'score':>5}  gallery"
    print(header)
    print("-" * len(header))

    approach_counter: dict[str, int] = {}
    for s in slides:
        slide_no = int(s.get("slide_no", -1))
        intent = s.get("intent_label", "?")
        approach = _approach_for(s)
        approach_counter[approach] = approach_counter.get(approach, 0) + 1

        attempts = code_attempts.get(slide_no, [])
        verdict = _verdict_for(slide_no, attempts)
        score = scores.get(slide_no)
        score_s = f"{score}/7" if score is not None else "—"

        in_gallery = "✓" if approach in gallery.get(intent, []) else "—"

        print(f"{slide_no:>3}  {intent:<24}  {approach:<32}  {verdict:<13}  {score_s:>5}  {in_gallery}")

    # --- Summary ---
    print()
    n_codegen = sum(1 for s in slides if code_attempts.get(int(s.get("slide_no", -1))))
    n_clean = sum(
        1 for s in slides
        if not any("retry" in t for t in code_attempts.get(int(s.get("slide_no", -1)), []))
        and code_attempts.get(int(s.get("slide_no", -1)))
    )
    n_retried = n_codegen - n_clean
    n_fallback = len(slides) - n_codegen
    print(f"codegen attempted:  {n_codegen}/{len(slides)}")
    print(f"  - clean (no retry): {n_clean}")
    print(f"  - needed retry:     {n_retried}")
    print(f"recipe path only:   {n_fallback}/{len(slides)}")

    duplicates = {a: c for a, c in approach_counter.items() if c > 1 and a != "(none)"}
    if duplicates:
        print("\nWARN  approach reuse detected:")
        for approach, count in sorted(duplicates.items(), key=lambda x: -x[1]):
            print(f"  {approach!r}  used {count}×")


if __name__ == "__main__":
    main()
