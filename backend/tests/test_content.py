import pytest
import json
from unittest.mock import patch, AsyncMock
from app.models import User, CheckIn, CheckInStatus
from app.routers.user import create_jwt_token
from app.utils.time_utils import get_today_cst

@pytest.fixture
def user(db):
    u = User(openid="content_test_user")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u

@pytest.fixture
def checkin(user, db):
    today = get_today_cst()
    c = CheckIn(
        user_id=user.id,
        date=today,
        topic="测试话题：工作中的一次小突破",
        status=CheckInStatus.topic_selected,
        refresh_count=0
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c

def test_generate_content_starts_discussion(user, checkin, client, db):
    """Test that sending first message starts discussion."""
    token = create_jwt_token(user.id)

    with patch("app.services.content_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "你在工作中有什么具体的突破想分享？是一次技术攻关，还是与人合作的突破？"

        response = client.post(
            "/api/generate_content",
            json={"checkin_id": checkin.id, "message": "我最近在工作上有个小进步"},
            headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert data["status"] == "discussing"
    assert data["draft"] is None

def test_generate_content_produces_draft(user, checkin, client, db):
    """Test that AI can produce a draft with the special markers after MIN_DISCUSSION_ROUNDS."""
    token = create_jwt_token(user.id)

    # Pre-seed one prior user message so MIN_DISCUSSION_ROUNDS (1) is satisfied
    prior_history = json.dumps([
        {"role": "user", "content": "我最近在工作上有个小进步"},
        {"role": "assistant", "content": "能说说具体是什么突破吗？"}
    ], ensure_ascii=False)
    checkin.conversation_history = prior_history
    checkin.status = CheckInStatus.discussing
    db.commit()

    draft_content = "上周我终于解决了困扰团队三个月的bug。那一刻，我感受到了久违的成就感。"
    ai_response = f"好的！<<<DRAFT_START>>>{draft_content}<<<DRAFT_END>>>"

    with patch("app.services.content_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = ai_response

        response = client.post(
            "/api/generate_content",
            json={"checkin_id": checkin.id, "message": "上周解决了一个难题，感觉很有成就感"},
            headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "draft_ready"
    assert data["draft"] == draft_content

def test_conversation_history_persisted(user, checkin, client, db):
    """Test that conversation history is saved to CheckIn."""
    token = create_jwt_token(user.id)

    with patch("app.services.content_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "能说说具体是什么突破吗？"

        client.post(
            "/api/generate_content",
            json={"checkin_id": checkin.id, "message": "工作有个小进步"},
            headers={"Authorization": f"Bearer {token}"}
        )

    db.expire_all()
    updated_checkin = db.query(CheckIn).filter(CheckIn.id == checkin.id).first()
    history = json.loads(updated_checkin.conversation_history)

    assert len(history) == 2  # user + assistant
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "工作有个小进步"
    assert history[1]["role"] == "assistant"

def test_confirm_content(user, checkin, client, db):
    """Test confirming content changes status to pending."""
    token = create_jwt_token(user.id)

    # Set up as draft_ready
    checkin.status = CheckInStatus.draft_ready
    checkin.content = "初稿内容"
    db.commit()

    with patch("app.services.content_service._quality_check", new_callable=AsyncMock) as mock_qc:
        mock_qc.return_value = {"pass": True, "issues": []}
        response = client.post(
            "/api/confirm_content",
            json={"checkin_id": checkin.id, "content": "用户修改后的内容"},
            headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    db.expire_all()
    updated = db.query(CheckIn).filter(CheckIn.id == checkin.id).first()
    assert updated.status == CheckInStatus.pending
    assert updated.content == "用户修改后的内容"


def test_confirm_content_soft_signal_when_quality_fails(user, checkin, client, db):
    token = create_jwt_token(user.id)
    checkin.status = CheckInStatus.draft_ready
    checkin.content = "初稿内容"
    db.commit()

    with patch("app.services.content_service._quality_check", new_callable=AsyncMock) as mock_qc:
        mock_qc.return_value = {"pass": False, "issues": ["缺少事实锚点"], "available": True}
        response = client.post(
            "/api/confirm_content",
            json={"checkin_id": checkin.id, "content": "用户修改后的内容"},
            headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["content_approved"] is False
    assert data["quality_issues"] == ["缺少事实锚点"]

    db.expire_all()
    updated = db.query(CheckIn).filter(CheckIn.id == checkin.id).first()
    assert updated.status == CheckInStatus.pending


def test_confirm_publish_allowed_after_quality_fail(user, checkin, client, db):
    token = create_jwt_token(user.id)
    checkin.status = CheckInStatus.pending
    checkin.content = "准备发布的内容"
    checkin.content_approved = False
    db.commit()

    response = client.post(
        "/api/confirm_publish",
        json={"checkin_id": checkin.id},
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200


def test_content_feedback_persisted(user, checkin, client, db):
    token = create_jwt_token(user.id)
    checkin.status = CheckInStatus.pending
    db.commit()

    response = client.post(
        "/api/content_feedback",
        json={"checkin_id": checkin.id, "feedback": "down"},
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["feedback"] == "down"

    db.expire_all()
    updated = db.query(CheckIn).filter(CheckIn.id == checkin.id).first()
    assert updated.content_feedback == "down"
    assert updated.content_feedback_at is not None

def test_confirm_publish(user, checkin, client, db):
    """Test that confirm_publish completes the checkin."""
    token = create_jwt_token(user.id)

    # Set up as pending
    checkin.status = CheckInStatus.pending
    checkin.content = "准备发布的内容"
    db.commit()

    response = client.post(
        "/api/confirm_publish",
        json={"checkin_id": checkin.id},
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "streak" in data
    assert "points_earned" in data

    db.expire_all()
    updated = db.query(CheckIn).filter(CheckIn.id == checkin.id).first()
    assert updated.status == CheckInStatus.completed

def test_prevent_duplicate_publish(user, checkin, client, db):
    """Test that completed checkin cannot be published again."""
    token = create_jwt_token(user.id)

    # Already completed
    checkin.status = CheckInStatus.completed
    db.commit()

    response = client.post(
        "/api/confirm_publish",
        json={"checkin_id": checkin.id},
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 400

def test_cannot_access_other_users_checkin(user, checkin, client, db):
    """Test that users cannot access other users' checkins."""
    other_user = User(openid="other_user_for_content_test")
    db.add(other_user)
    db.commit()
    db.refresh(other_user)

    other_token = create_jwt_token(other_user.id)

    response = client.post(
        "/api/generate_content",
        json={"checkin_id": checkin.id, "message": "test"},
        headers={"Authorization": f"Bearer {other_token}"}
    )

    assert response.status_code == 404

def test_status_transition_completed_blocks_message(user, checkin, client, db):
    """Test that completed checkin blocks new messages."""
    token = create_jwt_token(user.id)
    checkin.status = CheckInStatus.completed
    db.commit()

    with patch("app.services.content_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        response = client.post(
            "/api/generate_content",
            json={"checkin_id": checkin.id, "message": "再说点什么"},
            headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 400
