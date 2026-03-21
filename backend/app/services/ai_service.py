from openai import AsyncOpenAI
from ..config import settings

client = AsyncOpenAI(
    api_key=settings.deepseek_api_key,
    base_url="https://api.deepseek.com"
)

async def chat_completion(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 1000
) -> str:
    """Call DeepSeek API and return the assistant's text response."""
    response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response.choices[0].message.content.strip()
