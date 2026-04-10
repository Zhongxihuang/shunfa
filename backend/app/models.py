from sqlalchemy import Column, Integer, String, Date, Text, Boolean, DateTime, Enum as SAEnum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
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

    checkins = relationship("CheckIn", back_populates="user", lazy="selectin")
    topic_history = relationship("TopicHistory", back_populates="user", lazy="selectin")
    achievements = relationship("Achievement", back_populates="user", lazy="selectin")


class CheckIn(Base):
    __tablename__ = "checkins"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    topic = Column(Text, nullable=False)
    content = Column(Text, nullable=True)  # final published content
    conversation_history = Column(Text, nullable=True)  # JSON string
    status = Column(SAEnum(CheckInStatus), default=CheckInStatus.topic_selected, nullable=False)
    refresh_count = Column(Integer, default=0, nullable=False)  # topic refresh count for the day
    content_approved = Column(Boolean, default=False, nullable=False)  # 用户是否对初稿满意（质量反馈）
    content_feedback = Column(String, nullable=True)  # explicit user feedback: up / down
    content_feedback_at = Column(DateTime(timezone=True), nullable=True)
    points_earned = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="checkins")


class TopicHistory(Base):
    __tablename__ = "topic_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    topic = Column(Text, nullable=False)
    batch_id = Column(String, nullable=False)  # UUID for grouping topics shown together
    was_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="topic_history")


class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    achievement_type = Column(String, nullable=False)
    unlocked_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="achievements")

    __table_args__ = (
        # 每个用户每个成就只能解锁一次
        UniqueConstraint("user_id", "achievement_type", name="uq_user_achievement"),
    )
