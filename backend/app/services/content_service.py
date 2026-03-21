import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from ..models import CheckIn, CheckInStatus, User
from ..utils.time_utils import get_now_cst
from .ai_service import chat_completion

# How many discussion rounds before we try to generate a draft
MIN_DISCUSSION_ROUNDS = 1
MAX_DISCUSSION_ROUNDS = 3

SYSTEM_PROMPT_DISCUSS = """你是顺发写作助手，帮助用户把想法转化为微信公众号文章。

你的任务：
1. 用1-2个针对性问题，帮助用户挖掘出写作素材（他们的具体经历、感受、观点）
2. 当用户回答了至少1个问题，且你判断素材已经足够写出140-300字的文章时，直接开始生成初稿
3. 生成初稿时，用特殊格式包裹：<<<DRAFT_START>>>初稿内容<<<DRAFT_END>>>

风格要求：
- 轻松自然，像朋友聊天
- 引导用户说出具体细节，而不是泛泛而谈
- 不要过度追问，1-2轮就够了

你当前讨论的话题：{topic}"""

async def process_message(
    checkin: CheckIn,
    user_message: str,
    db: Session
) -> dict:
    """
    Process a user message in the discussion flow.
    Returns {"reply": str, "status": CheckInStatus, "draft": Optional[str]}
    """
    # Load conversation history
    history = json.loads(checkin.conversation_history or "[]")

    # Count user rounds
    user_rounds = sum(1 for msg in history if msg["role"] == "user")

    # Build messages for AI
    system_prompt = SYSTEM_PROMPT_DISCUSS.format(topic=checkin.topic)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    # Get AI response
    ai_response = await chat_completion(messages, temperature=0.8, max_tokens=600)

    # Check if draft was generated
    draft = None
    if "<<<DRAFT_START>>>" in ai_response and "<<<DRAFT_END>>>" in ai_response:
        if user_rounds < MIN_DISCUSSION_ROUNDS:
            # Too early for a draft — strip markers and continue discussing
            draft_start = ai_response.find("<<<DRAFT_START>>>")
            clean_reply = ai_response[:draft_start].strip() if draft_start > 0 else ai_response
            if not clean_reply:
                clean_reply = "能再多说一些吗？你有什么具体的经历想分享？"
            reply = clean_reply
            new_status = CheckInStatus.discussing
            draft = None
        else:
            start = ai_response.index("<<<DRAFT_START>>>") + len("<<<DRAFT_START>>>")
            end = ai_response.index("<<<DRAFT_END>>>")
            draft = ai_response[start:end].strip()
            # Clean reply - remove draft markers from display
            reply = ai_response[:ai_response.index("<<<DRAFT_START>>>")].strip()
            if not reply:
                reply = "我帮你整理了一份初稿，你看看怎么样～"
            new_status = CheckInStatus.draft_ready
            checkin.content = draft
    elif user_rounds >= MAX_DISCUSSION_ROUNDS:
        # Force draft generation after max rounds
        draft = await _force_generate_draft(checkin.topic, history + [{"role": "user", "content": user_message}])
        reply = "好的，我根据咱们聊的内容帮你整理了初稿～"
        new_status = CheckInStatus.draft_ready
        checkin.content = draft
    else:
        reply = ai_response
        new_status = CheckInStatus.discussing

    # Update conversation history
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": ai_response})
    checkin.conversation_history = json.dumps(history, ensure_ascii=False)
    checkin.status = new_status
    db.commit()

    return {"reply": reply, "status": new_status, "draft": draft}

async def _force_generate_draft(topic: str, conversation: list[dict]) -> str:
    """Force generate a draft based on conversation history."""
    conv_text = "\n".join([f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content']}" for m in conversation])

    prompt = f"""根据以下对话，帮用户写一篇微信公众号风格的文章初稿。

话题：{topic}

对话记录：
{conv_text}

要求：
- 字数140-300字
- 口语化，自然真实
- 以第一人称写
- 只输出文章内容，不要标题，不要额外说明"""

    messages = [{"role": "user", "content": prompt}]
    return await chat_completion(messages, temperature=0.7, max_tokens=500)

async def confirm_content(checkin: CheckIn, content: str, db: Session) -> None:
    """User confirms (possibly edited) content."""
    if checkin.status != CheckInStatus.draft_ready:
        raise ValueError("请先完成内容讨论，生成初稿后再确认")
    checkin.content = content
    checkin.status = CheckInStatus.pending
    db.commit()

async def confirm_publish(checkin: CheckIn, db: Session, user: User) -> dict:
    """User confirms publish. Updates checkin to completed."""
    if checkin.status == CheckInStatus.completed:
        raise ValueError("今日已完成发布，请勿重复提交")
    if checkin.status != CheckInStatus.pending:
        raise ValueError("请先确认内容后再发布")

    # Import here to avoid circular imports
    from .streak_service import calculate_and_update_streak
    from .points_service import apply_points_and_update_user
    from ..utils.time_utils import get_today_cst

    today = get_today_cst()

    # Update streak BEFORE calculating points (streak affects streak_bonus)
    new_streak = calculate_and_update_streak(user, today, db)

    # Apply points
    result = apply_points_and_update_user(user, checkin, db)

    # Complete the checkin
    checkin.status = CheckInStatus.completed
    checkin.completed_at = get_now_cst()
    db.commit()

    # Generate celebratory message
    message = _get_celebratory_message(new_streak, result["points_earned"])

    # Check and unlock achievements
    from .achievement_service import check_and_unlock
    newly_unlocked = check_and_unlock(user, checkin, db)

    return {
        "streak": new_streak,
        "points_earned": result["points_earned"],
        "total_points": result["total_points"],
        "level": result["level"],
        "diamonds": result["diamonds"],
        "message": message,
        "newly_unlocked": newly_unlocked,
    }


def _get_celebratory_message(streak: int, points_earned: int) -> str:
    """Generate a celebratory message based on streak."""
    if streak == 1:
        return f"太棒了！已连更1天，赚取{points_earned}积分！"
    elif streak < 7:
        return f"继续保持！已连更{streak}天，赚取{points_earned}积分！"
    elif streak < 30:
        return f"厉害！连更{streak}天了，赚取{points_earned}积分！"
    else:
        return f"传奇！连更{streak}天！赚取{points_earned}积分！"
