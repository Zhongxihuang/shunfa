"""Feishu Bitable REST API client.

Docs: https://open.feishu.cn/document/server-docs/docs/bitable-v1/

Usage:
    client = BitableClient(app_id, app_secret, app_token)
    record_id = await client.create_record(table_id, {"field": "value"})
"""

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

FEISHU_BASE = "https://open.feishu.cn/open-apis"


class BitableError(Exception):
    """Raised when Feishu API returns a non-zero code."""

    def __init__(self, code: int, msg: str):
        self.code = code
        self.msg = msg
        super().__init__(f"Feishu API error {code}: {msg}")


class BitableClient:
    """Async client for Feishu Bitable (Base) API with automatic token refresh."""

    def __init__(self, app_id: str, app_secret: str, app_token: str):
        self._app_id = app_id
        self._app_secret = app_secret
        self._app_token = app_token
        self._token: str | None = None
        self._token_expires_at: float = 0
        self._lock = asyncio.Lock()

    # ── Token management ──────────────────────────────────────────────────────

    async def _get_token(self) -> str:
        async with self._lock:
            if self._token and time.time() < self._token_expires_at - 60:
                return self._token
            await self._refresh_token()
            return self._token

    async def _refresh_token(self):
        url = f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal/"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                json={"app_id": self._app_id, "app_secret": self._app_secret},
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") != 0:
            raise BitableError(data.get("code", -1), data.get("msg", "token error"))

        self._token = data["tenant_access_token"]
        self._token_expires_at = time.time() + data.get("expire", 7200)

    async def _headers(self) -> dict:
        token = await self._get_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _check(self, data: dict):
        """Raise BitableError if API response code != 0."""
        code = data.get("code", 0)
        if code != 0:
            raise BitableError(code, data.get("msg", "unknown error"))

    # ── Record CRUD ───────────────────────────────────────────────────────────

    async def create_record(self, table_id: str, fields: dict[str, Any]) -> str:
        """Create a single record. Returns the new record_id."""
        url = f"{FEISHU_BASE}/bitable/v1/apps/{self._app_token}/tables/{table_id}/records"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                headers=await self._headers(),
                json={"fields": fields},
            )
            resp.raise_for_status()
            data = resp.json()

        self._check(data)
        return data["data"]["record"]["record_id"]

    async def batch_create_records(self, table_id: str, records: list[dict[str, Any]]) -> list[str]:
        """Batch create up to 500 records. Returns list of record_ids."""
        if not records:
            return []

        url = (
            f"{FEISHU_BASE}/bitable/v1/apps/{self._app_token}"
            f"/tables/{table_id}/records/batch_create"
        )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                headers=await self._headers(),
                json={"records": [{"fields": r} for r in records]},
            )
            resp.raise_for_status()
            data = resp.json()

        self._check(data)
        return [r["record_id"] for r in data["data"]["records"]]

    async def list_records(
        self,
        table_id: str,
        filter_formula: str = "",
        page_size: int = 20,
        page_token: str = "",
        sort: list | None = None,
    ) -> dict:
        """List records with optional filter formula. Returns raw API response data."""
        url = f"{FEISHU_BASE}/bitable/v1/apps/{self._app_token}/tables/{table_id}/records"
        params: dict = {"page_size": page_size}
        if filter_formula:
            params["filter"] = filter_formula
        if page_token:
            params["page_token"] = page_token
        if sort:
            import json as _json

            params["sort"] = _json.dumps(sort)

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                url,
                headers=await self._headers(),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        self._check(data)
        return data["data"]

    async def update_record(self, table_id: str, record_id: str, fields: dict[str, Any]) -> None:
        """Update fields on an existing record."""
        url = (
            f"{FEISHU_BASE}/bitable/v1/apps/{self._app_token}/tables/{table_id}/records/{record_id}"
        )
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.put(
                url,
                headers=await self._headers(),
                json={"fields": fields},
            )
            resp.raise_for_status()
            data = resp.json()

        self._check(data)

    async def batch_update_records(self, table_id: str, updates: list[dict]) -> None:
        """Batch update records. Each item must have record_id and fields."""
        if not updates:
            return

        url = (
            f"{FEISHU_BASE}/bitable/v1/apps/{self._app_token}"
            f"/tables/{table_id}/records/batch_update"
        )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                headers=await self._headers(),
                json={"records": updates},
            )
            resp.raise_for_status()
            data = resp.json()

        self._check(data)

    # ── Field management ──────────────────────────────────────────────────────

    async def add_field(self, table_id: str, field_name: str, field_type: int = 1) -> str:
        """Add a column (field) to a table. Returns the new field_id.

        Common field types:
          1  = Text (多行文本)
          2  = Number
          15 = URL
        """
        url = f"{FEISHU_BASE}/bitable/v1/apps/{self._app_token}/tables/{table_id}/fields"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                headers=await self._headers(),
                json={"field_name": field_name, "type": field_type},
            )
            resp.raise_for_status()
            data = resp.json()

        self._check(data)
        return data["data"]["field"]["field_id"]

    async def list_fields(self, table_id: str) -> list[dict]:
        """List all fields in a table."""
        url = f"{FEISHU_BASE}/bitable/v1/apps/{self._app_token}/tables/{table_id}/fields"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=await self._headers())
            resp.raise_for_status()
            data = resp.json()

        self._check(data)
        return data["data"].get("items", [])

    async def batch_delete_records(self, table_id: str, record_ids: list[str]) -> None:
        """Batch delete records by ID."""
        if not record_ids:
            return
        url = (
            f"{FEISHU_BASE}/bitable/v1/apps/{self._app_token}"
            f"/tables/{table_id}/records/batch_delete"
        )
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.request(
                "DELETE",
                url,
                headers=await self._headers(),
                json={"records": record_ids},
            )
            resp.raise_for_status()
            self._check(resp.json())


def get_bitable_client() -> BitableClient:
    """Factory using app settings. Call lazily to avoid import-time errors."""
    from ..config import settings

    return BitableClient(
        app_id=settings.feishu_app_id,
        app_secret=settings.feishu_app_secret,
        app_token=settings.feishu_bitable_app_token,
    )
