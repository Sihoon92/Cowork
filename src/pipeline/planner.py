"""content.json -> plan.json via Ollama (Phases 2-1 and 2-2)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.llm.ollama_client import chat, DEFAULT_MODEL
from src.pipeline.checks import check_slide_content
from src.pipeline.recipes import RECIPES
from src.pipeline.schemas import (
    SlideContent, SlideOutline, SlidePlan, SlideRecipe,
)
from src.pipeline.selector import select_recipe
from src.util import log

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

_JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)


def _try_repair_json(text: str):
    """Best-effort lenient fixes for common LLM JSON glitches.

    Handles:
      - trailing commas before } or ]
      - control characters (newlines/tabs) inside string literals are best-effort:
        we leave those alone since they may be intentional
    """
    import re as _re
    # Drop trailing commas: , } -> }   , ] -> ]
    fixed = _re.sub(r",\s*([}\]])", r"\1", text)
    return json.loads(fixed)


def parse_json_block(response: str):
    """Extract JSON from a fenced block, or fall back to the longest balanced object/array."""
    m = _JSON_FENCE_RE.search(response)
    raw: str
    if m:
        raw = m.group(1)
    else:
        # Fallback: locate the first { or [ and consume to the matching close.
        # Helps when format=json returns bare JSON without markdown fences.
        for opener, closer in (("{", "}"), ("[", "]")):
            start = response.find(opener)
            if start == -1:
                continue
            depth = 0
            for i in range(start, len(response)):
                ch = response[i]
                if ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        raw = response[start: i + 1]
                        break
            else:
                continue
            break
        else:
            raise ValueError("no JSON object or array found in response")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return _try_repair_json(raw)


_RETRY_SUFFIX = (
    "\n\nYour previous response could not be parsed as JSON. "
    "Reply with ONLY a single JSON object (no fences, no prose)."
)


def _call_llm_with_json_retry(
    prompt: str, model: str, max_retries: int = 2,
    *, json_mode: bool = True,
):
    """Call chat() and parse JSON, retrying up to max_retries times on ValueError.

    `json_mode=True` requests Ollama's structured output (`format=json`), which
    constrains the decoder to syntactically valid JSON at generation time.
    """
    last_error: ValueError | None = None
    current_prompt = prompt
    fmt = "json" if json_mode else None
    for attempt in range(max_retries + 1):
        response = chat(current_prompt, model=model, format=fmt)
        try:
            return parse_json_block(response)
        except ValueError as exc:
            last_error = exc
            if attempt < max_retries:
                log.warn(f"JSON parse failed (attempt {attempt + 1}), retrying")
                current_prompt = prompt + _RETRY_SUFFIX
    raise last_error  # type: ignore[misc]


def _coerce_to_outline_list(parsed) -> list:
    """Best-effort to extract a list of slide outlines from LLM output.

    Handles three observed wrapper shapes from `format=json` mode:
      1. bare list:                     [{...}, {...}]
      2. named wrapper:                 {"slides": [...]} / {"outline": [...]}
      3. unknown wrapper with one list: {"foo": [...]}  (use the list)
      4. nested wrapper:                {"result": {"slides": [...]}}
    """
    if isinstance(parsed, list):
        return parsed
    if not isinstance(parsed, dict):
        raise ValueError(f"expected JSON array or wrapper object, got {type(parsed).__name__}")

    # Known keys first
    for key in ("slides", "outline", "data", "items", "result", "list", "plan"):
        v = parsed.get(key)
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            inner = _coerce_to_outline_list(v)
            if inner:
                return inner

    # Fallback: any value that is a list of dicts and looks slide-like
    for v in parsed.values():
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            return v

    # Single-slide dict at the top level is almost always a mistake (LLM
    # forgot the list wrapper). Reject and let the retry loop handle it —
    # accepting a single dict would silently truncate decks to 1 slide.
    raise ValueError(
        f"could not find an outline list in dict keys={list(parsed.keys())}"
    )


# Alt-key maps for outline normalization. LLMs (especially smaller ones) drift
# in field naming over long lists; we map common variants back to canonical keys.
_OUTLINE_KEY_ALIASES = {
    "slide_no":     ("slide_no", "slide_number", "number", "no", "index", "idx"),
    "head_message": ("head_message", "message", "head", "title", "headline",
                     "subtitle", "summary", "content", "text", "body",
                     "description", "label"),
    "purpose":      ("purpose", "role", "intent", "goal", "objective"),
    "section_id":   ("section_id", "section", "sec_id", "section_key"),
}


def _pick_alias(item: dict, canonical: str):
    """Return the first non-None value among the canonical key + its aliases."""
    for k in _OUTLINE_KEY_ALIASES[canonical]:
        if k in item and item[k] is not None:
            return item[k]
    return None


def _normalize_outline_items(items: list, valid_section_ids: set[str]) -> list[dict]:
    """Best-effort key normalization. Does NOT invent semantic content.

    - slide_no: backfill from aliases or array index (idx + 1).
    - head_message / purpose: surface the alias value if present, else leave absent.
    - section_id: surface alias; collapse to None if not in valid_section_ids.
    - Slide 0 (the first item, conventionally cover) is forced to section_id=None.
    """
    out: list[dict] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            # leave bad shape alone — pydantic will reject and trigger LLM retry
            out.append(item)
            continue

        normalized: dict = {}

        slide_no = _pick_alias(item, "slide_no")
        normalized["slide_no"] = slide_no if slide_no is not None else (idx + 1)

        head = _pick_alias(item, "head_message")
        if head is not None:
            normalized["head_message"] = head

        purpose = _pick_alias(item, "purpose")
        if purpose is not None:
            normalized["purpose"] = purpose

        if idx == 0:
            normalized["section_id"] = None
        else:
            sec = _pick_alias(item, "section_id")
            if sec is not None and str(sec).strip() in valid_section_ids:
                normalized["section_id"] = str(sec).strip()
            else:
                normalized["section_id"] = None

        out.append(normalized)
    return out


def _format_section_ids_block(content: dict) -> str:
    """Render the valid section_ids list for prompt injection."""
    lines: list[str] = []
    for sec in content.get("sections", []):
        sid = sec.get("id")
        topic = sec.get("topic") or sec.get("title") or ""
        if sid:
            lines.append(f"- `{sid}` — {topic}")
    if not lines:
        return "(no sections defined — every slide gets section_id=null)"
    return "\n".join(lines)


def _validate_outline_items(
    items: list, valid_section_ids: set[str]
) -> tuple[list[dict], list[str]]:
    """Validate each normalized outline item with SlideOutline.

    Returns (validated_dicts, error_strings). Errors are per-item, formatted
    so the LLM can fix specifically named items on retry.
    """
    from pydantic import ValidationError

    ok: list[dict] = []
    errors: list[str] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"item[{idx}] is not a JSON object")
            continue
        try:
            validated = SlideOutline.model_validate(item)
        except ValidationError as exc:
            label = item.get("slide_no", f"index {idx}")
            for err in exc.errors():
                loc = ".".join(str(p) for p in err.get("loc", ())) or "?"
                msg = err.get("msg", "invalid")
                errors.append(f"slide_no={label} field={loc}: {msg}")
            continue
        except Exception as exc:  # noqa: BLE001
            label = item.get("slide_no", f"index {idx}")
            errors.append(f"slide_no={label}: {exc}")
            continue
        ok.append(validated.model_dump())
    return ok, errors


def generate_outline(content: dict, *, model: str = DEFAULT_MODEL) -> list[dict]:
    log.step("LLM call: outline")
    template = (PROMPTS_DIR / "story_outline.md").read_text(encoding="utf-8")
    valid_section_ids: set[str] = {
        sec["id"] for sec in content.get("sections", []) if sec.get("id")
    }
    base_prompt = template.format(
        content_json=json.dumps(content, ensure_ascii=False, indent=2),
        section_ids_block=_format_section_ids_block(content),
    )

    n_sections = len(valid_section_ids)
    expected_min_slides = max(2, n_sections + 1)  # cover + one per section min

    last_err: str | None = None
    for attempt in range(3):
        prompt = base_prompt
        if last_err:
            prompt = (
                base_prompt
                + "\n\nYour previous attempt was rejected with these issues:\n"
                + last_err
                + f"\nFix every issue and reply ONLY with a JSON ARRAY of "
                + f"AT LEAST {expected_min_slides} slide objects "
                + f"(deck has {n_sections} sections + cover). "
                + "DO NOT return a single object — wrap multiple slides in []."
            )
        parsed = _call_llm_with_json_retry(prompt, model=model)

        # Stage 1: shape coercion (list vs wrapper dict)
        try:
            raw_items = _coerce_to_outline_list(parsed)
        except ValueError as exc:
            last_err = str(exc)
            log.warn(f"outline attempt {attempt + 1} shape invalid: {last_err}")
            continue

        # Stage 2: alias normalization (cheap, deterministic, no semantic invention)
        normalized = _normalize_outline_items(raw_items, valid_section_ids)

        # Stage 3a: outline must cover at least one slide per section + cover.
        # Accepting a deck shorter than n_sections would silently drop content.
        if len(normalized) < expected_min_slides:
            last_err = (
                f"outline has {len(normalized)} slide(s), expected at least "
                f"{expected_min_slides} (cover + {n_sections} sections). "
                f"Generate one or more slides per section."
            )
            log.warn(f"outline attempt {attempt + 1}: {last_err}; retrying")
            continue

        # Stage 3b: per-item pydantic validation
        validated, errors = _validate_outline_items(normalized, valid_section_ids)
        if errors:
            last_err = "\n".join(f"- {e}" for e in errors)
            log.warn(
                f"outline attempt {attempt + 1}: {len(errors)} item(s) invalid; retrying"
            )
            continue

        log.ok(f"got {len(validated)} slides in outline")
        return validated

    raise ValueError(f"outline invalid after retries:\n{last_err}")


_DEFAULT_THEME = {
    "background": "#FFFFFF",
    "head_text":  "#1C2833",
    "head_rule":  "#065A82",
    "body_text":  "#1C2833",
    "bullet":     "#065A82",
    "accent":     "#21295C",
    # Legacy aliases kept so older slide code still resolves while pipeline migrates.
    "primary":    "#065A82",
    "neutral":    "#F2F2F2",
    "text_dark":  "#1C2833",
    "text_light": "#FFFFFF",
}

_DEFAULT_FONTS = {
    "header": "Pretendard Bold",
    "body": "Pretendard",
}


def derive_deck_meta(content: dict) -> dict:
    section_titles: dict[str, str] = {}
    for sec in content.get("sections", []):
        sid = sec.get("id")
        if sid:
            section_titles[sid] = sec.get("topic") or sec.get("title") or ""
    return {
        "title": content.get("meta", {}).get("title", ""),
        "theme": dict(_DEFAULT_THEME),
        "fonts": dict(_DEFAULT_FONTS),
        "slide_size": {"width_in": 13.333, "height_in": 7.5},
        "section_titles": section_titles,
    }


def _section_facts_for(content: dict, section_id: str | None) -> list[str]:
    """Return raw_facts for the given section_id. Empty list if section_id is None or unknown."""
    if section_id is None:
        return []
    for sec in content.get("sections", []):
        if sec.get("id") == section_id:
            return list(sec.get("raw_facts", []))
    return []


_SECTION_DIVIDER_KEYWORDS = (
    "section", "chapter", "part ", "transition", "intro to",
    "다음", "전환", "섹션", "장",
)


def _slide_position(idx: int, total: int, outline: dict) -> str:
    """Classify a slide by its role: first / last / section_divider / middle."""
    if idx == 0:
        return "first"
    if idx == total - 1:
        return "last"
    purpose = (outline.get("purpose") or "").lower()
    if any(kw in purpose for kw in _SECTION_DIVIDER_KEYWORDS):
        return "section_divider"
    return "middle"


# ---------------------------------------------------------------------------
# Plan v2 — content layer (LLM) + selector (code) + self-review (LLM)
# ---------------------------------------------------------------------------

def generate_slide_content(
    outline: dict,
    section_facts: list[str],
    section_title: str,
    *,
    model: str = DEFAULT_MODEL,
    recent_intents: list[str] | None = None,
    slide_position: str = "middle",
) -> SlideContent:
    """Stage 2: per-slide LLM call. Produces SlideContent (no recipe/data).

    Retries up to 3 times, feeding the LLM specific schema + deterministic
    check failures on each retry.
    """
    log.step(f"LLM call: content for slide {outline['slide_no']}")
    template = (PROMPTS_DIR / "slide_content.md").read_text(encoding="utf-8")
    recent = recent_intents or []
    recent_str = ", ".join(recent) if recent else "(none yet — pick freely)"

    base_prompt = template.format(
        slide_no=outline["slide_no"],
        section_id=outline.get("section_id") or "null",
        head_draft=outline.get("head_message", ""),
        slide_position=slide_position,
        recent_intents=recent_str,
        section_facts="\n".join(
            f"[{i}] {f}" for i, f in enumerate(section_facts)
        ) or "(no raw_facts available — slide is high-level)",
    )

    last_err: str | None = None
    for attempt in range(3):
        prompt = base_prompt
        if last_err:
            prompt = (
                base_prompt
                + "\n\nThe previous attempt was rejected with these issues:\n"
                + last_err
                + "\nFix EVERY issue and reply with ONLY the corrected JSON."
            )
        parsed = _call_llm_with_json_retry(prompt, model=model)
        if not isinstance(parsed, dict):
            last_err = "response was not a JSON object"
            continue

        # Force outline's slide_no/section_id (LLM sometimes drifts)
        parsed["slide_no"] = outline["slide_no"]
        parsed.setdefault("section_id", outline.get("section_id"))

        # Position-based intent override BEFORE pydantic. Cover/thesis slides
        # have no raw_facts so LLM often can't fill so_what; the framing intent
        # tells the schema to allow empty so_what. Forcing intent here saves a
        # retry round.
        if slide_position == "first":
            parsed["intent_label"] = "deck_opening"
        elif slide_position == "last":
            parsed["intent_label"] = "closing_thesis"
        elif slide_position == "section_divider":
            parsed["intent_label"] = "section_transition"

        # Stage A: pydantic schema (form floor)
        try:
            content = SlideContent.model_validate(parsed)
        except Exception as exc:
            last_err = f"schema invalid: {exc}"
            log.warn(f"slide_content attempt {attempt + 1}: {last_err}")
            continue

        # Stage B: position-based hard rules
        if slide_position == "first" and content.intent_label != "deck_opening":
            last_err = (
                f"slide_position=first requires intent_label='deck_opening', "
                f"got {content.intent_label!r}."
            )
            log.warn(f"slide_content attempt {attempt + 1}: {last_err}")
            continue

        # Stage C: deterministic checks (line fit, question, dup, metric format)
        det_issues = check_slide_content(content, section_title=section_title)
        if det_issues:
            last_err = "\n".join(f"- {code}: {msg}" for code, msg in det_issues)
            log.warn(
                f"slide_content attempt {attempt + 1}: {len(det_issues)} "
                f"deterministic issues; retrying"
            )
            continue

        return content

    raise ValueError(f"slide_content invalid after retries:\n{last_err}")


def _fallback_slide_content(outline: dict) -> SlideContent:
    """When LLM cannot produce valid content after retries.

    Falls back to general_facts intent with the head_draft echoed. This
    always passes pydantic + deterministic + selector (single_bullets).
    """
    head = outline.get("head_message") or "(no message)"
    return SlideContent(
        slide_no=outline["slide_no"],
        section_id=outline.get("section_id"),
        intent_label="general_facts",
        so_what=[
            {"type": "WHY", "question": "(fallback)", "answer": "근거 부족",
             "evidence": [], "feeds": []},
            {"type": "WHAT_NEXT", "question": "(fallback)", "answer": "근거 부족",
             "evidence": [], "feeds": []},
        ],
        head_message=head,
        head_derivation="fallback",
        key_takeaway=head,
        key_takeaway_derivation="fallback",
        knowledge={"narratives": [{"text": head}]},
    )


def _section_title_for(deck_meta: dict, section_id: str | None) -> str:
    if not section_id:
        return ""
    return (deck_meta.get("section_titles") or {}).get(section_id, "")


def make_plan(content: dict, *, model: str = DEFAULT_MODEL) -> dict:
    """v2: outline → per-slide content (LLM) → selector (code) → self-review.

    Returns dict with shape:
        {"deck_meta": {...}, "slides": [SlidePlan dump, ...]}
    where each SlidePlan = {"content": SlideContent dump, "recipe": str, "data": dict}.
    """
    deck_meta = derive_deck_meta(content)
    outline = generate_outline(content, model=model)

    plans: list[dict] = []
    recent_intents: list[str] = []
    total = len(outline)
    fallback_count = 0

    for idx, o in enumerate(outline):
        facts = _section_facts_for(content, o.get("section_id"))
        section_title = _section_title_for(deck_meta, o.get("section_id"))
        position = _slide_position(idx, total, o)
        try:
            slide_content = generate_slide_content(
                o, facts, section_title,
                model=model,
                recent_intents=recent_intents[-3:],
                slide_position=position,
            )
        except ValueError as exc:
            log.warn(
                f"slide {o.get('slide_no')} content unrecoverable: {exc}; "
                "falling back to general_facts"
            )
            slide_content = _fallback_slide_content(o)
            fallback_count += 1

        # Stage 4: selector (code, deterministic)
        sel = select_recipe(slide_content)
        if sel.fell_back:
            log.warn(
                f"slide {slide_content.slide_no} selector fallback: {sel.reason}"
            )

        plan = SlidePlan(content=slide_content, recipe=sel.recipe, data=sel.data)
        plans.append(plan.model_dump())
        recent_intents.append(slide_content.intent_label)

    if fallback_count:
        log.warn(f"{fallback_count}/{total} slides used content fallback")

    # Stage 5: deck self-review (one LLM call) — patches if available
    plans = _maybe_apply_self_review(plans, model=model)

    # Flat plan dict — keep "slides" as list of SlidePlan-shaped dicts.
    # For renderer compatibility, also surface key fields at top level of each
    # slide so existing render_slide can read recipe/data/head_message directly.
    rendered_slides = [_flatten_slide_for_render(p) for p in plans]
    return {
        "deck_meta": deck_meta,
        "slides": rendered_slides,
    }


def _flatten_slide_for_render(plan_dump: dict) -> dict:
    """Surface content fields at the top level so renderer doesn't have to
    reach into `content`. The full SlidePlan stays in `_full` for debugging
    and downstream tools (closing-slide auto-gen, plan editor, etc.)."""
    c = plan_dump["content"]
    return {
        "slide_no": c["slide_no"],
        "section_id": c.get("section_id"),
        "head_message": c["head_message"],
        "sub_message": c.get("key_takeaway"),
        "intent_label": c["intent_label"],
        "recipe": plan_dump["recipe"],
        "data": plan_dump["data"],
        "_full": plan_dump,   # so_what + knowledge + derivations preserved
    }


def _maybe_apply_self_review(plans: list[dict], *, model: str) -> list[dict]:
    """Stage 5: deck-level self-review. Best-effort — failures don't block.

    For now: log issues only. Patch application (intent swap, head rewrite)
    is a follow-on feature; the v2 floor is "content + selector" working,
    self-review surfaces issues to humans / future automation.
    """
    log.step("LLM call: deck self-review")
    template_path = PROMPTS_DIR / "self_review.md"
    if not template_path.exists():
        log.warn("self_review.md not found — skipping self-review")
        return plans

    summary_lines: list[str] = []
    for p in plans:
        c = p["content"]
        summary_lines.append(
            f"slide {c['slide_no']:02d}  "
            f"intent={c['intent_label']}  "
            f"recipe={p['recipe']}  "
            f"head={c['head_message']!r}\n"
            f"  takeaway: {c['key_takeaway']}\n"
            f"  so_what: {len(c.get('so_what', []))} Q&A"
        )
    plan_summary = "\n\n".join(summary_lines)

    template = template_path.read_text(encoding="utf-8")
    prompt = template.format(plan_summary=plan_summary)
    try:
        parsed = _call_llm_with_json_retry(prompt, model=model)
    except ValueError as exc:
        log.warn(f"self-review unparseable: {exc}; continuing without")
        return plans

    if not isinstance(parsed, dict):
        log.warn("self-review returned non-object; continuing without")
        return plans

    issues = parsed.get("issues") or []
    verdict = parsed.get("verdict", "PASS")
    log.info(f"self-review verdict={verdict}  issues={len(issues)}")
    for issue in issues[:6]:
        sno = issue.get("slide_no", "?")
        code = issue.get("code", "?")
        sev = issue.get("severity", "?")
        msg = issue.get("msg", "")
        log.detail(f"  slide {sno} [{sev}] {code}: {msg}", max_lines=2)
    return plans
