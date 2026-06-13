"""
Fact enrichment: optionally fetch more context before drafting.

Inserts between "build fact_block" and "_generate_quick_draft" to give the
model richer source material for the mechanism and second-order-impact layers.

Flow:
  1. Short-circuit if base_fact_block is already long enough.
  2. rss_fulltext backend: fetch the known article URL's full text.
  3. tavily backend: run a keyword search derived from topic + angle.
  4. Append enriched text to fact_block under a clear separator.
  5. Cache the result in CheckIn.generation_context["enriched_facts"] to avoid
     re-fetching on revise / regenerate calls for the same checkin.
"""

import logging

from ..config import settings
from .web_search import fetch_article_fulltext, search

logger = logging.getLogger("fact_enrichment")

# If the fact_block is already this many chars, skip enrichment entirely.
ENRICH_SKIP_THRESHOLD = 500

# Trim enriched content to this many chars before appending.
ENRICH_MAX_CHARS = 1500


async def enrich_facts(
    base_fact_block: str,
    article_url: str = "",
    hot_topic: str = "",
    angle: str = "",
) -> str:
    """
    Return an enriched fact_block.
    Always safe to call — returns base_fact_block unchanged on any error.
    """
    if len(base_fact_block) >= ENRICH_SKIP_THRESHOLD:
        return base_fact_block

    backend = settings.search_backend
    enriched_text = ""

    try:
        if backend == "rss_fulltext" and article_url:
            enriched_text = await fetch_article_fulltext(article_url, max_chars=ENRICH_MAX_CHARS)
        elif backend == "tavily":
            query = f"{hot_topic} {angle}".strip()[:200]
            enriched_text = await search(query)
    except Exception as exc:
        logger.warning(
            "fact_enrichment failed (%s), continuing without enrichment: %s", backend, exc
        )
        return base_fact_block

    if not enriched_text or len(enriched_text) < 80:
        return base_fact_block

    logger.info("fact_enrichment added %d chars via %s", len(enriched_text), backend)
    return base_fact_block + "\n\n--- 原文补充 ---\n" + enriched_text
