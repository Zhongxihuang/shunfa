from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional, List
from .models import CheckInStatus


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
