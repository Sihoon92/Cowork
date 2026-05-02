from src.pipeline.guideline_loader import (
    load_pattern_index,
    get_pattern_section,
    get_pattern_summary_cards,
    resolve_pattern,
)


def test_load_pattern_index_returns_known_patterns():
    idx = load_pattern_index()
    assert "Cover" in idx
    assert "Bullet List" in idx
    assert "Stat 강조" in idx
    assert "Matrix 비교" in idx


def test_get_pattern_section_returns_three_subsections():
    section = get_pattern_section("Cover")
    assert "언제" in section
    assert "구성" in section
    assert "주의" in section


def test_get_pattern_section_unknown_raises():
    try:
        get_pattern_section("DOES_NOT_EXIST")
    except KeyError:
        return
    raise AssertionError("expected KeyError")


def test_summary_cards_one_line_per_pattern():
    cards = get_pattern_summary_cards()
    assert len(cards) >= 9
    assert all("\n" not in c or c.count("\n") <= 1 for c in cards)
    assert any(c.startswith("Cover") for c in cards)


def test_resolve_pattern_with_parenthetical():
    assert resolve_pattern("Cover (표지)") == "Cover"


def test_resolve_pattern_case_insensitive():
    assert resolve_pattern("cover") == "Cover"


def test_resolve_pattern_with_whitespace():
    assert resolve_pattern("  Stat 강조  ") == "Stat 강조"


def test_resolve_pattern_unknown_returns_none():
    assert resolve_pattern("DOES_NOT_EXIST") is None
