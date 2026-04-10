"""Hot topic storage — reads/writes the 热点库 Bitable table."""

from datetime import date
from typing import List, Optional

from ..clients.bitable_client import BitableClient, get_bitable_client
from ..config import settings
from ..schemas import ScoredTopic, HotTopicRecord, TopicCategory, TopicStatus


# Bitable column names must match the actual table column names exactly.
# Adjust these if the Bitable table uses different Chinese column headers.
COL_DATE = "date"
COL_HOT_TOPIC = "hot_topic"
COL_HOT_SOURCE = "hot_source"
COL_HOT_URL = "hot_url"
COL_HOT_SUMMARY = "hot_summary"
COL_TOPIC_CATEGORY = "topic_category"
COL_AI_ANGLE = "ai_angle"
COL_AI_COUNTER_ANGLE = "ai_counter_angle"
COL_SCORE = "score"
COL_STATUS = "status"


def _topic_to_fields(topic: ScoredTopic, topic_date: Optional[date] = None) -> dict:
    d = topic_date or date.today()
    return {
        COL_DATE: d.isoformat(),
        COL_HOT_TOPIC: topic.hot_topic,
        COL_HOT_SOURCE: topic.hot_source,
        COL_HOT_URL: topic.hot_url,
        COL_HOT_SUMMARY: topic.hot_summary,
        COL_TOPIC_CATEGORY: topic.topic_category.value,
        COL_AI_ANGLE: topic.ai_angle,
        COL_AI_COUNTER_ANGLE: topic.ai_counter_angle,
        COL_SCORE: topic.score,
        COL_STATUS: topic.status.value,
    }


def _fields_to_record(record_id: str, fields: dict) -> HotTopicRecord:
    try:
        cat = TopicCategory(fields.get(COL_TOPIC_CATEGORY, "other"))
    except ValueError:
        cat = TopicCategory.other

    try:
        status = TopicStatus(fields.get(COL_STATUS, "pending"))
    except ValueError:
        status = TopicStatus.pending

    date_str = fields.get(COL_DATE)
    parsed_date = None
    if date_str:
        try:
            parsed_date = date.fromisoformat(str(date_str)[:10])
        except ValueError:
            pass

    return HotTopicRecord(
        record_id=record_id,
        topic_date=parsed_date,
        hot_topic=fields.get(COL_HOT_TOPIC, ""),
        hot_source=fields.get(COL_HOT_SOURCE, ""),
        hot_url=fields.get(COL_HOT_URL, ""),
        hot_summary=fields.get(COL_HOT_SUMMARY, ""),
        topic_category=cat,
        ai_angle=fields.get(COL_AI_ANGLE, ""),
        ai_counter_angle=fields.get(COL_AI_COUNTER_ANGLE, ""),
        score=int(fields.get(COL_SCORE, 0)),
        status=status,
    )


async def save_topics(
    topics: List[ScoredTopic],
    topic_date: Optional[date] = None,
    client: Optional[BitableClient] = None,
) -> List[str]:
    """Batch save scored topics to the hot topic Bitable table.

    Returns list of created record_ids.
    """
    if not topics:
        return []

    client = client or get_bitable_client()
    table_id = settings.bitable_hot_topic_table_id
    records = [_topic_to_fields(t, topic_date) for t in topics]
    return await client.batch_create_records(table_id, records)


async def get_pending_topics(
    limit: int = 5,
    topic_date: Optional[date] = None,
    client: Optional[BitableClient] = None,
) -> List[HotTopicRecord]:
    """Fetch pending hot topics ordered by score descending.

    The Bitable filter formula syntax:
      CurrentValue.[field] = "value"
    """
    client = client or get_bitable_client()
    table_id = settings.bitable_hot_topic_table_id
    effective_date = topic_date or date.today()
    filter_formula = (
        f'AND(CurrentValue.[{COL_STATUS}] = "pending",'
        f'CurrentValue.[{COL_DATE}] = "{effective_date.isoformat()}")'
    )

    data = await client.list_records(
        table_id,
        filter_formula=filter_formula,
        page_size=50,  # fetch more, sort in Python
    )

    items = data.get("items", [])
    records = [_fields_to_record(r["record_id"], r.get("fields", {})) for r in items]
    records.sort(key=lambda r: r.score, reverse=True)
    return records[:limit]


async def mark_as_pushed(
    record_ids: List[str],
    client: Optional[BitableClient] = None,
) -> None:
    """Mark given records as pushed."""
    if not record_ids:
        return
    client = client or get_bitable_client()
    table_id = settings.bitable_hot_topic_table_id
    updates = [
        {"record_id": rid, "fields": {COL_STATUS: TopicStatus.pushed.value}}
        for rid in record_ids
    ]
    await client.batch_update_records(table_id, updates)


async def mark_expired(
    before_date: date,
    client: Optional[BitableClient] = None,
) -> None:
    """Mark all pending records older than before_date as expired."""
    client = client or get_bitable_client()
    table_id = settings.bitable_hot_topic_table_id

    filter_formula = (
        f'AND(CurrentValue.[{COL_STATUS}] = "pending",'
        f'CurrentValue.[{COL_DATE}] < "{before_date.isoformat()}")'
    )
    data = await client.list_records(table_id, filter_formula=filter_formula, page_size=100)
    items = data.get("items", [])
    if not items:
        return

    record_ids = [r["record_id"] for r in items]
    updates = [
        {"record_id": rid, "fields": {COL_STATUS: TopicStatus.expired.value}}
        for rid in record_ids
    ]
    await client.batch_update_records(table_id, updates)
