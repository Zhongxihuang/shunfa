"""Tests for the paste-to-cards image job feature."""

from unittest.mock import AsyncMock, patch

from app.models import ImageJob, ImageJobStatus, User
from app.routers.user import create_jwt_token


def _auth(user):
    return {"Authorization": f"Bearer {create_jwt_token(user.id)}"}


def _make_user(db, openid="ij_user"):
    user = User(openid=openid)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_image_job_model_defaults(db):
    user = _make_user(db)
    job = ImageJob(user_id=user.id, raw_text="第一段\n第二段", template="a")
    db.add(job)
    db.commit()
    db.refresh(job)

    assert job.id is not None
    assert job.template == "a"
    assert job.status == ImageJobStatus.draft
    assert job.page_count == 0
    assert job.created_at is not None


def test_image_job_create_request_rejects_empty_text():
    import pytest
    from pydantic import ValidationError

    from app.schemas import ImageJobCreateRequest

    with pytest.raises(ValidationError):
        ImageJobCreateRequest(raw_text="", template="a")


def test_image_job_create_request_defaults_template_a():
    from app.schemas import ImageJobCreateRequest

    req = ImageJobCreateRequest(raw_text="一些文字")
    assert req.template == "a"
    assert req.cover_title is None


def test_create_image_job_returns_pagination(client, db):
    user = _make_user(db, openid="ij_create")
    resp = client.post(
        "/api/image_jobs",
        json={"raw_text": "封面金句\n正文一\n正文二", "template": "b"},
        headers=_auth(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["template"] == "b"
    assert body["pages"][0]["kind"] == "cover"
    assert body["pages"][0]["title"] == "封面金句"
    assert body["page_count"] == 2
    assert body["overflow"] is False
    assert body["status"] == "draft"


def test_create_image_job_requires_auth(client, db):
    resp = client.post("/api/image_jobs", json={"raw_text": "x", "template": "a"})
    assert resp.status_code in (401, 403)


def test_get_image_job_returns_404_for_other_users_job(client, db):
    owner = _make_user(db, openid="ij_owner")
    other = _make_user(db, openid="ij_other")
    created = client.post(
        "/api/image_jobs",
        json={"raw_text": "封面\n正文", "template": "a"},
        headers=_auth(owner),
    ).json()
    resp = client.get(f"/api/image_jobs/{created['job_id']}", headers=_auth(other))
    assert resp.status_code == 404


def test_render_image_job_returns_base64_images(client, db):
    user = _make_user(db, openid="ij_render")
    created = client.post(
        "/api/image_jobs",
        json={"raw_text": "封面\n正文一\n正文二", "template": "a"},
        headers=_auth(user),
    ).json()

    with patch(
        "app.routers.image_jobs.render_cards",
        new=AsyncMock(return_value=[b"PNG1", b"PNG2"]),
    ):
        resp = client.post(
            f"/api/image_jobs/{created['job_id']}/render",
            json={"template": "c"},
            headers=_auth(user),
        )

    assert resp.status_code == 200
    body = resp.json()
    import base64

    assert body["template"] == "c"  # template override took effect
    assert body["images"][0] == base64.b64encode(b"PNG1").decode("ascii")
    assert len(body["images"]) == 2


def test_render_image_job_502_on_render_failure(client, db):
    user = _make_user(db, openid="ij_fail")
    created = client.post(
        "/api/image_jobs",
        json={"raw_text": "封面\n正文", "template": "a"},
        headers=_auth(user),
    ).json()

    with patch(
        "app.routers.image_jobs.render_cards",
        new=AsyncMock(side_effect=RuntimeError("chromium boom")),
    ):
        resp = client.post(
            f"/api/image_jobs/{created['job_id']}/render",
            json={},
            headers=_auth(user),
        )
    assert resp.status_code == 502
