from app.models import CheckIn, CheckInStatus, User
from app.routers.user import create_jwt_token
from app.utils.time_utils import get_today_cst


def test_prompt_health_requires_auth(client):
    response = client.get("/api/admin/prompt_health")
    assert response.status_code == 403
    assert response.json()["error_code"] == "forbidden"


def test_prompt_health_rejects_regular_user(client, db):
    user = User(openid="regular_admin_probe")
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_jwt_token(user.id)
    response = client.get(
        "/api/admin/prompt_health",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_prompt_health_allows_web_admin(client, db):
    admin = User(openid="web_admin")
    checkin = CheckIn(
        user=admin,
        date=get_today_cst(),
        topic="测试话题",
        content="测试内容",
        status=CheckInStatus.completed,
        generation_context='{"prompt_version":"test-v1"}',
    )
    db.add_all([admin, checkin])
    db.commit()
    db.refresh(admin)

    token = create_jwt_token(admin.id)
    response = client.get(
        "/api/admin/prompt_health",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["by_version"]["test-v1"]["total_checkins"] == 1
