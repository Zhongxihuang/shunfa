"""RSS aggregation service — fetches and parses articles from multiple AI news sources."""

import asyncio
import hashlib
from typing import List

import feedparser
import httpx

from ..config import settings
from ..schemas import RawArticle


async def fetch_source(url: str, source_name: str) -> List[RawArticle]:
    """Fetch and parse a single RSS source. Returns empty list on any error."""
    try:
        async with httpx.AsyncClient(timeout=settings.rss_fetch_timeout) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            content = response.text
    except (httpx.HTTPError, httpx.TimeoutException):
        return []

    feed = feedparser.parse(content)
    articles: List[RawArticle] = []

    for entry in feed.entries[: settings.rss_max_articles_per_source]:
        title = entry.get("title", "").strip()
        if not title:
            continue
        summary = entry.get("summary", entry.get("description", "")).strip()
        # Strip HTML tags from summary (basic)
        summary = _strip_html(summary)[:500]

        articles.append(
            RawArticle(
                title=title,
                link=entry.get("link", ""),
                source=source_name,
                summary=summary,
                published_date=entry.get("published", None),
            )
        )

    return articles


async def fetch_all_sources() -> List[RawArticle]:
    """Fetch all configured RSS sources in parallel and return deduplicated articles."""
    sources = settings.rss_sources
    source_names = [_url_to_source_name(url) for url in sources]

    tasks = [fetch_source(url, name) for url, name in zip(sources, source_names)]
    results = await asyncio.gather(*tasks)

    all_articles: List[RawArticle] = []
    for batch in results:
        all_articles.extend(batch)

    return _deduplicate(all_articles)


def _deduplicate(articles: List[RawArticle]) -> List[RawArticle]:
    """Remove near-duplicate articles by title fingerprint."""
    seen: set = set()
    unique: List[RawArticle] = []
    for article in articles:
        fingerprint = _title_fingerprint(article.title)
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique.append(article)
    return unique


def _title_fingerprint(title: str) -> str:
    """Normalize title to a hash for deduplication."""
    normalized = title.lower().strip()
    return hashlib.md5(normalized.encode()).hexdigest()


def _url_to_source_name(url: str) -> str:
    """Derive a human-readable source name from a URL."""
    mapping = {
        "ycombinator": "Hacker News",
        "venturebeat": "VentureBeat AI",
        "techcrunch": "TechCrunch AI",
        "technologyreview": "MIT Tech Review",
        "theverge": "The Verge",
        "arstechnica": "Ars Technica",
        "jiqizhixin": "机器之心",
        "36kr": "36Kr",
    }
    for key, name in mapping.items():
        if key in url:
            return name
    return url.split("/")[2]  # fallback: domain


def _strip_html(text: str) -> str:
    """Remove HTML tags from a string (basic regex-free implementation)."""
    result = []
    inside_tag = False
    for char in text:
        if char == "<":
            inside_tag = True
        elif char == ">":
            inside_tag = False
        elif not inside_tag:
            result.append(char)
    return "".join(result).strip()
