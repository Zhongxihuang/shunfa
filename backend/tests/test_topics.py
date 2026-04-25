import pytest
from unittest.mock import patch, AsyncMock
from app.models import User, CheckIn, CheckInStatus, TopicHistory, HotTopic
from app.services.topic_service import generate_topics, MAX_DAILY_REFRESHES
from app.utils.time_utils import get_today_cst

@pytest.fixture
def user(db):
    u = User(openid="topic_test_user")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u

@pytest.fixture
def mock_ai_topics():
    """Mock AI topic generation to return predictable topics."""
    topics = ["测试选题一：关于日常观察", "测试选题二：关于学习成长", "测试选题三：关于人际关系"]
    with patch("app.services.topic_service._generate_topics_via_ai", new_callable=AsyncMock) as mock:
        mock.return_value = topics
        yield mock, topics

@pytest.mark.asyncio
async def test_generate_topics_returns_three(user, db, mock_ai_topics):
    """Test that generate_topics returns exactly 3 topics."""
    _, topics = mock_ai_topics
    result = await generate_topics(user.id, db)
    assert len(result["topics"]) == 3
    assert result["refresh_count"] == 0  # First load is free, count stays 0

@pytest.mark.asyncio
async def test_topics_saved_to_history(user, db, mock_ai_topics):
    """Test that generated topics are saved to TopicHistory."""
    _, topics = mock_ai_topics
    result = await generate_topics(user.id, db)

    db.expire_all()
    history = db.query(TopicHistory).filter(TopicHistory.user_id == user.id).all()
    assert len(history) == 3

@pytest.mark.asyncio
async def test_refresh_limit_enforced(user, db, mock_ai_topics):
    """Test that max daily refreshes are enforced."""
    # Create checkin with max refreshes already reached
    today = get_today_cst()
    checkin = CheckIn(
        user_id=user.id,
        date=today,
        topic="",
        status=CheckInStatus.topic_selected,
        refresh_count=MAX_DAILY_REFRESHES
    )
    db.add(checkin)
    db.commit()

    with pytest.raises(ValueError, match="最大刷新次数"):
        await generate_topics(user.id, db)

@pytest.mark.asyncio
async def test_deduplication_excludes_recent_topics(user, db):
    """Test that recent topics are excluded from generation."""
    # Track what topics AI was asked to exclude
    excluded_in_call = []

    async def mock_generate(exclude_topics):
        excluded_in_call.extend(exclude_topics)
        return ["新选题一", "新选题二", "新选题三"]

    # First batch
    with patch("app.services.topic_service._generate_topics_via_ai", new_callable=AsyncMock) as mock:
        mock.return_value = ["旧选题一", "旧选题二", "旧选题三"]
        await generate_topics(user.id, db)

    # Second batch - check that first batch topics are excluded
    with patch("app.services.topic_service._generate_topics_via_ai", side_effect=mock_generate):
        await generate_topics(user.id, db)

    assert "旧选题一" in excluded_in_call
    assert "旧选题二" in excluded_in_call
    assert "旧选题三" in excluded_in_call

@pytest.mark.asyncio
async def test_select_topic_creates_checkin(user, db, client):
    """Test that selecting a topic creates/updates a CheckIn."""
    from app.routers.user import create_jwt_token
    token = create_jwt_token(user.id)

    response = client.post(
        "/api/select_topic",
        json={"topic": "测试自定义选题"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "checkin_id" in data
    assert data["status"] == "topic_selected"

@pytest.mark.asyncio
async def test_daily_topics_endpoint(user, db, client, mock_ai_topics):
    """Test the daily topics API endpoint."""
    from app.routers.user import create_jwt_token
    token = create_jwt_token(user.id)

    response = client.post(
        "/api/daily_topics",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["topics"]) == 3
    assert data["refresh_count"] == 0  # First load is free, count stays 0
    assert data["max_refreshes"] == 3


@pytest.mark.asyncio
async def test_second_load_counts_as_refresh(user, db, mock_ai_topics):
    await generate_topics(user.id, db)
    result = await generate_topics(user.id, db)
    assert result["refresh_count"] == 1


def test_select_topic_resets_stale_checkin_state(user, db, client):
    from app.routers.user import create_jwt_token

    token = create_jwt_token(user.id)
    checkin = CheckIn(
        user_id=user.id,
        date=get_today_cst(),
        topic="旧话题",
        status=CheckInStatus.pending,
        content="旧草稿",
        conversation_history='[{"role":"user","content":"old"}]',
        content_approved=True,
        points_earned=45,
        content_feedback="down",
    )
    db.add(checkin)
    db.commit()

    response = client.post(
        "/api/select_topic",
        json={"topic": "新话题"},
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    db.refresh(checkin)
    assert checkin.topic == "新话题"
    assert checkin.status == CheckInStatus.topic_selected
    assert checkin.content is None
    assert checkin.conversation_history is None
    assert checkin.content_approved is False
    assert checkin.content_feedback is None


def test_select_hot_topic_snapshots_source_and_url(user, db, client):
    from app.routers.user import create_jwt_token

    token = create_jwt_token(user.id)
    hot_topic = HotTopic(
        topic_date=get_today_cst(),
        rank=1,
        title="OpenAI 新价格带",
        summary="新增了 100 美元这一档。",
        source="TechCrunch AI",
        url="https://example.com/openai-pricing",
        published_at="2026-04-10T09:00:00Z",
        category="ai_model",
        score=9,
        ai_angle="AI 定价分层开始了",
        ai_counter_angle="还是很贵",
    )
    db.add(hot_topic)
    db.commit()
    db.refresh(hot_topic)

    response = client.post(
        "/api/select_topic",
        json={"topic": "忽略这个字符串", "hot_topic_id": hot_topic.id},
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    checkin = db.query(CheckIn).filter(CheckIn.user_id == user.id).first()
    assert checkin.topic == "OpenAI 新价格带"
    assert checkin.topic_source == "TechCrunch AI"
    assert checkin.topic_url == "https://example.com/openai-pricing"
    assert checkin.topic_summary == "新增了 100 美元这一档。"


def test_select_topic_rejects_non_today_hot_topic(user, db, client):
    from datetime import timedelta
    from app.routers.user import create_jwt_token

    token = create_jwt_token(user.id)
    hot_topic = HotTopic(
        topic_date=get_today_cst() - timedelta(days=1),
        rank=1,
        title="昨天的热点",
        summary="这不是今天的热点。",
        source="TechCrunch AI",
        url="https://example.com/yesterday",
        published_at="2026-04-09T09:00:00Z",
        category="ai_model",
        score=9,
        ai_angle="昨天的判断",
        ai_counter_angle="昨天的反方",
    )
    db.add(hot_topic)
    db.commit()
    db.refresh(hot_topic)

    response = client.post(
        "/api/select_topic",
        json={"topic": "忽略", "hot_topic_id": hot_topic.id},
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404
