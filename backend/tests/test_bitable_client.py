"""Tests for BitableClient — all HTTP calls mocked via respx / httpx mock."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.clients.bitable_client import BitableClient, BitableError


@pytest.fixture
def client():
    return BitableClient(
        app_id="cli_test",
        app_secret="secret_test",
        app_token="app_token_test",
    )


TOKEN_RESPONSE = {
    "code": 0,
    "tenant_access_token": "test_token_abc",
    "expire": 7200,
}


def _mock_post(return_value: dict):
    """Helper: mock httpx.AsyncClient.post to return given JSON."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=return_value)
    return mock_resp


def _mock_get(return_value: dict):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=return_value)
    return mock_resp


# ── Token management ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_token_fetches_on_first_call(client):
    with patch("app.clients.bitable_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=_mock_post(TOKEN_RESPONSE))
        mock_cls.return_value = mock_http

        token = await client._get_token()

    assert token == "test_token_abc"
    assert client._token == "test_token_abc"


@pytest.mark.asyncio
async def test_get_token_uses_cache(client):
    client._token = "cached_token"
    client._token_expires_at = time.time() + 3600

    with patch("app.clients.bitable_client.httpx.AsyncClient") as mock_cls:
        token = await client._get_token()

    mock_cls.assert_not_called()
    assert token == "cached_token"


@pytest.mark.asyncio
async def test_get_token_refreshes_when_expired(client):
    client._token = "old_token"
    client._token_expires_at = time.time() - 10  # expired

    with patch("app.clients.bitable_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=_mock_post(TOKEN_RESPONSE))
        mock_cls.return_value = mock_http

        token = await client._get_token()

    assert token == "test_token_abc"


@pytest.mark.asyncio
async def test_refresh_token_raises_on_error_code(client):
    error_response = {"code": 10012, "msg": "app not exist"}

    with patch("app.clients.bitable_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=_mock_post(error_response))
        mock_cls.return_value = mock_http

        with pytest.raises(BitableError) as exc_info:
            await client._refresh_token()

    assert exc_info.value.code == 10012


# ── create_record ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_record_returns_record_id(client):
    client._token = "test_token"
    client._token_expires_at = time.time() + 3600

    create_response = {
        "code": 0,
        "data": {"record": {"record_id": "rec_abc123", "fields": {"name": "test"}}},
    }

    with patch("app.clients.bitable_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=_mock_post(create_response))
        mock_cls.return_value = mock_http

        record_id = await client.create_record("tbl_001", {"name": "test"})

    assert record_id == "rec_abc123"


@pytest.mark.asyncio
async def test_create_record_raises_on_api_error(client):
    client._token = "test_token"
    client._token_expires_at = time.time() + 3600

    error_response = {"code": 1254043, "msg": "table not found"}

    with patch("app.clients.bitable_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=_mock_post(error_response))
        mock_cls.return_value = mock_http

        with pytest.raises(BitableError) as exc_info:
            await client.create_record("tbl_bad", {"name": "test"})

    assert exc_info.value.code == 1254043


# ── batch_create_records ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_create_returns_record_ids(client):
    client._token = "test_token"
    client._token_expires_at = time.time() + 3600

    batch_response = {
        "code": 0,
        "data": {
            "records": [
                {"record_id": "rec_1", "fields": {}},
                {"record_id": "rec_2", "fields": {}},
            ]
        },
    }

    with patch("app.clients.bitable_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=_mock_post(batch_response))
        mock_cls.return_value = mock_http

        ids = await client.batch_create_records("tbl_001", [{"name": "a"}, {"name": "b"}])

    assert ids == ["rec_1", "rec_2"]


@pytest.mark.asyncio
async def test_batch_create_empty_returns_empty(client):
    ids = await client.batch_create_records("tbl_001", [])
    assert ids == []


# ── list_records ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_records_returns_items(client):
    client._token = "test_token"
    client._token_expires_at = time.time() + 3600

    list_response = {
        "code": 0,
        "data": {
            "items": [
                {"record_id": "rec_1", "fields": {"hot_topic": "DeepSeek V4", "score": 8}},
            ],
            "has_more": False,
            "page_token": "",
        },
    }

    with patch("app.clients.bitable_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_get(list_response))
        mock_cls.return_value = mock_http

        data = await client.list_records("tbl_001")

    assert len(data["items"]) == 1
    assert data["items"][0]["fields"]["score"] == 8


# ── update_record ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_record_succeeds(client):
    client._token = "test_token"
    client._token_expires_at = time.time() + 3600

    update_response = {
        "code": 0,
        "data": {"record": {"record_id": "rec_1", "fields": {"status": "pushed"}}},
    }

    with patch("app.clients.bitable_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.put = AsyncMock(return_value=_mock_post(update_response))
        mock_cls.return_value = mock_http

        await client.update_record("tbl_001", "rec_1", {"status": "pushed"})

    mock_http.put.assert_called_once()


@pytest.mark.asyncio
async def test_batch_update_records_uses_post(client):
    client._token = "test_token"
    client._token_expires_at = time.time() + 3600

    update_response = {
        "code": 0,
        "data": {
            "records": [
                {"record_id": "rec_1", "fields": {"status": "pushed"}},
            ]
        },
    }

    with patch("app.clients.bitable_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.post = AsyncMock(return_value=_mock_post(update_response))
        mock_cls.return_value = mock_http

        await client.batch_update_records(
            "tbl_001",
            [{"record_id": "rec_1", "fields": {"status": "pushed"}}],
        )

    mock_http.post.assert_called_once()
