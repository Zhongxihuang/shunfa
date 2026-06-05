from app.models import User
from app.routers.user import create_jwt_token


def test_create_jwt_token():
    """Test JWT token creation."""
    token = create_jwt_token(1)
    assert isinstance(token, str)
    assert len(token) > 0


def test_user_status_requires_auth(client):
    """Test that user_status endpoint requires auth."""
    response = client.get("/api/user_status")
    assert response.status_code == 401
    assert response.json()["error_code"] == "invalid_token"


def test_user_status_with_valid_token(client, db):
    """Test user_status with valid JWT."""
    # Create user and token
    user = User(openid="auth_test_openid", streak=3)
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_jwt_token(user.id)
    response = client.get("/api/user_status", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["streak"] == 3


def test_api_key_status_returns_masked_preview_only(client, db):
    user = User(openid="preview_key_user")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_jwt_token(user.id)

    save_response = client.post(
        "/api/user/api_key",
        json={"api_key": "sk-test-secret-123456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    status_response = client.get(
        "/api/user/api_key/status",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert save_response.status_code == 200
    assert save_response.json()["preview"] == "...3456"
    assert status_response.json()["preview"] == "...3456"
    assert "sk-test-secret" not in str(save_response.json())
    assert "sk-test-secret" not in str(status_response.json())


def test_short_api_key_status_returns_no_usable_preview(client, db):
    user = User(openid="short_key_user")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_jwt_token(user.id)

    response = client.post(
        "/api/user/api_key",
        json={"api_key": "sk-1234567"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["preview"] is None
