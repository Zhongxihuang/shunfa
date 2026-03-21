import pytest
from unittest.mock import patch, AsyncMock
from app.models import User, CheckIn, CheckInStatus, TopicHistory
from app.services.topic_service import generate_topics, MAX_DAILY_REFRESHES
from datetime import date

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
    assert result["refresh_count"] == 1

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
    today = date.today()
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
    assert data["refresh_count"] == 1
    assert data["max_refreshes"] == 3
