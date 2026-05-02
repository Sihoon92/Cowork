from unittest.mock import patch

from src.pipeline.critic import (
    critique_plan,
    apply_patches,
    revise_plan_until_pass,
)


SAMPLE_PLAN = {
    "deck_meta": {"title": "T", "theme": {"primary": "#000"}, "fonts": {}, "slide_size": {"width_in": 13.333, "height_in": 7.5}},
    "slides": [
        {"slide_no": 1, "purpose": "open", "head_message": "Hi", "layout_hint": "Cover", "content": {}},
        {"slide_no": 2, "purpose": "main", "head_message": "현황에 대해", "layout_hint": "Bullet List", "content": {}},
    ],
}


@patch("src.pipeline.critic.chat")
def test_critique_plan_parses_scores_and_verdict(mock_chat):
    mock_chat.return_value = '''```json
{
  "scores": {"story_flow": 5, "message_strength": 5, "content_balance": 5, "viz_fitness": 5, "layout_diversity": 5},
  "issues": [],
  "patches": [],
  "verdict": "PASS"
}
```'''
    result = critique_plan(SAMPLE_PLAN)
    assert result["verdict"] == "PASS"
    assert result["scores"]["story_flow"] == 5
    assert result["patches"] == []


def test_apply_patches_updates_head_message():
    plan = {
        "deck_meta": {},
        "slides": [
            {"slide_no": 1, "head_message": "old", "layout_hint": "Cover", "purpose": "p", "content": {}},
            {"slide_no": 2, "head_message": "old2", "layout_hint": "Bullet List", "purpose": "p", "content": {}},
        ],
    }
    patches = [
        {"slide_no": 2, "field": "head_message", "new_value": "신규 결론 메시지"},
    ]
    out = apply_patches(plan, patches)
    assert out["slides"][1]["head_message"] == "신규 결론 메시지"
    # Slide 1 untouched
    assert out["slides"][0]["head_message"] == "old"
    # Original plan not mutated
    assert plan["slides"][1]["head_message"] == "old2"


def test_apply_patches_unknown_slide_no_is_skipped():
    plan = {"deck_meta": {}, "slides": [{"slide_no": 1, "head_message": "x", "layout_hint": "Cover", "purpose": "p", "content": {}}]}
    patches = [{"slide_no": 99, "field": "head_message", "new_value": "y"}]
    out = apply_patches(plan, patches)
    assert out["slides"][0]["head_message"] == "x"  # no change


@patch("src.pipeline.critic.chat")
def test_revise_loop_stops_on_pass(mock_chat):
    mock_chat.return_value = '''```json
{"scores": {"story_flow":5,"message_strength":5,"content_balance":5,"viz_fitness":5,"layout_diversity":5},
 "issues": [], "patches": [], "verdict": "PASS"}
```'''
    out = revise_plan_until_pass(SAMPLE_PLAN, max_rounds=3)
    assert mock_chat.call_count == 1
    assert out == SAMPLE_PLAN  # no patches applied


@patch("src.pipeline.critic.chat")
def test_revise_loop_applies_patches_then_passes(mock_chat):
    mock_chat.side_effect = [
        '''```json
{"scores": {"story_flow":3,"message_strength":3,"content_balance":5,"viz_fitness":5,"layout_diversity":5},
 "issues": [{"slide_no":2,"axis":"message_strength","msg":"weak"}],
 "patches": [{"slide_no":2,"field":"head_message","new_value":"개선됨"}],
 "verdict": "REVISE"}
```''',
        '''```json
{"scores": {"story_flow":5,"message_strength":5,"content_balance":5,"viz_fitness":5,"layout_diversity":5},
 "issues": [], "patches": [], "verdict": "PASS"}
```''',
    ]
    out = revise_plan_until_pass(SAMPLE_PLAN, max_rounds=3)
    assert mock_chat.call_count == 2
    assert out["slides"][1]["head_message"] == "개선됨"


@patch("src.pipeline.critic.chat")
def test_revise_loop_gives_up_after_max(mock_chat):
    mock_chat.return_value = '''```json
{"scores": {"story_flow":2,"message_strength":2,"content_balance":2,"viz_fitness":2,"layout_diversity":2},
 "issues": [{"slide_no":1,"axis":"story_flow","msg":"bad"}],
 "patches": [{"slide_no":1,"field":"head_message","new_value":"x"}],
 "verdict": "REVISE"}
```'''
    out = revise_plan_until_pass(SAMPLE_PLAN, max_rounds=2)
    # max_rounds means total critique calls: 2 calls total
    assert mock_chat.call_count == 2
    # Last patches still applied even though verdict is REVISE
    assert out["slides"][0]["head_message"] == "x"
