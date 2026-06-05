"""Tests for fact enrichment service."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.fact_enrichment_service import ENRICH_SKIP_THRESHOLD, enrich_facts


@pytest.mark.asyncio
async def test_enrich_facts_short_circuits_when_fact_block_long():
    """No enrichment when fact_block already exceeds threshold."""
    long_block = "x" * ENRICH_SKIP_THRESHOLD
    result = await enrich_facts(base_fact_block=long_block, article_url="https://example.com")
    assert result == long_block


@pytest.mark.asyncio
async def test_enrich_facts_appends_fetched_fulltext():
    """rss_fulltext backend fetches article and appends to fact_block."""
    short_block = "标题：OpenAI 发布 o3"
    fetched_text = "OpenAI 在发布会上详细解释了 o3 的推理机制，包括思维链压缩和并行解码。" * 5

    with patch(
        "app.services.fact_enrichment_service.fetch_article_fulltext", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = fetched_text
        with patch("app.services.fact_enrichment_service.settings") as mock_settings:
            mock_settings.search_backend = "rss_fulltext"
            result = await enrich_facts(
                base_fact_block=short_block,
                article_url="https://openai.com/o3",
                hot_topic="OpenAI o3",
                angle="成本下降背后的架构变化",
            )

    assert short_block in result
    assert "原文补充" in result
    assert fetched_text[:100] in result


@pytest.mark.asyncio
async def test_enrich_facts_skips_when_fetched_text_too_short():
    """If fetched text is < 80 chars, return original fact_block unchanged."""
    short_block = "标题：OpenAI 发布 o3"

    with patch(
        "app.services.fact_enrichment_service.fetch_article_fulltext", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = "Too short."
        with patch("app.services.fact_enrichment_service.settings") as mock_settings:
            mock_settings.search_backend = "rss_fulltext"
            result = await enrich_facts(
                base_fact_block=short_block,
                article_url="https://openai.com/o3",
            )

    assert result == short_block


@pytest.mark.asyncio
async def test_enrich_facts_skips_when_no_url_for_rss_fulltext():
    """rss_fulltext backend with no URL returns original fact_block."""
    short_block = "标题：OpenAI 发布 o3"

    with patch("app.services.fact_enrichment_service.settings") as mock_settings:
        mock_settings.search_backend = "rss_fulltext"
        result = await enrich_facts(base_fact_block=short_block, article_url="")

    assert result == short_block


@pytest.mark.asyncio
async def test_enrich_facts_handles_fetch_exception_gracefully():
    """Errors during fetch are swallowed; original fact_block is returned."""
    short_block = "标题：OpenAI 发布 o3"

    with patch(
        "app.services.fact_enrichment_service.fetch_article_fulltext", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.side_effect = Exception("network error")
        with patch("app.services.fact_enrichment_service.settings") as mock_settings:
            mock_settings.search_backend = "rss_fulltext"
            result = await enrich_facts(
                base_fact_block=short_block,
                article_url="https://openai.com/o3",
            )

    assert result == short_block
