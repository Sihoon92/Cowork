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
