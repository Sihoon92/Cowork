# Gemma → PPTX Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an MVP that converts a `content.json` input into a finished `.pptx` file using a local Gemma model (gemma4:e4b via Ollama), python-pptx primitives, and a design guideline.

**Architecture:** Two-tier JSON (content → plan), Brain–Executor split (LLM plans/codes, subprocess executes), Primitives + Guideline (no fixed layout enum). Slide-by-slide independent generation with subprocess error recovery, then merge.

**Tech Stack:** Python 3.12 · python-pptx 1.0.2 · Ollama gemma4:e4b · pytest 9 · requests · Windows-friendly (PYTHONIOENCODING=utf-8 enforced).

**Spec:** [`docs/superpowers/specs/2026-05-02-gemma-pptx-pipeline-design.md`](../specs/2026-05-02-gemma-pptx-pipeline-design.md)

---

## Conventions

- All paths absolute from `C:\Users\sihoo\PythonProject\CoWork` (referred to as `<root>`).
- Run pytest with `PYTHONIOENCODING=utf-8 pytest <args>` on Windows.
- Slide size: 13.333 × 7.5 inches (16:9).
- Color values are uppercase 6-digit hex with leading `#`.
- All public functions get type hints. Docstrings optional (only for non-obvious WHY).
- TDD: write failing test → minimal impl → passing test → commit.

---

## Task 1: Project setup — pytest config, __init__ files, .gitignore

**Files:**
- Create: `pytest.ini`
- Create: `src/__init__.py`
- Create: `src/llm/__init__.py`
- Create: `src/pptx/__init__.py`
- Create: `src/pipeline/__init__.py`
- Create: `tests/__init__.py`
- Create: `.gitignore`

- [ ] **Step 1: Create pytest config**

Create `<root>/pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -ra --strict-markers
markers =
    live: tests that hit a real Ollama server (slow, requires `ollama serve`)
```

- [ ] **Step 2: Create empty __init__.py files**

```bash
touch src/__init__.py src/llm/__init__.py src/pptx/__init__.py tests/__init__.py
mkdir -p src/pipeline
touch src/pipeline/__init__.py
```

- [ ] **Step 3: Create .gitignore**

Create `<root>/.gitignore`:

```
__pycache__/
*.pyc
*.pyo
.pytest_cache/
output/
.superpowers/
*.pptx
!data/sample_*.pptx
.venv/
.env
```

- [ ] **Step 4: Verify pytest discovers existing tests**

Run: `PYTHONIOENCODING=utf-8 pytest --collect-only -q`
Expected: collects `tests/test_ollama.py` and `tests/test_pptx.py` without errors.

- [ ] **Step 5: Commit**

```bash
git init
git add pytest.ini .gitignore src/__init__.py src/llm/__init__.py src/pptx/__init__.py src/pipeline/__init__.py tests/__init__.py
git commit -m "chore: add pytest config and package init files"
```

---

## Task 2: Primitives foundations — color helper + set_bg + add_text

**Files:**
- Create: `src/pptx/primitives.py`
- Create: `tests/pptx/__init__.py`
- Create: `tests/pptx/test_primitives.py`

- [ ] **Step 1: Write failing test for `_hex_to_rgb`, `set_bg`, `add_text`**

Create `tests/pptx/__init__.py` (empty), then create `tests/pptx/test_primitives.py`:

```python
from pptx import Presentation
from pptx.util import Inches
from pptx.enum.shapes import MSO_SHAPE_TYPE

from src.pptx.primitives import _hex_to_rgb, set_bg, add_text


def _new_slide():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    return prs, slide


def test_hex_to_rgb_uppercase():
    rgb = _hex_to_rgb("#FF8800")
    assert (rgb[0], rgb[1], rgb[2]) == (255, 136, 0)


def test_hex_to_rgb_no_hash():
    rgb = _hex_to_rgb("00FF00")
    assert (rgb[0], rgb[1], rgb[2]) == (0, 255, 0)


def test_set_bg_paints_slide():
    prs, slide = _new_slide()
    set_bg(slide, "#1C2833")
    fill = slide.background.fill
    assert fill.type is not None
    assert (fill.fore_color.rgb[0], fill.fore_color.rgb[1], fill.fore_color.rgb[2]) == (0x1C, 0x28, 0x33)


def test_add_text_creates_textbox_with_content():
    prs, slide = _new_slide()
    add_text(slide, x=1.0, y=2.0, w=5.0, h=1.0, text="Hello", font_size=20, bold=True, color="#FF0000")
    textboxes = [s for s in slide.shapes if s.has_text_frame]
    assert len(textboxes) == 1
    tf = textboxes[0].text_frame
    run = tf.paragraphs[0].runs[0]
    assert run.text == "Hello"
    assert run.font.bold is True
    assert run.font.size.pt == 20
    assert (run.font.color.rgb[0], run.font.color.rgb[1], run.font.color.rgb[2]) == (255, 0, 0)


def test_add_text_alignment_center():
    prs, slide = _new_slide()
    add_text(slide, x=0, y=0, w=10, h=1, text="X", align="center")
    tb = [s for s in slide.shapes if s.has_text_frame][0]
    from pptx.enum.text import PP_ALIGN
    assert tb.text_frame.paragraphs[0].alignment == PP_ALIGN.CENTER
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pptx/test_primitives.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.pptx.primitives'` or similar.

- [ ] **Step 3: Implement primitives.py with three functions**

Create `<root>/src/pptx/primitives.py`:

```python
"""Layer 1 — Dumb executor primitives over python-pptx."""
from __future__ import annotations

from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

_ALIGN = {
    "left": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
}


def _hex_to_rgb(hex_color: str) -> RGBColor:
    h = hex_color.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def set_bg(slide, color: str) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = _hex_to_rgb(color)


def add_text(
    slide,
    x: float, y: float, w: float, h: float,
    text: str,
    *,
    font_size: float = 14,
    bold: bool = False,
    italic: bool = False,
    color: str = "#000000",
    align: str = "left",
    font: str = "Pretendard",
    line_spacing: float = 1.2,
) -> None:
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    para = tf.paragraphs[0]
    para.alignment = _ALIGN.get(align, PP_ALIGN.LEFT)
    para.line_spacing = line_spacing
    run = para.add_run()
    run.text = text
    run.font.name = font
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = _hex_to_rgb(color)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pptx/test_primitives.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pptx/primitives.py tests/pptx/__init__.py tests/pptx/test_primitives.py
git commit -m "feat(primitives): add hex-to-rgb, set_bg, add_text"
```

---

## Task 3: Primitives — add_rect

**Files:**
- Modify: `src/pptx/primitives.py`
- Modify: `tests/pptx/test_primitives.py`

- [ ] **Step 1: Add failing tests for `add_rect`**

Append to `tests/pptx/test_primitives.py`:

```python
from src.pptx.primitives import add_rect


def test_add_rect_with_fill():
    prs, slide = _new_slide()
    add_rect(slide, x=1, y=1, w=2, h=1, fill="#065A82")
    rects = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE]
    assert len(rects) == 1
    fc = rects[0].fill.fore_color.rgb
    assert (fc[0], fc[1], fc[2]) == (0x06, 0x5A, 0x82)


def test_add_rect_with_border():
    prs, slide = _new_slide()
    add_rect(slide, x=0, y=0, w=1, h=1, fill="#FFFFFF", border_color="#000000", border_width=2.0)
    rect = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE][0]
    assert rect.line.color.rgb is not None


def test_add_rect_rounded():
    prs, slide = _new_slide()
    add_rect(slide, x=0, y=0, w=1, h=1, fill="#FF0000", rounded=True)
    rect = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE][0]
    from pptx.enum.shapes import MSO_SHAPE
    assert rect.auto_shape_type == MSO_SHAPE.ROUNDED_RECTANGLE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pptx/test_primitives.py::test_add_rect_with_fill -v`
Expected: FAIL with `ImportError` for `add_rect`.

- [ ] **Step 3: Implement `add_rect`**

Append to `src/pptx/primitives.py`:

```python
from pptx.enum.shapes import MSO_SHAPE


def add_rect(
    slide,
    x: float, y: float, w: float, h: float,
    *,
    fill: str = "#FFFFFF",
    border_color: str | None = None,
    border_width: float = 0.0,
    rounded: bool = False,
) -> None:
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _hex_to_rgb(fill)
    if border_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = _hex_to_rgb(border_color)
        shape.line.width = Pt(border_width)
    # Strip default text frame contents to keep shape clean
    if shape.has_text_frame:
        shape.text_frame.text = ""
```

- [ ] **Step 4: Run tests**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pptx/test_primitives.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pptx/primitives.py tests/pptx/test_primitives.py
git commit -m "feat(primitives): add add_rect with optional border and rounded corners"
```

---

## Task 4: Primitives — add_line + add_arrow

**Files:**
- Modify: `src/pptx/primitives.py`
- Modify: `tests/pptx/test_primitives.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/pptx/test_primitives.py`:

```python
from src.pptx.primitives import add_line, add_arrow


def test_add_line_creates_connector():
    prs, slide = _new_slide()
    add_line(slide, x1=1, y1=1, x2=5, y2=3, color="#FF0000", width=2.0)
    lines = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.LINE]
    assert len(lines) == 1


def test_add_arrow_creates_arrow_connector():
    prs, slide = _new_slide()
    add_arrow(slide, x1=0, y1=0, x2=4, y2=0, color="#000000")
    # Arrow is a connector with end-arrow head; we just verify a shape was added
    assert len(slide.shapes) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pptx/test_primitives.py::test_add_line_creates_connector -v`
Expected: FAIL with `ImportError` for `add_line`.

- [ ] **Step 3: Implement `add_line` and `add_arrow`**

Append to `src/pptx/primitives.py`:

```python
from pptx.enum.shapes import MSO_CONNECTOR
from lxml import etree


def add_line(
    slide,
    x1: float, y1: float, x2: float, y2: float,
    *,
    color: str = "#000000",
    width: float = 1.5,
) -> None:
    conn = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT,
        Inches(x1), Inches(y1), Inches(x2), Inches(y2),
    )
    conn.line.color.rgb = _hex_to_rgb(color)
    conn.line.width = Pt(width)


def add_arrow(
    slide,
    x1: float, y1: float, x2: float, y2: float,
    *,
    color: str = "#000000",
    width: float = 2.0,
) -> None:
    conn = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT,
        Inches(x1), Inches(y1), Inches(x2), Inches(y2),
    )
    conn.line.color.rgb = _hex_to_rgb(color)
    conn.line.width = Pt(width)
    # Inject end-arrowhead via XML (python-pptx has no high-level API for this)
    ln = conn.line._get_or_add_ln()
    nsmap = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    tail = etree.SubElement(
        ln,
        "{http://schemas.openxmlformats.org/drawingml/2006/main}tailEnd",
    )
    tail.set("type", "triangle")
    tail.set("w", "med")
    tail.set("len", "med")
```

- [ ] **Step 4: Run tests**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pptx/test_primitives.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pptx/primitives.py tests/pptx/test_primitives.py
git commit -m "feat(primitives): add add_line and add_arrow"
```

---

## Task 5: Primitives — add_image (file-based)

**Files:**
- Modify: `src/pptx/primitives.py`
- Modify: `tests/pptx/test_primitives.py`
- Create: `tests/pptx/fixtures/dot.png`

- [ ] **Step 1: Create a tiny test PNG fixture**

Run from `<root>`:

```bash
mkdir -p tests/pptx/fixtures
python -c "
import struct, zlib
sig = b'\\x89PNG\\r\\n\\x1a\\n'
ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
ihdr_chunk = b'IHDR' + ihdr
ihdr_full = struct.pack('>I', 13) + ihdr_chunk + struct.pack('>I', zlib.crc32(ihdr_chunk))
raw = b'\\x00\\xFF\\x00\\x00'
comp = zlib.compress(raw)
idat_chunk = b'IDAT' + comp
idat_full = struct.pack('>I', len(comp)) + idat_chunk + struct.pack('>I', zlib.crc32(idat_chunk))
iend = b'IEND'
iend_full = struct.pack('>I', 0) + iend + struct.pack('>I', zlib.crc32(iend))
open('tests/pptx/fixtures/dot.png','wb').write(sig + ihdr_full + idat_full + iend_full)
print('ok')
"
```

Expected: prints `ok` and `tests/pptx/fixtures/dot.png` exists (~70 bytes).

- [ ] **Step 2: Add failing test**

Append to `tests/pptx/test_primitives.py`:

```python
from pathlib import Path
from src.pptx.primitives import add_image


def test_add_image_inserts_picture():
    prs, slide = _new_slide()
    fixture = Path(__file__).parent / "fixtures" / "dot.png"
    add_image(slide, x=1, y=1, w=2, h=2, image_path=str(fixture))
    pictures = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert len(pictures) == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pptx/test_primitives.py::test_add_image_inserts_picture -v`
Expected: FAIL with `ImportError` for `add_image`.

- [ ] **Step 4: Implement `add_image`**

Append to `src/pptx/primitives.py`:

```python
def add_image(
    slide,
    x: float, y: float, w: float, h: float,
    image_path: str,
) -> None:
    slide.shapes.add_picture(image_path, Inches(x), Inches(y), Inches(w), Inches(h))
```

- [ ] **Step 5: Run all primitives tests**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pptx/ -v`
Expected: 11 passed.

- [ ] **Step 6: Commit**

```bash
git add src/pptx/primitives.py tests/pptx/test_primitives.py tests/pptx/fixtures/dot.png
git commit -m "feat(primitives): add add_image"
```

---

## Task 6: Code Runner — happy path subprocess execution

**Files:**
- Create: `src/pptx/code_runner.py`
- Create: `tests/pptx/test_code_runner.py`

- [ ] **Step 1: Write failing test for `run_slide_code` happy path**

Create `tests/pptx/test_code_runner.py`:

```python
from pathlib import Path
import tempfile

from pptx import Presentation

from src.pptx.code_runner import run_slide_code, CodeExecutionError


HAPPY_CODE = '''
from pptx import Presentation
from pptx.util import Inches
import json, sys

def add_slide(prs, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    box.text_frame.text = data["msg"]

if __name__ == "__main__":
    data = json.loads(sys.stdin.read())
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    add_slide(prs, data)
    prs.save(sys.argv[1])
'''


def test_run_slide_code_creates_pptx(tmp_path):
    out = tmp_path / "slide.pptx"
    run_slide_code(HAPPY_CODE, {"msg": "Hello"}, out)
    assert out.exists()
    prs = Presentation(out)
    assert len(prs.slides) == 1


def test_run_slide_code_raises_on_python_error(tmp_path):
    bad = "raise RuntimeError('boom')\n"
    out = tmp_path / "bad.pptx"
    try:
        run_slide_code(bad, {}, out)
    except CodeExecutionError as e:
        assert "boom" in str(e) or "RuntimeError" in str(e)
    else:
        raise AssertionError("expected CodeExecutionError")


def test_run_slide_code_timeout(tmp_path):
    slow = "import time; time.sleep(60)\n"
    out = tmp_path / "slow.pptx"
    try:
        run_slide_code(slow, {}, out, timeout=2)
    except CodeExecutionError as e:
        assert "timeout" in str(e).lower()
    else:
        raise AssertionError("expected CodeExecutionError on timeout")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pptx/test_code_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.pptx.code_runner'`.

- [ ] **Step 3: Implement `run_slide_code`**

Strategy: write `code` to a temp `.py` file, invoke `python <tempfile> <output_path>` with `json.dumps(slide_data)` piped to its stdin. This matches the slide-code skeleton documented in the spec (the script reads stdin and saves to argv[1]).

Create `<root>/src/pptx/code_runner.py`:

```python
"""Subprocess-based execution of LLM-generated slide code."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


class CodeExecutionError(RuntimeError):
    def __init__(self, message: str, *, stderr: str = "", returncode: int = -1):
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


def run_slide_code(
    code: str,
    slide_data: dict,
    output_path: Path,
    *,
    timeout: int = 30,
) -> Path:
    """Execute slide-generation code in a subprocess; return output_path on success."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        script_path = f.name

    try:
        try:
            result = subprocess.run(
                [sys.executable, script_path, str(output_path)],
                input=json.dumps(slide_data).encode("utf-8"),
                capture_output=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as e:
            raise CodeExecutionError(
                f"slide code timed out after {timeout}s",
                stderr=(e.stderr or b"").decode("utf-8", errors="replace"),
            )
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass

    if result.returncode != 0:
        raise CodeExecutionError(
            f"slide code exited with {result.returncode}",
            stderr=result.stderr.decode("utf-8", errors="replace"),
            returncode=result.returncode,
        )

    if not output_path.exists():
        raise CodeExecutionError(
            "slide code completed but output_path was not created",
            stderr=result.stderr.decode("utf-8", errors="replace"),
        )

    return output_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pptx/test_code_runner.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pptx/code_runner.py tests/pptx/test_code_runner.py
git commit -m "feat(code_runner): add subprocess executor with timeout and isolated env"
```

---

## Task 7: Code Runner — error recovery loop with LLM fix

**Files:**
- Modify: `src/pptx/code_runner.py`
- Modify: `tests/pptx/test_code_runner.py`

- [ ] **Step 1: Add failing test for `render_slide_with_retry`**

Append to `tests/pptx/test_code_runner.py`:

```python
from src.pptx.code_runner import render_slide_with_retry


def test_render_slide_with_retry_succeeds_first_try(tmp_path):
    calls = {"n": 0}
    def fake_fix(original_code, traceback, slide_data):
        calls["n"] += 1
        return original_code  # not used since first run succeeds
    out = tmp_path / "ok.pptx"
    render_slide_with_retry(HAPPY_CODE, {"msg": "Hi"}, out, fix_callback=fake_fix, max_retries=3)
    assert out.exists()
    assert calls["n"] == 0


def test_render_slide_with_retry_recovers_after_one_failure(tmp_path):
    bad = "raise RuntimeError('boom')\n"
    fix_called = {"n": 0}
    def fix(original_code, traceback, slide_data):
        fix_called["n"] += 1
        assert "boom" in traceback or "RuntimeError" in traceback
        return HAPPY_CODE  # replace with working code
    out = tmp_path / "recovered.pptx"
    render_slide_with_retry(bad, {"msg": "Recovered"}, out, fix_callback=fix, max_retries=3)
    assert out.exists()
    assert fix_called["n"] == 1


def test_render_slide_with_retry_gives_up_after_max(tmp_path):
    bad = "raise RuntimeError('always')\n"
    def fix(original_code, traceback, slide_data):
        return bad  # never improves
    out = tmp_path / "fail.pptx"
    try:
        render_slide_with_retry(bad, {}, out, fix_callback=fix, max_retries=2)
    except CodeExecutionError as e:
        assert "after 2 retries" in str(e) or "retries" in str(e)
    else:
        raise AssertionError("expected CodeExecutionError after max retries")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pptx/test_code_runner.py -v -k retry`
Expected: FAIL with `ImportError` for `render_slide_with_retry`.

- [ ] **Step 3: Implement `render_slide_with_retry`**

Append to `src/pptx/code_runner.py`:

```python
from typing import Callable

FixCallback = Callable[[str, str, dict], str]


def _tail(text: str, lines: int = 20) -> str:
    return "\n".join(text.splitlines()[-lines:])


def render_slide_with_retry(
    code: str,
    slide_data: dict,
    output_path: Path,
    *,
    fix_callback: FixCallback,
    max_retries: int = 3,
    timeout: int = 30,
) -> Path:
    """Run slide code; on failure, ask fix_callback for a new full code and retry."""
    last_err: CodeExecutionError | None = None
    current_code = code
    attempts = 0
    while attempts <= max_retries:
        try:
            return run_slide_code(current_code, slide_data, output_path, timeout=timeout)
        except CodeExecutionError as e:
            last_err = e
            attempts += 1
            if attempts > max_retries:
                break
            current_code = fix_callback(current_code, _tail(e.stderr or str(e)), slide_data)
    raise CodeExecutionError(
        f"slide rendering failed after {max_retries} retries",
        stderr=last_err.stderr if last_err else "",
    )
```

- [ ] **Step 4: Run tests**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pptx/test_code_runner.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pptx/code_runner.py tests/pptx/test_code_runner.py
git commit -m "feat(code_runner): add render_slide_with_retry with fix callback"
```

---

## Task 8: Slide Merger — combine N single-slide pptx files

**Files:**
- Create: `src/pptx/merger.py`
- Create: `tests/pptx/test_merger.py`

- [ ] **Step 1: Write failing tests**

Create `tests/pptx/test_merger.py`:

```python
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from src.pptx.merger import merge_slides


def _make_one_slide(path: Path, text: str) -> Path:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    box.text_frame.text = text
    prs.save(path)
    return path


def test_merge_two_slides_into_one_deck(tmp_path):
    a = _make_one_slide(tmp_path / "a.pptx", "First")
    b = _make_one_slide(tmp_path / "b.pptx", "Second")
    out = tmp_path / "merged.pptx"
    merge_slides([a, b], out)
    final = Presentation(out)
    assert len(final.slides) == 2
    texts = []
    for sl in final.slides:
        for shp in sl.shapes:
            if shp.has_text_frame:
                texts.append(shp.text_frame.text)
    assert "First" in texts
    assert "Second" in texts


def test_merge_single_slide_passes_through(tmp_path):
    a = _make_one_slide(tmp_path / "a.pptx", "Only")
    out = tmp_path / "out.pptx"
    merge_slides([a], out)
    final = Presentation(out)
    assert len(final.slides) == 1


def test_merge_empty_list_raises(tmp_path):
    out = tmp_path / "out.pptx"
    try:
        merge_slides([], out)
    except ValueError:
        return
    raise AssertionError("expected ValueError on empty list")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pptx/test_merger.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `merge_slides` via XML copy**

Create `<root>/src/pptx/merger.py`:

```python
"""Merge multiple single-slide .pptx files into one presentation.

python-pptx has no public slide-copy API. We deep-copy the slide part XML and
re-link relationships into a destination presentation.
"""
from __future__ import annotations

import copy
from pathlib import Path

from pptx import Presentation
from pptx.oxml.ns import qn


def _copy_slide(dest_prs, source_slide) -> None:
    """Append a copy of source_slide into dest_prs."""
    # Use the same blank layout for predictability
    blank_layout = dest_prs.slide_layouts[6]
    new_slide = dest_prs.slides.add_slide(blank_layout)

    # Drop default placeholders that came from the layout
    for shp in list(new_slide.shapes):
        sp = shp._element
        sp.getparent().remove(sp)

    # Deep-copy each shape from the source
    src_spTree = source_slide.shapes._spTree
    dst_spTree = new_slide.shapes._spTree
    for child in src_spTree.iterchildren():
        tag = child.tag
        # Skip non-shape bookkeeping elements that the layout already provides
        if tag.endswith("}nvGrpSpPr") or tag.endswith("}grpSpPr"):
            continue
        dst_spTree.append(copy.deepcopy(child))

    # Copy slide background fill if present
    src_bg = source_slide._element.find(qn("p:cSld") + "/" + qn("p:bg"))
    if src_bg is not None:
        dst_cSld = new_slide._element.find(qn("p:cSld"))
        # Remove existing bg if any then insert source's
        for existing in dst_cSld.findall(qn("p:bg")):
            dst_cSld.remove(existing)
        dst_cSld.insert(0, copy.deepcopy(src_bg))


def merge_slides(slide_paths: list[Path], output_path: Path) -> Path:
    if not slide_paths:
        raise ValueError("merge_slides: slide_paths is empty")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Start from a fresh blank deck so dimensions/theme are consistent
    first = Presentation(slide_paths[0])
    final = Presentation()
    final.slide_width = first.slide_width
    final.slide_height = first.slide_height

    for path in slide_paths:
        src = Presentation(path)
        for sl in src.slides:
            _copy_slide(final, sl)

    final.save(output_path)
    return output_path
```

- [ ] **Step 4: Run tests**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pptx/test_merger.py -v`
Expected: 3 passed.

If `test_merge_two_slides_into_one_deck` fails on text content, the deep-copy may have lost relationships. Inspect with: `PYTHONIOENCODING=utf-8 pytest tests/pptx/test_merger.py -v -s` and check actual slide count first.

- [ ] **Step 5: Commit**

```bash
git add src/pptx/merger.py tests/pptx/test_merger.py
git commit -m "feat(merger): add merge_slides via XML deep-copy"
```

---

## Task 9: Primitives API reference doc

**Files:**
- Create: `guidelines/primitives_api.md`

- [ ] **Step 1: Write the API reference**

Create `<root>/guidelines/primitives_api.md`:

````markdown
# Primitives API Reference

Layer 1 dumb-executor functions exposed at `src.pptx.primitives`.

All coordinates and dimensions are in **inches**. Slide is **13.333 × 7.5** inches (16:9).
All colors are uppercase 6-digit hex with leading `#` (e.g., `#1C2833`).

## Functions

### `set_bg(slide, color)`
Paint slide background with a solid color.
- `color`: hex string

### `add_text(slide, x, y, w, h, text, *, font_size=14, bold=False, italic=False, color="#000000", align="left", font="Pretendard", line_spacing=1.2)`
Insert a text box at `(x, y)` with size `(w, h)`.
- `align` ∈ {`"left"`, `"center"`, `"right"`}
- For Korean text prefer `font="Pretendard"` or `"Malgun Gothic"`.

### `add_rect(slide, x, y, w, h, *, fill="#FFFFFF", border_color=None, border_width=0.0, rounded=False)`
Insert a rectangle (or rounded rectangle).
- `border_color=None` means no border.

### `add_line(slide, x1, y1, x2, y2, *, color="#000000", width=1.5)`
Insert a straight line connector.

### `add_arrow(slide, x1, y1, x2, y2, *, color="#000000", width=2.0)`
Insert a straight line with an end-arrow head (triangle).

### `add_image(slide, x, y, w, h, image_path)`
Insert a picture from disk at `(x, y)` with size `(w, h)`.

## Required Slide Code Skeleton

```python
from pptx import Presentation
from pptx.util import Inches
from src.pptx.primitives import (
    add_text, add_rect, add_line, add_arrow, add_image, set_bg,
)
import json, sys


def add_slide(prs: Presentation, data: dict) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    # Compose using primitives only.


if __name__ == "__main__":
    data = json.loads(sys.stdin.read())
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    add_slide(prs, data)
    prs.save(sys.argv[1])
```

## Constraints (for code generation)

- Only the imports shown above are allowed.
- No file I/O other than reading stdin and writing `sys.argv[1]`.
- All text and numbers must come from the `data` dict; no hardcoded content.
- Colors and fonts come from `data["deck_meta"]["theme"]` and `data["deck_meta"]["fonts"]`.
- Keep all content within `0.4` inch margin from slide edges.
````

- [ ] **Step 2: Commit**

```bash
git add guidelines/primitives_api.md
git commit -m "docs(guidelines): add primitives API reference"
```

---

## Task 10: Design guideline doc — first 9 patterns (the original star set)

**Files:**
- Create: `guidelines/design_guideline.md`

- [ ] **Step 1: Write the guideline doc**

Create `<root>/guidelines/design_guideline.md`. The doc has a header explaining usage, then one section per pattern. Start with the 9 originally agreed patterns (Cover, Bullet List, As-Is/To-Be, Flow, Roadmap, Matrix, Stat, Pyramid, Quote). Add the remaining 24 in Task 11.

````markdown
# Design Guideline

This document tells the LLM **what to draw and when**, not how to write the code.
For drawing primitives see [primitives_api.md](primitives_api.md).

When generating a slide, pick the single most appropriate pattern below for the
content, then compose primitives to realize it. Patterns are organized by intent.

## How to read each pattern
- **언제**: situations where this pattern is the right choice
- **구성**: how to lay out the slide using primitives
- **주의**: common mistakes to avoid

---

## A. 수치·데이터 표현

### Stat 강조 (Big Number)
- **언제**: 핵심 수치 1~3개를 청중에게 각인시킬 때. KPI, 성과 보고
- **구성**: 헤드 메시지(상단, 28pt bold) + 수치 1~3개를 가로로 큰 글자(72pt+, primary 색)로 배치 + 각 수치 아래 단위·라벨(14pt) + 하단에 1줄 해석(16pt)
- **주의**: 수치는 슬라이드 1장에 최대 3개. 수치보다 큰 시각 요소가 있으면 강조 효과가 무너짐

## B. 비교·대조

### Matrix 비교
- **언제**: 2~4개 옵션을 여러 기준으로 동시에 비교, 의사결정 지원
- **구성**: 1행=헤더(primary 색 사각형 + 흰 글씨), 1열=옵션 라벨. 각 셀은 짧은 텍스트(●●● 또는 점수). 추천안 행은 굵은 테두리 또는 accent 강조
- **주의**: 셀이 6×6 초과 시 가독성↓. 기준 5개 이하

### As-Is / To-Be
- **언제**: 현재 상태와 개선 후 상태를 대비할 때. 변화의 방향성 강조
- **구성**: 슬라이드 좌·우 50% 분할. 왼쪽 As-Is(neutral 어두운 톤), 오른쪽 To-Be(primary 색). 중앙에 큰 화살표(→). 각 영역 상단에 라벨, 하단에 3~4개 bullet
- **주의**: As-Is에 감정적 단어 금지("나쁜", "문제"). 사실 기술만. To-Be는 측정 가능한 결과로

## C. 프로세스·흐름

### Flow 다이어그램
- **언제**: 순서가 있는 프로세스, 단계별 작업 흐름
- **구성**: 사각형(단계)을 가로로 3~6개 배치, 화살표로 연결. 각 사각형 안에 단계명(16pt). 각 사각형 아래 1줄 설명(12pt). 핵심 단계는 accent 색
- **주의**: 7단계 초과 시 두 줄로 꺾기. 분기 3개 이상은 별도 슬라이드

## D. 시간·일정

### 추진계획 로드맵 (시간 × 카테고리)
- **언제**: 여러 카테고리의 작업이 시간 축 위에서 언제 진행되는지 보여줄 때
- **구성**: 1행=시간 헤더(월/분기, primary 사각형 + 흰 글씨), 1열=카테고리 라벨. 각 셀 위에 사각형 블록으로 작업 기간 표시. 마일스톤은 ◆(또는 작은 원). 카테고리별 같은 색
- **주의**: 셀 경계는 옅게. 블록 텍스트 8pt 이상 유지. 12개월 초과 시 분기 단위로 축약

## E. 구조·관계

### 피라미드 / 계층 구조
- **언제**: 우선순위, 위계, Maslow식 욕구, 조직 구조
- **구성**: 사다리꼴 사각형(또는 단순 사각형)을 위에서 아래로 점점 넓게 4~5단. 위=가장 중요/희소. 색은 진→옅 또는 옅→진
- **주의**: 5단 초과 시 라벨 잘림 주의. 가로 배치도 가능

## F. 메시지 전달

### Cover (표지)
- **언제**: 첫 슬라이드. 발표 시작
- **구성**: 배경 전체 primary 색. 제목 44pt+ 중앙 또는 좌하단 정렬. 부제목/날짜 18pt. 선택적으로 하단 accent 띠(높이 15%)
- **주의**: 본문 슬라이드와 동일 레이아웃 금지

### 인용
- **언제**: 실제 인용문, 핵심 원칙, 전환 슬라이드
- **구성**: 큰 따옴표 " 를 배경 장식(60pt, primary opacity 20%). 인용 텍스트 22pt 중앙 정렬. 출처 14pt 이탤릭 우측 정렬
- **주의**: 출처 없는 인용 금지. 슬라이드에 다른 요소 최소화

## G. 콘텐츠 밀도

### Bullet List
- **언제**: 나열형 정보. 다른 패턴이 맞지 않을 때 기본 선택
- **구성**: 헤드 메시지 24pt(상단). 그 아래 bullet 16pt, 앞에 ▪ 또는 primary 색 작은 사각형. 최대 5개
- **주의**: 6개 이상이면 두 컬럼으로 나누거나 슬라이드 분리

````

- [ ] **Step 2: Commit**

```bash
git add guidelines/design_guideline.md
git commit -m "docs(guidelines): add design guideline with 9 core patterns"
```

---

## Task 11: Design guideline — add remaining 24 patterns

**Files:**
- Modify: `guidelines/design_guideline.md`

- [ ] **Step 1: Append the remaining patterns**

Append to `<root>/guidelines/design_guideline.md`:

````markdown

## A. 수치·데이터 표현 (추가)

### Chart 슬라이드
- **언제**: 시계열·분포·비율을 차트로 보여줄 때
- **구성**: 헤드 메시지 상단. 차트 영역 슬라이드 70% 차지. python-pptx 네이티브 차트 객체 또는 사각형 조합으로 막대/선 표현. 범례는 차트 옆 또는 위
- **주의**: MVP에서는 add_rect 조합으로 막대차트 위주. 복잡한 차트는 6개 이하 데이터 포인트

### KPI Dashboard
- **언제**: 4~6개 핵심 지표를 한눈에
- **구성**: 2×2 또는 2×3 그리드. 각 셀: 라벨(14pt) + 큰 수치(48pt) + 변화량(▲/▼ + 색상)
- **주의**: 셀당 정보 3개 이하. 색상은 좋음=green, 나쁨=red 일관 적용

### Trend + Annotation
- **언제**: 시계열 + 주요 이벤트 포인트 표시
- **구성**: 라인 차트 + 핵심 시점에 핀(작은 원) + 라벨 텍스트
- **주의**: 핀 4개 이하. 라벨은 차트 위쪽에만

### Progress Bar
- **언제**: 달성률·진행률 시각화
- **구성**: 가로 긴 사각형(neutral) + 그 위에 percent만큼 채운 사각형(primary). 옆에 % 텍스트(24pt)
- **주의**: 여러 바 비교 시 정렬과 동일 너비 유지

### Top Ranking
- **언제**: Top 3/5/10 순위
- **구성**: 가로형 막대 또는 세로 리스트. 1위는 가장 진한 색 또는 ★. 순위 번호 큰 글자
- **주의**: 10개 초과 금지. 동률은 별도 표기

## B. 비교·대조 (추가)

### 2×2 Quadrant
- **언제**: SWOT, BCG 매트릭스, 우선순위 매트릭스(긴급도×중요도)
- **구성**: 슬라이드 중앙에 십자 분할. 각 사분면에 라벨(좌상/우상/좌하/우하). 사분면별 다른 톤. 축 라벨은 십자 양 끝
- **주의**: 사분면당 텍스트 짧게 유지(3줄 이하). 항목을 점으로 배치하는 경우 겹침 주의

### Pros & Cons
- **언제**: 한 옵션의 장점·단점을 양분 비교
- **구성**: 좌우 2분할. 좌=Pros(green 톤, + 아이콘), 우=Cons(red 톤, − 아이콘). 각 측 3~5 항목
- **주의**: 항목 수 좌우 동일하게. 한쪽이 너무 많으면 슬라이드 분리

### 3-Column Cards
- **언제**: 3가지 옵션을 카드로 비교
- **구성**: 가로 3분할 카드. 각 카드 = 헤더(옵션명) + 본문(특징 bullet 3개). 추천안은 accent 색 + 굵은 테두리 + ★
- **주의**: 4개 이상이면 카드가 좁아져 가독성↓. Matrix 비교로 전환

### Spectrum
- **언제**: 양극단 사이 위치 시각화. "보수↔혁신", "단순↔복잡"
- **구성**: 가로 그라데이션 바 + 양 끝에 라벨 + 현재 위치에 마커(원)
- **주의**: 1차원 스펙트럼만 권장. 2차원은 Quadrant로

## C. 프로세스·흐름 (추가)

### Cycle / Loop
- **언제**: PDCA 같은 순환 프로세스
- **구성**: 4~6개 사각형(또는 원)을 원형 배치. 곡선 화살표로 시계방향 연결
- **주의**: 단계 6개 초과 금지. 시작점은 시계 12시 또는 좌상단 명확히

### Funnel
- **언제**: 단계별 전환율, 마케팅·세일즈 깔때기
- **구성**: 위에서 아래로 점점 좁아지는 사다리꼴 4~6개. 각 단계: 라벨 + 수치 + 전환율(%)
- **주의**: 색상은 위에서 아래로 점점 어두워지게(또는 반대). 단계 7개 초과 금지

### Swim Lane
- **언제**: 부서·역할 × 프로세스 단계의 책임 분장
- **구성**: 가로 lane(역할), 세로 분할(단계). 각 셀에 작업 사각형. 작업 간 화살표는 lane 가로지를 수 있음
- **주의**: lane 4개 이하. 단계 5개 이하

### Decision Tree
- **언제**: 분기, 의사결정 흐름
- **구성**: 마름모(질문) + 사각형(액션). 위→아래 또는 좌→우 분기. 각 분기에 조건 텍스트
- **주의**: 깊이 4단 초과 금지. 초과 시 별도 슬라이드

### Force Field
- **언제**: 변화 추진력 vs 저항력 분석
- **구성**: 중앙 세로선(현 상태). 좌측에서 우측으로 향하는 화살표(추진력, green). 우측에서 좌측으로 향하는 화살표(저항력, red). 화살표 두께=강도
- **주의**: 양측 항목 4개 이하. 강도가 비슷해 보이지 않도록 두께 차이 명확히

## D. 시간·일정 (추가)

### Timeline
- **언제**: 역사·연혁·일자별 사건 나열
- **구성**: 가로 라인 + 일정 시점에 점/원. 각 점 위 또는 아래에 날짜·이벤트 텍스트. 위·아래 교차 배치 가능
- **주의**: 시점 7개 초과 시 가독성↓. 핵심 사건만 굵게

### Customer Journey
- **언제**: 고객 단계별 경험 + 감정 곡선
- **구성**: 가로 4~6단계(인지→탐색→구매→사용→재방문). 각 단계에 액션·터치포인트·감정. 감정은 곡선 그래프로 위·아래 변화
- **주의**: 단계당 텍스트 짧게. 감정 곡선이 핵심 메시지여야 함

## E. 구조·관계 (추가)

### Venn 다이어그램
- **언제**: 2~3개 집합의 교집합·차집합
- **구성**: 반투명 원 2~3개 겹침. 각 영역에 라벨. 교집합 영역은 텍스트 명시
- **주의**: 4개 원 금지(시각적 혼란). 영역별 텍스트 짧게

### Concentric Circles
- **언제**: 중심에서 바깥으로 영향력·범위 확산
- **구성**: 동심원 3~4개. 안쪽=핵심, 바깥=주변. 각 원 위에 라벨
- **주의**: 5개 초과 금지. 라벨은 원 위쪽 또는 우측에만

### Org Chart / Tree
- **언제**: 조직도, 트리 구조
- **구성**: 위에 루트 사각형 + 아래로 분기. 같은 레벨 사각형 크기·색 동일. 선으로 연결
- **주의**: 깊이 4단 + 노드 12개 이하. 초과 시 핵심 부서만

### Hub & Spoke
- **언제**: 중심 노드 + 방사형 가지. 허브 중심 관계
- **구성**: 중앙에 큰 원(허브) + 주변 4~8개 작은 원(spoke). 선으로 연결. 허브는 primary, spoke는 neutral
- **주의**: spoke 8개 초과 시 별도 슬라이드. 라벨이 겹치지 않게 배치

### Iceberg
- **언제**: 표면(보이는 것) vs 심층(숨겨진 것) 대비
- **구성**: 가로선=수면. 위 작은 삼각형(표면), 아래 큰 사다리꼴(심층). 각 영역에 항목 bullet
- **주의**: 위·아래 비율 1:3 정도. 항목 각 영역 4개 이하

## F. 메시지 전달 (추가)

### Big Statement
- **언제**: 전환·강조 슬라이드. 한 문장으로 임팩트
- **구성**: 슬라이드 중앙에 1문장(48pt+). 배경 단순한 색. 다른 요소 없음
- **주의**: 문장 30자 이내. 다른 슬라이드와 강한 대비

### Problem-Solution-Benefit
- **언제**: 3단 서사. 제안서·기획서 핵심
- **구성**: 가로 3분할. 좌=문제(red 톤), 중=해결(neutral 톤), 우=효과(green 톤). 각 영역 상단 아이콘 또는 번호
- **주의**: 3개 영역의 텍스트 분량 균형. 화살표(→) 사이에

### Section Divider
- **언제**: 섹션 전환
- **구성**: 큰 번호(72pt+, primary 색) + 섹션 제목(36pt). 배경 전체 neutral 또는 흰색. 매우 단순하게
- **주의**: 본문 슬라이드와 명확히 다른 시각적 무게

### Headline + Image
- **언제**: 큰 헤드라인 + 보조 이미지
- **구성**: 좌측 60% 텍스트(헤드 36pt + 보조 16pt), 우측 40% 이미지. 또는 위 30% 헤드, 아래 70% 이미지
- **주의**: 이미지 quality가 낮으면 사용 금지

## G. 콘텐츠 밀도 (추가)

### Icon Grid
- **언제**: 기능·특징 4~9개 나열
- **구성**: 2×2, 2×3, 3×3 그리드. 각 셀: 아이콘(또는 색 사각형) + 라벨 + 1줄 설명
- **주의**: 9개 초과 시 슬라이드 분리. 아이콘 스타일 일관성

### 3-Card Highlights
- **언제**: 핵심 메시지 3개를 균형 있게
- **구성**: 가로 3분할 카드. 카드 = 큰 숫자/아이콘 + 짧은 제목 + 1줄 설명
- **주의**: 텍스트 분량 카드별 동일하게. 3개 정확히

### Featured Callout
- **언제**: 한 핵심 박스 강조 + 주변 보조 텍스트
- **구성**: 슬라이드 중앙·좌측 큰 박스(primary 색) + 우측 보조 bullet 3~4개. 박스 안 핵심 문장 24pt
- **주의**: 핵심 박스가 시선 90% 차지하도록

### Photo + Caption
- **언제**: 큰 사진 + 짧은 캡션. 감정·장면 전달
- **구성**: 사진 슬라이드 80% 차지. 캡션은 사진 하단 띠 또는 우측 분할
- **주의**: 사진 해상도 충분해야 함. 캡션 30자 이내

### Comparison Table
- **언제**: 텍스트 중심 비교표 (Matrix와 다름: 점수 X, 텍스트 O)
- **구성**: 1행 헤더(옵션명), 1열 라벨(비교 항목). 셀에 짧은 텍스트(예: "$$$", "Yes/No")
- **주의**: 6×6 초과 시 가독성↓

## H. 메타·구조

### Agenda / 목차
- **언제**: 표지 다음 슬라이드. 발표 흐름 안내
- **구성**: 좌측 또는 중앙에 번호 매김 리스트(01·02·03). 각 항목 = 번호(primary 색) + 섹션명(20pt)
- **주의**: 항목 7개 초과 금지

### Summary / Recap
- **언제**: 발표 마지막 직전. 핵심 메시지 재나열
- **구성**: 좌측 "정리:" 헤더 + 우측 3~5개 핵심 메시지 bullet. 각 메시지 앞에 ★ 또는 번호
- **주의**: 새로운 정보 추가 금지. 기존 헤드 메시지 재구성

### Next Steps / Action Plan
- **언제**: 실행 계획 명시
- **구성**: 표 형태. 1행=헤더(누가/언제/무엇). 각 행=액션 아이템
- **주의**: 5개 이하. 담당자 모호 금지

### Q&A
- **언제**: 발표 끝, 질의응답 시작
- **구성**: 슬라이드 중앙에 큰 "Q&A" 또는 "?" 글자(96pt+, primary 색). 하단에 발표자 연락처
- **주의**: 다른 요소 최소화

### Thank You / Closing
- **언제**: 마지막 슬라이드
- **구성**: 중앙 또는 좌하단 "감사합니다" 또는 "Thank You"(48pt+). 발표자 이름·소속·연락처
- **주의**: 표지와 시각적 통일감

### Reference / 참고자료
- **언제**: 출처·인용 출처 목록
- **구성**: 작은 폰트(11~12pt) 다수. 좌측 [n] 번호 + 우측 출처 텍스트
- **주의**: 길어지면 슬라이드 2장으로 분리. 폰트 너무 작지 않게(11pt 최소)
````

- [ ] **Step 2: Commit**

```bash
git add guidelines/design_guideline.md
git commit -m "docs(guidelines): add 24 additional design patterns across 8 categories"
```

---

## Task 12: Code generator — prompt template + extract_code_block helper

**Files:**
- Create: `prompts/code_generation.txt`
- Create: `src/pipeline/code_generator.py`
- Create: `tests/pipeline/__init__.py`
- Create: `tests/pipeline/test_code_generator.py`

- [ ] **Step 1: Write prompt template**

Create `<root>/prompts/code_generation.txt`:

```
You are a Python code generator for python-pptx slides.

Generate a single Python script that creates ONE slide for the given plan.

You MUST use this exact skeleton (no other imports allowed):

```python
from pptx import Presentation
from pptx.util import Inches
from src.pptx.primitives import (
    add_text, add_rect, add_line, add_arrow, add_image, set_bg,
)
import json, sys


def add_slide(prs, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    # Compose the slide using primitives only.
    pass


if __name__ == "__main__":
    data = json.loads(sys.stdin.read())
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    add_slide(prs, data)
    prs.save(sys.argv[1])
```

Constraints:
- Slide is 13.333 x 7.5 inches.
- All text/numbers must be read from `data`. Do NOT hardcode the slide content.
- Colors and fonts MUST come from `data["deck_meta"]["theme"]` and `data["deck_meta"]["fonts"]`.
- Keep all content within 0.4 inch margin from slide edges.
- Output a SINGLE python script in a ```python ... ``` code block. No prose before or after.

Layout pattern selected: {layout_hint}
Pattern guideline:
{pattern_guideline}

Slide data passed at runtime (this is what `data` will contain):
{slide_data_json}

Now produce the script.
```

- [ ] **Step 2: Write failing tests**

Create `tests/pipeline/__init__.py` (empty), then `tests/pipeline/test_code_generator.py`:

```python
from src.pipeline.code_generator import extract_code_block, build_codegen_prompt


def test_extract_code_block_python_fenced():
    response = """Here is the code:
```python
def add_slide(prs, data):
    pass
```
That's it."""
    code = extract_code_block(response)
    assert "def add_slide" in code
    assert "Here is" not in code
    assert "That's it" not in code


def test_extract_code_block_no_fence_returns_raw():
    response = "from pptx import Presentation\ndef add_slide(prs, data): pass\n"
    code = extract_code_block(response)
    assert "from pptx" in code


def test_extract_code_block_strips_only_first_python_fence():
    response = "```python\nA = 1\n```\nNot code\n```python\nB = 2\n```"
    code = extract_code_block(response)
    assert "A = 1" in code
    assert "B = 2" not in code


def test_build_codegen_prompt_includes_layout_and_data():
    prompt = build_codegen_prompt(
        layout_hint="Cover",
        pattern_guideline="Cover pattern: full-bleed primary color background.",
        slide_data={"head_message": "Hello", "deck_meta": {"theme": {"primary": "#065A82"}}},
    )
    assert "Cover" in prompt
    assert "Cover pattern" in prompt
    assert "Hello" in prompt
    assert "#065A82" in prompt
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pipeline/test_code_generator.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement code_generator helpers**

Create `<root>/src/pipeline/code_generator.py`:

```python
"""Phase 4 — generate slide python code from a single slide plan via LLM."""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.llm.ollama_client import chat

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "code_generation.txt"

_FENCE_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)


def extract_code_block(response: str) -> str:
    """Return the contents of the first ```python ...``` fence, or raw response if none."""
    m = _FENCE_RE.search(response)
    if m:
        return m.group(1)
    return response


def build_codegen_prompt(
    *,
    layout_hint: str,
    pattern_guideline: str,
    slide_data: dict,
) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(
        layout_hint=layout_hint,
        pattern_guideline=pattern_guideline,
        slide_data_json=json.dumps(slide_data, ensure_ascii=False, indent=2),
    )


def generate_slide_code(
    *,
    layout_hint: str,
    pattern_guideline: str,
    slide_data: dict,
    model: str = "gemma4:e4b",
) -> str:
    prompt = build_codegen_prompt(
        layout_hint=layout_hint,
        pattern_guideline=pattern_guideline,
        slide_data=slide_data,
    )
    response = chat(prompt, model=model)
    return extract_code_block(response)
```

- [ ] **Step 5: Run tests**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pipeline/test_code_generator.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add prompts/code_generation.txt src/pipeline/code_generator.py tests/pipeline/__init__.py tests/pipeline/test_code_generator.py
git commit -m "feat(code_generator): add prompt template and code-block extractor"
```

---

## Task 13: Guideline lookup — find pattern by name

**Files:**
- Create: `src/pipeline/guideline_loader.py`
- Create: `tests/pipeline/test_guideline_loader.py`

- [ ] **Step 1: Write failing tests**

Create `tests/pipeline/test_guideline_loader.py`:

```python
from src.pipeline.guideline_loader import (
    load_pattern_index,
    get_pattern_section,
    get_pattern_summary_cards,
)


def test_load_pattern_index_returns_known_patterns():
    idx = load_pattern_index()
    assert "Cover" in idx
    assert "Bullet List" in idx
    assert "Stat 강조" in idx
    assert "Matrix 비교" in idx


def test_get_pattern_section_returns_three_subsections():
    section = get_pattern_section("Cover")
    assert "언제" in section
    assert "구성" in section
    assert "주의" in section


def test_get_pattern_section_unknown_raises():
    try:
        get_pattern_section("DOES_NOT_EXIST")
    except KeyError:
        return
    raise AssertionError("expected KeyError")


def test_summary_cards_one_line_per_pattern():
    cards = get_pattern_summary_cards()
    assert len(cards) >= 9
    assert all("\n" not in c or c.count("\n") <= 1 for c in cards)
    assert any(c.startswith("Cover") for c in cards)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pipeline/test_guideline_loader.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement guideline_loader**

Create `<root>/src/pipeline/guideline_loader.py`:

```python
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
        name = m.group(1).strip()
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
```

- [ ] **Step 4: Run tests**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pipeline/test_guideline_loader.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/guideline_loader.py tests/pipeline/test_guideline_loader.py
git commit -m "feat(guideline_loader): parse design_guideline.md into pattern index"
```

---

## Task 14: Planner Phase 2-1 — story outline

**Files:**
- Create: `prompts/story_outline.txt`
- Create: `src/pipeline/planner.py`
- Create: `tests/pipeline/test_planner.py`

- [ ] **Step 1: Write the prompt template**

Create `<root>/prompts/story_outline.txt`:

```
You design slide story arcs.

Given the user's content, output a JSON list of slides with `slide_no`, `purpose`, and `head_message`.

Rules:
- Avoid "intro / body / conclusion" flat structure.
- Each `head_message` must be a CONCLUSION sentence (not a topic label). 25 chars or less. Korean preferred when language=ko.
- Order slides BLUF: what audience cares about most goes first.
- Cover slide is always slide_no=1.
- Output ONLY a JSON array in a ```json ... ``` code block. No prose.

Content:
{content_json}

Now produce the JSON.
```

- [ ] **Step 2: Write failing tests**

Create `tests/pipeline/test_planner.py`:

```python
from unittest.mock import patch

from src.pipeline.planner import generate_outline, parse_json_block


def test_parse_json_block_extracts_array():
    response = """ok here:
```json
[
  {"slide_no": 1, "purpose": "open", "head_message": "Hello"},
  {"slide_no": 2, "purpose": "close", "head_message": "Bye"}
]
```
done"""
    parsed = parse_json_block(response)
    assert isinstance(parsed, list)
    assert parsed[0]["slide_no"] == 1
    assert parsed[1]["head_message"] == "Bye"


def test_parse_json_block_object_form():
    response = '```json\n{"a": 1}\n```'
    parsed = parse_json_block(response)
    assert parsed == {"a": 1}


def test_parse_json_block_raises_on_missing():
    try:
        parse_json_block("no json here")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


@patch("src.pipeline.planner.chat")
def test_generate_outline_returns_list_of_dicts(mock_chat):
    mock_chat.return_value = '```json\n[{"slide_no":1,"purpose":"open","head_message":"Hi"}]\n```'
    out = generate_outline({"meta": {"title": "T"}, "sections": []})
    assert isinstance(out, list)
    assert out[0]["slide_no"] == 1
    assert "open" == out[0]["purpose"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pipeline/test_planner.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement planner Phase 2-1**

Create `<root>/src/pipeline/planner.py`:

```python
"""content.json -> plan.json via Ollama (Phases 2-1 and 2-2)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.llm.ollama_client import chat

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

_JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)


def parse_json_block(response: str):
    m = _JSON_FENCE_RE.search(response)
    if not m:
        raise ValueError("no ```json``` fence found in response")
    return json.loads(m.group(1))


def generate_outline(content: dict, *, model: str = "gemma4:e4b") -> list[dict]:
    template = (PROMPTS_DIR / "story_outline.txt").read_text(encoding="utf-8")
    prompt = template.format(content_json=json.dumps(content, ensure_ascii=False, indent=2))
    response = chat(prompt, model=model)
    parsed = parse_json_block(response)
    if not isinstance(parsed, list):
        raise ValueError(f"expected JSON array, got {type(parsed).__name__}")
    return parsed
```

- [ ] **Step 5: Run tests**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pipeline/test_planner.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add prompts/story_outline.txt src/pipeline/planner.py tests/pipeline/test_planner.py
git commit -m "feat(planner): add Phase 2-1 story outline generation"
```

---

## Task 15: Planner Phase 2-2 — slide detail

**Files:**
- Create: `prompts/slide_detail.txt`
- Modify: `src/pipeline/planner.py`
- Modify: `tests/pipeline/test_planner.py`

- [ ] **Step 1: Write prompt template**

Create `<root>/prompts/slide_detail.txt`:

```
You expand a single slide outline into full detail.

Pick the BEST design pattern for this slide from the catalog (one name from the catalog), then produce structured `content` for that pattern.

Available pattern catalog (one-liners):
{pattern_cards}

Detailed guideline for the pattern you choose will be passed downstream when generating the actual slide; for now you only need to choose the pattern name and produce content matching it.

Slide outline:
- slide_no: {slide_no}
- purpose: {purpose}
- head_message: {head_message}

Relevant section content (raw facts):
{section_facts}

Output ONLY a JSON object in a ```json ... ``` code block:
{{
  "slide_no": {slide_no},
  "purpose": "{purpose}",
  "head_message": "{head_message}",
  "layout_hint": "<exactly one pattern name from the catalog>",
  "content": {{ ...pattern-specific keys... }}
}}
```

- [ ] **Step 2: Append failing tests**

Append to `tests/pipeline/test_planner.py`:

```python
from src.pipeline.planner import generate_slide_detail, derive_deck_meta, make_plan


@patch("src.pipeline.planner.chat")
def test_generate_slide_detail_returns_full_dict(mock_chat):
    mock_chat.return_value = """```json
{
  "slide_no": 1,
  "purpose": "open",
  "head_message": "Hi",
  "layout_hint": "Cover",
  "content": {"title": "Hi", "subtitle": "subj"}
}
```"""
    out = generate_slide_detail(
        outline={"slide_no": 1, "purpose": "open", "head_message": "Hi"},
        section_facts=[],
    )
    assert out["layout_hint"] == "Cover"
    assert out["content"]["title"] == "Hi"


def test_derive_deck_meta_uses_default_theme_when_no_tone():
    meta = derive_deck_meta({"meta": {"title": "T"}})
    assert "theme" in meta
    assert meta["theme"]["primary"].startswith("#")
    assert meta["slide_size"] == {"width_in": 13.333, "height_in": 7.5}


@patch("src.pipeline.planner.chat")
def test_make_plan_combines_outline_and_details(mock_chat):
    mock_chat.side_effect = [
        '```json\n[{"slide_no":1,"purpose":"open","head_message":"Hi"}]\n```',  # outline
        '```json\n{"slide_no":1,"purpose":"open","head_message":"Hi","layout_hint":"Cover","content":{}}\n```',  # detail
    ]
    plan = make_plan({"meta": {"title": "T"}, "sections": []})
    assert "deck_meta" in plan
    assert len(plan["slides"]) == 1
    assert plan["slides"][0]["layout_hint"] == "Cover"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pipeline/test_planner.py -v`
Expected: 3 new tests FAIL with `ImportError`.

- [ ] **Step 4: Implement Phase 2-2 + deck_meta + make_plan**

Append to `<root>/src/pipeline/planner.py`:

```python
from src.pipeline.guideline_loader import get_pattern_summary_cards


_DEFAULT_THEME = {
    "primary": "#065A82",
    "accent": "#21295C",
    "neutral": "#F2F2F2",
    "text_dark": "#1C2833",
    "text_light": "#FFFFFF",
}

_DEFAULT_FONTS = {
    "header": "Pretendard Bold",
    "body": "Pretendard",
}


def derive_deck_meta(content: dict) -> dict:
    return {
        "title": content.get("meta", {}).get("title", ""),
        "theme": dict(_DEFAULT_THEME),
        "fonts": dict(_DEFAULT_FONTS),
        "slide_size": {"width_in": 13.333, "height_in": 7.5},
    }


def _section_facts_for(content: dict, slide_no: int) -> list[str]:
    # MVP: return all raw_facts from all sections. Later we can map by topic.
    facts: list[str] = []
    for sec in content.get("sections", []):
        facts.extend(sec.get("raw_facts", []))
    return facts


def generate_slide_detail(
    outline: dict,
    section_facts: list[str],
    *,
    model: str = "gemma4:e4b",
) -> dict:
    template = (PROMPTS_DIR / "slide_detail.txt").read_text(encoding="utf-8")
    cards = "\n".join(f"- {c}" for c in get_pattern_summary_cards())
    prompt = template.format(
        pattern_cards=cards,
        slide_no=outline["slide_no"],
        purpose=outline["purpose"],
        head_message=outline["head_message"],
        section_facts="\n".join(f"- {f}" for f in section_facts),
    )
    response = chat(prompt, model=model)
    parsed = parse_json_block(response)
    if not isinstance(parsed, dict):
        raise ValueError("expected JSON object for slide detail")
    for required in ("slide_no", "purpose", "head_message", "layout_hint", "content"):
        if required not in parsed:
            raise ValueError(f"slide detail missing key: {required}")
    return parsed


def make_plan(content: dict, *, model: str = "gemma4:e4b") -> dict:
    outline = generate_outline(content, model=model)
    slides: list[dict] = []
    for o in outline:
        facts = _section_facts_for(content, o["slide_no"])
        detail = generate_slide_detail(o, facts, model=model)
        slides.append(detail)
    return {
        "deck_meta": derive_deck_meta(content),
        "slides": slides,
    }
```

- [ ] **Step 5: Run tests**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pipeline/test_planner.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add prompts/slide_detail.txt src/pipeline/planner.py tests/pipeline/test_planner.py
git commit -m "feat(planner): add Phase 2-2 slide detail and make_plan orchestrator"
```

---

## Task 16: Builder — orchestrator that wires planner + code_generator + code_runner + merger

**Files:**
- Create: `src/pipeline/builder.py`
- Create: `tests/pipeline/test_builder.py`

- [ ] **Step 1: Write failing tests using fakes**

Create `tests/pipeline/test_builder.py`:

```python
from pathlib import Path
from unittest.mock import patch

from pptx import Presentation

from src.pipeline.builder import build_presentation


HAPPY_CODE = '''
from pptx import Presentation
from pptx.util import Inches
import json, sys

def add_slide(prs, data):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(1))
    box.text_frame.text = data["head_message"]

if __name__ == "__main__":
    data = json.loads(sys.stdin.read())
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    add_slide(prs, data)
    prs.save(sys.argv[1])
'''


@patch("src.pipeline.builder.make_plan")
@patch("src.pipeline.builder.generate_slide_code")
def test_build_presentation_end_to_end(mock_codegen, mock_plan, tmp_path):
    mock_plan.return_value = {
        "deck_meta": {"title": "T", "theme": {"primary": "#065A82"}, "fonts": {}, "slide_size": {"width_in": 13.333, "height_in": 7.5}},
        "slides": [
            {"slide_no": 1, "purpose": "open", "head_message": "First", "layout_hint": "Cover", "content": {}},
            {"slide_no": 2, "purpose": "main", "head_message": "Second", "layout_hint": "Bullet List", "content": {}},
        ],
    }
    mock_codegen.return_value = HAPPY_CODE

    content = {"meta": {"title": "T"}, "sections": []}
    out = tmp_path / "deck.pptx"
    workdir = tmp_path / "work"

    build_presentation(content, output_path=out, workdir=workdir)

    assert out.exists()
    prs = Presentation(out)
    assert len(prs.slides) == 2
    # plan.json should be persisted in workdir for debugging
    assert (workdir / "plan.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pipeline/test_builder.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement builder**

Create `<root>/src/pipeline/builder.py`:

```python
"""End-to-end orchestrator: content.json -> output.pptx."""
from __future__ import annotations

import json
from pathlib import Path

from src.pipeline.planner import make_plan
from src.pipeline.code_generator import generate_slide_code
from src.pipeline.guideline_loader import get_pattern_section
from src.pptx.code_runner import render_slide_with_retry
from src.pptx.merger import merge_slides


def _fix_callback_factory(layout_hint: str, slide_data: dict):
    pattern_guideline = get_pattern_section(layout_hint)

    def fix(original_code: str, traceback: str, _slide_data: dict) -> str:
        # Re-prompt with traceback context to regenerate full code
        from src.pipeline.code_generator import build_codegen_prompt
        from src.llm.ollama_client import chat
        from src.pipeline.code_generator import extract_code_block

        base = build_codegen_prompt(
            layout_hint=layout_hint,
            pattern_guideline=pattern_guideline,
            slide_data=slide_data,
        )
        prompt = (
            base
            + "\n\nThe previous code failed with this error. Regenerate the FULL script (no partial patches):\n"
            + traceback
            + "\n\nPrevious code:\n```python\n"
            + original_code
            + "\n```\n"
        )
        return extract_code_block(chat(prompt))

    return fix


def build_presentation(
    content: dict,
    *,
    output_path: Path,
    workdir: Path,
) -> Path:
    output_path = Path(output_path)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    slides_dir = workdir / "slides"
    slides_dir.mkdir(exist_ok=True)

    plan = make_plan(content)
    (workdir / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    slide_paths: list[Path] = []
    for slide_plan in plan["slides"]:
        layout_hint = slide_plan["layout_hint"]
        pattern_guideline = get_pattern_section(layout_hint)
        slide_data = {**slide_plan, "deck_meta": plan["deck_meta"]}
        code = generate_slide_code(
            layout_hint=layout_hint,
            pattern_guideline=pattern_guideline,
            slide_data=slide_data,
        )
        out = slides_dir / f"slide_{slide_plan['slide_no']:02d}.pptx"
        render_slide_with_retry(
            code,
            slide_data,
            out,
            fix_callback=_fix_callback_factory(layout_hint, slide_data),
            max_retries=3,
        )
        slide_paths.append(out)

    return merge_slides(slide_paths, output_path)
```

- [ ] **Step 4: Run tests**

Run: `PYTHONIOENCODING=utf-8 pytest tests/pipeline/test_builder.py -v`
Expected: 1 passed.

- [ ] **Step 5: Run full unit suite to verify nothing regressed**

Run: `PYTHONIOENCODING=utf-8 pytest -v --ignore=tests/test_ollama.py`
Expected: all tests pass (Ollama-live test excluded).

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/builder.py tests/pipeline/test_builder.py
git commit -m "feat(builder): orchestrate plan -> codegen -> render -> merge"
```

---

## Task 17: Sample content + live E2E smoke test

**Files:**
- Create: `data/sample_content.json`
- Create: `tests/test_e2e_live.py`
- Create: `scripts/run_pipeline.py`

- [ ] **Step 1: Author a small sample content**

Create `<root>/data/sample_content.json`:

```json
{
  "meta": {
    "title": "CoWork PPTX 파이프라인 데모",
    "audience": "개발팀",
    "tone": "데이터 중심, 결론부터",
    "duration_min": 5,
    "language": "ko"
  },
  "sections": [
    {
      "id": "s1",
      "topic": "배경",
      "raw_facts": [
        "Ollama gemma4:e4b 로컬 모델 활용",
        "JSON 입력 → PPTX 자동 생성"
      ]
    },
    {
      "id": "s2",
      "topic": "구성",
      "raw_facts": [
        "Layer 1: primitives (add_text, add_rect 등)",
        "Layer 2: design guideline (33 패턴)",
        "Layer 3: Gemma가 코드 직접 생성"
      ]
    },
    {
      "id": "s3",
      "topic": "결과",
      "raw_facts": [
        "슬라이드별 독립 생성 후 머지",
        "에러 시 최대 3회 재시도"
      ]
    }
  ]
}
```

- [ ] **Step 2: Write a runner script**

Create `<root>/scripts/run_pipeline.py`:

```python
"""Run the full pipeline against data/sample_content.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make src importable when run from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.builder import build_presentation


def main():
    root = Path(__file__).resolve().parents[1]
    content_path = root / "data" / "sample_content.json"
    output_path = root / "output" / "demo.pptx"
    workdir = root / "output" / "work"

    content = json.loads(content_path.read_text(encoding="utf-8"))
    out = build_presentation(content, output_path=output_path, workdir=workdir)
    print(f"OK → {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write live smoke test (marked `live`)**

Create `<root>/tests/test_e2e_live.py`:

```python
"""End-to-end test that hits real Ollama. Run with: pytest -m live"""
from pathlib import Path
import json

import pytest
from pptx import Presentation

from src.llm.ollama_client import is_available
from src.pipeline.builder import build_presentation


pytestmark = pytest.mark.live


@pytest.fixture
def sample_content():
    root = Path(__file__).resolve().parents[1]
    return json.loads((root / "data" / "sample_content.json").read_text(encoding="utf-8"))


def test_e2e_pipeline_produces_pptx(sample_content, tmp_path):
    if not is_available():
        pytest.skip("Ollama server not running")
    out = tmp_path / "demo.pptx"
    workdir = tmp_path / "work"
    build_presentation(sample_content, output_path=out, workdir=workdir)
    assert out.exists()
    prs = Presentation(out)
    assert len(prs.slides) >= 2
    # plan.json must be saved
    plan = json.loads((workdir / "plan.json").read_text(encoding="utf-8"))
    assert "slides" in plan
    assert len(plan["slides"]) == len(prs.slides)
```

- [ ] **Step 4: Run only non-live tests to confirm no regressions**

Run: `PYTHONIOENCODING=utf-8 pytest -m "not live" -v`
Expected: all unit tests pass.

- [ ] **Step 5: Run the live test (Ollama must be running)**

Run: `PYTHONIOENCODING=utf-8 pytest -m live -v`

Expected: 1 passed if Ollama is running and Gemma generates valid code (may take 1–5 minutes). If it fails, examine `output/work/plan.json` and `output/work/slides/*.pptx` plus stderr from `code_runner` for the failing slide.

- [ ] **Step 6: Run the script manually to inspect output**

Run: `PYTHONIOENCODING=utf-8 python scripts/run_pipeline.py`

Expected: prints `OK → ...\output\demo.pptx`. Open the file in PowerPoint or LibreOffice and visually verify:
- Slide count matches plan.json
- Each slide has a non-empty headline
- No content goes off-slide

- [ ] **Step 7: Commit**

```bash
git add data/sample_content.json scripts/run_pipeline.py tests/test_e2e_live.py
git commit -m "feat(e2e): add sample content, runner script, and live smoke test"
```

---

## Task 18: README — quick start

**Files:**
- Create: `README.md`

- [ ] **Step 1: Author README**

Create `<root>/README.md`:

````markdown
# CoWork — Gemma → PPTX

Local-LLM-driven PowerPoint generator. Takes a `content.json`, plans the deck with
Ollama (gemma4:e4b), generates python-pptx code per slide, executes each in an
isolated subprocess, and merges into a single `.pptx`.

See `docs/superpowers/specs/2026-05-02-gemma-pptx-pipeline-design.md` for the design.

## Setup

```bash
pip install -r requirements.txt
ollama pull gemma4:e4b   # one-time
ollama serve             # in another terminal
```

## Run

```bash
PYTHONIOENCODING=utf-8 python scripts/run_pipeline.py
# → output/demo.pptx
```

## Tests

```bash
# unit only (fast, no LLM)
PYTHONIOENCODING=utf-8 pytest -m "not live"

# end-to-end with Ollama (slow)
PYTHONIOENCODING=utf-8 pytest -m live
```

## Layout

```
src/
  llm/ollama_client.py
  pptx/
    primitives.py     # Layer 1 — add_text/add_rect/add_line/add_arrow/add_image/set_bg
    code_runner.py    # subprocess execution + retry
    merger.py         # XML-level slide copy
  pipeline/
    planner.py        # content.json -> plan.json (Phase 2-1, 2-2)
    code_generator.py # plan -> python-pptx code via LLM
    guideline_loader.py
    builder.py        # orchestrator
guidelines/
  primitives_api.md   # API reference (LLM-readable)
  design_guideline.md # 33 patterns across 8 categories
prompts/
  story_outline.txt
  slide_detail.txt
  code_generation.txt
data/
  sample_content.json
```

## Troubleshooting

- **UnicodeEncodeError on Windows**: always set `PYTHONIOENCODING=utf-8`.
- **Slide rendering fails after 3 retries**: inspect `output/work/slides/` and stderr; the LLM may need a smaller layout hint or simpler content. Reduce slide count or use a richer model.
- **Pretendard font missing**: change `_DEFAULT_FONTS` in `src/pipeline/planner.py` to `Malgun Gothic` (Windows) or another installed Korean font.
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup, run, and troubleshooting"
```

---

## Final verification

- [ ] **Run the full unit test suite once more**

Run: `PYTHONIOENCODING=utf-8 pytest -m "not live" -v`
Expected: every test passes.

- [ ] **Open the live-generated demo.pptx**

If Ollama is running and the live test passes, manually open `output/demo.pptx` in PowerPoint or LibreOffice and confirm:
- Cover slide reads naturally
- Each slide's head_message matches its visual emphasis
- No content is clipped at slide edges
- Color/font are consistent across slides

If issues are found, they belong to the next iteration (Stage 5/6 critique loops in the spec) — out of scope for this MVP plan.
