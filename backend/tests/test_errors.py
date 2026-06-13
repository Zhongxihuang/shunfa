from app.config import settings
from app.models import User
from app.routers.user import create_jwt_token


def test_missing_api_key_returns_error_code(client, db):
    original_require_user_api_key = settings.require_user_api_key
    settings.require_user_api_key = True
    try:
        user = User(openid="missing_api_key_user")
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_jwt_token(user.id)

        response = client.post(
            "/api/daily_topics",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        settings.require_user_api_key = original_require_user_api_key

    assert response.status_code == 400
    assert response.json()["error_code"] == "missing_api_key"
    assert "DeepSeek" in response.json()["message"]


def test_invalid_token_returns_error_code(client):
    response = client.get("/api/user_status", headers={"Authorization": "Bearer invalid"})

    assert response.status_code == 401
    assert response.json()["error_code"] == "invalid_token"
