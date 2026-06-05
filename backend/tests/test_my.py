from datetime import date, timedelta

from app.models import CheckIn, CheckInStatus, User
from app.routers.user import create_jwt_token


def _auth_headers(user_id: int):
    token = create_jwt_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def _create_checkin(
    db, user_id: int, d: date, content_approved: bool = True, status=CheckInStatus.completed
):
    checkin = CheckIn(
        user_id=user_id,
        date=d,
        topic=f"Topic on {d}",
        content=f"Content on {d}",
        status=status,
        content_approved=content_approved,
    )
    db.add(checkin)
    db.commit()
    return checkin


class TestMyCheckins:
    def test_get_my_checkins_empty(self, client, db):
        user = User(openid="test_empty_user")
        db.add(user)
        db.commit()

        response = client.get("/api/my/checkins", headers=_auth_headers(user.id))
        assert response.status_code == 200
        data = response.json()
        assert data["checkins"] == []
        assert data["total"] == 0
        assert data["draft_count"] == 0

    def test_get_my_checkins_with_checkins(self, client, db):
        user = User(openid="test_user_checkins")
        db.add(user)
        db.commit()

        today = date.today()
        _create_checkin(db, user.id, today, content_approved=True)
        _create_checkin(db, user.id, today - timedelta(days=1), content_approved=False)

        response = client.get("/api/my/checkins", headers=_auth_headers(user.id))
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["draft_count"] == 0  # both are completed

    def test_get_my_checkins_filter_completed(self, client, db):
        user = User(openid="test_filter_user")
        db.add(user)
        db.commit()

        today = date.today()
        _create_checkin(db, user.id, today, status=CheckInStatus.completed)
        _create_checkin(db, user.id, today - timedelta(days=1), status=CheckInStatus.discussing)

        response = client.get(
            "/api/my/checkins?status_filter=completed", headers=_auth_headers(user.id)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

        response = client.get(
            "/api/my/checkins?status_filter=draft", headers=_auth_headers(user.id)
        )
        data = response.json()
        assert data["draft_count"] == 1


class TestMyStats:
    def test_get_my_stats_empty(self, client, db):
        user = User(openid="test_stats_empty")
        db.add(user)
        db.commit()

        response = client.get("/api/my/stats", headers=_auth_headers(user.id))
        assert response.status_code == 200
        data = response.json()

        assert "last_30_days" in data
        assert "summary" in data
        # 30 days all zero
        assert len(data["last_30_days"]) == 30
        assert all(day["total"] == 0 for day in data["last_30_days"])
        assert data["summary"]["total"] == 0
        assert data["summary"]["approved"] == 0
        assert data["summary"]["approval_rate"] == 0.0

    def test_get_my_stats_with_checkins(self, client, db):
        user = User(openid="test_stats_user")
        db.add(user)
        db.commit()

        today = date.today()
        d5 = today - timedelta(days=5)
        d4 = today - timedelta(days=4)
        d3 = today - timedelta(days=3)
        d10 = today - timedelta(days=10)
        d20 = today - timedelta(days=20)

        # day 5: approved (2/2 total since we can't duplicate dates)
        _create_checkin(db, user.id, d5, content_approved=True)
        # day 4: not approved
        _create_checkin(db, user.id, d4, content_approved=False)
        # day 3: approved
        _create_checkin(db, user.id, d3, content_approved=True)
        # day 10: approved
        _create_checkin(db, user.id, d10, content_approved=True)
        # day 20: not approved
        _create_checkin(db, user.id, d20, content_approved=False)

        response = client.get("/api/my/stats", headers=_auth_headers(user.id))
        assert response.status_code == 200
        data = response.json()

        # day 5: 1 total, 1 approved → rate 1.0
        day5_data = next((d for d in data["last_30_days"] if d["date"] == str(d5)), None)
        assert day5_data is not None
        assert day5_data["total"] == 1
        assert day5_data["approved"] == 1
        assert day5_data["approval_rate"] == 1.0

        # day 4: 1 total, 0 approved → rate 0.0
        day4_data = next((d for d in data["last_30_days"] if d["date"] == str(d4)), None)
        assert day4_data["total"] == 1
        assert day4_data["approved"] == 0
        assert day4_data["approval_rate"] == 0.0

        # summary: 5 total, 3 approved → rate 0.6
        assert data["summary"]["total"] == 5
        assert data["summary"]["approved"] == 3
        assert data["summary"]["approval_rate"] == 0.6

    def test_get_my_stats_requires_auth(self, client):
        response = client.get("/api/my/stats")
        # No auth header → HTTPBearer denies with 403
        assert response.status_code in (401, 403)

    def test_get_my_stats_fills_missing_days(self, client, db):
        """Days with no checkins should still appear with 0 values."""
        user = User(openid="test_stats_gaps")
        db.add(user)
        db.commit()

        today = date.today()
        # Only checkin on day 15
        _create_checkin(db, user.id, today - timedelta(days=15), content_approved=True)

        response = client.get("/api/my/stats", headers=_auth_headers(user.id))
        assert response.status_code == 200
        data = response.json()

        # All 30 days present
        assert len(data["last_30_days"]) == 30
        # Day 15 has the checkin
        day15_str = str(today - timedelta(days=15))
        day15 = next((d for d in data["last_30_days"] if d["date"] == day15_str), None)
        assert day15 is not None
        assert day15["total"] == 1
        assert day15["approved"] == 1
