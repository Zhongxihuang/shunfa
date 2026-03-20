from pydantic import BaseModel
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
    topic: str


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
