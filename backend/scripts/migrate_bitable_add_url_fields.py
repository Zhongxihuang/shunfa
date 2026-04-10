"""One-time migration: add hot_url and hot_summary columns to the hot topic Bitable table.

Run from the backend/ directory:
    python scripts/migrate_bitable_add_url_fields.py

Safe to run multiple times — skips fields that already exist.
"""

import asyncio
import sys
import os

# Allow running from backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.clients.bitable_client import get_bitable_client
from app.config import settings

FIELDS_TO_ADD = [
    ("hot_url", 1),      # Text type — stored as plain string URL
    ("hot_summary", 1),  # Text type — article summary snippet
]


async def main():
    client = get_bitable_client()
    table_id = settings.bitable_hot_topic_table_id

    print(f"Fetching existing fields for table: {table_id}")
    existing = await client.list_fields(table_id)
    existing_names = {f["field_name"] for f in existing}
    print(f"Existing fields: {existing_names}")

    for field_name, field_type in FIELDS_TO_ADD:
        if field_name in existing_names:
            print(f"  [skip] '{field_name}' already exists")
        else:
            field_id = await client.add_field(table_id, field_name, field_type)
            print(f"  [ok]   Created '{field_name}' (field_id={field_id})")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
