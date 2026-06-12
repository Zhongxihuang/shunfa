"""W2.x closed-loop smoke: main path (checkin → publish) AND the
independent paste-to-cards side tool (image_jobs → render) in one session.

The two paths share auth and user state but nothing else — image_jobs
does not touch streak/points. This test asserts the whole product loop
plus the side tool from a freshly registered user's perspective.
"""

from unittest.mock import AsyncMock, patch

from app.models import CheckIn, CheckInStatus, ImageJob, ImageJobStatus, User
from app.routers.user import _hash_password
from app.utils.time_utils import get_today_cst


async def _fake_quick_generate(**kwargs):
    return {
        "content": "顺发把启动摩擦压进一条不断点的闭环。\n先发出去，习惯才有机会发生。",
        "platform": kwargs.get("platform", "xiaohongshu"),
        "char_count": 40,
        "fact_pass": True,
        "fact_issues": [],
        "discussion_pass": True,
        "discussion_issues": [],
    }


async def _fake_confirm_content(checkin, content, db, api_key=""):
    checkin.content = content
    checkin.content_approved = True
    checkin.status = CheckInStatus.pending
    db.commit()
    return {
        "quality_pass": True,
        "quality_issues": [],
        "quality_available": True,
        "fact_pass": True,
        "fact_issues": [],
        "discussion_pass": True,
        "discussion_issues": [],
        "topic": checkin.topic,
    }


async def _fake_compose_assets(checkin, api_key):
    return {
        "pages": ["先发出去，习惯才有机会发生。", "顺发把启动摩擦压成一条闭环。"],
        "title": "先发出去",
        "tags": ["顺发", "表达", "AI", "发布", "闭环"],
    }


async def _fake_generate_post_copy(content, api_key=""):
    return {"title": "AI 生成的标题：先发出去", "tags": ["顺发", "闭环", "表达"]}


def test_w2x_closed_loop_main_path_and_paste_to_cards(client, db):
    """End-to-end: register → save BYOK key → main path checkin+publish
    → independent paste-to-cards flow → assert both paths' final state."""
    today = get_today_cst()
    user = User(
        openid="w2x_smoke_openid",
        username="w2x_smoke_user",
        password_hash=_hash_password("test"),
        deepseek_api_key="sk-w2x-smoke-key",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # ── Auth: login with username + password (web path) ─────────────────────
    login_response = client.post(
        "/api/auth_login",
        json={"username": "w2x_smoke_user", "password": "test"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # ── Main path: pick topic → quick generate → confirm → compose → publish ──
    checkin = CheckIn(
        user_id=user.id,
        date=today,
        topic="完美主义让表达变难",
        status=CheckInStatus.topic_selected,
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)

    with (
        patch(
            "app.services.generation_orchestrator.quick_generate",
            new=AsyncMock(side_effect=_fake_quick_generate),
        ),
        patch(
            "app.routers.content.confirm_content",
            new=AsyncMock(side_effect=_fake_confirm_content),
        ),
        patch(
            "app.routers.content.compose_post_assets",
            new=AsyncMock(side_effect=_fake_compose_assets),
        ),
    ):
        # 1. quick generate fills the draft
        quick_resp = client.post(
            "/api/quick_generate",
            json={
                "checkin_id": checkin.id,
                "hot_topic": checkin.topic,
                "angle": "低摩擦闭环",
                "platform": "xiaohongshu",
            },
            headers=headers,
        )
        assert quick_resp.status_code == 200
        draft = quick_resp.json()["content"]
        assert "闭环" in draft

        # 2. confirm content runs the quality check
        confirm_resp = client.post(
            "/api/confirm_content",
            json={"checkin_id": checkin.id, "content": draft},
            headers=headers,
        )
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["status"] == "pending"

        # 3. compose post assets (returns pages + title + tags)
        compose_resp = client.post(
            "/api/compose_post_assets",
            json={"checkin_id": checkin.id, "template": "beige"},
            headers=headers,
        )
        assert compose_resp.status_code == 200
        assert len(compose_resp.json()["pages"]) == 2
        assert compose_resp.json()["title"]

        # 4. confirm publish: real streak/points get written
        publish_resp = client.post(
            "/api/confirm_publish",
            json={"checkin_id": checkin.id},
            headers=headers,
        )
        assert publish_resp.status_code == 200
        published = publish_resp.json()
        assert published["points_earned"] > 0
        assert published["streak"] == 1

    # Main-path state assertions (DB side).
    db.refresh(checkin)
    db.refresh(user)
    assert checkin.status == CheckInStatus.completed
    assert checkin.points_earned == published["points_earned"]
    assert user.streak == 1
    assert user.points == published["total_points"]

    # ── Side path: paste-to-cards (W2.x) ─────────────────────────────────────
    # Mock both the AI copy and the render — paste-to-cards is fully
    # independent from streak/points, so user state must NOT change.
    with (
        patch(
            "app.services.compose_service.chat_completion",
            new=AsyncMock(side_effect=lambda *a, **kw: '{"pages":["p"],'
            '"title":"小红书风标题","tags":["AI","效率","发布"]}'),
        ),
        patch(
            "app.routers.image_jobs.render_cards",
            new=AsyncMock(return_value=[b"\x89PNG\r\n\x1a\n" + b"a" * 200] * 2),
        ),
    ):
        # 1. paste text → create image job (also fires AI copy generation)
        paste_resp = client.post(
            "/api/image_jobs",
            json={
                "raw_text": draft,
                "template": "a",
                "cover_title": "封面金句",
            },
            headers=headers,
        )
        assert paste_resp.status_code == 200
        paste_body = paste_resp.json()
        job_id = paste_body["job_id"]
        assert paste_body["ai_title"] == "小红书风标题"
        assert paste_body["ai_tags"] == ["AI", "效率", "发布"]
        assert paste_body["page_count"] >= 1

        # 2. render the job to base64 PNGs
        render_resp = client.post(
            f"/api/image_jobs/{job_id}/render",
            json={"template": "b"},
            headers=headers,
        )
        assert render_resp.status_code == 200
        render_body = render_resp.json()
        assert render_body["template"] == "b"
        assert len(render_body["images"]) == 2
        # base64 decodes back to something PNG-shaped
        import base64
        decoded = base64.b64decode(render_body["images"][0])
        assert decoded.startswith(b"\x89PNG")

    # 3. GET round-trips the persisted copy (LLM mock is gone)
    get_resp = client.get(f"/api/image_jobs/{job_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["ai_title"] == "小红书风标题"
    assert get_resp.json()["ai_tags"] == ["AI", "效率", "发布"]

    # 4. Job DB state.
    job = db.query(ImageJob).filter(ImageJob.id == job_id).one()
    assert job.status == ImageJobStatus.rendered
    assert job.template == "b"  # last render set the template
    assert job.page_count == render_body["page_count"]

    # ── Final invariant: image_jobs did NOT touch streak/points ──────────────
    db.refresh(user)
    assert user.streak == 1
    assert user.points == published["total_points"]
    # The main-path publish and the side tool are isolated.
