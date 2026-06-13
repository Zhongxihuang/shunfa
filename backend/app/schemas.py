from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from .models import CheckInStatus

# ── RSS / Hot Topic schemas ──────────────────────────────────────────────────


class TopicCategory(StrEnum):
    ai_model = "ai_model"  # 大模型发布/更新
    ai_product = "ai_product"  # AI产品/应用
    startup = "startup"  # 创业/融资
    policy = "policy"  # 政策/监管
    tech = "tech"  # 技术突破
    industry = "industry"  # 行业动态
    other = "other"


class TopicStatus(StrEnum):
    pending = "pending"  # 待推送
    pushed = "pushed"  # 已推送
    expired = "expired"  # 过期


class Platform(StrEnum):
    twitter = "twitter"
    xiaohongshu = "xiaohongshu"
    linkedin = "linkedin"
    weibo = "weibo"
    wechat_short = "wechat_short"
    generic = "generic"


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
    # True when topics are synthetic backups (no real hot topics loaded yet),
    # so the client can warn the user and offer a meaningful reload.
    is_fallback: bool = False


class HotTopicAnalysisRequest(BaseModel):
    angle: str | None = Field(default=None, max_length=300)


class HotTopicAnalysisResponse(BaseModel):
    opportunities: list[str] = []
    risks: list[str] = []
    recommended_frame: str = ""
    angles: list[str] = []


# ── Content mode schemas ─────────────────────────────────────────────────────


class ContentMode(StrEnum):
    quick = "quick"
    deep = "deep"


class QuickGenerateRequest(BaseModel):
    topic_id: int | None = None
    hot_topic: str = Field(..., min_length=1, max_length=200)
    angle: str = Field(..., min_length=1, max_length=300)
    platform: Platform = Platform.xiaohongshu
    checkin_id: int | None = None
    opportunities: list[str] = []
    risks: list[str] = []
    discussion_brief: dict | None = None


class QuickGenerateResponse(BaseModel):
    content: str
    platform: Platform
    char_count: int
    fact_pass: bool = True
    fact_issues: list[str] = []
    discussion_pass: bool = True
    discussion_issues: list[str] = []


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
    # Subtraction experiment (W2.7): when False the client hides all
    # gamification UI (streak / points / level / diamonds / achievements).
    gamification_enabled: bool = True
    # Streak freeze (W3.8): protection cards that save the streak on a missed day.
    streak_freezes: int = 0

    class Config:
        from_attributes = True


class WebLoginRequest(BaseModel):
    password: str


class LoginRequest(BaseModel):
    code: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8)
    # Appendix B (flywheel attribution): which external post/channel sent this
    # user, e.g. "jike_0608". Optional; written into the register event metadata.
    src: str | None = Field(default=None, max_length=64)


class GamificationOverrideRequest(BaseModel):
    user_id: int
    # "on" / "off" force the arm; null clears the override (back to md5 bucket).
    override: str | None = None


class WebAuthLoginRequest(BaseModel):
    username: str = Field(..., max_length=100)
    password: str = Field(..., max_length=200)


class ApiKeyStatusResponse(BaseModel):
    configured: bool
    preview: str | None = None  # last 4 chars e.g. "...ab12"
    # Entry-loop free trial. When free_quota_enabled is False the frontend
    # should fall back to the legacy "configure key to start" copy.
    free_quota_enabled: bool = False
    free_quota_limit: int = 0
    free_quota_used: int = 0
    free_quota_remaining: int = 0


class SaveApiKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=10, pattern=r"^sk-")


# ── Diamond sink / redemption (W3.9) ───────────────────────────────────────────


class RedeemRequest(BaseModel):
    item: str = Field(..., min_length=1, max_length=64)


class RedeemResponse(BaseModel):
    item: str
    cost: int
    diamonds: int  # remaining effective balance
    streak_freezes: int


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
    angle: str | None = Field(default=None, max_length=300)
    platform: Platform | None = None
    discussion_brief: dict | None = None


class MessageResponse(BaseModel):
    reply: str
    status: CheckInStatus
    draft: str | None = None


class SelectTopicRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=100)
    batch_id: str | None = None  # If from suggestion, provide batch_id to mark was_used accurately
    hot_topic_id: int | None = None
    selected_angle: str | None = Field(default=None, max_length=300)
    platform: Platform | None = None


class SelectTopicResponse(BaseModel):
    checkin_id: int
    status: CheckInStatus


class ConfirmContentRequest(BaseModel):
    checkin_id: int
    content: str = Field(..., min_length=1, max_length=5000)  # possibly edited by user


class ReviewContentRequest(BaseModel):
    checkin_id: int
    content: str = Field(..., min_length=1, max_length=5000)


class ReviewContentResponse(BaseModel):
    content_approved: bool
    quality_issues: list[str]
    quality_available: bool = True
    fact_pass: bool = True
    fact_issues: list[str] = []
    discussion_pass: bool = True
    discussion_issues: list[str] = []
    topic: str


class ReviseContentRequest(BaseModel):
    checkin_id: int
    content: str = Field(..., min_length=1, max_length=5000)
    issues: list[str] = []
    instruction: str | None = Field(default=None, max_length=500)


class ReviseContentResponse(BaseModel):
    content: str
    char_count: int
    fact_pass: bool = True
    fact_issues: list[str] = []
    discussion_pass: bool = True
    discussion_issues: list[str] = []


class ConfirmPublishRequest(BaseModel):
    checkin_id: int


class ContentFeedbackRequest(BaseModel):
    checkin_id: int
    feedback: str = Field(..., pattern="^(up|down)$")
    reason_tags: list[str] = []
    free_text: str | None = Field(default=None, max_length=500)


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


# ── Compose post assets schemas ──────────────────────────────────────────────


class ComposePostAssetsRequest(BaseModel):
    checkin_id: int
    template: Literal["beige", "magazine"]
    regenerate: bool = False


class ComposePostAssetsResponse(BaseModel):
    pages: list[str]  # 1-3 segments of body text, each for one image
    title: str  # Xiaohongshu-style title (with emoji, ≤20 chars)
    tags: list[str]  # 5-8 hashtags without # prefix


# ── W1.4 真发布 MVP: format + export ──────────────────────────────────────────


class FormatPostRequest(BaseModel):
    checkin_id: int
    platform: str = Field(
        default="xiaohongshu",
        max_length=32,
        description=(
            "Target platform id. Supported: xiaohongshu, moments, wechat_official, "
            "twitter, weibo, generic. Unknown ids fall back to generic."
        ),
    )


class FormattedPostResponse(BaseModel):
    checkin_id: int
    platform: str  # the platform id actually used (may be 'generic' fallback)
    requested_platform: str  # what the caller asked for, before fallback
    title: str
    body: str
    tags: list[str]
    char_count: int
    truncated: bool
    truncated_marker: str = ""
    text: str  # the full pre-formatted text (title + body + tags), ready to paste


# ── Paste-to-cards (image jobs) ──────────────────────────────────────────────


class ImageJobCreateRequest(BaseModel):
    raw_text: str = Field(min_length=1, max_length=20000)
    template: Literal["a", "b", "c"] = "a"
    cover_title: str | None = Field(default=None, max_length=120)


class ImageJobRenderRequest(BaseModel):
    template: Literal["a", "b", "c"] | None = None


class PageModel(BaseModel):
    index: int
    kind: Literal["cover", "body"]
    title: str | None = None
    paragraphs: list[str] = []


class ImageJobResponse(BaseModel):
    job_id: int
    template: str
    cover_title: str | None
    pages: list[PageModel]
    page_count: int
    overflow: bool
    status: str
    # AI-generated Xiaohongshu-style title (best-effort, may be empty if LLM
    # failed). Pair with `ai_tags` for the "copy" convenience layer.
    ai_title: str = ""
    # AI-generated hashtags, no # prefix, 2-6 chars each (best-effort).
    ai_tags: list[str] = []


class ImageJobRenderResponse(BaseModel):
    job_id: int
    template: str
    images: list[str]  # base64-encoded PNG, one per page
    page_count: int
