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
    """
    today = get_today_cst()

    # Get today's refresh count from CheckIn
    today_checkin = db.query(CheckIn).filter(
        CheckIn.user_id == user_id,
        CheckIn.date == today
    ).first()

    refresh_count = today_checkin.refresh_count if today_checkin else 0

    if refresh_count >= MAX_DAILY_REFRESHES:
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

    # Increment refresh count (create or update CheckIn)
    if today_checkin:
        today_checkin.refresh_count = refresh_count + 1
    else:
        today_checkin = CheckIn(
            user_id=user_id,
            date=today,
            topic="",  # Will be set when user selects a topic
            status=CheckInStatus.topic_selected,
            refresh_count=1
        )
        db.add(today_checkin)

    db.commit()

    return {
        "topics": [{"topic": t, "batch_id": batch_id} for t in topics],
        "refresh_count": refresh_count + 1,
        "batch_id": batch_id
    }

async def _generate_topics_via_ai(exclude_topics: list[str]) -> list[str]:
    """Generate 3 writing topics via DeepSeek AI."""
    exclude_text = ""
    if exclude_topics:
        exclude_text = f"\n\n请避免以下已出现过的选题：\n" + "\n".join(f"- {t}" for t in exclude_topics[:20])

    prompt = f"""你是一个帮助用户找到有价值的写作话题的助手。请生成3个适合在微信公众号或朋友圈分享的写作选题。

要求：
1. 选题要具体、有深度，不要过于泛泛
2. 适合普通人分享自己的观点和经历
3. 选题长度在15-30字之间
4. 每个选题用一行表示，不要加编号或符号{exclude_text}

只输出3个选题，每个占一行，不要其他内容。"""

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
