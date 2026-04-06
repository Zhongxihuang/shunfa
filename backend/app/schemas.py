from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List
from enum import Enum
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
    published_date: Optional[str] = None


class ScoredTopic(BaseModel):
    hot_topic: str
    hot_source: str
    topic_category: TopicCategory = TopicCategory.other
    ai_angle: str = ""
    ai_counter_angle: str = ""
    score: int = Field(ge=1, le=10)
    status: TopicStatus = TopicStatus.pending


class HotTopicRecord(ScoredTopic):
    record_id: str = ""
    topic_date: Optional[date] = None


# ── Content mode schemas ─────────────────────────────────────────────────────

class ContentMode(str, Enum):
    quick = "quick"
    deep = "deep"


class QuickGenerateRequest(BaseModel):
    hot_topic: str = Field(..., min_length=1, max_length=200)
    angle: str = Field(..., min_length=1, max_length=300)
    platform: Platform = Platform.xiaohongshu


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
    reminder_time: Optional[str]
    reminder_enabled: bool
    last_checkin_date: Optional[date]
    today_completed: bool
    reminder_needed: bool = False

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    code: str  # WeChat login code


class WebLoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    user: UserStatusResponse


# Topic schemas (used in Phase 2)
class TopicCard(BaseModel):
    topic: str
    batch_id: str


class TopicsResponse(BaseModel):
    topics: List[TopicCard]
    refresh_count: int
    max_refreshes: int = 3


# Content schemas (used in Phase 3)
class MessageRequest(BaseModel):
    checkin_id: int
    message: str


class MessageResponse(BaseModel):
    reply: str
    status: CheckInStatus
    draft: Optional[str] = None


class SelectTopicRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=100)
    batch_id: Optional[str] = None  # If from suggestion, provide batch_id to mark was_used accurately


class SelectTopicResponse(BaseModel):
    checkin_id: int
    status: CheckInStatus


class ConfirmContentRequest(BaseModel):
    checkin_id: int
    content: str  # possibly edited by user


class ConfirmPublishRequest(BaseModel):
    checkin_id: int


class PublishResponse(BaseModel):
    streak: int
    points_earned: int
    total_points: int
    level: int
    diamonds: int
    message: str  # celebratory message
    newly_unlocked: List[dict] = []  # 本次新解锁的成就


class AchievementItem(BaseModel):
    type: str
    name: str
    desc: str
    unlocked_at: Optional[str] = None


class AchievementsResponse(BaseModel):
    achievements: List[AchievementItem]
    total: int
