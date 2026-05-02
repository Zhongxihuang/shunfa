"""
Discussion service — handles the conversational content creation flow.

Exported functions:
    - process_message(checkin, user_message, db, api_key, angle) -> dict
    - reset_checkin_for_new_topic(checkin, topic, status) -> None
    - count_real_user_rounds(history) -> int
    - MIN_DISCUSSION_ROUNDS: int
    - MAX_DISCUSSION_ROUNDS: int
    - AUTO_SUGGEST_SENTINEL, REFRESH_ANGLES_SENTINEL, ANGLE_HISTORY_MARKER: str
"""

import json

from sqlalchemy.orm import Session

from ..models import CheckIn, CheckInStatus
from ..services.ai_service import chat_completion
from ..services.prompt_templates import prompts

MIN_DISCUSSION_ROUNDS = 1
MAX_DISCUSSION_ROUNDS = 3

AUTO_SUGGEST_SENTINEL = prompts.auto_suggest_sentinel
REFRESH_ANGLES_SENTINEL = prompts.refresh_angles_sentinel
ANGLE_HISTORY_MARKER = prompts.angle_history_marker


def _prune_angle_suggestion_history(history: list[dict]) -> list[dict]:
    """Remove angle suggestion system turns, including legacy assistant replies."""
    pruned: list[dict] = []
    skip_next_assistant = False
    for msg in history:
        content = msg.get("content")
        marker = msg.get("marker")
        role = msg.get("role")
        is_angle_marker = marker == ANGLE_HISTORY_MARKER
        is_angle_sentinel = content in (AUTO_SUGGEST_SENTINEL, REFRESH_ANGLES_SENTINEL)

        if is_angle_marker or is_angle_sentinel:
            skip_next_assistant = role == "user"
            continue

        if skip_next_assistant and role == "assistant":
            skip_next_assistant = False
            continue

        skip_next_assistant = False
        pruned.append(msg)
    return pruned


def count_real_user_rounds(history: list[dict]) -> int:
    return sum(
        1 for msg in _prune_angle_suggestion_history(history) if msg.get("role") == "user"
    )


def reset_checkin_for_new_topic(checkin: CheckIn, topic: str, status: CheckInStatus) -> None:
    """Clear stale state when restarting a same-day session with a new topic."""
    checkin.topic = topic
    checkin.topic_source = None
    checkin.topic_url = None
    checkin.topic_summary = None
    checkin.topic_published_at = None
    checkin.status = status
    checkin.content = None
    checkin.conversation_history = None
    checkin.content_approved = False
    checkin.content_feedback = None
    checkin.content_feedback_at = None
    checkin.points_earned = 0
    checkin.completed_at = None


async def _force_generate_draft(topic: str, conversation: list[dict], api_key: str = "") -> str:
    """Force generate a draft when max discussion rounds are reached."""
    conv_text = "\n".join(
        [f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content']}" for m in conversation]
    )
    prompt = prompts.force_generate_draft_prompt.format(topic=topic, conversation=conv_text)
    messages = [{"role": "user", "content": prompt}]
    return await chat_completion(messages, temperature=0.75, max_tokens=450, api_key=api_key)


async def process_message(
    checkin: CheckIn,
    user_message: str,
    db: Session,
    api_key: str = "",
    angle: str = "",
) -> dict:
    """
    Process a user message in the discussion flow.
    Returns {"reply": str, "status": CheckInStatus, "draft": Optional[str]}
    """
    if user_message in (AUTO_SUGGEST_SENTINEL, REFRESH_ANGLES_SENTINEL):
        prompt = prompts.angle_suggestion_prompt.format(
            topic=checkin.topic,
            angle=angle or "待用户选择",
        )
        ai_response = await chat_completion(
            [{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=300,
            api_key=api_key,
        )
        history = _prune_angle_suggestion_history(
            json.loads(checkin.conversation_history or "[]")
        )
        history.append({"role": "user", "content": user_message, "marker": ANGLE_HISTORY_MARKER})
        history.append({"role": "assistant", "content": ai_response, "marker": ANGLE_HISTORY_MARKER})
        checkin.conversation_history = json.dumps(history, ensure_ascii=False)
        checkin.status = CheckInStatus.discussing
        db.commit()
        return {"reply": ai_response, "status": CheckInStatus.discussing, "draft": None}

    history = json.loads(checkin.conversation_history or "[]")
    user_rounds = count_real_user_rounds(history)
    real_history = _prune_angle_suggestion_history(history)

    system_prompt = prompts.system_prompt_discuss.format(
        topic=checkin.topic,
        angle=angle or "（用户自定义方向）",
    )
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(real_history)
    messages.append({"role": "user", "content": user_message})

    ai_response = await chat_completion(messages, temperature=0.8, max_tokens=600, api_key=api_key)

    draft = None
    if "<<<DRAFT_START>>>" in ai_response and "<<<DRAFT_END>>>" in ai_response:
        if user_rounds < MIN_DISCUSSION_ROUNDS:
            draft_start = ai_response.find("<<<DRAFT_START>>>")
            clean_reply = (
                ai_response[:draft_start].strip() if draft_start > 0 else ai_response
            )
            if not clean_reply:
                clean_reply = "能再多说一些吗？你有什么具体的经历想分享？"
            reply = clean_reply
            new_status = CheckInStatus.discussing
            draft = None
        else:
            start = ai_response.index("<<<DRAFT_START>>>") + len("<<<DRAFT_START>>>")
            end = ai_response.index("<<<DRAFT_END>>>")
            draft = ai_response[start:end].strip()
            reply = ai_response[:ai_response.index("<<<DRAFT_START>>>")].strip()
            if not reply:
                reply = "我帮你整理了一份初稿，你看看怎么样～"
            new_status = CheckInStatus.draft_ready
            checkin.content = draft
    elif user_rounds >= MAX_DISCUSSION_ROUNDS:
        draft = await _force_generate_draft(
            checkin.topic,
            real_history + [{"role": "user", "content": user_message}],
            api_key=api_key,
        )
        reply = "好的，我根据咱们聊的内容帮你整理了初稿～"
        new_status = CheckInStatus.draft_ready
        checkin.content = draft
    else:
        reply = ai_response
        new_status = CheckInStatus.discussing

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": ai_response})
    checkin.conversation_history = json.dumps(history, ensure_ascii=False)
    checkin.status = new_status
    db.commit()

    return {"reply": reply, "status": new_status, "draft": draft}
