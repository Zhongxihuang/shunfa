import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.models import User
from app.routers.user import create_jwt_token


def test_create_jwt_token():
    """Test JWT token creation."""
    token = create_jwt_token(1)
    assert isinstance(token, str)
    assert len(token) > 0


def test_login_creates_new_user(client, db):
    """Test that login creates a new user when openid is new."""
    with patch("app.routers.user.get_wechat_openid", new_callable=AsyncMock) as mock_get_openid:
        mock_get_openid.return_value = "test_openid_123"

        response = client.post("/api/login", json={"code": "test_code"})
        assert response.status_code == 200
        data = response.json()

        assert "token" in data
        assert "user" in data
        assert data["user"]["streak"] == 0
        assert data["user"]["points"] == 0
        assert data["user"]["level"] == 1
        assert data["user"]["diamonds"] == 3


def test_login_returns_existing_user(client, db):
    """Test that login returns existing user data."""
    # Create a user directly
    user = User(openid="existing_openid", streak=5, points=150, level=2, diamonds=4)
    db.add(user)
    db.commit()

    with patch("app.routers.user.get_wechat_openid", new_callable=AsyncMock) as mock_get_openid:
        mock_get_openid.return_value = "existing_openid"

        response = client.post("/api/login", json={"code": "test_code"})
        assert response.status_code == 200
        data = response.json()

        assert data["user"]["streak"] == 5
        assert data["user"]["points"] == 150
        assert data["user"]["level"] == 2


def test_login_idempotent(client, db):
    """Test that multiple logins with same openid don't create duplicate users."""
    with patch("app.routers.user.get_wechat_openid", new_callable=AsyncMock) as mock_get_openid:
        mock_get_openid.return_value = "same_openid"

        client.post("/api/login", json={"code": "code1"})
        client.post("/api/login", json={"code": "code2"})

        users = db.query(User).filter(User.openid == "same_openid").all()
        assert len(users) == 1


def test_user_status_requires_auth(client):
    """Test that user_status endpoint requires auth."""
    response = client.get("/api/user_status")
    assert response.status_code == 403  # No auth header = 403


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
