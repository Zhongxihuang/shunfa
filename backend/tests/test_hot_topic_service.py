"""Tests for hot topic AI scoring and angle generation."""

import json
from datetime import UTC, datetime

import pytest
from unittest.mock import AsyncMock, patch

from app.services.hot_topic_service import (
    score_articles,
    generate_angles,
    score_and_filter,
)
from app.schemas import RawArticle, TopicCategory

# Use UTC ISO format so _is_recent() passes the 3-day filter in tests
RECENT_DATE = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


SAMPLE_ARTICLES = [
    RawArticle(
        title="DeepSeek V4 Released: 50% Cost Reduction",
        link="https://hn.com/1",
        source="Hacker News",
        summary="DeepSeek announced V4 with major cost improvements.",
        published_date=RECENT_DATE,
    ),
    RawArticle(
        title="Company X Hires 50 AI Engineers",
        link="https://hn.com/2",
        source="Hacker News",
        summary="Routine hiring announcement.",
        published_date=RECENT_DATE,
    ),
    RawArticle(
        title="OpenAI GPT-5 Pricing Increases 20%",
        link="https://vb.com/1",
        source="VentureBeat AI",
        summary="OpenAI raised API prices.",
        published_date=RECENT_DATE,
    ),
]


# ── score_articles ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_articles_returns_scores():
    mock_response = json.dumps([
        {"index": 0, "score": 8, "category": "ai_model"},
        {"index": 1, "score": 3, "category": "industry"},
        {"index": 2, "score": 7, "category": "ai_product"},
    ])

    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = mock_response
        scores = await score_articles(SAMPLE_ARTICLES)

    assert len(scores) == 3
    assert scores[0]["score"] == 8
    assert scores[1]["score"] == 3
    assert scores[2]["score"] == 7


@pytest.mark.asyncio
async def test_score_articles_handles_invalid_json():
    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "not valid json at all"
        scores = await score_articles(SAMPLE_ARTICLES)

    assert len(scores) == 3
    assert all("score" in item for item in scores)


@pytest.mark.asyncio
async def test_score_articles_empty_input():
    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        scores = await score_articles([])

    mock_ai.assert_not_called()
    assert scores == []


# ── generate_angles ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_angles_returns_angles():
    mock_response = json.dumps({
        "ai_angle": "国产AI的性价比之战已经进入白热化阶段...",
        "ai_counter_angle": "成本降低不等于质量提升...",
    })

    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = mock_response
        angles = await generate_angles("DeepSeek V4 Released", "Cost reduction summary")

    assert angles["ai_angle"] == "国产AI的性价比之战已经进入白热化阶段..."
    assert angles["ai_counter_angle"] == "成本降低不等于质量提升..."


@pytest.mark.asyncio
async def test_generate_angles_handles_invalid_json():
    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "Some non-JSON response from AI"
        angles = await generate_angles("Test topic")

    assert angles["ai_angle"] != ""
    assert angles["ai_counter_angle"] != ""


# ── score_and_filter ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_and_filter_returns_qualifying_topics():
    score_response = json.dumps([
        {"index": 0, "score": 8, "category": "ai_model"},
        {"index": 1, "score": 3, "category": "industry"},   # below threshold (3 < 8)
        {"index": 2, "score": 8, "category": "ai_product"}, # qualifies (8 >= 8)
    ])
    angle_response = json.dumps({
        "ai_angle": "Some insight angle",
        "ai_counter_angle": "Counter perspective",
    })
    # translate response: line-by-line "[idx] content" format
    translate_titles_response = "[0] DeepSeek V4发布：成本降低50%\n[1] X公司招聘50名AI工程师\n[2] OpenAI GPT-5定价上涨20%"
    translate_response = "[0] DeepSeek发布V4，成本大降\n[1] X公司招聘50名AI工程师\n[2] OpenAI GPT-5涨价20%"

    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [translate_titles_response, translate_response, score_response, angle_response, angle_response]
        topics = await score_and_filter(SAMPLE_ARTICLES)

    assert len(topics) == 2
    # Sorted by (score + source_boost, title):
    # VentureBeat has no boost → effective 8, Hacker News has -5 boost → effective 3
    # VentureBeat article (score 8) ranks first
    assert topics[0].score == 8
    assert topics[0].hot_source == "VentureBeat AI"
    assert topics[1].score == 8
    assert topics[1].hot_source == "Hacker News"
    assert topics[0].topic_category == TopicCategory.ai_product


@pytest.mark.asyncio
async def test_score_and_filter_empty_input():
    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        topics = await score_and_filter([])

    mock_ai.assert_not_called()
    assert topics == []


@pytest.mark.asyncio
async def test_score_and_filter_falls_back_when_all_below_threshold():
    score_response = json.dumps([
        {"index": 0, "score": 1, "category": "industry"},
        {"index": 1, "score": 2, "category": "industry"},
        {"index": 2, "score": 3, "category": "industry"},
    ])
    angle_response = json.dumps({
        "ai_angle": "Some insight angle",
        "ai_counter_angle": "Counter perspective",
    })
    # translate response: line-by-line format
    translate_titles_response = "[0] 标题1\n[1] 标题2\n[2] 标题3"
    translate_response = "[0] Translated 1\n[1] Translated 2\n[2] Translated 3"

    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [translate_titles_response, translate_response, score_response, angle_response, angle_response, angle_response]
        topics = await score_and_filter(SAMPLE_ARTICLES)

    assert len(topics) == 3
    assert all(topic.hot_url for topic in topics)


@pytest.mark.asyncio
async def test_score_and_filter_preserves_url_and_summary():
    score_response = json.dumps([{"index": 0, "score": 8, "category": "ai_model"}])
    angle_response = json.dumps({"ai_angle": "Some angle", "ai_counter_angle": "Counter"})
    # Translation is called for qualifying articles; summary gets replaced by translated version
    translate_titles_response = "[0] DeepSeek V4发布成本大降"
    translate_response = "[0] DeepSeek发布V4，成本大幅降低"

    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [translate_titles_response, translate_response, score_response, angle_response]
        topics = await score_and_filter([SAMPLE_ARTICLES[0]])

    assert len(topics) == 1
    assert topics[0].hot_url == "https://hn.com/1"
    # summary is replaced by translated version
    assert topics[0].hot_summary == "DeepSeek发布V4，成本大幅降低"


@pytest.mark.asyncio
async def test_score_and_filter_all_below_threshold():
    score_response = json.dumps([
        {"index": 0, "score": 2, "category": "industry"},
        {"index": 1, "score": 3, "category": "industry"},
        {"index": 2, "score": 4, "category": "industry"},
    ])
    angle_response = json.dumps({"ai_angle": "Test angle", "ai_counter_angle": "Counter"})
    # translate response: line-by-line format
    translate_titles_response = "[0] t0标题\n[1] t1标题\n[2] t2标题"
    translate_response = "[0] t0\n[1] t1\n[2] t2"

    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [translate_titles_response, translate_response, score_response, angle_response, angle_response, angle_response]
        topics = await score_and_filter(SAMPLE_ARTICLES)

    assert len(topics) == 3


@pytest.mark.asyncio
async def test_score_and_filter_unknown_category_falls_back():
    score_response = json.dumps([
        {"index": 0, "score": 9, "category": "completely_unknown_category"},
    ])
    angle_response = json.dumps({"ai_angle": "Test angle", "ai_counter_angle": "Counter"})
    translate_titles_response = "[0] 未知标题"
    translate_response = "[0] Translated unknown"

    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [translate_titles_response, translate_response, score_response, angle_response]
        topics = await score_and_filter([SAMPLE_ARTICLES[0]])

    assert len(topics) == 1
    assert topics[0].topic_category == TopicCategory.other
