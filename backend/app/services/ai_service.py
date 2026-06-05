import logging
from typing import Any

from openai import APIError, AsyncOpenAI, RateLimitError, Timeout
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger("ai_service")


def _get_client(api_key: str) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=60.0,
    )


def get_system_api_key() -> str:
    from ..config import settings

    if not settings.deepseek_api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is not configured. "
            "Set it in your .env file for system-level operations (hot topic processing, etc.)."
        )
    return settings.deepseek_api_key


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
    api_key: str = "",
) -> str:
    """Call DeepSeek API and return the assistant's text response."""
    if not api_key:
        api_key = get_system_api_key()
    client = _get_client(api_key)
    response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()
