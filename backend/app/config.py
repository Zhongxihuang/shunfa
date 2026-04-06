from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    deepseek_api_key: str
    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 720
    database_url: str = "sqlite:///./shunfa.db"
    environment: str = "development"
    admin_password: str = "shunfa2024"

    # RSS aggregation settings
    rss_sources: List[str] = [
        "https://news.ycombinator.com/rss",
        "https://venturebeat.com/category/ai/feed/",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.technologyreview.com/feed/",
    ]
    topic_score_threshold: int = 6
    rss_fetch_timeout: int = 30
    rss_max_articles_per_source: int = 10

    # Coze plugin auth
    coze_plugin_token: str = "shunfa-coze-token"

    # Feishu / Bitable settings
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_bitable_app_token: str = ""
    bitable_hot_topic_table_id: str = ""
    bitable_voice_record_table_id: str = ""

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
