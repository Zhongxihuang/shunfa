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
    analysis_frame = angle.strip() or f"把「{topic}」作为行业变化的信号，分析其现象、机制和二阶影响"
    return {
        "topic": topic,
        "facts": [line for line in fact_block.splitlines() if line.strip()],
        "fact_boundaries": [
            "只使用事实素材中明确给出的标题、来源、时间、摘要和链接",
            "不要补充素材外的数字、公司关系、发布时间线或监管结论",
        ],
        "analysis_frame": analysis_frame,
        "structural_tension": counter_angle
        or "核心张力：这是一次结构性变化，还是短期热度？它改变了哪个层面的规则？",
        "primary_view": clean_opportunities[0]
        if clean_opportunities
        else "这件事释放了可分析的行业信号。",
        "counter_view": counter_angle or "反方视角：事件的影响被高估，或因果链尚不清晰。",
        "lead_judgment": analysis_frame,
        "analysis_closer": "结尾给出一个有边界的趋势判断，不召唤读者「大家怎么看」。",
        "opportunities": clean_opportunities,
        "risks": clean_risks,
        "platform": platform,
    }


def format_discussion_brief(brief: dict[str, Any] | None) -> str:
    if not brief:
        return "暂无结构化分析策略。"
    lines = [
        f"分析框架：{brief.get('analysis_frame', '') or brief.get('selected_stance', '')}",
        f"结构性张力：{brief.get('structural_tension', '') or brief.get('controversy_axis', '')}",
        f"主要视角：{brief.get('primary_view', '') or brief.get('heat_reason', '')}",
        f"反向视角：{brief.get('counter_view', '') or brief.get('opposing_camp', '')}",
        f"开篇判断：{brief.get('lead_judgment', '') or brief.get('opening_hook', '')}",
        f"分析收尾：{brief.get('analysis_closer', '') or brief.get('discussion_trigger', '')}",
    ]
    opportunities = brief.get("opportunities") or []
    risks = brief.get("risks") or []
    if opportunities:
        lines.append("分析切入点：" + "；".join(opportunities[:4]))
    if risks:
        lines.append("风险提示：" + "；".join(risks[:4]))
    boundaries = brief.get("fact_boundaries") or []
    if boundaries:
        lines.append("事实边界：" + "；".join(boundaries[:4]))
    return "\n".join(line for line in lines if line.strip() and not line.endswith("："))
