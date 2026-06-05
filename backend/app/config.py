import logging

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    deepseek_api_key: str | None = None
    require_user_api_key: bool = False
    api_key_encryption_secret: str = "change-me-to-a-random-32-char-secret"
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 720
    database_url: str = "sqlite:///./shunfa.db"  # or postgresql://user:pass@host:5432/dbname
    environment: str = "development"
    rate_limit_storage_uri: str = ""
    rate_limit_default: str = "100/minute"
    generation_rate_limit: str = "10/minute"
    ai_analysis_rate_limit: str = "10/minute"
    publish_rate_limit: str = "20/minute"
    deepseek_request_timeout_seconds: int = 60
    admin_password: str = ""
    cors_allow_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    wechat_app_id: str = ""
    wechat_app_secret: str = ""

    # RSS aggregation settings
    rss_sources: list[str] = [
        # English
        "https://news.ycombinator.com/rss",
        "https://venturebeat.com/category/ai/feed/",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.technologyreview.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://feeds.arstechnica.com/arstechnica/index",
        # Chinese
        "https://www.leiphone.com/feed",  # 雷锋网，AI/科技综合
        "https://36kr.com/feed",            # 36Kr，综合新闻
    ]
    topic_score_threshold: int = 8
    rss_fetch_timeout: int = 30
    rss_max_articles_per_source: int = 10

    # Coze plugin auth
    coze_plugin_token: str = ""

    # Feishu / Bitable settings
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_bitable_app_token: str = ""
    bitable_voice_record_table_id: str = ""

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}

    def validate_jwt_secret(self) -> None:
        """Validate JWT secret at startup. Raises ValueError if secret is too weak."""
        if self.environment == "production":
            if len(self.jwt_secret_key) < 32:
                raise ValueError(
                    f"JWT_SECRET_KEY is too short for production. "
                    f"Got {len(self.jwt_secret_key)} chars, need at least 32. "
                    f"Please set a strong random secret in your environment."
                )
            weak_secrets = {"secret", "password", "jwt_secret", "changeme", "test_secret"}
            if self.jwt_secret_key.lower() in weak_secrets:
                raise ValueError(
                    "JWT_SECRET_KEY is a known weak secret in production. "
                    "Please set a strong random secret."
                )

    def validate_encryption_secret(self) -> None:
        """Validate Fernet encryption secret at startup."""
        if self.environment == "production":
            default = "change-me-to-a-random-32-char-secret"
            if self.api_key_encryption_secret == default:
                raise ValueError(
                    "API_KEY_ENCRYPTION_SECRET must be changed from the default in production. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
                )
            if len(self.api_key_encryption_secret) < 32:
                raise ValueError(
                    "API_KEY_ENCRYPTION_SECRET must be at least 32 characters in production."
                )

    def validate_cors(self) -> list[str]:
        """
        Return the validated CORS origins.
        In production, warns if localhost origins are present.
        """
        origins = self.cors_allow_origins
        if self.environment == "production":
            if "*" in origins:
                raise ValueError(
                    "CORS_ALLOW_ORIGINS must not contain '*' in production when Authorization headers are used."
                )
            localhost_origins = [o for o in origins if "localhost" in o or "127.0.0.1" in o]
            if localhost_origins:
                logger = logging.getLogger("config")
                logger.warning(
                    f"CORS contains localhost origins in production: {localhost_origins}. "
                    f"This is a security risk. Please use only production domains."
                )
        return origins


settings = Settings()

# Validate at import time
if settings.environment == "production":
    settings.validate_jwt_secret()
    settings.validate_encryption_secret()
