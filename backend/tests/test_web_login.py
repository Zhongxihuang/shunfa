import pytest
from app.models import User
from app.routers.user import create_jwt_token


def test_web_login_correct_password(client, db):
    """Correct password returns token and user."""
    response = client.post("/api/web_login", json={"password": "test123"})
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert "user" in data
    assert data["user"]["streak"] == 0


def test_web_login_wrong_password(client, db):
    """Wrong password returns 401."""
    response = client.post("/api/web_login", json={"password": "wrongpassword"})
    assert response.status_code == 401


def test_web_login_idempotent(client, db):
    """Multiple logins with correct password return same user."""
    client.post("/api/web_login", json={"password": "test123"})
    client.post("/api/web_login", json={"password": "test123"})

    users = db.query(User).filter(User.openid == "web_admin").all()
    assert len(users) == 1


def test_web_login_token_works_for_user_status(client, db):
    """Token from web_login can access /api/user_status."""
    resp = client.post("/api/web_login", json={"password": "test123"})
    token = resp.json()["token"]

    status_resp = client.get("/api/user_status", headers={"Authorization": f"Bearer {token}"})
    assert status_resp.status_code == 200
    assert "streak" in status_resp.json()
