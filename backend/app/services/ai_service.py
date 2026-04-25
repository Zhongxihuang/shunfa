import logging
from typing import Any

from openai import APIError, AsyncOpenAI, RateLimitError, Timeout
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import settings

logger = logging.getLogger("ai_service")

# Module-level singleton client — connections are pooled internally by httpx
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com",
            timeout=60.0,  # explicit timeout per request
        )
    return _client


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=8),
    retry=retry_if_exception_type((Timeout, RateLimitError, APIError)),
    before_sleep=lambda retry_state: logger.warning(
        f"chat_completion retry {retry_state.attempt_number}/3 "
        f"(waiting {retry_state.next_action.sleep}s): {retry_state.outcome.exception()}"
    ),
    reraise=True,
)
async def chat_completion(
    messages: list[dict[str, Any]],
    temperature: float = 0.7,
    max_tokens: int = 1000,
) -> str:
    """
    Call DeepSeek API and return the assistant's text response.

    Retry policy (via tenacity):
      - 3 attempts with exponential back-off (2s, 4s, 8s)
      - retries on: Timeout, RateLimitError (429), 5xx API errors
      - logs each retry attempt for observability
    """
    client = _get_client()
    response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()
