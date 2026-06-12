from datetime import timedelta
from unittest.mock import AsyncMock, patch

from app.models import HotTopic, User
from app.routers.user import create_jwt_token
from app.schemas import ScoredTopic, TopicCategory
from app.utils.time_utils import get_today_cst


def _create_admin_token(db) -> str:
    admin = User(openid="web_admin")
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return create_jwt_token(admin.id)


def test_hot_topics_today_returns_structured_topics(client, db):
    user = User(openid="hot_topics_user")
    db.add(user)
    db.commit()
    db.refresh(user)

    db.add_all(
        [
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
        ]
    )
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
    assert data["is_fallback"] is False


def test_hot_topics_today_falls_back_to_latest_topics(client, db):
    user = User(openid="hot_topics_fallback_user")
    db.add(user)
    db.commit()
    db.refresh(user)

    old_topic = HotTopic(
        topic_date=get_today_cst() - timedelta(days=1),
        rank=1,
        title="昨天仍可用的AI热点",
        summary="今天刷新失败时，仍展示最近的可用热点。",
        source="TechCrunch AI",
        url="https://example.com/yesterday-still-valid",
        category="ai_model",
        score=9,
        ai_angle="刷新失败不应该导致首页空白",
        ai_counter_angle="旧热点也要注意时效性",
    )
    db.add(old_topic)
    db.commit()

    token = create_jwt_token(user.id)
    response = client.get(
        "/api/hot_topics/today",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["date"] == get_today_cst().isoformat()
    assert data["topics"][0]["title"] == "昨天仍可用的AI热点"
    assert data["topics"][0]["id"] != old_topic.id
    # Cloned-but-real topics are stale, not synthetic backups.
    assert data["is_fallback"] is False

    detail_response = client.get(
        f"/api/hot_topics/{data['topics'][0]['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_response.status_code == 200


def test_hot_topics_today_seeds_static_fallback_when_empty(client, db):
    user = User(openid="hot_topics_empty_fallback_user")
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_jwt_token(user.id)
    response = client.get(
        "/api/hot_topics/today",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["date"] == get_today_cst().isoformat()
    assert len(data["topics"]) == 3
    assert data["topics"][0]["source"] == "顺发兜底"
    assert data["is_fallback"] is True

    detail_response = client.get(
        f"/api/hot_topics/{data['topics'][0]['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_response.status_code == 200


def test_hot_topics_reload_replaces_fallback_with_fresh(client, db):
    user = User(openid="hot_topics_reload_user")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_jwt_token(user.id)

    fresh_topic = ScoredTopic(
        hot_topic="重新加载拿到的真实热点",
        hot_source="TechCrunch AI",
        hot_url="https://example.com/reloaded",
        hot_summary="用户点重新加载后抓到的真实热点。",
        topic_category=TopicCategory.ai_product,
        ai_angle="按需刷新让备用话题退场",
        ai_counter_angle="按需刷新也有成本，需要限流",
        score=9,
    )

    with (
        patch(
            "app.services.hot_topic_refresh_service.fetch_all_sources", new_callable=AsyncMock
        ) as mock_fetch,
        patch(
            "app.services.hot_topic_refresh_service.score_and_filter", new_callable=AsyncMock
        ) as mock_score,
    ):
        mock_fetch.return_value = [object()]
        mock_score.return_value = [fresh_topic]
        response = client.post(
            "/api/hot_topics/reload",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["is_fallback"] is False
    assert data["topics"][0]["title"] == "重新加载拿到的真实热点"


def test_hot_topics_reload_stays_fallback_when_no_fresh(client, db):
    user = User(openid="hot_topics_reload_fallback_user")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_jwt_token(user.id)

    with patch(
        "app.services.hot_topic_refresh_service.fetch_all_sources", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = []
        response = client.post(
            "/api/hot_topics/reload",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["is_fallback"] is True
    assert len(data["topics"]) == 3


def test_hot_topics_health_reports_current_supply(client, db):
    user = User(openid="hot_topics_health_user")
    db.add(user)
    db.commit()
    db.refresh(user)

    db.add(
        HotTopic(
            topic_date=get_today_cst(),
            rank=1,
            title="健康检查热点",
            summary="健康检查摘要",
            source="TechCrunch AI",
            url="https://example.com/health",
            category="ai_model",
            score=9,
        )
    )
    db.commit()

    token = create_jwt_token(user.id)
    response = client.get(
        "/api/hot_topics/health",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["today_count"] == 1


def test_hot_topics_refresh_seeds_fallback_when_rss_empty(client, db):
    token = _create_admin_token(db)
    with patch(
        "app.services.hot_topic_refresh_service.fetch_all_sources", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = []
        response = client.post(
            "/api/hot_topics/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["status"] == "fallback_no_fresh_topics"
    assert result["available_topics"] == 3

    today_count = db.query(HotTopic).filter(HotTopic.topic_date == get_today_cst()).count()
    assert today_count == 3


def test_hot_topics_refresh_rejects_regular_user(client, db):
    user = User(openid="hot_topics_refresh_regular_user")
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_jwt_token(user.id)
    with patch(
        "app.services.hot_topic_refresh_service.fetch_all_sources", new_callable=AsyncMock
    ) as mock_fetch:
        response = client.post(
            "/api/hot_topics/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403
    mock_fetch.assert_not_awaited()


def test_hot_topics_refresh_replaces_with_fresh_topics(client, db):
    fresh_topic = ScoredTopic(
        hot_topic="OpenAI 发布企业新能力",
        hot_source="TechCrunch AI",
        hot_url="https://example.com/fresh",
        hot_summary="企业团队开始测试新能力。",
        topic_category=TopicCategory.ai_product,
        ai_angle="AI产品竞争转向团队工作流",
        ai_counter_angle="产品发布不等于真实采用",
        score=9,
    )

    token = _create_admin_token(db)
    with (
        patch(
            "app.services.hot_topic_refresh_service.fetch_all_sources", new_callable=AsyncMock
        ) as mock_fetch,
        patch(
            "app.services.hot_topic_refresh_service.score_and_filter", new_callable=AsyncMock
        ) as mock_score,
    ):
        mock_fetch.return_value = [object()]
        mock_score.return_value = [fresh_topic]
        response = client.post(
            "/api/hot_topics/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["status"] == "fresh"
    assert result["available_topics"] == 1

    saved = db.query(HotTopic).filter(HotTopic.topic_date == get_today_cst()).one()
    assert saved.title == "OpenAI 发布企业新能力"
    assert saved.source == "TechCrunch AI"


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
            '"recommended_frame":"团队工作流才是重点",'
            '"angles":["从团队协作写","从产品形态写"]}'
        )
        response = client.post(
            f"/api/hot_topics/{hot_topic.id}/analysis",
            json={"angle": "从企业团队切入"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["recommended_frame"] == "团队工作流才是重点"
    assert data["opportunities"] == ["可写工作流变化"]

    prompt_text = mock_ai.await_args.kwargs["messages"][0]["content"]
    assert "标题：OpenAI 发布新产品" in prompt_text
    assert "摘要：产品开始面向企业团队。" in prompt_text
    assert "推荐角度：AI 产品竞争转向团队工作流" in prompt_text
    assert "用户当前角度：从企业团队切入" in prompt_text
