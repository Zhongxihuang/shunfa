"""Tests for hot_topic_store — all BitableClient calls mocked."""

import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from app.services.hot_topic_store import (
    save_topics,
    get_pending_topics,
    mark_as_pushed,
    mark_expired,
)
from app.schemas import ScoredTopic, TopicCategory, TopicStatus


def _make_topic(score: int = 8, category: TopicCategory = TopicCategory.ai_model) -> ScoredTopic:
    return ScoredTopic(
        hot_topic="DeepSeek V4 Released",
        hot_source="Hacker News",
        hot_url="https://hn.com/item?id=123",
        hot_summary="DeepSeek announced V4 with major cost improvements.",
        topic_category=category,
        ai_angle="国产AI性价比之战",
        ai_counter_angle="成本降低不等于质量提升",
        score=score,
    )


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.batch_create_records = AsyncMock(return_value=["rec_1", "rec_2"])
    client.list_records = AsyncMock(return_value={"items": [], "has_more": False})
    client.update_record = AsyncMock()
    client.batch_update_records = AsyncMock()
    return client


# ── save_topics ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_topics_calls_batch_create(monkeypatch):
    monkeypatch.setattr("app.services.hot_topic_store.settings.bitable_hot_topic_table_id", "tbl_hot")
    client = _mock_client()
    topics = [_make_topic(8), _make_topic(7)]

    ids = await save_topics(topics, topic_date=date(2026, 4, 2), client=client)

    client.batch_create_records.assert_called_once()
    call_args = client.batch_create_records.call_args
    assert call_args[0][0] == "tbl_hot"
    assert len(call_args[0][1]) == 2
    assert ids == ["rec_1", "rec_2"]


@pytest.mark.asyncio
async def test_save_topics_empty_returns_empty(monkeypatch):
    monkeypatch.setattr("app.services.hot_topic_store.settings.bitable_hot_topic_table_id", "tbl_hot")
    client = _mock_client()

    ids = await save_topics([], client=client)

    client.batch_create_records.assert_not_called()
    assert ids == []


@pytest.mark.asyncio
async def test_save_topics_includes_date_in_fields(monkeypatch):
    monkeypatch.setattr("app.services.hot_topic_store.settings.bitable_hot_topic_table_id", "tbl_hot")
    client = _mock_client()
    topic = _make_topic()

    await save_topics([topic], topic_date=date(2026, 4, 2), client=client)

    records_arg = client.batch_create_records.call_args[0][1]
    assert records_arg[0]["date"] == "2026-04-02"
    assert records_arg[0]["score"] == 8
    assert records_arg[0]["status"] == "pending"
    assert records_arg[0]["hot_url"] == "https://hn.com/item?id=123"
    assert records_arg[0]["hot_summary"] == "DeepSeek announced V4 with major cost improvements."


# ── get_pending_topics ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_pending_topics_returns_records(monkeypatch):
    monkeypatch.setattr("app.services.hot_topic_store.settings.bitable_hot_topic_table_id", "tbl_hot")
    client = _mock_client()
    client.list_records = AsyncMock(return_value={
        "items": [
            {
                "record_id": "rec_1",
                "fields": {
                    "date": "2026-04-02",
                    "hot_topic": "DeepSeek V4",
                    "hot_source": "HN",
                    "topic_category": "ai_model",
                    "ai_angle": "angle",
                    "ai_counter_angle": "counter",
                    "score": 8,
                    "status": "pending",
                },
            }
        ],
        "has_more": False,
    })

    records = await get_pending_topics(limit=5, client=client)

    assert len(records) == 1
    assert records[0].hot_topic == "DeepSeek V4"
    assert records[0].score == 8
    assert records[0].status == TopicStatus.pending
    assert records[0].record_id == "rec_1"
    assert records[0].topic_date is not None
    assert records[0].hot_url == ""      # not in fixture fields → defaults to ""
    assert records[0].hot_summary == ""  # not in fixture fields → defaults to ""
    assert 'CurrentValue.[date]' in client.list_records.call_args.kwargs["filter_formula"]


@pytest.mark.asyncio
async def test_get_pending_topics_returns_empty_when_none(monkeypatch):
    monkeypatch.setattr("app.services.hot_topic_store.settings.bitable_hot_topic_table_id", "tbl_hot")
    client = _mock_client()

    records = await get_pending_topics(client=client)
    assert records == []


# ── mark_as_pushed ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_as_pushed_calls_batch_update(monkeypatch):
    monkeypatch.setattr("app.services.hot_topic_store.settings.bitable_hot_topic_table_id", "tbl_hot")
    client = _mock_client()

    await mark_as_pushed(["rec_1", "rec_2"], client=client)

    client.batch_update_records.assert_called_once()
    updates = client.batch_update_records.call_args[0][1]
    assert len(updates) == 2
    assert updates[0]["fields"]["status"] == "pushed"


@pytest.mark.asyncio
async def test_mark_as_pushed_empty_is_noop(monkeypatch):
    monkeypatch.setattr("app.services.hot_topic_store.settings.bitable_hot_topic_table_id", "tbl_hot")
    client = _mock_client()

    await mark_as_pushed([], client=client)
    client.batch_update_records.assert_not_called()


# ── mark_expired ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_expired_updates_old_records(monkeypatch):
    monkeypatch.setattr("app.services.hot_topic_store.settings.bitable_hot_topic_table_id", "tbl_hot")
    client = _mock_client()
    client.list_records = AsyncMock(return_value={
        "items": [
            {"record_id": "old_rec_1", "fields": {"status": "pending"}},
            {"record_id": "old_rec_2", "fields": {"status": "pending"}},
        ],
        "has_more": False,
    })

    await mark_expired(before_date=date(2026, 4, 2), client=client)

    client.batch_update_records.assert_called_once()
    updates = client.batch_update_records.call_args[0][1]
    assert len(updates) == 2
    assert all(u["fields"]["status"] == "expired" for u in updates)


@pytest.mark.asyncio
async def test_mark_expired_noop_when_no_old_records(monkeypatch):
    monkeypatch.setattr("app.services.hot_topic_store.settings.bitable_hot_topic_table_id", "tbl_hot")
    client = _mock_client()  # default returns empty items

    await mark_expired(before_date=date(2026, 4, 2), client=client)
    client.batch_update_records.assert_not_called()
