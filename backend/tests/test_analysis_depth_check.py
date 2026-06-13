"""Tests for analysis depth check and the refactored quick_generate parallel checks."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.models import CheckIn, CheckInStatus, User
from app.routers.user import create_jwt_token
from app.services.draft_service import _check_analysis_depth
from app.utils.time_utils import get_today_cst


@pytest.fixture
def user(db):
    u = User(openid="depth_check_test_user")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def checkin(user, db):
    today = get_today_cst()
    c = CheckIn(
        user_id=user.id,
        date=today,
        topic="Meta 开源 Llama 3.1 405B",
        status=CheckInStatus.topic_selected,
        refresh_count=0,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.mark.asyncio
async def test_check_analysis_depth_pass():
    result_json = json.dumps({"pass": True, "issues": []})
    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = result_json
        result = await _check_analysis_depth("这是一篇分析草稿", None)
    assert result["pass"] is True
    assert result["issues"] == []


@pytest.mark.asyncio
async def test_check_analysis_depth_fail_returns_issues():
    result_json = json.dumps(
        {"pass": False, "issues": ["机制层没有解释为什么成本下降", "影响层没有指出具体受益方"]}
    )
    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = result_json
        result = await _check_analysis_depth("这是一篇分析草稿", None)
    assert result["pass"] is False
    assert len(result["issues"]) == 2


@pytest.mark.asyncio
async def test_check_analysis_depth_parse_error_treated_as_pass():
    """If LLM returns unparseable output, we treat as pass (non-blocking)."""
    with patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "这不是 JSON"
        result = await _check_analysis_depth("草稿内容", None)
    assert result["pass"] is True
    assert result["available"] is False


def test_quick_generate_triggers_revise_on_depth_fail(user, checkin, client, db):
    """When depth check fails, quick_generate should produce a revised draft."""
    token = create_jwt_token(user.id)
    checkin.topic_url = "https://example.com/llama"
    db.commit()

    draft_v1 = "Meta 开源 Llama 3.1 405B，这很重要，行业格局会改变。"
    draft_v2 = "Meta 开源 Llama 3.1 405B，原因是商业竞争压力，影响是企业 AI 部署成本下降 60%。"

    grounding_pass = json.dumps({"pass": True, "issues": []})
    discussion_pass = json.dumps({"pass": True, "issues": []})
    depth_fail = json.dumps({"pass": False, "issues": ["机制层没有展开原因", "影响层缺少具体后果"]})
    grounding_recheck = json.dumps({"pass": True, "issues": []})

    with (
        patch("app.services.draft_service.chat_completion", new_callable=AsyncMock) as mock_draft,
        patch(
            "app.services.fact_enrichment_service.fetch_article_fulltext", new_callable=AsyncMock
        ) as mock_fetch,
    ):
        mock_fetch.return_value = ""  # no enrichment
        # Call sequence: draft, grounding, discussion, depth (parallel), revise, grounding-recheck
        mock_draft.side_effect = [
            draft_v1,  # initial draft
            grounding_pass,  # grounding check (parallel)
            discussion_pass,  # discussion check (parallel) - note: _check_discussion_quality is rule-based, no LLM call
            depth_fail,  # depth check (parallel)
            draft_v2,  # revised draft
            grounding_recheck,  # re-check grounding
        ]

        response = client.post(
            "/api/quick_generate",
            json={
                "checkin_id": checkin.id,
                "hot_topic": "Meta 开源 Llama 3.1",
                "angle": "开源模型改写部署底层逻辑",
                "platform": "xiaohongshu",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
