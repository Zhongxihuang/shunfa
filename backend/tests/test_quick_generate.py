"""Tests for quick_generate and _format_for_platform."""

import os
import pytest
from unittest.mock import AsyncMock, patch

from app.models import User, CheckIn, CheckInStatus, HotTopic
from app.routers.user import create_jwt_token
from app.utils.time_utils import get_today_cst
from app.services.draft_service import (
    quick_generate,
    build_quick_generate_context,
    _format_for_platform,
    remove_identity_framing,
)
from app.services.generation_context import parse_generation_context
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
    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [SAMPLE_XHS, '{"pass": true, "issues": []}']
        result = await quick_generate(
            hot_topic="DeepSeek V4定价发布，比GPT-5便宜70%",
            angle="国产AI性价比之战",
            platform="xiaohongshu",
        )

    assert result["platform"] == "xiaohongshu"
    assert result["content"] == SAMPLE_XHS
    assert result["char_count"] == len(SAMPLE_XHS)
    assert mock_ai.await_count == 2


@pytest.mark.asyncio
async def test_quick_generate_twitter():
    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [SAMPLE_TWITTER, '{"pass": true, "issues": []}']
        result = await quick_generate(
            hot_topic="DeepSeek V4定价",
            angle="用户为工作流确定性付钱",
            platform="twitter",
        )

    assert result["platform"] == "twitter"
    assert len(result["content"]) <= 280


@pytest.mark.asyncio
async def test_quick_generate_default_platform():
    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = ["生成的内容", '{"pass": true, "issues": []}']
        result = await quick_generate(hot_topic="热点", angle="角度")

    assert result["platform"] == "xiaohongshu"


@pytest.mark.asyncio
async def test_quick_generate_prompt_includes_topic_and_angle():
    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = ["内容", '{"pass": true, "issues": []}']
        await quick_generate(
            hot_topic="OpenAI涨价20%",
            angle="用户在为确定性付钱",
            platform="xiaohongshu",
        )

    call_messages = mock_ai.await_args_list[0].args[0]
    prompt_text = call_messages[0]["content"]
    assert "OpenAI涨价20%" in prompt_text
    assert "用户在为确定性付钱" in prompt_text
    assert "xiaohongshu" in prompt_text
    assert "有从业者视角" not in prompt_text
    assert "不得出现\"作为AI从业者\"" in prompt_text


def test_quick_generate_prompt_forbids_identity_framing():
    from app.services.prompt_templates import prompts

    prompt = prompts.system_prompt_quick.format(
        hot_topic="OpenAI 发布新产品",
        angle="这会引发新的产品讨论",
        platform="weibo",
        fact_block="标题：OpenAI 发布新产品",
        discussion_brief="核心立场：这会引发新的产品讨论",
    )

    assert "不要用\"从业者\"给观点背书" in prompt
    assert "不得出现\"作为AI从业者\"" in prompt


def test_remove_identity_framing_strips_forbidden_phrases():
    content = (
        "作为 AI 从业者，我觉得这件事真正该讨论的是分发。\n"
        "站在行业从业者角度，OpenAI这次不是简单更新。"
    )

    result = remove_identity_framing(content)

    assert "从业者" not in result
    assert "我觉得这件事真正该讨论的是分发。" in result
    assert "OpenAI这次不是简单更新。" in result


def test_build_quick_generate_context_contains_structured_facts():
    fact_block = build_quick_generate_context(
        hot_topic="OpenAI 涨价",
        summary="OpenAI 新增中间价格档。",
        source="TechCrunch AI",
        published_at="2026-04-10T09:00:00Z",
        url="https://example.com/openai",
    )

    assert "标题：OpenAI 涨价" in fact_block
    assert "来源：TechCrunch AI" in fact_block
    assert "摘要：OpenAI 新增中间价格档。" in fact_block
    assert "原文链接：https://example.com/openai" in fact_block


@pytest.mark.asyncio
async def test_quick_generate_linkedin():
    long_content = "字" * 350
    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [long_content, '{"pass": true, "issues": []}']
        result = await quick_generate(
            hot_topic="热点",
            angle="角度",
            platform="linkedin",
        )

    assert len(result["content"]) <= 500


@pytest.mark.asyncio
async def test_quick_generate_api_accepts_web_platforms(client):
    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [
            "微博风格的热点短评",
            '{"pass": true, "issues": []}',
        ]
        token = _get_test_token(client)
        response = client.post(
            "/api/quick_generate",
            json={
                "hot_topic": "AI 产品新动态",
                "angle": "真正的竞争在工作流",
                "platform": "weibo",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["platform"] == "weibo"


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


def test_format_weibo_truncates_over_target_length():
    content = "字" * 400
    result = _format_for_platform(content, "weibo")
    assert len(result) <= 260


def test_format_wechat_short_truncates_over_target_length():
    content = "字" * 500
    result = _format_for_platform(content, "wechat_short")
    assert len(result) <= 380


def test_format_generic_preserves_content():
    content = "字" * 600
    result = _format_for_platform(content, "generic")
    assert result == content


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
    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [
            "生成的AI洞察内容\n有观点有角度\n值得发出去",
            '{"pass": true, "issues": []}',
        ]
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


def test_quick_generate_api_uses_hot_topic_context_when_topic_id_provided(client, db):
    user = User(openid="quick_generate_topic_context_user")
    db.add(user)
    db.commit()
    db.refresh(user)

    hot_topic = HotTopic(
        topic_date=get_today_cst(),
        rank=1,
        title="OpenAI 新增 100 美元价格带",
        summary="从 20 美元到 100 美元之间新增中间订阅档。",
        source="TechCrunch AI",
        url="https://example.com/openai-pricing",
        published_at="2026-04-10T09:00:00Z",
        category="ai_model",
        score=9,
        ai_angle="AI 定价开始分层",
        ai_counter_angle="依然太贵",
    )
    db.add(hot_topic)
    db.commit()
    db.refresh(hot_topic)

    token = create_jwt_token(user.id)

    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [
            "这是一条严格基于热点事实的初稿",
            '{"pass": true, "issues": []}',
        ]
        response = client.post(
            "/api/quick_generate",
            json={
                "topic_id": hot_topic.id,
                "hot_topic": "旧标题",
                "angle": "AI 产品正在做分层定价",
                "platform": "xiaohongshu",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    prompt_text = mock_ai.await_args_list[0].args[0][0]["content"]
    assert "来源：TechCrunch AI" in prompt_text
    assert "摘要：从 20 美元到 100 美元之间新增中间订阅档。" in prompt_text
    assert "原文链接：https://example.com/openai-pricing" in prompt_text
    assert "不得补充你记忆里的旧新闻" in prompt_text


def test_quick_generate_updates_checkin_snapshot_when_topic_id_changes(client, db):
    user = User(openid="quick_generate_snapshot_user")
    db.add(user)
    db.commit()
    db.refresh(user)

    old_topic = HotTopic(
        topic_date=get_today_cst(),
        rank=1,
        title="旧热点",
        summary="旧摘要",
        source="Old Source",
        url="https://example.com/old",
        published_at="2026-04-10T08:00:00Z",
        category="ai_model",
        score=8,
    )
    new_topic = HotTopic(
        topic_date=get_today_cst(),
        rank=2,
        title="新热点",
        summary="新摘要",
        source="New Source",
        url="https://example.com/new",
        published_at="2026-04-10T09:00:00Z",
        category="policy",
        score=9,
    )
    db.add_all([old_topic, new_topic])
    db.commit()
    db.refresh(old_topic)
    db.refresh(new_topic)

    checkin = CheckIn(
        user_id=user.id,
        date=get_today_cst(),
        topic=old_topic.title,
        topic_source=old_topic.source,
        topic_url=old_topic.url,
        topic_summary=old_topic.summary,
        topic_published_at=old_topic.published_at,
        status=CheckInStatus.topic_selected,
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)

    token = create_jwt_token(user.id)

    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = ["基于新热点的内容", '{"pass": true, "issues": []}']
        response = client.post(
            "/api/quick_generate",
            json={
                "topic_id": new_topic.id,
                "checkin_id": checkin.id,
                "hot_topic": old_topic.title,
                "angle": "新的判断",
                "platform": "xiaohongshu",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    db.refresh(checkin)
    assert checkin.topic == "新热点"
    assert checkin.topic_source == "New Source"
    assert checkin.topic_url == "https://example.com/new"
    assert checkin.topic_summary == "新摘要"


def test_quick_generate_rejects_non_today_hot_topic(client, db):
    from datetime import timedelta

    user = User(openid="quick_generate_non_today_user")
    db.add(user)
    db.commit()
    db.refresh(user)

    hot_topic = HotTopic(
        topic_date=get_today_cst() - timedelta(days=1),
        rank=1,
        title="昨天的热点",
        summary="昨天的摘要",
        source="TechCrunch AI",
        url="https://example.com/yesterday",
        published_at="2026-04-09T09:00:00Z",
        category="ai_model",
        score=8,
    )
    db.add(hot_topic)
    db.commit()
    db.refresh(hot_topic)

    token = create_jwt_token(user.id)
    response = client.post(
        "/api/quick_generate",
        json={
            "topic_id": hot_topic.id,
            "hot_topic": hot_topic.title,
            "angle": "测试",
            "platform": "xiaohongshu",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_quick_generate_retries_when_grounding_check_fails():
    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [
            "第一版文案里写了素材没有的旧价格",
            '{"pass": false, "issues": ["提到了素材中没有的旧价格信息"]}',
            "修正后的文案只保留素材里的信息",
            '{"pass": true, "issues": []}',
        ]
        result = await quick_generate(
            hot_topic="OpenAI 新定价",
            angle="AI 服务开始分层定价",
            platform="xiaohongshu",
            fact_block=build_quick_generate_context(
                hot_topic="OpenAI 新定价",
                summary="新增中间价格带。",
                source="TechCrunch AI",
                published_at="2026-04-10T09:00:00Z",
                url="https://example.com/openai",
            ),
        )

    assert result["content"] == "修正后的文案只保留素材里的信息"
    assert mock_ai.await_count == 4
    retry_prompt = mock_ai.await_args_list[2].args[0][0]["content"]
    assert "上一版存在超出素材的事实" in retry_prompt


def test_quick_generate_persists_draft_when_checkin_id_provided(client, db):
    user = User(openid="quick_generate_persist_user")
    db.add(user)
    db.commit()
    db.refresh(user)

    checkin = CheckIn(
        user_id=user.id,
        date=get_today_cst(),
        topic="旧话题",
        status=CheckInStatus.topic_selected,
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)

    token = create_jwt_token(user.id)

    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "这是可直接发布的初稿"
        response = client.post(
            "/api/quick_generate",
            json={
                "topic_id": None,
                "checkin_id": checkin.id,
                "hot_topic": "ChatGPT 新价格带",
                "angle": "AI 产品正在做分层定价",
                "platform": "xiaohongshu",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    db.refresh(checkin)
    assert checkin.topic == "ChatGPT 新价格带"
    assert checkin.content == "这是可直接发布的初稿"
    assert checkin.status == CheckInStatus.draft_ready


def test_quick_generate_persists_generation_context(client, db):
    user = User(openid="quick_generate_context_persist_user")
    db.add(user)
    db.commit()
    db.refresh(user)

    hot_topic = HotTopic(
        topic_date=get_today_cst(),
        rank=1,
        title="OpenAI 新产品引发讨论",
        summary="OpenAI 发布的新产品引发了用户对平台能力的讨论。",
        source="TechCrunch AI",
        url="https://example.com/openai-product",
        published_at="2026-04-10T09:00:00Z",
        category="ai_product",
        score=9,
        ai_angle="真正值得聊的是平台能力",
        ai_counter_angle="也可能只是一次普通更新",
    )
    checkin = CheckIn(
        user_id=user.id,
        date=get_today_cst(),
        topic=hot_topic.title,
        status=CheckInStatus.topic_selected,
    )
    db.add_all([hot_topic, checkin])
    db.commit()
    db.refresh(hot_topic)
    db.refresh(checkin)

    token = create_jwt_token(user.id)
    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = ["这次真正值得聊的是平台能力，而不是功能更新本身。", '{"pass": true, "issues": []}']
        response = client.post(
            "/api/quick_generate",
            json={
                "topic_id": hot_topic.id,
                "checkin_id": checkin.id,
                "hot_topic": hot_topic.title,
                "angle": "真正值得聊的是平台能力",
                "platform": "weibo",
                "opportunities": ["可以写平台能力变化"],
                "risks": ["不要补充未确认功能细节"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    db.refresh(checkin)
    context = parse_generation_context(checkin)
    assert context["platform"] == "weibo"
    assert context["selected_angle"] == "真正值得聊的是平台能力"
    assert context["hot_topic_id"] == hot_topic.id
    assert context["discussion_brief"]["risks"] == ["不要补充未确认功能细节"]
    assert context["fact_guard_result"]["pass"] is True
