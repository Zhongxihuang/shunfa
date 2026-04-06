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
- 如果用户选了角度编号（如"1"、"2"），**立即生成初稿**。不要说"好的"，不要追问，直接写。
- 如果用户说了类似"不知道"、"随便"、"都行"，先追问一句，不要直接写稿。
- 如果用户说了具体的内容或想法，**立即生成初稿**。不要追问，不要说"我理解"。
- 生成初稿时，用格式包裹：<<<DRAFT_START>>>初稿内容<<<DRAFT_END>>>

【追问风格】（当用户回答模糊时用）
- 用懂AI圈子的朋友的口吻——你知道这个话题最有争议的点在哪
- 提供2-3个可选角度让用户选择，而不是开放式追问
- 一次只问一个问题，有画面感，触发用户的圈内记忆
- 不要问"你有什么看法"，问"你是不是也觉得..."、"你们团队有没有..."

【格式要求（小红书/朋友圈）】（必须严格遵守）
- 总字数 140-220 字
- 分 3-6 个短句，每句一行
- 大量使用"..."、"！"、"？"制造情绪起伏
- 不要写标题、不要开头总起句
- 不要用"首先、其次、最后、总的来说、其实我认为"等结构词
- 不要用句号结尾句

【内容要求】（最重要）
- **必须有AI圈洞察**——读者看完觉得"这只有真正在关注AI的人才知道"，愿意转发给同行
- **必须有观点**——不是描述事实，而是说明趋势/原因/影响
- **必须有身份信号**——发出去代表用户是关注AI的人，不是路人
- **禁止"正确但无聊"**——任何人都能说出来的通用感慨，一概不许出现
- 细节要具体：具体的数字、产品名、场景，不是一般性的描述

【语气要求】
- 像给AI圈朋友发消息，不是写作文
- 有情绪（惊喜、震惊、顿悟、吐槽）
- 用"我"开头，自然口语
- 可以有个人立场，像懂行的人在评论这件事

【禁止出现的词句——违反即重写】
- 任何 # 标签（绝对禁止）
- "大家怎么看"、"你们觉得呢"、"欢迎讨论"（禁止甩锅给读者）
- "最近聊这个事的人挺多"、"这件事引发了广泛讨论"（废话开头）
- "有人觉得A，也有人觉得B"（没有立场的骑墙描述）
- "工作和生活平衡"、"保持专注"、"个人成长"、"总的来说"
- "其实我认为"、"值得注意的是"、"不得不说"
- "要保持积极"、"要相信自己"、"不要太在意"
- "大家都有过"、"这是一个普遍现象"

【必须做到】
- 有且只有一个明确立场，全文围绕这个立场展开
- 读完知道作者支持什么/反对什么，不是两边都说

当前热点：{topic}
推荐角度：{angle}"""


SYSTEM_PROMPT_QUICK = """你是顺发AI洞察者内容助手。用户选了一个AI热点和推荐角度，你要在30秒内生成一条可以直接发出去的内容。

要求：
- 直接生成内容，不要问问题，不要说"好的"
- 基于给定的热点和推荐角度生成，不要偏离
- 有且只有一个明确立场，全文围绕这个立场展开
- 有AI圈洞察，让人觉得"这人真的在关注AI"
- 绝对禁止：# 标签、"大家怎么看"、"有人觉得A也有人觉得B"、骑墙式描述

热点：{hot_topic}
推荐角度：{angle}
目标平台：{platform}

平台格式要求：
- xiaohongshu（小红书/朋友圈）：140-220字，短句换行，情绪化口语，用"..."和"！"
- twitter（推特/微博）：100-180字，一个核心观点，简洁有力
- linkedin（领英）：200-350字，专业语气，背景+观点+延伸思考，可以用段落

直接输出内容，不要任何解释或包装文字。"""

AUTO_SUGGEST_SENTINEL = "__auto_suggest_angles__"

ANGLE_SUGGESTION_PROMPT = """针对AI热点「{topic}」（推荐角度参考：{angle}），给出 2-3 个能写出"AI洞察者"风格的具体写作角度。

要求：
- 每个角度是一个有观点的立场，不是事实描述
- 每个角度用 15-25 字写出，要有画面感或情绪点
- 编号列出（1. 2. 3.）
- 轻松语气，像AI圈子里的朋友帮你出主意
- 最后加一句"选一个编号，或者直接说你的想法～"
- 不要开场白，直接列出角度

角度示例风格：
- "观点"类：一个反常识的AI行业洞察，让同行想转发
- "吐槽"类：AI从业者才懂的那个痛点，说出来别人会会心一笑
- "发现"类：大家都见过但没人说破的AI行业现象
- "预判"类：基于这个热点，对行业趋势的判断"""

REFRESH_ANGLES_SENTINEL = "__refresh_angles__"

# Marker in conversation history that separates angle suggestions from real user input
ANGLE_HISTORY_MARKER = "__angle_suggestion__"

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
        history = json.loads(checkin.conversation_history or "[]")
        # Remove any previous angle suggestions before adding new ones
        history = [m for m in history if m.get("content") not in (AUTO_SUGGEST_SENTINEL, REFRESH_ANGLES_SENTINEL)]
        history.append({"role": "user", "content": user_message, "marker": ANGLE_HISTORY_MARKER})
        history.append({"role": "assistant", "content": ai_response})
        checkin.conversation_history = json.dumps(history, ensure_ascii=False)
        checkin.status = CheckInStatus.discussing
        db.commit()
        return {"reply": ai_response, "status": CheckInStatus.discussing, "draft": None}

    # Load conversation history
    history = json.loads(checkin.conversation_history or "[]")

    # Count real user rounds (skip angle suggestion entries)
    user_rounds = sum(
        1 for msg in history
        if msg["role"] == "user" and msg.get("marker") != ANGLE_HISTORY_MARKER
    )

    # Strip angle suggestions from history — they are context only, not real conversation
    real_history = [
        m for m in history
        if m.get("marker") != ANGLE_HISTORY_MARKER and m.get("content") not in (AUTO_SUGGEST_SENTINEL, REFRESH_ANGLES_SENTINEL)
    ]

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

【格式要求】（必须严格遵守）
- 总字数 140-220 字
- 分 3-6 个短句，每句一行，不用句号结尾
- 大量使用"..."、"！"、"？"制造情绪起伏
- 不要写标题、不要总起句
- 不要用"首先、其次、最后、总的来说、其实我认为"等结构词

【内容要求】（最重要）
- **必须有行业/圈子洞察**——读者看完觉得"这只有懂行的人才知道"，愿意转发给同行
- **必须有精准共鸣点**——读者看完觉得"这不就是我吗"，不是泛泛的感慨
- **必须有身份信号**——发出去代表用户是哪种人，不是一个普通感慨
- **禁止"正确但无聊"**——任何人都能说出来的通用感慨，一概不许出现
- 细节要具体：具体的时间、动作、对话、数字，不是一般性的描述

【语气要求】
- 像给闺蜜/朋友发消息，有情绪（惊喜、崩溃、顿悟、吐槽）
- 有画面感的细节，不是泛泛而谈
- 自然口语，以"我"开头

【禁止词句】
"工作和生活平衡"、"保持专注"、"个人成长"、"总的来说"、
"其实我认为"、"值得注意的是"、任何"#"标签、
"要保持积极"、"要相信自己"、"不要太在意"、
"大家都有过"、"这是一个普遍现象"

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
1. 有行业/圈子洞察——不是谁都写得出来的感慨
2. 有精准共鸣点——读者会觉得"这不就是我吗"
3. 有身份信号——发出去能代表作者是哪种人
4. 细节具体——有具体场景/时间/动作，不是一般性描述

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
        return json.loads(result)
    except:
        return {"pass": True, "issues": []}  # 降级兜底


async def confirm_content(checkin: CheckIn, content: str, db: Session) -> dict:
    """User confirms (possibly edited) content. Returns quality check result."""
    if checkin.status != CheckInStatus.draft_ready:
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
