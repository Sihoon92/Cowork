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
