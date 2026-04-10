import json
import uuid
from datetime import timedelta
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from ..models import TopicHistory, CheckIn, CheckInStatus
from ..utils.time_utils import get_today_cst, get_now_cst
from .ai_service import chat_completion

MAX_DAILY_REFRESHES = 3
TOPICS_PER_BATCH = 3

async def generate_topics(user_id: int, db: Session) -> dict:
    """
    Generate 3 topic suggestions for the user.
    Returns {"topics": [...], "refresh_count": int, "batch_id": str}

    The first load (refresh_count == 0, no prior CheckIn) is free and does not
    consume a refresh slot. Only user-initiated refreshes (refresh_count > 0)
    count against the daily quota.
    """
    today = get_today_cst()

    # Use with_for_update to lock the row and prevent race conditions
    today_checkin = db.query(CheckIn).filter(
        CheckIn.user_id == user_id,
        CheckIn.date == today
    ).with_for_update().first()

    refresh_count = today_checkin.refresh_count if today_checkin else 0

    # First load (refresh_count == 0) is free; only check limit on refreshes
    is_first_load = today_checkin is None

    if not is_first_load and refresh_count >= MAX_DAILY_REFRESHES:
        raise ValueError(f"已达到今日最大刷新次数({MAX_DAILY_REFRESHES}次)")

    # Get topics shown in the last 24 hours for deduplication
    twenty_four_hours_ago = get_now_cst() - timedelta(hours=24)
    recent_topics = db.query(TopicHistory.topic).filter(
        TopicHistory.user_id == user_id,
        TopicHistory.created_at >= twenty_four_hours_ago
    ).all()
    recent_topic_texts = [t.topic for t in recent_topics]

    # Generate new topics via AI
    topics = await _generate_topics_via_ai(recent_topic_texts)

    # Save to topic history
    batch_id = str(uuid.uuid4())
    for topic in topics:
        history = TopicHistory(
            user_id=user_id,
            topic=topic,
            batch_id=batch_id,
            was_used=False
        )
        db.add(history)

    # Update CheckIn: only increment refresh_count for user-initiated refreshes
    if is_first_load:
        if not today_checkin:
            today_checkin = CheckIn(
                user_id=user_id,
                date=today,
                topic="",  # Will be set when user selects a topic
                status=CheckInStatus.topic_selected,
                refresh_count=0
            )
            db.add(today_checkin)
        # refresh_count stays 0 on first load
    else:
        today_checkin.refresh_count = refresh_count + 1

    db.commit()

    new_refresh_count = today_checkin.refresh_count
    return {
        "topics": [{"topic": t, "batch_id": batch_id} for t in topics],
        "refresh_count": new_refresh_count,
        "batch_id": batch_id
    }

async def _generate_topics_via_ai(exclude_topics: list[str]) -> list[str]:
    """Generate 3 writing topics via DeepSeek AI."""
    exclude_text = ""
    if exclude_topics:
        exclude_text = f"\n\n请避免以下已出现过的选题：\n" + "\n".join(f"- {t}" for t in exclude_topics[:20])

    prompt = f"""生成 3 个能让目标读者觉得"这只有懂行的人才知道"的写作选题。

要求：
1. 每个选题必须是一个"内行洞察"或"圈内人才懂的角度"
2. 选题要具体、有情绪点，让人看完想说"确实是这样"
3. 长度 15-25 字，每行一个，不要编号
4. 适合在小红书/朋友圈分享，普通话题不要{exclude_text}

直接输出 3 个选题，每行一个，不要其他内容。"""

    messages = [{"role": "user", "content": prompt}]
    response = await chat_completion(messages, temperature=0.9, max_tokens=200)

    # Parse topics - split by newlines and clean up
    topics = [line.strip() for line in response.split('\n') if line.strip()]

    # Ensure we have exactly 3 topics
    if len(topics) < 3:
        # Pad with defaults if AI returns fewer
        defaults = ["分享一件最近让你有所感悟的小事", "聊聊你最近学到的一个新认知", "记录今天一个让你印象深刻的瞬间"]
        topics.extend(defaults[len(topics):3])

    return topics[:3]
