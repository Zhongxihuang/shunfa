"""Tests for compose_service.generate_post_copy — the safe-failure variant
used by the image_jobs paste-to-cards flow.

The original compose_post_assets() raises HTTPException(502) when the LLM
returns malformed JSON twice. The image_jobs flow needs a different contract:
the user has already pasted their article, and we only want the AI-generated
title + tags on top of the deterministic pagination. If the AI call fails,
we MUST still return 200 with empty title/tags so the user can still get
their image cards — they just lose the convenience copy.
"""

import json
from unittest.mock import AsyncMock, patch

from app.services.compose_service import generate_post_copy

# A typical LLM response wrapped in markdown code fences — the LLM sometimes
# adds them even when not asked.
GOOD_PAYLOAD = json.dumps(
    {
        "pages": ["page 1", "page 2"],
        "title": "OpenAI 这次定价暗藏玄机",
        "tags": ["OpenAI", "AI 定价", "行业观察"],
    },
    ensure_ascii=False,
)


async def test_returns_title_and_tags_on_success():
    """Happy path: LLM returns well-formed JSON with title + tags."""

    async def fake_chat(messages, temperature, max_tokens, api_key):
        return GOOD_PAYLOAD

    with patch("app.services.compose_service.chat_completion", side_effect=fake_chat):
        result = await generate_post_copy("OpenAI 宣布新增 100 美元一档定价。", api_key="")

    assert result == {
        "title": "OpenAI 这次定价暗藏玄机",
        "tags": ["OpenAI", "AI 定价", "行业观察"],
    }


async def test_strips_markdown_fences():
    """LLM responses often arrive wrapped in ```json ... ```. The parser must
    still extract the JSON correctly."""

    fenced = "```json\n" + GOOD_PAYLOAD + "\n```"

    async def fake_chat(messages, temperature, max_tokens, api_key):
        return fenced

    with patch("app.services.compose_service.chat_completion", side_effect=fake_chat):
        result = await generate_post_copy("内容", api_key="")

    assert result["title"] == "OpenAI 这次定价暗藏玄机"
    assert len(result["tags"]) == 3


async def test_returns_empty_on_first_parse_failure_then_success():
    """When the first LLM response is unparseable but the retry succeeds,
    we still get the good title + tags."""

    async def fake_chat(messages, temperature, max_tokens, api_key):
        if temperature == 0.7:
            return "this is not JSON at all"
        return GOOD_PAYLOAD

    with patch("app.services.compose_service.chat_completion", side_effect=fake_chat):
        result = await generate_post_copy("内容", api_key="")

    assert result["title"] == "OpenAI 这次定价暗藏玄机"


async def test_returns_empty_on_both_attempts_failing():
    """The whole point of this variant: AI copy failure MUST NOT bubble up.
    The image_jobs flow already has the user's text + pagination; losing the
    copy is a degraded but recoverable UX, not an error."""

    async def fake_chat(messages, temperature, max_tokens, api_key):
        return "still not JSON"

    with patch("app.services.compose_service.chat_completion", side_effect=fake_chat):
        result = await generate_post_copy("内容", api_key="")

    assert result == {"title": "", "tags": []}


async def test_returns_empty_on_empty_input():
    """No content = no point calling the LLM."""

    with patch("app.services.compose_service.chat_completion", new_callable=AsyncMock) as mock:
        result = await generate_post_copy("", api_key="")
    assert result == {"title": "", "tags": []}
    mock.assert_not_called()


async def test_returns_empty_on_chat_completion_exception():
    """Network errors / API key errors must not break the image_jobs flow."""

    async def boom(messages, temperature, max_tokens, api_key):
        raise RuntimeError("network down")

    with patch("app.services.compose_service.chat_completion", side_effect=boom):
        result = await generate_post_copy("内容", api_key="")
    assert result == {"title": "", "tags": []}


async def test_drops_empty_tag_strings():
    """LLM occasionally returns `["", "AI", ""]`; the caller should never
    see empty strings in the final tag list."""

    payload = json.dumps({"title": "好的标题", "tags": ["", "  ", "AI", ""]})

    async def fake_chat(messages, temperature, max_tokens, api_key):
        return payload

    with patch("app.services.compose_service.chat_completion", side_effect=fake_chat):
        result = await generate_post_copy("内容", api_key="")

    assert result["title"] == "好的标题"
    assert result["tags"] == ["AI"]


async def test_handles_missing_title_or_tags_keys():
    """The LLM might return only one of title/tags. We accept partial output
    rather than failing the whole image job."""

    payload = json.dumps({"title": "只有标题"})  # no tags key

    async def fake_chat(messages, temperature, max_tokens, api_key):
        return payload

    with patch("app.services.compose_service.chat_completion", side_effect=fake_chat):
        result = await generate_post_copy("内容", api_key="")
    assert result == {"title": "只有标题", "tags": []}
