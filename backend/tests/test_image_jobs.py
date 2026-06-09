"""Tests for the paste-to-cards image job feature."""

from app.models import ImageJob, ImageJobStatus, User


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
