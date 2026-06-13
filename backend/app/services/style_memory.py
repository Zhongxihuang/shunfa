"""Style memory — the learning loop built on top of `content_feedback`.

Every time a user taps 👎 ("这版一般") on a draft, the preview pages record a
`content_feedback="down"` flag plus optional `feedback_reason_tags` and
`feedback_free_text` inside the check-in's generation context. On their own these
signals just sit in the database. This module turns them into an actionable
preference string that is injected into the next generation prompt via the
existing `extra_requirements` mechanism in `draft_service`, so the model stops
repeating the mistakes a user already flagged.

Design notes:
- Only 👎 feedback is actionable. A 👍 means "keep doing what you did" — it has
  no concrete correction to inject, so it is ignored here.
- The user's own free-text note is the strongest signal and is surfaced
  verbatim (most recent ones first, capped to keep the prompt small).
- Known reason tags map to concrete writing instructions; unknown tags are
  ignored rather than guessed at.
- The result is intentionally compact (a few lines) to avoid drowning the base
  prompt or blowing the token budget.
"""

from sqlalchemy.orm import Session

from ..models import CheckIn
from .generation_context import load_generation_context

# Reason tags emitted by the preview clients (web + miniprogram) map to a single
# concrete instruction each. Keep this vocabulary in sync with the frontends.
REASON_TAG_INSTRUCTIONS: dict[str, str] = {
    "too_flat": "之前的内容被反馈太平淡，请增强观点锐度，给出更鲜明的立场和判断。",
    "quality_issue": "之前的内容被反馈质量不足，请保证逻辑清晰、分析有深度，不要空泛复述。",
    "too_long": "之前的内容被反馈偏长，请更精炼，砍掉铺垫直接给观点。",
    "too_short": "之前的内容被反馈偏短，请把判断展开到机制层和影响层。",
    "off_topic": "之前的内容被反馈跑题，请紧扣给定角度，不要发散到无关话题。",
}

# How many free-text notes to surface (most recent first).
MAX_FREE_TEXT_NOTES = 2


def build_style_memory(db: Session, user_id: int, limit: int = 10) -> str:
    """Aggregate a user's recent 👎 feedback into a compact preference string.

    Args:
        db: active session.
        user_id: the user whose feedback history to read.
        limit: how many of the most-recent down-voted check-ins to consider.

    Returns:
        A short, newline-separated instruction block, or "" when there is no
        actionable signal.
    """
    rows = (
        db.query(CheckIn)
        .filter(CheckIn.user_id == user_id, CheckIn.content_feedback == "down")
        .order_by(
            CheckIn.content_feedback_at.desc().nullslast(),
            CheckIn.id.desc(),
        )
        .limit(limit)
        .all()
    )
    if not rows:
        return ""

    tag_instructions: list[str] = []
    seen_tags: set[str] = set()
    free_text_notes: list[str] = []

    for checkin in rows:
        context = load_generation_context(checkin)
        for tag in context.feedback_reason_tags:
            instruction = REASON_TAG_INSTRUCTIONS.get(tag)
            if instruction and tag not in seen_tags:
                seen_tags.add(tag)
                tag_instructions.append(instruction)
        note = (context.feedback_free_text or "").strip()
        if note and note not in free_text_notes and len(free_text_notes) < MAX_FREE_TEXT_NOTES:
            free_text_notes.append(note)

    lines: list[str] = list(tag_instructions)
    for note in free_text_notes:
        lines.append(f"用户明确提过的偏好：{note}")

    return "\n".join(lines)
