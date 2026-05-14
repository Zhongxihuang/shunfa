import json
from unittest.mock import AsyncMock, patch

import pytest

from app.models import CheckIn, CheckInStatus, User
from app.routers.user import create_jwt_token
from app.services.discussion_service import reset_checkin_for_new_topic
from app.services.generation_context import parse_generation_context
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

    with patch("app.services.discussion_service.chat_completion", new_callable=AsyncMock) as mock_ai:
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


def test_reset_checkin_clears_generation_context(checkin):
    checkin.generation_context = json.dumps(
        {"selected_angle": "旧角度", "platform": "weibo"},
        ensure_ascii=False,
    )

    reset_checkin_for_new_topic(checkin, "新话题", CheckInStatus.topic_selected)

    assert checkin.topic == "新话题"
    assert checkin.generation_context is None


def test_generate_content_uses_angle_and_platform(user, checkin, client, db):
    token = create_jwt_token(user.id)

    with patch("app.services.discussion_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "这个角度可以继续展开。"

        response = client.post(
            "/api/generate_content",
            json={
                "checkin_id": checkin.id,
                "message": "我想写这个热点",
                "angle": "真正值得聊的是分发权",
                "platform": "weibo",
            },
            headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    prompt_text = mock_ai.await_args.args[0][0]["content"]
    assert "推荐角度：真正值得聊的是分发权" in prompt_text
    assert "目标平台：weibo" in prompt_text
    db.refresh(checkin)
    context = parse_generation_context(checkin)
    assert context["selected_angle"] == "真正值得聊的是分发权"
    assert context["platform"] == "weibo"

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

    with patch("app.services.discussion_service.chat_completion", new_callable=AsyncMock) as mock_ai:
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


def test_generate_content_strips_identity_framing_from_draft(user, checkin, client, db):
    token = create_jwt_token(user.id)
    prior_history = json.dumps([
        {"role": "user", "content": "我想写这个热点"},
        {"role": "assistant", "content": "你想强调哪个判断？"}
    ], ensure_ascii=False)
    checkin.conversation_history = prior_history
    checkin.status = CheckInStatus.discussing
    db.commit()

    draft_content = "作为AI从业者，我觉得这次真正该讨论的是分发权。"
    ai_response = f"<<<DRAFT_START>>>{draft_content}<<<DRAFT_END>>>"

    with patch("app.services.discussion_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = ai_response

        response = client.post(
            "/api/generate_content",
            json={"checkin_id": checkin.id, "message": "就写分发权"},
            headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    data = response.json()
    assert "从业者" not in data["draft"]
    assert data["draft"] == "我觉得这次真正该讨论的是分发权。"

def test_conversation_history_persisted(user, checkin, client, db):
    """Test that conversation history is saved to CheckIn."""
    token = create_jwt_token(user.id)

    with patch("app.services.discussion_service.chat_completion", new_callable=AsyncMock) as mock_ai:
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

    with patch("app.services.draft_service._quality_check", new_callable=AsyncMock) as mock_qc:
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


def test_confirm_content_checks_user_edits_against_fact_block(user, checkin, client, db):
    token = create_jwt_token(user.id)
    checkin.status = CheckInStatus.draft_ready
    checkin.content = "初稿内容"
    checkin.topic_source = "TechCrunch AI"
    checkin.topic_summary = "OpenAI 发布新产品。"
    checkin.topic_url = "https://example.com/openai"
    db.commit()

    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [
            '{"pass": false, "issues": ["新增了素材中没有的价格信息"]}',
            '{"pass": true, "issues": []}',
        ]
        response = client.post(
            "/api/confirm_content",
            json={"checkin_id": checkin.id, "content": "OpenAI 发布新产品，价格是 100 美元。"},
            headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["fact_pass"] is False
    assert data["fact_issues"] == ["新增了素材中没有的价格信息"]
    assert data["content_approved"] is False


def test_review_content_allows_completed_without_mutating_status(user, checkin, client, db):
    token = create_jwt_token(user.id)
    checkin.status = CheckInStatus.completed
    checkin.content = "已经发布的内容"
    db.commit()

    with patch("app.services.draft_service._quality_check", new_callable=AsyncMock) as mock_qc:
        mock_qc.return_value = {"pass": True, "issues": [], "available": True}
        response = client.post(
            "/api/review_content",
            json={"checkin_id": checkin.id, "content": "已经发布的内容"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["content_approved"] is True
    db.refresh(checkin)
    assert checkin.status == CheckInStatus.completed
    assert checkin.content == "已经发布的内容"


def test_revise_content_uses_quality_issues_and_persists_draft(user, checkin, client, db):
    token = create_jwt_token(user.id)
    checkin.status = CheckInStatus.pending
    checkin.content = "旧草稿"
    checkin.topic_source = "TechCrunch AI"
    checkin.topic_summary = "OpenAI 发布新产品。"
    db.commit()

    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [
            "改写后的草稿",
            '{"pass": true, "issues": []}',
        ]
        response = client.post(
            "/api/revise_content",
            json={
                "checkin_id": checkin.id,
                "content": "旧草稿",
                "issues": ["缺少明确判断"],
                "instruction": "更像参与讨论",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "改写后的草稿"
    assert data["char_count"] == len("改写后的草稿")
    db.refresh(checkin)
    assert checkin.content == "改写后的草稿"
    assert checkin.status == CheckInStatus.draft_ready

    prompt_text = mock_ai.await_args_list[0].args[0][0]["content"]
    assert "缺少明确判断" in prompt_text
    assert "更像参与讨论" in prompt_text
    assert "OpenAI 发布新产品" in prompt_text


def test_get_checkin_returns_topic_snapshot(user, checkin, client, db):
    token = create_jwt_token(user.id)
    checkin.topic_source = "TechCrunch AI"
    checkin.topic_url = "https://example.com/openai"
    checkin.topic_summary = "OpenAI 新增中间价格带。"
    checkin.topic_published_at = "2026-04-10T09:00:00Z"
    db.commit()

    response = client.get(
        f"/api/checkin/{checkin.id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["topic_source"] == "TechCrunch AI"
    assert data["topic_url"] == "https://example.com/openai"


def test_confirm_content_soft_signal_when_quality_fails(user, checkin, client, db):
    token = create_jwt_token(user.id)
    checkin.status = CheckInStatus.draft_ready
    checkin.content = "初稿内容"
    db.commit()

    with patch("app.services.draft_service._quality_check", new_callable=AsyncMock) as mock_qc:
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

    with patch("app.services.discussion_service.chat_completion", new_callable=AsyncMock):
        response = client.post(
            "/api/generate_content",
            json={"checkin_id": checkin.id, "message": "再说点什么"},
            headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 400
