from pathlib import Path
import subprocess
import sys
import textwrap

PREAMBLE_PATH = Path(__file__).resolve().parents[2] / "guidelines" / "v2" / "preamble.py"


def test_preamble_imports_clean(tmp_path: Path):
    """The preamble must execute on its own without errors."""
    out = tmp_path / "x.py"
    out.write_text(PREAMBLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(out)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_patch_shapes_casts_floats(tmp_path: Path):
    code = PREAMBLE_PATH.read_text(encoding="utf-8") + textwrap.dedent("""
        prs = Presentation()
        prs.slide_width = SLIDE_W
        prs.slide_height = SLIDE_H
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        _patch_shapes(slide)
        # All four positional args are floats — the patch must cast them.
        slide.shapes.add_textbox(Inches(1.0).emu * 1.0,
                                 Inches(1.0).emu * 1.0,
                                 Inches(2.0).emu * 1.0,
                                 Inches(1.0).emu * 1.0)
        out = r"{out_pptx}"
        prs.save(out)
    """)
    pptx = tmp_path / "out.pptx"
    script = tmp_path / "run.py"
    script.write_text(code.replace("{out_pptx}", str(pptx)), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(script)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert pptx.exists() and pptx.stat().st_size > 0
