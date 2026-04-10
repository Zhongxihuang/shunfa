"""Tests for quick_generate and _format_for_platform."""

import os
import pytest
from unittest.mock import AsyncMock, patch

from app.services.content_service import quick_generate, _format_for_platform
from app.config import settings

SAMPLE_XHS = (
    "DeepSeek V4定价出来了，比GPT-5便宜70%...\n"
    "大家都说国产AI赢了，但企业客户并没有迁移\n"
    "用户不是在为模型能力付钱，是在为工作流的确定性付钱\n"
    "价格战打完，比的才是生态"
)

SAMPLE_TWITTER = (
    "DeepSeek V4比GPT-5便宜70%，但企业API调用量没有迁移。"
    "说明用户不是在为模型能力付钱，是在为工作流的确定性付钱。"
    "价格战打完，真正的护城河才开始比拼。"
)


# ── quick_generate ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quick_generate_xiaohongshu():
    with patch("app.services.content_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = SAMPLE_XHS
        result = await quick_generate(
            hot_topic="DeepSeek V4定价发布，比GPT-5便宜70%",
            angle="国产AI性价比之战",
            platform="xiaohongshu",
        )

    assert result["platform"] == "xiaohongshu"
    assert result["content"] == SAMPLE_XHS
    assert result["char_count"] == len(SAMPLE_XHS)
    mock_ai.assert_called_once()


@pytest.mark.asyncio
async def test_quick_generate_twitter():
    with patch("app.services.content_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = SAMPLE_TWITTER
        result = await quick_generate(
            hot_topic="DeepSeek V4定价",
            angle="用户为工作流确定性付钱",
            platform="twitter",
        )

    assert result["platform"] == "twitter"
    assert len(result["content"]) <= 280


@pytest.mark.asyncio
async def test_quick_generate_default_platform():
    with patch("app.services.content_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "生成的内容"
        result = await quick_generate(hot_topic="热点", angle="角度")

    assert result["platform"] == "xiaohongshu"


@pytest.mark.asyncio
async def test_quick_generate_prompt_includes_topic_and_angle():
    with patch("app.services.content_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "内容"
        await quick_generate(
            hot_topic="OpenAI涨价20%",
            angle="用户在为确定性付钱",
            platform="xiaohongshu",
        )

    call_messages = mock_ai.call_args[0][0]
    prompt_text = call_messages[0]["content"]
    assert "OpenAI涨价20%" in prompt_text
    assert "用户在为确定性付钱" in prompt_text
    assert "xiaohongshu" in prompt_text


@pytest.mark.asyncio
async def test_quick_generate_linkedin():
    long_content = "字" * 350
    with patch("app.services.content_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = long_content
        result = await quick_generate(
            hot_topic="热点",
            angle="角度",
            platform="linkedin",
        )

    assert len(result["content"]) <= 500


# ── _format_for_platform ──────────────────────────────────────────────────────

def test_format_twitter_truncates_at_280():
    long_content = "A" * 400
    result = _format_for_platform(long_content, "twitter")
    assert len(result) <= 280


def test_format_twitter_short_content_unchanged():
    short = "Short tweet content."
    result = _format_for_platform(short, "twitter")
    assert result == short


def test_format_twitter_prefers_newline_break():
    first_segment = "A" * 200
    second_segment = "B" * 200
    content = first_segment + "\n" + second_segment
    result = _format_for_platform(content, "twitter")
    assert len(result) <= 280
    assert "B" not in result


def test_format_xiaohongshu_short_unchanged():
    content = "字" * 250
    result = _format_for_platform(content, "xiaohongshu")
    assert result == content


def test_format_xiaohongshu_truncates_over_300():
    content = "字" * 400
    result = _format_for_platform(content, "xiaohongshu")
    assert len(result) <= 300


def test_format_linkedin_allows_up_to_500():
    content = "字" * 400
    result = _format_for_platform(content, "linkedin")
    assert result == content


def test_format_linkedin_truncates_over_500():
    content = "字" * 600
    result = _format_for_platform(content, "linkedin")
    assert len(result) <= 500


def test_format_unknown_platform_unchanged():
    content = "Some content"
    result = _format_for_platform(content, "wechat")
    assert result == content


# ── API endpoint ──────────────────────────────────────────────────────────────

def _get_test_token(client) -> str:
    os.environ.setdefault("ADMIN_PASSWORD", settings.admin_password)
    resp = client.post("/api/web_login", json={"password": settings.admin_password})
    if resp.status_code == 200 and "token" in resp.json():
        return resp.json()["token"]
    return "invalid"


def test_quick_generate_api_requires_auth(client):
    response = client.post(
        "/api/quick_generate",
        json={
            "hot_topic": "DeepSeek V4",
            "angle": "角度",
            "platform": "xiaohongshu",
        },
    )
    assert response.status_code == 403


def test_quick_generate_api_endpoint(client):
    with patch("app.services.content_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "生成的AI洞察内容\n有观点有角度\n值得发出去"
        token = _get_test_token(client)
        response = client.post(
            "/api/quick_generate",
            json={
                "hot_topic": "DeepSeek V4发布",
                "angle": "国产AI性价比之战",
                "platform": "xiaohongshu",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert data["platform"] == "xiaohongshu"
    assert data["char_count"] > 0
