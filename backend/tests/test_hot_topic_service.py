"""Tests for hot topic AI scoring and angle generation."""

import json
import pytest
from unittest.mock import AsyncMock, patch

from app.services.hot_topic_service import (
    score_articles,
    generate_angles,
    score_and_filter,
)
from app.schemas import RawArticle, TopicCategory


SAMPLE_ARTICLES = [
    RawArticle(
        title="DeepSeek V4 Released: 50% Cost Reduction",
        link="https://hn.com/1",
        source="Hacker News",
        summary="DeepSeek announced V4 with major cost improvements.",
    ),
    RawArticle(
        title="Company X Hires 50 AI Engineers",
        link="https://hn.com/2",
        source="Hacker News",
        summary="Routine hiring announcement.",
    ),
    RawArticle(
        title="OpenAI GPT-5 Pricing Increases 20%",
        link="https://vb.com/1",
        source="VentureBeat AI",
        summary="OpenAI raised API prices.",
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
        {"index": 1, "score": 3, "category": "industry"},   # below threshold
        {"index": 2, "score": 7, "category": "ai_product"},
    ])
    angle_response = json.dumps({
        "ai_angle": "Some insight angle",
        "ai_counter_angle": "Counter perspective",
    })

    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [score_response, angle_response, angle_response]
        topics = await score_and_filter(SAMPLE_ARTICLES)

    assert len(topics) == 2
    # Should be sorted by score descending
    assert topics[0].score == 8
    assert topics[1].score == 7
    assert topics[0].topic_category == TopicCategory.ai_model


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

    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [score_response, angle_response, angle_response, angle_response]
        topics = await score_and_filter(SAMPLE_ARTICLES)

    assert len(topics) == 3
    assert all(topic.hot_url for topic in topics)


@pytest.mark.asyncio
async def test_score_and_filter_preserves_url_and_summary():
    score_response = json.dumps([{"index": 0, "score": 8, "category": "ai_model"}])
    angle_response = json.dumps({"ai_angle": "Some angle", "ai_counter_angle": "Counter"})

    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [score_response, angle_response]
        topics = await score_and_filter([SAMPLE_ARTICLES[0]])

    assert len(topics) == 1
    assert topics[0].hot_url == "https://hn.com/1"
    assert topics[0].hot_summary == "DeepSeek announced V4 with major cost improvements."


@pytest.mark.asyncio
async def test_score_and_filter_all_below_threshold():
    score_response = json.dumps([
        {"index": 0, "score": 2, "category": "industry"},
        {"index": 1, "score": 3, "category": "industry"},
        {"index": 2, "score": 4, "category": "industry"},
    ])
    angle_response = json.dumps({"ai_angle": "Test angle", "ai_counter_angle": "Counter"})

    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [score_response, angle_response, angle_response, angle_response]
        topics = await score_and_filter(SAMPLE_ARTICLES)

    assert len(topics) == 3


@pytest.mark.asyncio
async def test_score_and_filter_unknown_category_falls_back():
    score_response = json.dumps([
        {"index": 0, "score": 9, "category": "completely_unknown_category"},
    ])
    angle_response = json.dumps({"ai_angle": "Test angle", "ai_counter_angle": "Counter"})

    with patch("app.services.hot_topic_service.chat_completion", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = [score_response, angle_response]
        topics = await score_and_filter([SAMPLE_ARTICLES[0]])

    assert len(topics) == 1
    assert topics[0].topic_category == TopicCategory.other
