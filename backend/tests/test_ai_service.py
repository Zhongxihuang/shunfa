from unittest.mock import patch

from app.config import settings
from app.services.ai_service import _get_client


def test_deepseek_client_uses_configured_base_url_and_timeout():
    original_base_url = settings.deepseek_base_url
    original_timeout = settings.deepseek_request_timeout_seconds
    settings.deepseek_base_url = "http://127.0.0.1:1081/v1"
    settings.deepseek_request_timeout_seconds = 12

    try:
        with patch("app.services.ai_service.AsyncOpenAI") as mock_client:
            _get_client("sk-test")
    finally:
        settings.deepseek_base_url = original_base_url
        settings.deepseek_request_timeout_seconds = original_timeout

    mock_client.assert_called_once_with(
        api_key="sk-test",
        base_url="http://127.0.0.1:1081/v1",
        timeout=12.0,
    )
