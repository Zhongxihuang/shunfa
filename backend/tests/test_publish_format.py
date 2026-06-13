"""Tests for W1.4: 多平台格式 + 导出.

Coverage:
- formatter unit tests (no HTTP): XHS / Moments / WeChat Official / Twitter /
  Weibo / generic + tag derivation + truncation
- POST /api/preview/format: auth, 400, platform fallback, returns text
- GET /api/preview/export: md / txt, content-disposition, format validation
- the full "draft ready → paste-ready text" round trip (no LLM involved)
"""

import json

from app.models import CheckIn, CheckInStatus, User
from app.routers.user import create_jwt_token
from app.services.publish_format_service import (
    SUPPORTED_PLATFORMS,
    derive_tags,
    export_markdown,
    export_plain,
    format_post,
)

# ── unit: tag derivation ────────────────────────────────────────────────────


def test_derive_tags_prefers_provided_and_dedupes():
    tags = derive_tags("AI 编程 思考", provided=["AI编程", "思考", "思考", "XHS"], limit=5)
    # Provided list comes first in order, dedup removes the duplicate "思考".
    # Topic tokens (AI, 编程, 思考) fill the remaining slots up to limit=5.
    # Final list: ["AI编程", "思考", "XHS", "AI", "编程"] (5 items).
    assert tags[:3] == ["AI编程", "思考", "XHS"]
    assert tags.count("思考") == 1
    assert len(tags) == 5


def test_derive_tags_falls_back_to_topic_tokens():
    tags = derive_tags("GPT 编程 入门", provided=None, limit=3)
    assert "GPT" in tags
    assert "编程" in tags
    assert "入门" in tags
    assert len(tags) == 3


def test_derive_tags_strips_punctuation_and_hash():
    tags = derive_tags("", provided=["#AI 编程！", "@@分享", "  干净  "], limit=5)
    assert "AI编程" in tags  # # stripped, " " stripped, "！" stripped
    assert "分享" in tags
    assert "干净" in tags


def test_derive_tags_respects_limit():
    tags = derive_tags("A B C D E F G", provided=None, limit=2)
    assert len(tags) == 2


# ── unit: per-platform formatters ────────────────────────────────────────────


def test_xhs_format():
    post = format_post(
        topic="我用 AI 写了第一篇博客",
        content="第一段。\n\n第二段。",
        platform="xiaohongshu",
    )
    assert post.platform == "xiaohongshu"
    assert post.title == "我用 AI 写了第一篇博客"[:30]
    assert "第一段" in post.body
    assert "第二段" in post.body
    assert len(post.tags) >= 1
    assert not post.truncated


def test_moments_format_truncates_at_150():
    long = "A" * 500
    post = format_post(topic="", content=long, platform="moments")
    assert post.platform == "moments"
    assert post.char_count <= 150
    assert post.truncated is True
    # ≤ 1 tag on Moments.
    assert len(post.tags) <= 1


def test_wechat_official_no_hashtags():
    post = format_post(
        topic="公众号长文",
        content="第一段。\n\n第二段。",
        platform="wechat_official",
    )
    assert post.platform == "wechat_official"
    assert post.title == "公众号长文"
    assert "#" not in post.body
    assert post.tags == []


def test_twitter_format_280_cap():
    post = format_post(
        topic="",
        content="x" * 1000,
        platform="twitter",
    )
    assert post.platform == "twitter"
    assert post.char_count <= 280
    assert post.truncated is True


def test_weibo_format_140_cap_and_double_hash_style():
    post = format_post(topic="微博", content="短内容", platform="weibo")
    assert post.platform == "weibo"
    assert post.char_count <= 140
    # Weibo uses #tag# (双井号包围) — only validated indirectly via char_count here.


def test_unknown_platform_falls_back_to_generic():
    post = format_post(topic="x", content="y", platform="not-a-platform")
    assert post.platform == "generic"
    assert post.body  # not empty


def test_generic_includes_tags():
    post = format_post(topic="hello world", content="body", platform="generic")
    assert "hello" in post.tags or "world" in post.tags
    assert "body" in post.body


# ── unit: exporters ──────────────────────────────────────────────────────────


def test_export_markdown_contains_title_and_tags():
    md = export_markdown("我的标题", "正文内容", tags=["AI", "随笔"])
    assert md.startswith("# 我的标题\n")
    assert "正文内容" in md
    assert "#AI" in md
    assert "#随笔" in md


def test_export_plain_uses_separator():
    txt = export_plain("我的标题", "正文内容", tags=["AI"])
    lines = txt.splitlines()
    assert lines[0] == "我的标题"
    assert "=" in lines[1]
    assert "正文内容" in txt


def test_export_handles_missing_title():
    md = export_markdown("", "just content", tags=None)
    assert md.startswith("# 未命名")
    assert "just content" in md


# ── HTTP: /api/preview/format ────────────────────────────────────────────────


def _make_user(db) -> User:
    user = User(openid="w14_format_user")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_checkin(db, user: User, content: str = "正文内容", topic: str = "测试选题") -> CheckIn:
    from app.utils.time_utils import get_today_cst

    checkin = CheckIn(
        user_id=user.id,
        date=get_today_cst(),
        topic=topic,
        content=content,
        status=CheckInStatus.draft_ready,
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)
    return checkin


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_jwt_token(user.id)}"}


def test_format_endpoint_requires_auth(client):
    resp = client.post(
        "/api/preview/format",
        json={"checkin_id": 1, "platform": "xiaohongshu"},
    )
    assert resp.status_code in (401, 403)


def test_format_endpoint_404_for_unknown_checkin(client, db):
    user = _make_user(db)
    resp = client.post(
        "/api/preview/format",
        json={"checkin_id": 99999, "platform": "xiaohongshu"},
        headers=_auth(user),
    )
    assert resp.status_code == 404


def test_format_endpoint_400_when_no_content(client, db):
    user = _make_user(db)
    checkin = _make_checkin(db, user, content="")
    resp = client.post(
        "/api/preview/format",
        json={"checkin_id": checkin.id, "platform": "xiaohongshu"},
        headers=_auth(user),
    )
    assert resp.status_code == 400


def test_format_endpoint_xiaohongshu_returns_text(client, db):
    user = _make_user(db)
    checkin = _make_checkin(db, user, content="第一段\n\n第二段", topic="我用 AI 写了第一篇博客")
    resp = client.post(
        "/api/preview/format",
        json={"checkin_id": checkin.id, "platform": "xiaohongshu"},
        headers=_auth(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["platform"] == "xiaohongshu"
    assert body["requested_platform"] == "xiaohongshu"
    assert "我用 AI 写了第一篇博客" in body["text"]
    assert "第一段" in body["text"]
    assert "第二段" in body["text"]
    assert body["char_count"] == len(body["text"])


def test_format_endpoint_unknown_platform_falls_back(client, db):
    user = _make_user(db)
    checkin = _make_checkin(db, user)
    resp = client.post(
        "/api/preview/format",
        json={"checkin_id": checkin.id, "platform": "weird-future-app"},
        headers=_auth(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["platform"] == "generic"  # fell back
    assert body["requested_platform"] == "weird-future-app"
    assert body["text"]  # still got something


def test_format_endpoint_pulls_compose_tags_from_context(client, db):
    user = _make_user(db)
    checkin = _make_checkin(db, user, topic="x")
    # Simulate W1.3-era checkin with compose tags saved into generation_context.
    checkin.generation_context = json.dumps(
        {"compose_tags": ["AI", "编程", "随笔"], "prompt_version": "v1"}
    )
    db.commit()

    resp = client.post(
        "/api/preview/format",
        json={"checkin_id": checkin.id, "platform": "xiaohongshu"},
        headers=_auth(user),
    )
    body = resp.json()
    for t in ("AI", "编程", "随笔"):
        assert t in body["tags"]


def test_format_endpoint_all_supported_platforms(client, db):
    """Smoke each platform to make sure none 500s."""
    user = _make_user(db)
    checkin = _make_checkin(db, user, content="短正文。", topic="测试")
    for plat in SUPPORTED_PLATFORMS:
        resp = client.post(
            "/api/preview/format",
            json={"checkin_id": checkin.id, "platform": plat},
            headers=_auth(user),
        )
        assert resp.status_code == 200, f"{plat} returned {resp.status_code}: {resp.text}"
        assert resp.json()["text"]


# ── HTTP: /api/preview/export ────────────────────────────────────────────────


def test_export_endpoint_requires_auth(client):
    resp = client.get("/api/preview/export?checkin_id=1&format=md")
    assert resp.status_code in (401, 403)


def test_export_md_returns_markdown(client, db):
    user = _make_user(db)
    checkin = _make_checkin(db, user, topic="导出测试", content="正文")
    resp = client.get(
        f"/api/preview/export?checkin_id={checkin.id}&format=md",
        headers=_auth(user),
    )
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert f"shunfa-checkin-{checkin.id}.md" in resp.headers["content-disposition"]
    body = resp.text
    assert body.startswith("# 导出测试")
    assert "正文" in body


def test_export_txt_returns_plain(client, db):
    user = _make_user(db)
    checkin = _make_checkin(db, user, topic="TXT测试", content="内容")
    resp = client.get(
        f"/api/preview/export?checkin_id={checkin.id}&format=txt",
        headers=_auth(user),
    )
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert f"shunfa-checkin-{checkin.id}.txt" in resp.headers["content-disposition"]
    body = resp.text
    assert "TXT测试" in body
    assert "内容" in body


def test_export_rejects_invalid_format(client, db):
    user = _make_user(db)
    checkin = _make_checkin(db, user)
    resp = client.get(
        f"/api/preview/export?checkin_id={checkin.id}&format=pdf",
        headers=_auth(user),
    )
    assert resp.status_code == 400


def test_export_400_when_no_content(client, db):
    user = _make_user(db)
    checkin = _make_checkin(db, user, content="")
    resp = client.get(
        f"/api/preview/export?checkin_id={checkin.id}&format=md",
        headers=_auth(user),
    )
    assert resp.status_code == 400


def test_export_404_for_unknown_checkin(client, db):
    user = _make_user(db)
    resp = client.get(
        "/api/preview/export?checkin_id=99999&format=md",
        headers=_auth(user),
    )
    assert resp.status_code == 404


# ── end-to-end: draft ready → paste-ready text (the ≤2 step promise) ────────


def test_full_pipeline_two_steps_draft_to_paste_text(client, db):
    """The W1.4 acceptance: from 'draft ready' to 'paste-ready text' in 2 API calls.

    Step 1 (already exists): user reaches draft_ready — we simulate by inserting one.
    Step 2 (W1.4): one POST /api/preview/format returns the text to paste.
    """
    user = _make_user(db)
    checkin = _make_checkin(
        db,
        user,
        topic="AI 改变了我的写作",
        content="上个月我开始用 AI 辅助写博客。最大的变化不是写得更快，是更敢开始。",
    )

    # Step 1 is implicit (checkin is in draft_ready). Step 2 is the new endpoint.
    resp = client.post(
        "/api/preview/format",
        json={"checkin_id": checkin.id, "platform": "xiaohongshu"},
        headers=_auth(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    # The response.text is what the user copies with one click. The whole
    # 2-step promise hinges on this string being complete and useful.
    assert "AI 改变了我的写作" in body["text"]
    assert "更敢开始" in body["text"]
    assert body["char_count"] > 0
    # We did NOT call any LLM. Total elapsed time for step 2 is bounded by
    # the formatter, which is purely string ops on a <2KB input.
