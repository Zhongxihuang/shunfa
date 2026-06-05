"""
Web search / article fetch backend.

Backends (controlled by settings.search_backend):
  rss_fulltext  — fetch the known article URL and extract text (default, free)
  tavily        — call Tavily Search API (requires TAVILY_API_KEY)
"""

import re

import httpx

from ..config import settings

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Shunfa/1.0)"}


async def fetch_article_fulltext(url: str, max_chars: int = 2000) -> str:
    """Fetch a URL and return extracted plain text (best-effort)."""
    if not url or not url.startswith("http"):
        return ""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url, headers=_HEADERS)
            if response.status_code != 200:
                return ""
            return _extract_text(response.text)[:max_chars]
    except Exception:
        return ""


async def search(query: str, max_chars: int = 1200) -> str:
    """Search for additional facts. Returns plain-text result blob."""
    backend = settings.search_backend
    if backend == "tavily":
        return await _search_tavily(query, max_chars)
    return ""


async def _search_tavily(query: str, max_chars: int) -> str:
    if not settings.tavily_api_key:
        return ""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.tavily_api_key,
                    "query": query,
                    "max_results": 3,
                    "search_depth": "basic",
                },
            )
            data = resp.json()
        snippets = [r.get("content", "") for r in data.get("results", [])[:3]]
        return "\n".join(snippets)[:max_chars]
    except Exception:
        return ""


def _extract_text(html: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    # Drop script / style blocks entirely
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Drop all remaining tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Normalize whitespace
    return re.sub(r"\s+", " ", text).strip()
