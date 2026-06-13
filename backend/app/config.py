import logging

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    require_user_api_key: bool = False
    # Entry-loop "先爽后配": new users get this many free generations on the
    # platform's shared key before being asked to bring their own. 0 = disabled
    # (preserves the legacy hard BYOK wall). The shared key is `deepseek_api_key`.
    free_quota_limit: int = 0
    # Subtraction experiment (W2.7): percentage of users (0-100) for whom ALL
    # gamification UI is hidden, so Week-3 can measure whether gamification
    # creates retention. 0 = everyone keeps gamification (safe default).
    subtraction_experiment_pct: int = 0
    api_key_encryption_secret: str = "change-me-to-a-random-32-char-secret"
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 720
    database_url: str = "sqlite:///./shunfa.db"  # or postgresql://user:pass@host:5432/dbname
    environment: str = "development"
    enable_metrics: bool = False
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
        # English — AI-focused feeds (verified signal quality)
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://venturebeat.com/category/ai/feed/",
        "https://www.technologyreview.com/feed/",
        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "https://www.artificialintelligence-news.com/feed/",
        "https://openai.com/blog/rss.xml",
        "https://jack-clark.net/feed/",  # Import AI (Jack Clark)
        # Chinese
        "https://syncedreview.com/feed/",  # 机器之心
        "https://36kr.com/feed",
    ]
    topic_score_threshold: int = 8
    rss_fetch_timeout: int = 30
    rss_max_articles_per_source: int = 10

    # Fact enrichment (agent capability)
    # Options: "rss_fulltext" (default, zero cost), "tavily", "deepseek"
    search_backend: str = "rss_fulltext"
    tavily_api_key: str = ""

    # Coze plugin auth
    enable_coze_plugin: bool = False
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
        non_dev_envs = {"production", "staging"}
        if self.environment in non_dev_envs:
            default = "change-me-to-a-random-32-char-secret"
            if self.api_key_encryption_secret == default:
                raise ValueError(
                    "API_KEY_ENCRYPTION_SECRET must be changed from the default in non-development environments. "
                    'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
                )
            if len(self.api_key_encryption_secret) < 32:
                raise ValueError("API_KEY_ENCRYPTION_SECRET must be at least 32 characters.")

    def validate_admin_password(self) -> None:
        """Validate admin password strength at startup."""
        if self.environment == "production":
            if len(self.admin_password) < 12:
                raise ValueError("ADMIN_PASSWORD must be at least 12 characters in production.")

    def validate_rate_limit_storage(self) -> None:
        """Warn when production relies on the in-memory rate limiter.

        slowapi's default storage is per-process and in-memory. Behind more than
        one worker/replica each process keeps its own counters, so the effective
        limit multiplies by the worker count and an attacker can simply spread
        requests across workers. Production should point
        `RATE_LIMIT_STORAGE_URI` at a shared backend (e.g. redis://...).
        """
        if self.environment == "production" and not self.rate_limit_storage_uri:
            logger = logging.getLogger("config")
            logger.warning(
                "RATE_LIMIT_STORAGE_URI is empty in production. The in-memory "
                "rate limiter is per-process and will not hold across multiple "
                "workers/replicas. Set a shared backend (e.g. redis://...) to "
                "enforce limits globally."
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
    settings.validate_admin_password()
    settings.validate_rate_limit_storage()
