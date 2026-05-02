from pathlib import Path
from unittest.mock import patch

from src.pipeline.visual_critic import (
    conversion_tools_available,
    pptx_to_image,
    critique_slide_visual,
)


def test_conversion_tools_available_returns_bool():
    result = conversion_tools_available()
    assert isinstance(result, bool)


@patch("src.pipeline.visual_critic.conversion_tools_available", return_value=False)
def test_pptx_to_image_returns_none_when_tools_missing(mock_avail, tmp_path):
    fake_pptx = tmp_path / "x.pptx"
    fake_pptx.write_bytes(b"PK")
    assert pptx_to_image(fake_pptx, tmp_path / "img") is None


@patch("src.pipeline.visual_critic.conversion_tools_available", return_value=False)
def test_critique_slide_visual_skips_when_tools_missing(mock_avail, tmp_path):
    fake_pptx = tmp_path / "x.pptx"
    fake_pptx.write_bytes(b"PK")
    result = critique_slide_visual(fake_pptx)
    assert result["verdict"] == "SKIP"
    assert result["issues"] == []
    assert "reason" in result


@patch("src.pipeline.visual_critic.chat_with_image")
@patch("src.pipeline.visual_critic.pptx_to_image")
def test_critique_slide_visual_pass(mock_convert, mock_vision, tmp_path):
    fake_image = tmp_path / "fake.jpg"
    fake_image.write_bytes(b"jpegfake")
    mock_convert.return_value = fake_image
    mock_vision.return_value = '''```json
{"issues": [], "verdict": "PASS"}
```'''
    fake_pptx = tmp_path / "s.pptx"
    fake_pptx.write_bytes(b"PK")
    result = critique_slide_visual(fake_pptx)
    assert result["verdict"] == "PASS"


@patch("src.pipeline.visual_critic.chat_with_image")
@patch("src.pipeline.visual_critic.pptx_to_image")
def test_critique_slide_visual_fix(mock_convert, mock_vision, tmp_path):
    fake_image = tmp_path / "fake.jpg"
    fake_image.write_bytes(b"jpegfake")
    mock_convert.return_value = fake_image
    mock_vision.return_value = '''```json
{"issues": [{"severity":"high","msg":"text overflow"}], "verdict": "FIX"}
```'''
    fake_pptx = tmp_path / "s.pptx"
    fake_pptx.write_bytes(b"PK")
    result = critique_slide_visual(fake_pptx)
    assert result["verdict"] == "FIX"
    assert "overflow" in result["issues"][0]["msg"]
