"""
Compose service — generates post assets (pages, title, tags) from checkin content.

Single LLM call produces a JSON with:
  - pages: list[str]  (1-3 segments for image rendering)
  - title: str        (Xiaohongshu-style title with emoji)
  - tags: list[str]   (5-8 hashtags without # prefix)
"""

import json
import logging

from fastapi import HTTPException

from ..models import CheckIn
from ..services.ai_service import chat_completion
from ..services.prompt_templates import prompts

logger = logging.getLogger("compose_service")

MAX_PAGES = 3


def _parse_compose_response(raw: str) -> dict:
    """Parse LLM JSON output. Returns dict with pages, title, tags."""
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    return json.loads(text)


async def compose_post_assets(
    checkin: CheckIn,
    api_key: str,
) -> dict:
    """
    Call DeepSeek once to produce pages + title + tags.
    Retries once on JSON parse failure; raises 502 on second failure.
    """
    if not checkin.content:
        raise HTTPException(status_code=400, detail="CheckIn has no content to compose")

    prompt = prompts.compose_post_assets_prompt.format(content=checkin.content)
    messages = [{"role": "user", "content": prompt}]

    # Attempt 1
    raw = await chat_completion(messages, temperature=0.7, max_tokens=800, api_key=api_key)
    try:
        data = _parse_compose_response(raw)
    except (json.JSONDecodeError, KeyError, ValueError):
        logger.warning("compose_post_assets: first parse failed, retrying")
        # Attempt 2
        raw = await chat_completion(messages, temperature=0.5, max_tokens=800, api_key=api_key)
        try:
            data = _parse_compose_response(raw)
        except Exception as e:
            logger.error(f"compose_post_assets: second parse failed: {e!r}")
            raise HTTPException(status_code=502, detail="LLM_PARSE_ERROR") from e

    # Validate and sanitise
    pages = data.get("pages", [])
    if not isinstance(pages, list) or len(pages) == 0:
        pages = [checkin.content]  # graceful fallback: single page
    pages = [str(p).strip() for p in pages if str(p).strip()][:MAX_PAGES]

    title = str(data.get("title", "")).strip()
    tags = [str(t).strip() for t in data.get("tags", []) if str(t).strip()]

    return {"pages": pages, "title": title, "tags": tags}
