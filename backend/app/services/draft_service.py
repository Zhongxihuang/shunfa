"""
Draft service — handles quick-mode generation and draft confirmation flows.

Exported functions:
    - quick_generate(hot_topic, angle, platform, fact_block, api_key) -> dict
    - confirm_content(checkin, content, db, api_key) -> dict
    - build_quick_generate_context(...) -> str
    - build_quick_generate_context_from_checkin(checkin) -> str
    - format_for_platform(content, platform) -> str
"""

import asyncio
import json
import re

from sqlalchemy.orm import Session

from ..models import CheckIn, CheckInStatus
from ..services.ai_service import chat_completion
from ..services.generation_context import format_discussion_brief
from ..services.prompt_templates import prompts

FORBIDDEN_IDENTITY_PATTERNS = [
    re.compile(r"作为\s*(?:一名|一个)?\s*(?:AI|人工智能)?\s*(?:行业)?\s*从业者[，,、：:\s]*"),
    re.compile(
        r"站在\s*(?:AI|人工智能)?\s*(?:行业)?\s*从业者\s*(?:的)?\s*(?:角度|视角)[，,、：:\s]*"
    ),
    re.compile(
        r"从\s*(?:AI|人工智能)?\s*(?:行业)?\s*从业者\s*(?:的)?\s*(?:角度|视角)\s*(?:来看|看)?[，,、：:\s]*"
    ),
    re.compile(r"(?:AI|人工智能)?\s*(?:行业)?\s*从业者\s*(?:视角|角度)"),
    re.compile(r"作为\s*(?:一名|一个)?\s*(?:做)?AI(?:产品|方向)?的人[，,、：:\s]*"),
    re.compile(r"在AI公司工作(?:这些年)?[，,、：:\s]*"),
    re.compile(r"业内人看[，,、：:\s]*"),
    re.compile(r"懂行的人都知道[，,、：:\s]*"),
    re.compile(r"行业内幕[，,、：:\s]*"),
]


def remove_identity_framing(content: str) -> str:
    """Remove identity-backed phrasing the product does not want in drafts."""
    cleaned = content
    for pattern in FORBIDDEN_IDENTITY_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    lines = [line.strip() for line in cleaned.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def build_quick_generate_context(
    hot_topic: str,
    summary: str = "",
    source: str = "",
    published_at: str | None = None,
    url: str = "",
) -> str:
    """Build a fact block string from topic metadata."""
    facts = [f"标题：{hot_topic}"]
    if source:
        facts.append(f"来源：{source}")
    if published_at:
        facts.append(f"发布时间：{published_at}")
    if summary:
        facts.append(f"摘要：{summary}")
    if url:
        facts.append(f"原文链接：{url}")
    if len(facts) == 1:
        facts.append(
            "素材说明：当前只有标题，没有更多事实素材。"
            "不得补充任何标题外的具体事实、数字、时间线或背景。"
        )
    return "\n".join(facts)


def build_quick_generate_context_from_checkin(checkin: CheckIn) -> str:
    return build_quick_generate_context(
        hot_topic=checkin.topic,
        summary=checkin.topic_summary or "",
        source=checkin.topic_source or "",
        published_at=checkin.topic_published_at,
        url=checkin.topic_url or "",
    )


async def _generate_quick_draft(
    hot_topic: str,
    angle: str,
    platform: str,
    fact_block: str,
    discussion_brief: dict | None,
    temperature: float,
    api_key: str = "",
    extra_requirements: str = "",
) -> str:
    prompt = prompts.system_prompt_quick.format(
        hot_topic=hot_topic,
        angle=angle,
        platform=platform,
        fact_block=fact_block,
        discussion_brief=format_discussion_brief(discussion_brief),
    )
    if extra_requirements:
        prompt = f"{prompt}\n\n额外修正要求：\n{extra_requirements}"
    return await chat_completion(
        [{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=600,
        api_key=api_key,
    )


async def _check_quick_generate_grounding(draft: str, fact_block: str, api_key: str = "") -> dict:
    result = await chat_completion(
        [
            {
                "role": "user",
                "content": prompts.fact_guard_prompt.format(fact_block=fact_block, draft=draft),
            }
        ],
        temperature=0.1,
        max_tokens=300,
        api_key=api_key,
    )
    try:
        parsed = json.loads(result)
        return {
            "pass": bool(parsed.get("pass", False)),
            "issues": parsed.get("issues", []),
            "available": True,
        }
    except Exception:
        return {
            "pass": False,
            "issues": ["事实校验结果不可解析，请更保守地重写，只保留素材内能确认的事实。"],
            "available": False,
        }


async def _check_discussion_quality(
    draft: str, discussion_brief: dict | None, api_key: str = ""
) -> dict:
    issues: list[str] = []
    stripped = draft.strip()
    if not stripped:
        issues.append("内容为空")
    if "大家怎么看" in stripped or "你怎么看" in stripped:
        issues.append("结尾用了甩锅式提问")
    if any(token in stripped for token in ("据报道", "报道称", "新闻显示")) and len(stripped) < 180:
        issues.append("内容更像新闻复述，缺少明确判断")
    if any(pattern.search(stripped) for pattern in FORBIDDEN_IDENTITY_PATTERNS):
        issues.append("存在身份背书表达")

    return {"pass": not issues, "issues": issues, "available": False}


async def _check_analysis_depth(
    draft: str, discussion_brief: dict | None, api_key: str = ""
) -> dict:
    """Check whether the draft has real analytical depth (mechanism + concrete impact)."""
    result = await chat_completion(
        [
            {
                "role": "user",
                "content": prompts.analysis_depth_check_prompt.format(
                    draft=draft,
                    discussion_brief=format_discussion_brief(discussion_brief),
                ),
            }
        ],
        temperature=0.1,
        max_tokens=300,
        api_key=api_key,
    )
    try:
        parsed = json.loads(result)
        return {
            "pass": bool(parsed.get("pass", True)),
            "issues": parsed.get("issues", []),
            "available": True,
        }
    except Exception:
        # On parse error, don't block publishing — treat as pass
        return {"pass": True, "issues": [], "available": False}


async def quick_generate(
    hot_topic: str,
    angle: str,
    platform: str = "xiaohongshu",
    fact_block: str | None = None,
    discussion_brief: dict | None = None,
    api_key: str = "",
) -> dict:
    """
    Quick mode: single-shot content generation. No session state required.

    Returns {"content": str, "platform": str, "char_count": int}
    """
    effective_fact_block = fact_block or build_quick_generate_context(hot_topic)

    # Generate initial draft
    content = await _generate_quick_draft(
        hot_topic=hot_topic,
        angle=angle,
        platform=platform,
        fact_block=effective_fact_block,
        discussion_brief=discussion_brief,
        temperature=0.45,
        api_key=api_key,
    )
    content = remove_identity_framing(content.strip())

    # Run all three quality checks in parallel
    grounding, discussion, depth = await asyncio.gather(
        _check_quick_generate_grounding(content, effective_fact_block, api_key),
        _check_discussion_quality(content, discussion_brief, api_key),
        _check_analysis_depth(content, discussion_brief, api_key),
    )

    # Collect all failing issues and revise once if needed
    all_issues: list[str] = []
    if not grounding["pass"]:
        all_issues.extend(grounding.get("issues", []) or ["严格只使用事实素材，不补充素材外事实。"])
    if not discussion["pass"]:
        all_issues.extend(discussion.get("issues", []) or ["内容要更有分析深度，不要仅复述新闻。"])
    if not depth["pass"]:
        all_issues.extend(depth.get("issues", []) or ["分析深度不足，请展开机制层和影响层。"])

    if all_issues:
        fixes = "\n".join(f"- {issue}" for issue in all_issues)
        content = await _generate_quick_draft(
            hot_topic=hot_topic,
            angle=angle,
            platform=platform,
            fact_block=effective_fact_block,
            discussion_brief=discussion_brief,
            temperature=0.25,
            api_key=api_key,
            extra_requirements=f"上一版存在以下问题，请逐一修正：\n{fixes}",
        )
        content = remove_identity_framing(content.strip())
        # Re-run grounding check only to update the response field
        grounding = await _check_quick_generate_grounding(content, effective_fact_block, api_key)

    content = _format_for_platform(content, platform)
    return {
        "content": content,
        "platform": platform,
        "char_count": len(content),
        "fact_pass": bool(grounding.get("pass", False)),
        "fact_issues": grounding.get("issues", []),
        "discussion_pass": bool(discussion.get("pass", False)),
        "discussion_issues": discussion.get("issues", []),
    }


async def revise_content_with_feedback(
    checkin: CheckIn,
    content: str,
    issues: list[str],
    db: Session,
    api_key: str = "",
    instruction: str = "",
) -> dict:
    """Rewrite a draft using quality feedback while preserving stored topic context."""
    if checkin.status not in (CheckInStatus.draft_ready, CheckInStatus.pending):
        raise ValueError("请先生成初稿后再根据提示改写")

    from ..services.generation_context import (
        build_fact_block_from_checkin,
        parse_generation_context,
        update_generation_context,
    )

    context = parse_generation_context(checkin)
    platform = context.get("platform", "xiaohongshu")
    discussion_brief = context.get("discussion_brief")
    angle = context.get("selected_angle", "")
    fact_block = build_fact_block_from_checkin(checkin)
    feedback_lines = "\n".join(f"- {issue}" for issue in issues if issue.strip())
    if instruction.strip():
        feedback_lines = f"{feedback_lines}\n- {instruction.strip()}".strip()
    if not feedback_lines:
        feedback_lines = "- 让内容更有明确立场，更像参与热点讨论。"

    prompt = prompts.revise_content_prompt.format(
        topic=checkin.topic,
        platform=platform,
        angle=angle or "沿用当前角度",
        fact_block=fact_block,
        discussion_brief=format_discussion_brief(discussion_brief),
        current_content=content,
        issues=feedback_lines,
    )
    revised = await chat_completion(
        [{"role": "user", "content": prompt}],
        temperature=0.35,
        max_tokens=650,
        api_key=api_key,
    )
    revised = _format_for_platform(remove_identity_framing(revised.strip()), platform)

    has_snapshot_facts = any(
        [
            checkin.topic_source,
            checkin.topic_summary,
            checkin.topic_url,
            checkin.topic_published_at,
        ]
    )
    fact_result = (
        await _check_quick_generate_grounding(revised, fact_block, api_key)
        if has_snapshot_facts
        else {"pass": True, "issues": [], "available": False}
    )
    discussion_result = await _check_discussion_quality(revised, discussion_brief, api_key)

    checkin.content = revised
    checkin.status = CheckInStatus.draft_ready
    checkin.content_approved = False
    update_generation_context(
        checkin,
        revision_source_issues=issues,
        revision_instruction=instruction.strip() or None,
        revision_fact_guard={"pass": fact_result["pass"], "issues": fact_result.get("issues", [])},
        revision_discussion_guard={
            "pass": discussion_result["pass"],
            "issues": discussion_result.get("issues", []),
        },
    )
    db.commit()

    return {
        "content": revised,
        "char_count": len(revised),
        "fact_pass": fact_result["pass"],
        "fact_issues": fact_result.get("issues", []),
        "discussion_pass": discussion_result["pass"],
        "discussion_issues": discussion_result.get("issues", []),
    }


def _format_for_platform(content: str, platform: str) -> str:
    """Trim/adjust content to fit platform constraints."""

    def trim_to_limit(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:limit].rsplit("\n", 1)[0] if "\n" in text[:limit] else text[:limit]

    if platform == "twitter":
        content = trim_to_limit(content, 220)
    elif platform == "xiaohongshu":
        content = trim_to_limit(content, 300)
    elif platform == "weibo":
        content = trim_to_limit(content, 260)
    elif platform == "wechat_short":
        content = trim_to_limit(content, 380)
    elif platform == "linkedin":
        content = trim_to_limit(content, 500)
    return content


async def _quality_check(
    draft: str,
    topic: str,
    api_key: str = "",
    platform: str = "xiaohongshu",
    fact_block: str = "",
    discussion_brief: dict | None = None,
) -> dict:
    """检查初稿是否符合质量标准。返回 {pass: bool, issues: list[str]}"""
    prompt = prompts.quality_check_prompt.format(
        draft=draft,
        platform=platform,
        fact_block=fact_block or f"标题：{topic}",
        discussion_brief=format_discussion_brief(discussion_brief),
    )
    messages = [{"role": "user", "content": prompt}]
    result = await chat_completion(messages, temperature=0.3, max_tokens=300, api_key=api_key)
    try:
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


async def review_content_quality(checkin: CheckIn, content: str, api_key: str = "") -> dict:
    """Review content quality without mutating checkin state."""
    from ..services.generation_context import (
        build_fact_block_from_checkin,
        parse_generation_context,
    )

    context = parse_generation_context(checkin)
    platform = context.get("platform", "xiaohongshu")
    discussion_brief = context.get("discussion_brief")
    fact_block = build_fact_block_from_checkin(checkin)
    has_snapshot_facts = any(
        [
            checkin.topic_source,
            checkin.topic_summary,
            checkin.topic_url,
            checkin.topic_published_at,
        ]
    )
    fact_result = (
        await _check_quick_generate_grounding(content, fact_block, api_key)
        if has_snapshot_facts
        else {"pass": True, "issues": [], "available": False}
    )
    qc_result = await _quality_check(
        content,
        checkin.topic,
        api_key,
        platform=platform,
        fact_block=fact_block,
        discussion_brief=discussion_brief,
    )
    discussion_result = await _check_discussion_quality(content, discussion_brief, api_key)

    return {
        "quality_pass": bool(
            qc_result["pass"] and fact_result["pass"] and discussion_result["pass"]
        ),
        "quality_issues": qc_result.get("issues", []),
        "quality_available": qc_result.get("available", True),
        "fact_pass": fact_result["pass"],
        "fact_issues": fact_result.get("issues", []),
        "discussion_pass": discussion_result["pass"],
        "discussion_issues": discussion_result.get("issues", []),
        "topic": checkin.topic,
    }


async def confirm_content(checkin: CheckIn, content: str, db: Session, api_key: str = "") -> dict:
    """User confirms (possibly edited) content. Returns quality check result."""
    if checkin.status not in (CheckInStatus.draft_ready, CheckInStatus.pending):
        raise ValueError("请先完成内容讨论，生成初稿后再确认")

    review_result = await review_content_quality(checkin, content, api_key=api_key)

    checkin.content_approved = review_result["quality_pass"]
    checkin.content = content
    checkin.status = CheckInStatus.pending
    from ..services.generation_context import update_generation_context

    update_generation_context(
        checkin,
        confirm_fact_guard={
            "pass": review_result["fact_pass"],
            "issues": review_result.get("fact_issues", []),
        },
        confirm_quality_guard={
            "pass": review_result["quality_pass"],
            "issues": review_result.get("quality_issues", []),
        },
        confirm_discussion_guard={
            "pass": review_result["discussion_pass"],
            "issues": review_result.get("discussion_issues", []),
        },
    )
    db.commit()

    return review_result
