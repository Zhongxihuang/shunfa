from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field

from .models import CheckInStatus

# ── RSS / Hot Topic schemas ──────────────────────────────────────────────────

class TopicCategory(str, Enum):
    ai_model = "ai_model"       # 大模型发布/更新
    ai_product = "ai_product"   # AI产品/应用
    startup = "startup"         # 创业/融资
    policy = "policy"           # 政策/监管
    tech = "tech"               # 技术突破
    industry = "industry"       # 行业动态
    other = "other"


class TopicStatus(str, Enum):
    pending = "pending"     # 待推送
    pushed = "pushed"       # 已推送
    expired = "expired"     # 过期


class Platform(str, Enum):
    twitter = "twitter"
    xiaohongshu = "xiaohongshu"
    linkedin = "linkedin"


class RawArticle(BaseModel):
    title: str
    link: str
    source: str
    summary: str = ""
    published_date: str | None = None


class ScoredTopic(BaseModel):
    hot_topic: str
    hot_source: str
    hot_url: str = ""
    hot_summary: str = ""
    published_at: str | None = None
    topic_category: TopicCategory = TopicCategory.other
    ai_angle: str = ""
    ai_counter_angle: str = ""
    score: int = Field(ge=1, le=10)
    status: TopicStatus = TopicStatus.pending


class HotTopicRecord(ScoredTopic):
    record_id: str = ""
    topic_date: date | None = None


class HotTopicListItem(BaseModel):
    id: int
    title: str
    summary: str = ""
    source: str
    url: str
    published_at: str | None = None
    score: int
    category: str
    ai_angle: str = ""
    ai_counter_angle: str = ""


class HotTopicsResponse(BaseModel):
    date: date
    topics: list[HotTopicListItem]


# ── Content mode schemas ─────────────────────────────────────────────────────

class ContentMode(str, Enum):
    quick = "quick"
    deep = "deep"


class QuickGenerateRequest(BaseModel):
    topic_id: int | None = None
    hot_topic: str = Field(..., min_length=1, max_length=200)
    angle: str = Field(..., min_length=1, max_length=300)
    platform: Platform = Platform.xiaohongshu
    checkin_id: int | None = None


class QuickGenerateResponse(BaseModel):
    content: str
    platform: Platform
    char_count: int


# User schemas
class UserStatusResponse(BaseModel):
    id: int
    streak: int
    longest_streak: int
    points: int
    level: int
    diamonds: int
    reminder_time: str | None
    reminder_enabled: bool
    last_checkin_date: date | None
    today_completed: bool
    reminder_needed: bool = False

    class Config:
        from_attributes = True


class WebLoginRequest(BaseModel):
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8)


class WebAuthLoginRequest(BaseModel):
    username: str
    password: str


class ApiKeyStatusResponse(BaseModel):
    configured: bool
    preview: str | None = None  # last 4 chars e.g. "...ab12"


class SaveApiKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=10, pattern=r"^sk-")


class LoginResponse(BaseModel):
    token: str
    user: UserStatusResponse


# Topic schemas (used in Phase 2)
class TopicCard(BaseModel):
    topic: str
    batch_id: str


class TopicsResponse(BaseModel):
    topics: list[TopicCard]
    refresh_count: int
    max_refreshes: int = 3


# Content schemas (used in Phase 3)
class MessageRequest(BaseModel):
    checkin_id: int
    message: str = Field(..., min_length=1, max_length=2000)


class MessageResponse(BaseModel):
    reply: str
    status: CheckInStatus
    draft: str | None = None


class SelectTopicRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=100)
    batch_id: str | None = None  # If from suggestion, provide batch_id to mark was_used accurately
    hot_topic_id: int | None = None


class SelectTopicResponse(BaseModel):
    checkin_id: int
    status: CheckInStatus


class ConfirmContentRequest(BaseModel):
    checkin_id: int
    content: str = Field(..., min_length=1, max_length=5000)  # possibly edited by user


class ConfirmPublishRequest(BaseModel):
    checkin_id: int


class ContentFeedbackRequest(BaseModel):
    checkin_id: int
    feedback: str = Field(..., pattern="^(up|down)$")


class ContentFeedbackResponse(BaseModel):
    checkin_id: int
    feedback: str
    recorded: bool = True


class PublishResponse(BaseModel):
    streak: int
    points_earned: int
    total_points: int
    level: int
    diamonds: int
    message: str  # celebratory message
    newly_unlocked: list[dict] = []  # 本次新解锁的成就


class AchievementItem(BaseModel):
    type: str
    name: str
    desc: str
    unlocked_at: str | None = None


class AchievementsResponse(BaseModel):
    achievements: list[AchievementItem]
    total: int


# ── My page schemas ────────────────────────────────────────────────────────────

class CheckInHistoryItem(BaseModel):
    id: int
    date: date
    topic: str
    topic_source: str | None
    content: str | None
    status: str
    points_earned: int
    created_at: datetime

    class Config:
        from_attributes = True


class CheckInHistoryResponse(BaseModel):
    checkins: list[CheckInHistoryItem]
    total: int
    draft_count: int


# ── Stats schemas ────────────────────────────────────────────────────────────

class DailyStatsItem(BaseModel):
    date: date
    total: int
    approved: int
    approval_rate: float


class StatsSummary(BaseModel):
    total: int
    approved: int
    approval_rate: float


class StatsResponse(BaseModel):
    last_30_days: list[DailyStatsItem]
    summary: StatsSummary
