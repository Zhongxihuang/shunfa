import json
from unittest.mock import AsyncMock, patch

import pytest

from app.models import CheckIn, CheckInStatus, User
from app.routers.user import create_jwt_token
from app.utils.time_utils import get_today_cst

VALID_LLM_RESPONSE = json.dumps(
    {
        "pages": ["这是第一段内容，介绍核心观点。", "这是第二段，补充细节。"],
        "title": "🔥 两句话说透这件事",
        "tags": ["AI", "热点", "科技", "观点", "独立思考"],
    },
    ensure_ascii=False,
)


@pytest.fixture
def user(db):
    u = User(openid="compose_test_user")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def checkin_with_content(user, db):
    c = CheckIn(
        user_id=user.id,
        date=get_today_cst(),
        topic="测试话题",
        content="这是一段测试正文，用来验证图文素材生成功能是否正常工作。内容足够长以触发分页逻辑。",
        status=CheckInStatus.draft_ready,
        refresh_count=0,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def checkin_no_content(user, db):
    c = CheckIn(
        user_id=user.id,
        date=get_today_cst(),
        topic="无内容话题",
        content=None,
        status=CheckInStatus.topic_selected,
        refresh_count=0,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_compose_post_assets_success(user, checkin_with_content, client):
    token = create_jwt_token(user.id)
    with patch("app.services.compose_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = VALID_LLM_RESPONSE
        response = client.post(
            "/api/compose_post_assets",
            json={"checkin_id": checkin_with_content.id, "template": "beige"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["pages"], list)
    assert 1 <= len(data["pages"]) <= 3
    assert isinstance(data["title"], str) and data["title"]
    assert isinstance(data["tags"], list) and len(data["tags"]) >= 1


def test_compose_post_assets_respects_dynamic_page_count(user, checkin_with_content, client):
    """Page count is determined by content, not hard-capped at 3."""
    token = create_jwt_token(user.id)
    four_pages = json.dumps(
        {
            "pages": ["p1", "p2", "p3", "p4"],
            "title": "标题",
            "tags": ["a", "b"],
        },
        ensure_ascii=False,
    )
    with patch("app.services.compose_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = four_pages
        response = client.post(
            "/api/compose_post_assets",
            json={"checkin_id": checkin_with_content.id, "template": "magazine"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    assert len(response.json()["pages"]) == 4


def test_compose_post_assets_invalid_json_retries_then_502(user, checkin_with_content, client):
    token = create_jwt_token(user.id)
    with patch("app.services.compose_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "not valid json {{"
        response = client.post(
            "/api/compose_post_assets",
            json={"checkin_id": checkin_with_content.id, "template": "beige"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 502
    assert mock_ai.call_count == 2  # retried once


def test_compose_post_assets_no_content_400(user, checkin_no_content, client):
    token = create_jwt_token(user.id)
    response = client.post(
        "/api/compose_post_assets",
        json={"checkin_id": checkin_no_content.id, "template": "beige"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_compose_post_assets_unauthenticated_403(checkin_with_content, client):
    response = client.post(
        "/api/compose_post_assets",
        json={"checkin_id": checkin_with_content.id, "template": "beige"},
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "forbidden"


def test_compose_post_assets_wrong_user_404(checkin_with_content, client, db):
    other = User(openid="other_compose_user")
    db.add(other)
    db.commit()
    db.refresh(other)
    token = create_jwt_token(other.id)
    response = client.post(
        "/api/compose_post_assets",
        json={"checkin_id": checkin_with_content.id, "template": "beige"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
