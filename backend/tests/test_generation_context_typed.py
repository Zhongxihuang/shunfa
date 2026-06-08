"""Tests for the typed generation_context accessor.

generation_context is a JSON Text column that grew into an untyped grab-bag of
~20 keys (platform, selected_angle, discussion_brief, feedback tags, guard
results, …). These tests pin down a Pydantic accessor that gives type safety at
read sites while staying backward-compatible with any JSON already stored: it
must tolerate unknown/legacy keys and round-trip without silently adding or
dropping data.
"""

import json

from app.models import CheckIn
from app.services.generation_context import (
    GenerationContext,
    dump_generation_context,
    load_generation_context,
    parse_generation_context,
    store_generation_context,
)


def _checkin(context: dict | None) -> CheckIn:
    return CheckIn(
        generation_context=json.dumps(context, ensure_ascii=False)
        if context is not None
        else None
    )


def test_empty_checkin_yields_defaults():
    ctx = load_generation_context(_checkin(None))
    assert isinstance(ctx, GenerationContext)
    assert ctx.platform is None
    assert ctx.selected_angle is None
    assert ctx.feedback_reason_tags == []
    assert ctx.compose_tags == []


def test_known_keys_are_typed():
    raw = {
        "generation_mode": "deep",
        "platform": "xiaohongshu",
        "selected_angle": "AI 取代的是流程不是岗位",
        "char_count": 187,
        "feedback_reason_tags": ["too_flat", "too_long"],
        "feedback_free_text": "再犀利一点",
        "discussion_brief": {"analysis_frame": "信号", "platform": "xiaohongshu"},
    }
    ctx = load_generation_context(_checkin(raw))
    assert ctx.generation_mode == "deep"
    assert ctx.platform == "xiaohongshu"
    assert ctx.char_count == 187
    assert ctx.feedback_reason_tags == ["too_flat", "too_long"]
    assert ctx.feedback_free_text == "再犀利一点"
    assert ctx.discussion_brief["analysis_frame"] == "信号"


def test_unknown_legacy_keys_are_preserved():
    raw = {"platform": "weibo", "some_legacy_field": {"nested": 1}, "v0_flag": True}
    ctx = load_generation_context(_checkin(raw))
    # Unknown keys survive on the model and round-trip back out unchanged.
    dumped = dump_generation_context(ctx)
    assert dumped["some_legacy_field"] == {"nested": 1}
    assert dumped["v0_flag"] is True
    assert dumped["platform"] == "weibo"


def test_round_trip_preserves_exact_keys():
    raw = {
        "platform": "xiaohongshu",
        "selected_angle": "x",
        "feedback_reason_tags": ["quality_issue"],
        "confirm_fact_guard": {"pass": True, "issues": []},
        "legacy_only": "keep me",
    }
    ctx = load_generation_context(_checkin(raw))
    dumped = dump_generation_context(ctx)
    # No keys invented, none dropped — dump matches the original stored dict.
    assert dumped == raw


def test_dump_does_not_inject_unset_defaults():
    raw = {"platform": "weibo"}
    ctx = load_generation_context(_checkin(raw))
    dumped = dump_generation_context(ctx)
    # feedback_reason_tags/compose_tags default to [] in-memory but must NOT be
    # written back when they were never stored.
    assert "feedback_reason_tags" not in dumped
    assert "compose_tags" not in dumped
    assert dumped == {"platform": "weibo"}


def test_malformed_json_loads_empty_model():
    checkin = CheckIn(generation_context="{not valid json")
    ctx = load_generation_context(checkin)
    assert ctx.platform is None
    assert ctx.feedback_reason_tags == []


def test_store_writes_serialized_json_back_to_checkin():
    checkin = _checkin({"platform": "weibo"})
    ctx = load_generation_context(checkin)
    ctx.selected_angle = "新角度"
    store_generation_context(checkin, ctx)
    # The dict accessor (still used widely) sees the merged result.
    reparsed = parse_generation_context(checkin)
    assert reparsed["platform"] == "weibo"
    assert reparsed["selected_angle"] == "新角度"


def test_attribute_mutation_is_marked_and_dumped():
    ctx = load_generation_context(_checkin({"platform": "weibo"}))
    ctx.char_count = 42
    dumped = dump_generation_context(ctx)
    assert dumped["char_count"] == 42
    assert dumped["platform"] == "weibo"
