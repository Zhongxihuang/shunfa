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
