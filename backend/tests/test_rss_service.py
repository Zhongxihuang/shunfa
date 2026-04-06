"""Tests for RSS aggregation service."""

import pytest
import httpx
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.rss_service import (
    fetch_source,
    fetch_all_sources,
    _deduplicate,
    _title_fingerprint,
    _url_to_source_name,
    _strip_html,
)
from app.schemas import RawArticle


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(filename: str) -> str:
    return (FIXTURES_DIR / filename).read_text()


# ── fetch_source ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_source_parses_articles():
    xml = _load_fixture("sample_rss_hn.xml")

    with patch("app.services.rss_service.httpx.AsyncClient") as mock_client_cls:
        mock_response = MagicMock()
        mock_response.text = xml
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        articles = await fetch_source("https://news.ycombinator.com/rss", "Hacker News")

    assert len(articles) == 3
    assert articles[0].title == "DeepSeek V4 Released: 50% Cost Reduction in Reasoning"
    assert articles[0].source == "Hacker News"
    assert articles[0].link == "https://news.ycombinator.com/item?id=12345"


@pytest.mark.asyncio
async def test_fetch_source_returns_empty_on_http_error():
    with patch("app.services.rss_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client_cls.return_value = mock_client

        articles = await fetch_source("https://example.com/rss", "TestSource")

    assert articles == []


@pytest.mark.asyncio
async def test_fetch_source_returns_empty_on_4xx():
    with patch("app.services.rss_service.httpx.AsyncClient") as mock_client_cls:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock())
        )
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        articles = await fetch_source("https://example.com/rss", "TestSource")

    assert articles == []


# ── deduplication ─────────────────────────────────────────────────────────────

def test_deduplicate_removes_exact_title_duplicates():
    articles = [
        RawArticle(title="DeepSeek V4 Released", link="https://a.com", source="HN"),
        RawArticle(title="DeepSeek V4 Released", link="https://b.com", source="VB"),
        RawArticle(title="OpenAI GPT-5 Pricing Update", link="https://c.com", source="TC"),
    ]
    result = _deduplicate(articles)
    assert len(result) == 2
    assert result[0].title == "DeepSeek V4 Released"
    assert result[1].title == "OpenAI GPT-5 Pricing Update"


def test_deduplicate_case_insensitive():
    articles = [
        RawArticle(title="deepseek v4 released", link="https://a.com", source="HN"),
        RawArticle(title="DeepSeek V4 Released", link="https://b.com", source="VB"),
    ]
    result = _deduplicate(articles)
    assert len(result) == 1


def test_deduplicate_keeps_unique():
    articles = [
        RawArticle(title="Article A", link="https://a.com", source="HN"),
        RawArticle(title="Article B", link="https://b.com", source="VB"),
        RawArticle(title="Article C", link="https://c.com", source="TC"),
    ]
    result = _deduplicate(articles)
    assert len(result) == 3


# ── helper functions ──────────────────────────────────────────────────────────

def test_url_to_source_name_known_sources():
    assert _url_to_source_name("https://news.ycombinator.com/rss") == "Hacker News"
    assert _url_to_source_name("https://venturebeat.com/category/ai/feed/") == "VentureBeat AI"
    assert _url_to_source_name("https://techcrunch.com/category/artificial-intelligence/feed/") == "TechCrunch AI"
    assert _url_to_source_name("https://www.technologyreview.com/feed/") == "MIT Tech Review"


def test_strip_html_removes_tags():
    assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"
    assert _strip_html("No HTML here") == "No HTML here"
    assert _strip_html("<a href='url'>Link text</a>") == "Link text"


@pytest.mark.asyncio
async def test_fetch_all_sources_combines_and_deduplicates():
    hn_xml = _load_fixture("sample_rss_hn.xml")
    vb_xml = _load_fixture("sample_rss_venturebeat.xml")

    call_count = 0
    xml_responses = [hn_xml, vb_xml, "", "", ""]

    async def fake_get(url, **kwargs):
        nonlocal call_count
        mock_response = MagicMock()
        mock_response.text = xml_responses[call_count % len(xml_responses)]
        mock_response.raise_for_status = MagicMock()
        call_count += 1
        return mock_response

    with patch("app.services.rss_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = fake_get
        mock_client_cls.return_value = mock_client

        with patch("app.services.rss_service.settings") as mock_settings:
            mock_settings.rss_sources = [
                "https://news.ycombinator.com/rss",
                "https://venturebeat.com/category/ai/feed/",
            ]
            mock_settings.rss_fetch_timeout = 30
            mock_settings.rss_max_articles_per_source = 10

            articles = await fetch_all_sources()

    # HN: 3 articles + VB: 2 articles = 5 total (no duplicates in sample data)
    assert len(articles) == 5
