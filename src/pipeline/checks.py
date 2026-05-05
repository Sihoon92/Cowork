"""Deterministic checks for slide content — no LLM, no I/O.

These functions catch the failures pydantic can't (semantic shape) and the
LLM self-review can't justify spending tokens on (form-only). Code that LLM
keeps tripping over → moved here.

Used by:
  - planner Stage 3 to decide if a content output passes
  - self-review prompt to anchor "you already know X is broken" feedback
"""
from __future__ import annotations

import re
from typing import Iterable

from src.pipeline.schemas import SlideContent, SoWhatQA


# ---------------------------------------------------------------------------
# Line-fit estimation
# ---------------------------------------------------------------------------

# Per-character width estimates @ 18pt Pretendard, in inches.
# Korean glyphs are roughly square; ASCII letters are narrower.
# These are CONSERVATIVE (over-estimating) so we err toward "doesn't fit"
# and ask the LLM to shorten.
_KO_CHAR_W_18PT = 0.20
_EN_CHAR_W_18PT = 0.115
_DIGIT_W_18PT = 0.13
_PUNCT_W_18PT = 0.10
_SPACE_W_18PT = 0.07


def _char_width(ch: str, font_size: float) -> float:
    """Estimate character width at given font size (18pt baseline)."""
    scale = font_size / 18.0
    if ch == " ":
        return _SPACE_W_18PT * scale
    if ch.isdigit():
        return _DIGIT_W_18PT * scale
    if ch.isalpha() and ord(ch) < 128:
        return _EN_CHAR_W_18PT * scale
    if ch in ".,;:!?-—–·":
        return _PUNCT_W_18PT * scale
    # CJK / fallback
    return _KO_CHAR_W_18PT * scale


def estimated_line_count(text: str, *, font_size: float = 18, width_in: float = 12.13) -> int:
    """Estimate how many display lines `text` will wrap to in a textbox of
    `width_in` inches at `font_size` pt.

    Greedy word-break simulation. CJK has no word boundaries so we break at
    any character. Returns >=1.
    """
    if not text:
        return 1
    cur_w = 0.0
    lines = 1
    for ch in text:
        w = _char_width(ch, font_size)
        if cur_w + w > width_in:
            lines += 1
            cur_w = w
        else:
            cur_w += w
    return lines


# ---------------------------------------------------------------------------
# Question-form detection
# ---------------------------------------------------------------------------

_QUESTION_TAILS = ("?", "까", "는가", "할까", "일까", "인가", "있을까", "는지", "을지", "ㄹ까")


def is_question(text: str) -> bool:
    """Korean/English question detection via terminal pattern."""
    s = text.strip()
    if not s:
        return False
    return any(s.endswith(t) for t in _QUESTION_TAILS)


# ---------------------------------------------------------------------------
# Title / message duplication
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[\s\.,!?·—–\-:;]+")


def _normalize(text: str) -> str:
    return _PUNCT_RE.sub("", text.strip().lower())


def same_as_section_title(head: str, section_title: str) -> bool:
    """True if head_message is essentially identical to the section title."""
    if not head or not section_title:
        return False
    return _normalize(head) == _normalize(section_title)


# ---------------------------------------------------------------------------
# Bigram Jaccard overlap (cheap "similar meaning" approximation)
# ---------------------------------------------------------------------------

def _tokens(text: str) -> list[str]:
    """Char-bigrams for CJK-friendly overlap. Strips punctuation/spaces first."""
    s = _normalize(text)
    if len(s) < 2:
        return [s] if s else []
    return [s[i:i + 2] for i in range(len(s) - 1)]


def jaccard_overlap(text_a: str, text_b: str) -> float:
    """Char-bigram Jaccard similarity in [0, 1]. 0.7+ = very similar."""
    a = set(_tokens(text_a))
    b = set(_tokens(text_b))
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# Metric / trend format checks
# ---------------------------------------------------------------------------

def metric_label_valid(label: str) -> bool:
    """≤25자 + 의문형 아님 + 비어있지 않음."""
    if not label or not label.strip():
        return False
    s = label.strip()
    if len(s) > 25:
        return False
    if is_question(s):
        return False
    return True


_TREND_DIRECTION_RE = re.compile(
    r"[+\-]|증가|감소|역대|최|상승|하락|확대|축소|개선|악화|YoY|MoM"
)


def trend_has_direction(trend: str | None) -> bool:
    """Trend 문자열에 부호·방향어가 들어있는지."""
    if not trend:
        return True   # 빈 trend는 OK (선택적 필드)
    return bool(_TREND_DIRECTION_RE.search(trend))


# ---------------------------------------------------------------------------
# Evidence sufficiency
# ---------------------------------------------------------------------------

def evidence_sufficient(so_what: Iterable[SoWhatQA]) -> tuple[bool, str]:
    """Return (ok, reason). NOT ok when WHY/HOW_MUCH both lack evidence —
    that's the slide-is-weak signal.

    If so_what is empty entirely (framing slides), this returns ok=True;
    callers must use the framing-intent skip in check_slide_content to
    avoid triggering the body-slide rule.
    """
    qa_list = list(so_what)
    if not qa_list:
        return True, ""    # framing slides legitimately have no so_what
    why_qa = [q for q in qa_list if q.type == "WHY"]
    hm_qa = [q for q in qa_list if q.type == "HOW_MUCH"]

    why_has_ev = any(q.evidence for q in why_qa)
    hm_has_ev = any(q.evidence for q in hm_qa)

    if why_qa and not why_has_ev:
        return False, "WHY 답변에 evidence가 비어있음 — 가장 약한 신호"
    if not why_has_ev and not hm_has_ev and (why_qa or hm_qa):
        return False, "WHY와 HOW_MUCH 모두 evidence가 비어있음 — 슬라이드 약체"
    return True, ""


# ---------------------------------------------------------------------------
# Aggregator — full slide content check
# ---------------------------------------------------------------------------

_FRAMING_INTENTS = {"deck_opening", "closing_thesis", "section_transition"}


def check_slide_content(
    content: SlideContent,
    *,
    section_title: str | None = None,
    head_max_lines: int = 1,
) -> list[tuple[str, str]]:
    """Run all deterministic checks. Return list of (issue_code, message).

    Framing intents (deck_opening / closing_thesis / section_transition) skip
    the takeaway-dup, metric format, and so_what evidence checks because they
    legitimately have minimal/empty content beyond head_message.
    """
    issues: list[tuple[str, str]] = []
    is_framing = content.intent_label in _FRAMING_INTENTS

    head = content.head_message

    # Head: line fit (always)
    if estimated_line_count(head) > head_max_lines:
        issues.append((
            "head_too_long",
            f"head_message가 {head_max_lines}줄 초과 — 짧게 다시 쓰라"
        ))

    # Head: question form (always)
    if is_question(head):
        issues.append(("head_is_question", "head_message가 의문형 — 결론으로 다시 쓰라"))

    # Head: section title duplication (always)
    if section_title and same_as_section_title(head, section_title):
        issues.append((
            "head_duplicates_section",
            f"head_message가 section_title({section_title!r})과 동일"
        ))

    if is_framing:
        # Framing slides skip the rest — no takeaway/metric/so_what required
        return issues

    # Body slide checks below

    # Head ↔ key_takeaway 중복
    if content.key_takeaway and jaccard_overlap(head, content.key_takeaway) > 0.7:
        issues.append((
            "takeaway_duplicates_head",
            "key_takeaway가 head_message와 너무 비슷 — 다른 의미층으로 다시 쓰라"
        ))

    # Metrics format
    for i, m in enumerate(content.knowledge.metrics):
        if not metric_label_valid(m.label):
            issues.append((
                f"metric[{i}].label_invalid",
                f"metric[{i}].label 부적합 (≤25자, 의문형 아님, 비어있지 않음): {m.label!r}"
            ))
        if m.trend and not trend_has_direction(m.trend):
            issues.append((
                f"metric[{i}].trend_no_direction",
                f"metric[{i}].trend에 부호·방향어 없음: {m.trend!r}"
            ))

    # so_what evidence
    ok, reason = evidence_sufficient(content.so_what)
    if not ok:
        issues.append(("so_what_weak_evidence", reason))

    return issues
