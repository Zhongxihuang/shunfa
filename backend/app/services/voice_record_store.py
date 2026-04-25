"""Voice record storage — reads/writes the 发声记录 Bitable table."""

from datetime import date

from pydantic import BaseModel

from ..clients.bitable_client import BitableClient, get_bitable_client
from ..config import settings
from ..schemas import Platform


class VoiceRecord(BaseModel):
    record_id: str = ""
    date: date | None = None
    user_id: str = ""
    hot_topic: str = ""
    angle: str = ""
    content: str = ""
    platform: Platform = Platform.xiaohongshu
    mode: str = "quick"       # "quick" or "deep"
    status: str = "草稿"       # 草稿 / 已采纳 / 已复制
    adopted: bool = False


# Bitable column names
COL_DATE = "date"
COL_USER_ID = "user_id"
COL_HOT_TOPIC = "hot_topic"
COL_ANGLE = "angle"
COL_CONTENT = "content"
COL_PLATFORM = "platform"
COL_MODE = "mode"
COL_STATUS = "status"
COL_ADOPTED = "adopted"


def _record_to_fields(record: VoiceRecord) -> dict:
    d = record.date or date.today()
    return {
        COL_DATE: d.isoformat(),
        COL_USER_ID: record.user_id,
        COL_HOT_TOPIC: record.hot_topic,
        COL_ANGLE: record.angle,
        COL_CONTENT: record.content,
        COL_PLATFORM: record.platform.value,
        COL_MODE: record.mode,
        COL_STATUS: record.status,
        COL_ADOPTED: record.adopted,
    }


def _fields_to_voice_record(record_id: str, fields: dict) -> VoiceRecord:
    date_str = fields.get(COL_DATE)
    parsed_date = None
    if date_str:
        try:
            parsed_date = date.fromisoformat(str(date_str)[:10])
        except ValueError:
            pass

    try:
        platform = Platform(fields.get(COL_PLATFORM, "xiaohongshu"))
    except ValueError:
        platform = Platform.xiaohongshu

    return VoiceRecord(
        record_id=record_id,
        date=parsed_date,
        user_id=fields.get(COL_USER_ID, ""),
        hot_topic=fields.get(COL_HOT_TOPIC, ""),
        angle=fields.get(COL_ANGLE, ""),
        content=fields.get(COL_CONTENT, ""),
        platform=platform,
        mode=fields.get(COL_MODE, "quick"),
        status=fields.get(COL_STATUS, "草稿"),
        adopted=bool(fields.get(COL_ADOPTED, False)),
    )


async def save_voice_record(
    record: VoiceRecord,
    client: BitableClient | None = None,
) -> str:
    """Save a single voice record. Returns the created record_id."""
    client = client or get_bitable_client()
    table_id = settings.bitable_voice_record_table_id
    return await client.create_record(table_id, _record_to_fields(record))


async def get_user_records(
    user_id: str,
    limit: int = 20,
    client: BitableClient | None = None,
) -> list[VoiceRecord]:
    """Fetch recent voice records for a user, newest first."""
    client = client or get_bitable_client()
    table_id = settings.bitable_voice_record_table_id

    filter_formula = f'CurrentValue.[{COL_USER_ID}] = "{user_id}"'
    sort = [{"field_name": COL_DATE, "order": "DESC"}]

    data = await client.list_records(
        table_id,
        filter_formula=filter_formula,
        page_size=limit,
        sort=sort,
    )
    items = data.get("items", [])
    return [_fields_to_voice_record(r["record_id"], r.get("fields", {})) for r in items]


async def update_record_status(
    record_id: str,
    status: str,
    adopted: bool,
    client: BitableClient | None = None,
) -> None:
    """Update status and adopted flag on an existing voice record."""
    client = client or get_bitable_client()
    table_id = settings.bitable_voice_record_table_id
    await client.update_record(
        table_id,
        record_id,
        {COL_STATUS: status, COL_ADOPTED: adopted},
    )
