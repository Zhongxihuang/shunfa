import pytest

from app.config import Settings


def test_production_rejects_wildcard_cors_with_authorization():
    settings = Settings(
        jwt_secret_key="x" * 32,
        environment="production",
        api_key_encryption_secret="y" * 32,
        cors_allow_origins=["*"],
    )

    with pytest.raises(ValueError, match="CORS"):
        settings.validate_cors()


def test_rate_limit_and_timeout_defaults_are_explicit():
    settings = Settings(jwt_secret_key="test-secret")

    assert settings.rate_limit_default == "100/minute"
    assert settings.generation_rate_limit == "10/minute"
    assert settings.ai_analysis_rate_limit == "10/minute"
    assert settings.publish_rate_limit == "20/minute"
    assert settings.deepseek_request_timeout_seconds == 60
