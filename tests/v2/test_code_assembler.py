from pathlib import Path

from src.pipeline_v2.code_assembler import assemble_slide_module


def test_assemble_includes_preamble_body_footer(tmp_path: Path):
    body = "def build_slide(prs):\n    slide = prs.slides[0]\n    pass\n"
    out_pptx = tmp_path / "out.pptx"
    code = assemble_slide_module(body, out_pptx)
    assert "from pptx import Presentation" in code      # preamble
    assert "def build_slide(prs):" in code              # body
    assert "_patch_shapes(slide)" in code               # footer
    assert str(out_pptx) in code                        # footer save path


def test_assemble_strips_main_block_in_body(tmp_path: Path):
    body = (
        "def build_slide(prs):\n    pass\n\n"
        "if __name__ == '__main__':\n    print('ignore')\n"
    )
    code = assemble_slide_module(body, tmp_path / "x.pptx")
    # The LLM's __main__ block is preserved as-is; our footer comes after.
    # Verify the footer is the LAST __main__ block.
    assert code.rstrip().endswith("prs.save(_OUT_PATH)")
