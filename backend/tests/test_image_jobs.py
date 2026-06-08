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
