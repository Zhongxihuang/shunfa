import json
from typing import Any

from ..models import CheckIn


def parse_generation_context(checkin: CheckIn) -> dict[str, Any]:
    if not checkin.generation_context:
        return {}
    try:
        data = json.loads(checkin.generation_context)
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def set_generation_context(checkin: CheckIn, context: dict[str, Any]) -> dict[str, Any]:
    checkin.generation_context = json.dumps(context, ensure_ascii=False)
    return context


def update_generation_context(checkin: CheckIn, **updates: Any) -> dict[str, Any]:
    context = parse_generation_context(checkin)
    for key, value in updates.items():
        if value is not None:
            context[key] = value
    return set_generation_context(checkin, context)


def build_fact_block_from_checkin(checkin: CheckIn) -> str:
    from .draft_service import build_quick_generate_context

    return build_quick_generate_context(
        hot_topic=checkin.topic,
        summary=checkin.topic_summary or "",
        source=checkin.topic_source or "",
        published_at=checkin.topic_published_at,
        url=checkin.topic_url or "",
    )


def build_discussion_brief(
    topic: str,
    fact_block: str,
    angle: str,
    platform: str = "xiaohongshu",
    opportunities: list[str] | None = None,
    risks: list[str] | None = None,
    counter_angle: str = "",
) -> dict[str, Any]:
    clean_opportunities = [item.strip() for item in opportunities or [] if item.strip()]
    clean_risks = [item.strip() for item in risks or [] if item.strip()]
    selected_stance = angle.strip() or f"围绕「{topic}」给出一个明确判断"
    return {
        "topic": topic,
        "facts": [line for line in fact_block.splitlines() if line.strip()],
        "fact_boundaries": [
            "只使用事实素材中明确给出的标题、来源、时间、摘要和链接",
            "不要补充素材外的数字、公司关系、发布时间线或监管结论",
        ],
        "heat_reason": clean_opportunities[0] if clean_opportunities else "这件事值得讨论，因为它暴露了热点背后的判断分歧。",
        "controversy_axis": counter_angle or "真正的分歧在于：这是短期新闻噪音，还是会改变用户、产品或行业判断的信号。",
        "supporting_camp": "赞同方会认为这件事释放了明确变化信号。",
        "opposing_camp": counter_angle or "反对方会认为这只是短期热度，不能过度解读。",
        "selected_stance": selected_stance,
        "stance_reason": "这个立场比单纯复述新闻更适合引发讨论。",
        "opening_hook": selected_stance,
        "discussion_trigger": "结尾留下一个可被赞同或反驳的判断，不使用“大家怎么看”式提问。",
        "opportunities": clean_opportunities,
        "risks": clean_risks,
        "platform": platform,
    }


def format_discussion_brief(brief: dict[str, Any] | None) -> str:
    if not brief:
        return "暂无结构化讨论策略。"
    lines = [
        f"核心立场：{brief.get('selected_stance', '')}",
        f"热度原因：{brief.get('heat_reason', '')}",
        f"争议轴：{brief.get('controversy_axis', '')}",
        f"反方观点：{brief.get('opposing_camp', '')}",
        f"开头钩子：{brief.get('opening_hook', '')}",
        f"讨论触发：{brief.get('discussion_trigger', '')}",
    ]
    opportunities = brief.get("opportunities") or []
    risks = brief.get("risks") or []
    if opportunities:
        lines.append("机会点：" + "；".join(opportunities[:4]))
    if risks:
        lines.append("风险提示：" + "；".join(risks[:4]))
    boundaries = brief.get("fact_boundaries") or []
    if boundaries:
        lines.append("事实边界：" + "；".join(boundaries[:4]))
    return "\n".join(line for line in lines if line.strip() and not line.endswith("："))
