from pathlib import Path
from src.pipeline_v2.prompts import load_prompt


def test_load_prompt_substitutes(tmp_path: Path, monkeypatch):
    prompts = tmp_path / "prompts" / "v2"
    prompts.mkdir(parents=True)
    (prompts / "demo.md").write_text("Hello {name}!", encoding="utf-8")
    monkeypatch.setattr("src.pipeline_v2.prompts.PROMPTS_DIR", prompts)
    out = load_prompt("demo", name="world")
    assert out == "Hello world!"


def test_load_prompt_missing_placeholder_raises(tmp_path: Path, monkeypatch):
    prompts = tmp_path / "prompts" / "v2"
    prompts.mkdir(parents=True)
    (prompts / "demo.md").write_text("Hi {name} {age}", encoding="utf-8")
    monkeypatch.setattr("src.pipeline_v2.prompts.PROMPTS_DIR", prompts)
    import pytest
    with pytest.raises(KeyError):
        load_prompt("demo", name="x")  # 'age' missing
