import enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class CheckInStatus(enum.Enum):
    topic_selected = "topic_selected"
    discussing = "discussing"
    draft_ready = "draft_ready"
    pending = "pending"
    completed = "completed"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    openid = Column(String, unique=True, index=True, nullable=False)
    streak = Column(Integer, default=0, nullable=False)
    longest_streak = Column(Integer, default=0, nullable=False)
    points = Column(Integer, default=0, nullable=False)
    level = Column(Integer, default=1, nullable=False)
    diamonds = Column(Integer, default=3, nullable=False)
    reminder_time = Column(String, nullable=True)  # "HH:MM" format
    reminder_enabled = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_checkin_date = Column(Date, nullable=True)
    token_version = Column(Integer, default=0, nullable=False)
    username = Column(String(100), unique=True, nullable=True, index=True)
    password_hash = Column(String(256), nullable=True)
    deepseek_api_key = Column(String(512), nullable=True)  # encrypted via Fernet
    # Entry-loop free trial: how many shared-key generations this user has used.
    free_quota_used = Column(Integer, default=0, nullable=False)
    # Streak freeze (W3.8): protection cards that save the streak on a missed day.
    # Everyone starts with one free card; more can be redeemed with diamonds.
    streak_freezes = Column(Integer, default=1, nullable=False)
    # Diamond sink (W3.9): lifetime diamonds spent on redemptions. Effective
    # balance = earned (3 + points//100) − spent, so spending actually persists.
    diamonds_spent = Column(Integer, default=0, nullable=False)
    # Appendix A (cold-start within-subject experiment): per-user override of the
    # stable md5 gamification bucket. "on"/"off" force the arm; NULL falls back to
    # in_subtraction_experiment() so existing users are completely unchanged.
    gamification_override = Column(String(8), nullable=True)

    checkins = relationship("CheckIn", back_populates="user", lazy="selectin")
    topic_history = relationship("TopicHistory", back_populates="user", lazy="selectin")
    achievements = relationship("Achievement", back_populates="user", lazy="selectin")


class CheckIn(Base):
    __tablename__ = "checkins"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    topic = Column(Text, nullable=False)
    topic_source = Column(String, nullable=True)
    topic_url = Column(Text, nullable=True)
    topic_summary = Column(Text, nullable=True)
    topic_published_at = Column(String, nullable=True)
    generation_context = Column(
        Text, nullable=True
    )  # JSON: platform, selected angle, discussion brief, guard results
    content = Column(Text, nullable=True)  # final published content
    conversation_history = Column(Text, nullable=True)  # JSON string
    status = Column(SAEnum(CheckInStatus), default=CheckInStatus.topic_selected, nullable=False)
    refresh_count = Column(Integer, default=0, nullable=False)  # topic refresh count for the day
    content_approved = Column(
        Boolean, default=False, nullable=False
    )  # 用户是否对初稿满意（质量反馈）
    content_feedback = Column(String, nullable=True)  # explicit user feedback: up / down
    content_feedback_at = Column(DateTime(timezone=True), nullable=True)
    points_earned = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="checkins")

    __table_args__ = (
        # Prevent duplicate checkins for same user on same date
        UniqueConstraint("user_id", "date", name="uq_checkin_user_date"),
        # Composite indexes for common query patterns
        Index("ix_checkins_user_date_status", "user_id", "date", "status"),
    )


class TopicHistory(Base):
    __tablename__ = "topic_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    topic = Column(Text, nullable=False)
    batch_id = Column(String, nullable=False)  # UUID for grouping topics shown together
    was_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="topic_history")

    __table_args__ = (
        Index("ix_topic_history_user_topic_batch", "user_id", "topic", "batch_id"),
        Index("ix_topic_history_user_topic_created", "user_id", "topic", "created_at"),
    )


class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    achievement_type = Column(String, nullable=False)
    unlocked_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="achievements")

    __table_args__ = (
        # 每个用户每个成就只能解锁一次
        UniqueConstraint("user_id", "achievement_type", name="uq_user_achievement"),
    )


class HotTopic(Base):
    __tablename__ = "hot_topics"

    id = Column(Integer, primary_key=True, index=True)
    topic_date = Column(Date, nullable=False, index=True)
    rank = Column(Integer, default=0, nullable=False)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    source = Column(String, nullable=False)
    url = Column(Text, nullable=False)
    published_at = Column(String, nullable=True)
    category = Column(String, nullable=False, default="other")
    score = Column(Integer, default=0, nullable=False)
    ai_angle = Column(Text, nullable=True)
    ai_counter_angle = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("topic_date", "title", name="uq_hot_topics_date_title"),)


class Event(Base):
    """Product analytics event (added in 2026-06 W1.1).

    Used to compute the funnel, the north-star metric (≥3-day streak ratio), and
    any custom funnel for product retrofits. Tracking is best-effort — see
    `app.services.analytics.track` — failures must never break the request flow.
    """

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    # Nullable so login-failure / anonymous events can still be recorded.
    # SET NULL on user delete: we keep the event, lose the linkage.
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event = Column(String(64), nullable=False)
    props_json = Column(Text, nullable=True)  # JSON string; nullable when no props
    ts = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        # Funnel queries: "for user X, in time window, find event Y"
        Index("ix_events_user_event_ts", "user_id", "event", "ts"),
        # Global event counts / time-range slices
        Index("ix_events_event_ts", "event", "ts"),
        # Time-range queries across all events
        Index("ix_events_ts", "ts"),
    )
