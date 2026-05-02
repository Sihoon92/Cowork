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
def test_outline_retries_on_invalid_json(mock_chat):
    mock_chat.side_effect = [
        "no json fence here",  # first call - bad
        '```json\n[{"slide_no":1,"purpose":"p","head_message":"H"}]\n```',  # second - good
    ]
    out = generate_outline({"meta": {"title": "T"}, "sections": []})
    assert len(out) == 1
    assert mock_chat.call_count == 2


@patch("src.pipeline.planner.chat")
def test_outline_gives_up_after_max_retries(mock_chat):
    mock_chat.return_value = "no fence ever"
    try:
        generate_outline({"meta": {"title": "T"}, "sections": []})
    except ValueError:
        # max_retries=2 means initial + 2 retries = 3 calls total
        assert mock_chat.call_count == 3
        return
    raise AssertionError("expected ValueError")


@patch("src.pipeline.planner.chat")
def test_make_plan_combines_outline_and_details(mock_chat):
    mock_chat.side_effect = [
        '```json\n[{"slide_no":1,"purpose":"open","head_message":"Hi","section_id":null}]\n```',  # outline with section_id
        '```json\n{"slide_no":1,"purpose":"open","head_message":"Hi","layout_hint":"Cover","content":{}}\n```',  # detail
    ]
    plan = make_plan({"meta": {"title": "T"}, "sections": []})
    assert "deck_meta" in plan
    assert len(plan["slides"]) == 1
    assert plan["slides"][0]["layout_hint"] == "Cover"
    assert plan["slides"][0].get("section_id") is None  # preserved from outline


def test_section_facts_for_returns_only_matching_section():
    from src.pipeline.planner import _section_facts_for
    content = {
        "sections": [
            {"id": "s1", "raw_facts": ["fact A", "fact B"]},
            {"id": "s2", "raw_facts": ["fact C"]},
        ]
    }
    assert _section_facts_for(content, "s1") == ["fact A", "fact B"]
    assert _section_facts_for(content, "s2") == ["fact C"]
    assert _section_facts_for(content, None) == []
    assert _section_facts_for(content, "missing") == []


@patch("src.pipeline.planner.chat")
def test_make_plan_preserves_section_id_through_detail(mock_chat):
    mock_chat.side_effect = [
        '```json\n[{"slide_no":2,"purpose":"data","head_message":"H","section_id":"s1"}]\n```',
        '```json\n{"slide_no":2,"purpose":"data","head_message":"H","layout_hint":"Bullet List","content":{"bullets":["fact A","fact B"]}}\n```',
    ]
    plan = make_plan({
        "meta": {"title": "T"},
        "sections": [{"id": "s1", "raw_facts": ["fact A", "fact B"]}],
    })
    assert plan["slides"][0]["section_id"] == "s1"
