from datetime import timedelta
from unittest.mock import AsyncMock, patch

from app.models import HotTopic, User
from app.routers.user import create_jwt_token
from app.utils.time_utils import get_today_cst


def test_hot_topics_today_returns_structured_topics(client, db):
    user = User(openid="hot_topics_user")
    db.add(user)
    db.commit()
    db.refresh(user)

    db.add_all([
        HotTopic(
            topic_date=get_today_cst(),
            rank=1,
            title="OpenAI 发布新定价",
            summary="一档新的中间层价格带出现了。",
            source="TechCrunch AI",
            url="https://example.com/openai-pricing",
            published_at="2026-04-10T08:00:00Z",
            category="ai_model",
            score=9,
            ai_angle="AI 服务开始做价格分层",
            ai_counter_angle="仍然太贵，离大众太远",
        ),
        HotTopic(
            topic_date=get_today_cst(),
            rank=2,
            title="Claude Code 工作流走红",
            summary="开发者开始讨论人机协作流程。",
            source="VentureBeat AI",
            url="https://example.com/claude-code",
            published_at="2026-04-10T09:00:00Z",
            category="startup",
            score=8,
            ai_angle="真正的壁垒变成流程设计",
            ai_counter_angle="明星工作流不一定可复制",
        ),
    ])
    db.commit()

    token = create_jwt_token(user.id)
    response = client.get(
        "/api/hot_topics/today",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["topics"]) == 2
    assert data["topics"][0]["title"] == "OpenAI 发布新定价"
    assert data["topics"][0]["url"] == "https://example.com/openai-pricing"
    assert data["topics"][0]["source"] == "TechCrunch AI"


def test_hot_topic_detail_returns_today_topic(client, db):
    user = User(openid="hot_topic_detail_user")
    db.add(user)
    db.commit()
    db.refresh(user)

    hot_topic = HotTopic(
        topic_date=get_today_cst(),
        rank=1,
        title="今日AI热点",
        summary="今日摘要",
        source="TechCrunch AI",
        url="https://example.com/today",
        published_at="2026-04-10T08:00:00Z",
        category="ai_model",
        score=9,
        ai_angle="推荐立场",
        ai_counter_angle="反向立场",
    )
    db.add(hot_topic)
    db.commit()
    db.refresh(hot_topic)

    token = create_jwt_token(user.id)
    response = client.get(
        f"/api/hot_topics/{hot_topic.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == hot_topic.id
    assert data["title"] == "今日AI热点"
    assert data["ai_angle"] == "推荐立场"


def test_hot_topic_detail_rejects_non_today_topic(client, db):
    user = User(openid="hot_topic_old_detail_user")
    db.add(user)
    db.commit()
    db.refresh(user)

    hot_topic = HotTopic(
        topic_date=get_today_cst() - timedelta(days=1),
        rank=1,
        title="昨天AI热点",
        summary="昨天摘要",
        source="TechCrunch AI",
        url="https://example.com/yesterday",
        category="ai_model",
        score=9,
    )
    db.add(hot_topic)
    db.commit()
    db.refresh(hot_topic)

    token = create_jwt_token(user.id)
    response = client.get(
        f"/api/hot_topics/{hot_topic.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_hot_topic_analysis_builds_prompt_and_parses_json(client, db):
    user = User(openid="hot_topic_analysis_user")
    db.add(user)
    db.commit()
    db.refresh(user)

    hot_topic = HotTopic(
        topic_date=get_today_cst(),
        rank=1,
        title="OpenAI 发布新产品",
        summary="产品开始面向企业团队。",
        source="TechCrunch AI",
        url="https://example.com/openai-product",
        published_at="2026-04-10T08:00:00Z",
        category="ai_product",
        score=9,
        ai_angle="AI 产品竞争转向团队工作流",
        ai_counter_angle="产品形态仍然不够清晰",
    )
    db.add(hot_topic)
    db.commit()
    db.refresh(hot_topic)

    token = create_jwt_token(user.id)
    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = (
            '{"opportunities":["可写工作流变化"],'
            '"risks":["不要编造产品细节"],'
            '"recommended_stance":"团队工作流才是重点",'
            '"angles":["从团队协作写","从产品形态写"]}'
        )
        response = client.post(
            f"/api/hot_topics/{hot_topic.id}/analysis",
            json={"angle": "从企业团队切入"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["recommended_stance"] == "团队工作流才是重点"
    assert data["opportunities"] == ["可写工作流变化"]

    prompt_text = mock_ai.await_args.kwargs["messages"][0]["content"]
    assert "标题：OpenAI 发布新产品" in prompt_text
    assert "摘要：产品开始面向企业团队。" in prompt_text
    assert "推荐角度：AI 产品竞争转向团队工作流" in prompt_text
    assert "用户当前角度：从企业团队切入" in prompt_text
