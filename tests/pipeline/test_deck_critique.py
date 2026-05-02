from pathlib import Path
from unittest.mock import patch

from src.pipeline.critic import (
    critique_deck_storyline,
    critique_deck_visual,
    make_thumbnail_grid,
)


SAMPLE_PLAN = {
    "deck_meta": {},
    "slides": [
        {"slide_no": 1, "head_message": "프로젝트 시작", "layout_hint": "Cover"},
        {"slide_no": 2, "head_message": "핵심 결과 3가지", "layout_hint": "Bullet List"},
        {"slide_no": 3, "head_message": "다음 단계", "layout_hint": "Bullet List"},
    ],
}


@patch("src.pipeline.critic.chat")
def test_critique_deck_storyline_pass(mock_chat):
    mock_chat.return_value = '''```json
{"issues": [], "verdict": "PASS"}
```'''
    result = critique_deck_storyline(SAMPLE_PLAN)
    assert result["verdict"] == "PASS"
    # Verify the prompt contained the head_messages
    sent_prompt = mock_chat.call_args[0][0]
    assert "프로젝트 시작" in sent_prompt
    assert "다음 단계" in sent_prompt


@patch("src.pipeline.critic.chat")
def test_critique_deck_storyline_fix(mock_chat):
    mock_chat.return_value = '''```json
{"issues": [{"slide_no":2,"msg":"non-sequitur"}], "verdict": "FIX"}
```'''
    result = critique_deck_storyline(SAMPLE_PLAN)
    assert result["verdict"] == "FIX"
    assert result["issues"][0]["slide_no"] == 2


@patch("src.pipeline.critic.conversion_tools_available", return_value=False)
def test_critique_deck_visual_skips_when_tools_missing(mock_tools, tmp_path):
    paths = [tmp_path / "a.pptx", tmp_path / "b.pptx"]
    for p in paths:
        p.write_bytes(b"PK")
    result = critique_deck_visual(paths)
    assert result["verdict"] == "SKIP"


@patch("src.pipeline.critic.chat_with_image")
@patch("src.pipeline.critic.make_thumbnail_grid")
def test_critique_deck_visual_pass(mock_grid, mock_vision, tmp_path):
    fake_grid = tmp_path / "grid.jpg"
    fake_grid.write_bytes(b"jpeg")
    mock_grid.return_value = fake_grid
    mock_vision.return_value = '''```json
{"issues": [], "verdict": "PASS"}
```'''
    result = critique_deck_visual([tmp_path / "a.pptx"])
    assert result["verdict"] == "PASS"


@patch("src.pipeline.critic.conversion_tools_available", return_value=False)
def test_make_thumbnail_grid_returns_none_when_tools_missing(mock_tools, tmp_path):
    out = tmp_path / "grid.jpg"
    result = make_thumbnail_grid([tmp_path / "a.pptx"], out)
    assert result is None
