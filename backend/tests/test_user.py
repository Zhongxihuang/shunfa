from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

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
