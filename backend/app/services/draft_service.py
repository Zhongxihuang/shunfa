"""
Draft service — handles quick-mode generation and draft confirmation flows.

Exported functions:
    - quick_generate(hot_topic, angle, platform, fact_block, api_key) -> dict
    - confirm_content(checkin, content, db, api_key) -> dict
    - build_quick_generate_context(...) -> str
    - build_quick_generate_context_from_checkin(checkin) -> str
    - format_for_platform(content, platform) -> str
"""

import json

from sqlalchemy.orm import Session

from ..models import CheckIn, CheckInStatus
from ..services.ai_service import chat_completion
from ..services.prompt_templates import prompts


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
    temperature: float,
    api_key: str = "",
    extra_requirements: str = "",
) -> str:
    prompt = prompts.system_prompt_quick.format(
        hot_topic=hot_topic,
        angle=angle,
        platform=platform,
        fact_block=fact_block,
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
                "content": prompts.fact_guard_prompt.format(
                    fact_block=fact_block, draft=draft
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
            "pass": bool(parsed.get("pass", False)),
            "issues": parsed.get("issues", []),
            "available": True,
        }
    except Exception:
        return {
            "pass": False,
            "issues": [
                "事实校验结果不可解析，请更保守地重写，只保留素材内能确认的事实。"
            ],
            "available": False,
        }


async def quick_generate(
    hot_topic: str,
    angle: str,
    platform: str = "xiaohongshu",
    fact_block: str | None = None,
    api_key: str = "",
) -> dict:
    """
    Quick mode: single-shot content generation. No session state required.

    Returns {"content": str, "platform": str, "char_count": int}
    """
    effective_fact_block = fact_block or build_quick_generate_context(hot_topic)

    content = await _generate_quick_draft(
        hot_topic=hot_topic,
        angle=angle,
        platform=platform,
        fact_block=effective_fact_block,
        temperature=0.45,
        api_key=api_key,
    )
    grounding = await _check_quick_generate_grounding(content, effective_fact_block, api_key)
    if not grounding["pass"]:
        fixes = (
            "\n".join(f"- {issue}" for issue in grounding["issues"])
            if grounding["issues"]
            else "- 严格只使用事实素材，不补充素材外事实。"
        )
        content = await _generate_quick_draft(
            hot_topic=hot_topic,
            angle=angle,
            platform=platform,
            fact_block=effective_fact_block,
            temperature=0.2,
            api_key=api_key,
            extra_requirements=(
                "上一版存在超出素材的事实，请严格删除或改写以下问题：\n"
                f"{fixes}"
            ),
        )
    content = _format_for_platform(content.strip(), platform)
    return {"content": content, "platform": platform, "char_count": len(content)}


def _format_for_platform(content: str, platform: str) -> str:
    """Trim/adjust content to fit platform constraints."""
    if platform == "twitter":
        if len(content) > 280:
            content = (
                content[:280].rsplit("\n", 1)[0]
                if "\n" in content[:280]
                else content[:280]
            )
    elif platform == "xiaohongshu":
        if len(content) > 300:
            content = (
                content[:300].rsplit("\n", 1)[0]
                if "\n" in content[:300]
                else content[:300]
            )
    elif platform == "linkedin":
        if len(content) > 500:
            content = (
                content[:500].rsplit("\n", 1)[0]
                if "\n" in content[:500]
                else content[:500]
            )
    return content


async def _quality_check(draft: str, topic: str, api_key: str = "") -> dict:
    """检查初稿是否符合质量标准。返回 {pass: bool, issues: list[str]}"""
    prompt = prompts.quality_check_prompt.format(draft=draft)
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


async def confirm_content(checkin: CheckIn, content: str, db: Session, api_key: str = "") -> dict:
    """User confirms (possibly edited) content. Returns quality check result."""
    if checkin.status not in (CheckInStatus.draft_ready, CheckInStatus.pending):
        raise ValueError("请先完成内容讨论，生成初稿后再确认")

    qc_result = await _quality_check(content, checkin.topic, api_key)
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
