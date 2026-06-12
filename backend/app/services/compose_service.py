"""
Compose service — generates post assets (pages, title, tags) from checkin content.

Single LLM call produces a JSON with:
  - pages: list[str]  (dynamic page count: 80-160 chars each, no hard limit)
  - title: str        (judgment sentence, ≤22 chars)
  - tags: list[str]   (5-8 hashtags without # prefix)
"""

import json
import logging

from fastapi import HTTPException

from ..models import CheckIn
from ..services.ai_service import chat_completion
from ..services.prompt_templates import prompts

logger = logging.getLogger("compose_service")

MAX_PAGES = 6  # safety cap; content determines actual page count


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
    raw = await chat_completion(messages, temperature=0.7, max_tokens=1400, api_key=api_key)
    try:
        data = _parse_compose_response(raw)
    except (json.JSONDecodeError, KeyError, ValueError):
        logger.warning("compose_post_assets: first parse failed, retrying")
        # Attempt 2
        raw = await chat_completion(messages, temperature=0.5, max_tokens=1400, api_key=api_key)
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


async def generate_post_copy(
    content: str,
    api_key: str = "",
) -> dict:
    """Generate Xiaohongshu-style title + tags from article content.

    This is a safe-failure variant of `compose_post_assets` used by the
    paste-to-cards (image_jobs) flow. The contract is intentionally different:

    - `compose_post_assets` is tied to a CheckIn; on LLM parse failure it
      raises HTTPException(502) because the caller is asking the AI to
      produce ALL post assets (pages + title + tags) and a bad parse is a
      user-visible error.
    - `generate_post_copy` is a convenience layer ON TOP of the deterministic
      pagination the user already has. If the AI call fails, the user can
      still save their image cards — they just lose the AI-generated copy.
      Therefore, NEVER raise. Return `{"title": "", "tags": []}` on any
      failure mode (empty input, network error, parse error, retry failure).

    Args:
        content: the user's pasted article body. May be empty.
        api_key: BYOK / shared API key, plumbed through unchanged.

    Returns:
        `{"title": str, "tags": list[str]}`. Both are best-effort and may be
        empty.
    """
    if not content or not content.strip():
        return {"title": "", "tags": []}

    prompt = prompts.compose_post_assets_prompt.format(content=content)
    messages = [{"role": "user", "content": prompt}]

    # Attempt 1
    try:
        raw = await chat_completion(
            messages, temperature=0.7, max_tokens=1400, api_key=api_key
        )
        data = _parse_compose_response(raw)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("generate_post_copy: first parse failed, retrying: %r", e)
        # Attempt 2 — same prompt, lower temperature for more conservative output
        try:
            raw = await chat_completion(
                messages, temperature=0.5, max_tokens=1400, api_key=api_key
            )
            data = _parse_compose_response(raw)
        except Exception as e2:
            logger.warning("generate_post_copy: second attempt failed: %r", e2)
            return {"title": "", "tags": []}
    except Exception as e:
        # Network errors, auth errors, etc. — never propagate.
        logger.warning("generate_post_copy: chat_completion raised: %r", e)
        return {"title": "", "tags": []}

    title = str(data.get("title", "")).strip()
    tags = [str(t).strip() for t in data.get("tags", []) if str(t).strip()]
    return {"title": title, "tags": tags}
