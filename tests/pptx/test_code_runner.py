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
        assert "boom" in str(e) or "RuntimeError" in str(e) or "boom" in e.stderr or "RuntimeError" in e.stderr
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
