import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from ..models import CheckIn, CheckInStatus, User
from ..utils.time_utils import get_now_cst
from .ai_service import chat_completion

# How many discussion rounds before we try to generate a draft
MIN_DISCUSSION_ROUNDS = 1
MAX_DISCUSSION_ROUNDS = 3

SYSTEM_PROMPT_DISCUSS = """你是顺发AI洞察者内容助手，帮用户在社交媒体上持续输出有观点的AI内容，经营"AI行业洞察者"人设。

收到用户消息后，立刻判断并执行：
- 如果用户选了角度编号（如"1"、"2"），立即生成初稿，不追问。
- 如果用户说"随便"、"都行"、"不知道"，用推荐角度直接生成初稿。
- 如果用户说了具体想法，立即生成初稿。
- 生成初稿时用：<<<DRAFT_START>>>初稿内容<<<DRAFT_END>>>

【追问风格】（仅当用户明确要求换方向时使用）
- 提供2-3个可选角度，编号列出
- 一次只问一个问题

【人设锚点】
像你在字节/阿里做AI方向的朋友，下班后在朋友圈随手写的。不是自媒体运营，是从业者的随手记录。

【格式要求（小红书/朋友圈）】
- 总字数 140-220 字
- 分 3-6 个自然段落，每段一行
- 标点正常使用，不刻意堆叠感叹号和省略号
- 不写标题，不写开头总起句
- 不用"首先、其次、最后、总的来说"等结构词

【内容要求】
- 必须有从业者视角——读者觉得"这人确实在这个行业"
- 必须有观点——不是描述新闻，而是判断趋势/原因/影响
- 细节要具体：产品名、公司名、具体数字或场景
- 禁止"正确但无聊"的泛泛感慨

【语气要求】
- 平实自信，偶尔有锐度，不刻意煽情
- 用"我"开头，自然口语
- 有明确立场，不骑墙

反例（不得出现类似语气）：
× "这不就是在告诉我们...！！！"——刻意煽情
× "大家怎么看"——甩锅读者
× "有人觉得A，也有人觉得B"——没有立场
× "#AI #科技"——标签污染

当前热点：{topic}
推荐角度：{angle}"""


SYSTEM_PROMPT_QUICK = """你是一个在大厂做AI方向的从业者，随手写一条社交媒体内容。

基于给定热点和角度，直接生成内容。不问问题，不说"好的"。
有且只有一个明确立场，全文围绕这个立场。
有从业者视角，让人觉得"这人确实在这个行业"。

热点：{hot_topic}
推荐角度：{angle}
目标平台：{platform}

平台格式：
- xiaohongshu（小红书/朋友圈）：140-220字，短段落换行，口语但不卖萌，观点清晰
- twitter（推特/微博）：100-180字，一个核心观点，简洁有力
- linkedin（领英）：200-350字，专业语气，背景+观点+延伸思考

直接输出内容，不要解释。"""

AUTO_SUGGEST_SENTINEL = "__auto_suggest_angles__"

ANGLE_SUGGESTION_PROMPT = """针对AI热点「{topic}」（推荐角度参考：{angle}），给出 2-3 个写作角度。

要求：
- 每个角度是一个有立场的判断，不是事实描述
- 每个角度 15-25 字，要具体
- 编号列出（1. 2. 3.）
- 像同行聊天时抛出的话题
- 最后加"选编号，或直接说你的想法"
- 不要开场白

角度类型参考：
- "行业内幕"类：只有从业者知道的信息差
- "反常识"类：看起来对但实际上错的行业认知
- "趋势判断"类：基于事实的方向性判断"""

REFRESH_ANGLES_SENTINEL = "__refresh_angles__"

# Marker in conversation history that separates angle suggestions from real user input
ANGLE_HISTORY_MARKER = "__angle_suggestion__"


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
    return sum(1 for msg in _prune_angle_suggestion_history(history) if msg.get("role") == "user")


def reset_checkin_for_new_topic(checkin: CheckIn, topic: str, status: CheckInStatus) -> None:
    """Clear stale state when restarting a same-day session with a new topic."""
    checkin.topic = topic
    checkin.status = status
    checkin.content = None
    checkin.conversation_history = None
    checkin.content_approved = False
    checkin.content_feedback = None
    checkin.content_feedback_at = None
    checkin.points_earned = 0
    checkin.completed_at = None

async def quick_generate(hot_topic: str, angle: str, platform: str = "xiaohongshu") -> dict:
    """Quick mode: single-shot content generation. No session state required.

    Returns {"content": str, "platform": str, "char_count": int}
    """
    prompt = SYSTEM_PROMPT_QUICK.format(
        hot_topic=hot_topic,
        angle=angle,
        platform=platform,
    )
    content = await chat_completion(
        [{"role": "user", "content": prompt}],
        temperature=0.75,
        max_tokens=600,
    )
    content = _format_for_platform(content.strip(), platform)
    return {"content": content, "platform": platform, "char_count": len(content)}


def _format_for_platform(content: str, platform: str) -> str:
    """Trim / adjust content to fit platform constraints."""
    if platform == "twitter":
        # Hard cap at 280 chars; try to cut at last sentence boundary
        if len(content) > 280:
            content = content[:280].rsplit("\n", 1)[0] if "\n" in content[:280] else content[:280]
    elif platform == "xiaohongshu":
        # 140-220 chars target; if over 300 chars trim to last newline within 300
        if len(content) > 300:
            content = content[:300].rsplit("\n", 1)[0] if "\n" in content[:300] else content[:300]
    elif platform == "linkedin":
        # 200-400 chars target; allow up to 500
        if len(content) > 500:
            content = content[:500].rsplit("\n", 1)[0] if "\n" in content[:500] else content[:500]
    return content


async def process_message(
    checkin: CheckIn,
    user_message: str,
    db: Session,
    angle: str = "",
) -> dict:
    """
    Process a user message in the discussion flow.
    Returns {"reply": str, "status": CheckInStatus, "draft": Optional[str]}
    """
    # Handle angle suggestion on page load or refresh
    if user_message in (AUTO_SUGGEST_SENTINEL, REFRESH_ANGLES_SENTINEL):
        prompt = ANGLE_SUGGESTION_PROMPT.format(
            topic=checkin.topic,
            angle=angle or "待用户选择",
        )
        ai_response = await chat_completion(
            [{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=300,
        )
        history = _prune_angle_suggestion_history(json.loads(checkin.conversation_history or "[]"))
        history.append({"role": "user", "content": user_message, "marker": ANGLE_HISTORY_MARKER})
        history.append({"role": "assistant", "content": ai_response, "marker": ANGLE_HISTORY_MARKER})
        checkin.conversation_history = json.dumps(history, ensure_ascii=False)
        checkin.status = CheckInStatus.discussing
        db.commit()
        return {"reply": ai_response, "status": CheckInStatus.discussing, "draft": None}

    # Load conversation history
    history = json.loads(checkin.conversation_history or "[]")

    # Count real user rounds (skip angle suggestion entries)
    user_rounds = count_real_user_rounds(history)

    # Strip angle suggestions from history — they are context only, not real conversation
    real_history = _prune_angle_suggestion_history(history)

    # Build messages for AI
    system_prompt = SYSTEM_PROMPT_DISCUSS.format(
        topic=checkin.topic,
        angle=angle or "（用户自定义方向）",
    )
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(real_history)
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
        draft = await _force_generate_draft(checkin.topic, real_history + [{"role": "user", "content": user_message}])
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

    prompt = f"""根据以下信息，写一条小红书/朋友圈风格的帖子。

【格式要求】
- 总字数 140-220 字
- 分 3-6 个自然段落，每段一行
- 标点正常使用，不刻意堆叠感叹号和省略号
- 不写标题，不写开头总起句
- 不用"首先、其次、最后、总的来说"等结构词

【内容要求】
- 必须有从业者视角——读者觉得"这人确实在这个行业"
- 必须有观点——不是描述新闻，而是判断趋势/原因/影响
- 细节要具体：产品名、公司名、具体数字或场景
- 禁止"正确但无聊"的泛泛感慨

【语气要求】
- 像从业者朋友圈随手写的，平实自信，偶尔犀利
- 自然口语，以"我"开头
- 有明确立场，不骑墙

话题：{topic}
用户素材：
{conv_text}

直接输出帖子内容，不要解释。"""

    messages = [{"role": "user", "content": prompt}]
    return await chat_completion(messages, temperature=0.75, max_tokens=450)

async def _quality_check(draft: str, topic: str) -> dict:
    """检查初稿是否符合质量标准。返回 {pass: bool, issues: list[str]}"""
    prompt = f"""审查以下小红书帖子，判断它是否值得发布。

质量标准（必须全部满足）：
1. 有从业者视角——不是谁都写得出来的感慨
2. 有明确立场——读者知道作者支持/反对什么，不是两边都说
3. 有事实锚点——至少有一个具体产品名/数字/公司名
4. 语气成熟——不像学生写的感想，像有几年工作经验的人写的
5. 格式干净——无 # 标签，无连续感叹号，无波浪号

帖子内容：
{draft}

话题：{topic}

逐条判断是否符合以上标准，用 JSON 输出：
{{"pass": true/false, "issues": ["具体问题描述"]}}
"""
    messages = [{"role": "user", "content": prompt}]
    result = await chat_completion(messages, temperature=0.3, max_tokens=300)
    try:
        import json
        parsed = json.loads(result)
        return {
            "pass": bool(parsed.get("pass", False)),
            "issues": parsed.get("issues", []),
            "available": True,
        }
    except Exception:
        return {
            "pass": False,
            "issues": ["本次质量提示暂不可用，可直接发布"],
            "available": False,
        }


async def confirm_content(checkin: CheckIn, content: str, db: Session) -> dict:
    """User confirms (possibly edited) content. Returns quality check result."""
    if checkin.status not in (CheckInStatus.draft_ready, CheckInStatus.pending):
        raise ValueError("请先完成内容讨论，生成初稿后再确认")

    # AI 质量自检
    qc_result = await _quality_check(content, checkin.topic)
    checkin.content_approved = qc_result["pass"]

    checkin.content = content
    checkin.status = CheckInStatus.pending
    db.commit()

    return {
        "quality_pass": qc_result["pass"],
        "quality_issues": qc_result.get("issues", []),
        "quality_available": qc_result.get("available", True),
        "topic": checkin.topic,
    }

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
