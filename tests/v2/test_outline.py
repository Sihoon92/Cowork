import json
import pytest

from src.pipeline_v2.outline import generate_outline


pytestmark = pytest.mark.live


def test_outline_smoke():
    content = {
        "meta": {"title": "AI in 2026"},
        "sections": [
            {"heading": "Today", "body": "GPT-class models everywhere."},
            {"heading": "Action", "body": "Pilot, measure, expand."},
        ],
    }
    out = generate_outline(content)
    assert out["slides"][0]["kind"] == "title"
    assert out["slides"][-1]["kind"] == "closing"
    bodies = [s for s in out["slides"] if s["kind"] == "body"]
    assert len(bodies) >= 2
    for s in bodies:
        assert s["content_structure"] in {
            "comparison","process","hierarchy","matrix","metric",
            "narrative","enumeration","timeline","system","other",
        }
