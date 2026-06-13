"""Orchestration for quick-mode content generation.

The `/quick_generate` HTTP handler used to carry ~70 lines of branching that had
nothing to do with HTTP: resolving the fact block from a hot-topic record vs. a
check-in snapshot, fact enrichment (with caching), discussion-brief assembly,
style-memory injection, the model call, and persisting the result + typed
generation_context back onto the check-in. That logic lives here so the router
stays thin (DI + 404/400 validation) and this flow becomes unit-testable in
isolation.

Inputs are already-resolved domain objects: the router performs the 404/400
lookups (those are HTTP concerns) and hands over `checkin` / `topic_record`.
"""

from typing import Any

from sqlalchemy.orm import Session

from ..models import CheckIn, CheckInStatus, HotTopic, User
from .draft_service import (
    build_quick_generate_context,
    build_quick_generate_context_from_checkin,
    quick_generate,
)
from .fact_enrichment_service import enrich_facts
from .generation_context import (
    build_discussion_brief,
    load_generation_context,
    update_generation_context,
)
from .prompt_templates import prompts
from .style_memory import build_style_memory


async def run_quick_generation(
    *,
    db: Session,
    user: User,
    api_key: str,
    hot_topic: str,
    angle: str,
    platform: str,
    discussion_brief: dict[str, Any] | None = None,
    opportunities: list[str] | None = None,
    risks: list[str] | None = None,
    checkin: CheckIn | None = None,
    topic_record: HotTopic | None = None,
    charge_free_quota: bool = False,
) -> dict[str, Any]:
    """Resolve facts, draft, persist, and return the quick-generate result dict.

    The router is responsible for the 404/400 guards (`checkin` not found,
    already completed; `topic_record` not today's). This function assumes those
    checks have passed.
    """
    fact_block = None
    counter_angle = ""

    if topic_record is not None:
        hot_topic = topic_record.title
        counter_angle = topic_record.ai_counter_angle or ""
        fact_block = build_quick_generate_context(
            hot_topic=topic_record.title,
            summary=topic_record.summary or "",
            source=topic_record.source,
            published_at=topic_record.published_at,
            url=topic_record.url,
        )
    elif checkin is not None:
        context = load_generation_context(checkin)
        counter_angle = context.counter_angle or ""
        if any(
            [
                checkin.topic_source,
                checkin.topic_summary,
                checkin.topic_url,
                checkin.topic_published_at,
            ]
        ):
            hot_topic = checkin.topic
            fact_block = build_quick_generate_context_from_checkin(checkin)

    effective_fact_block = fact_block or build_quick_generate_context(hot_topic)

    # Fact enrichment: try to get more context before drafting.
    article_url = (
        (topic_record.url if topic_record else None) or (checkin.topic_url if checkin else "") or ""
    )
    cached_facts = load_generation_context(checkin).enriched_facts if checkin else None
    if cached_facts:
        # Reuse cached enrichment from a prior generate/revise call.
        effective_fact_block = cached_facts
    else:
        effective_fact_block = await enrich_facts(
            base_fact_block=effective_fact_block,
            article_url=article_url,
            hot_topic=hot_topic,
            angle=angle,
        )

    resolved_brief = discussion_brief or build_discussion_brief(
        topic=hot_topic,
        fact_block=effective_fact_block,
        angle=angle,
        platform=platform,
        opportunities=opportunities,
        risks=risks,
        counter_angle=counter_angle,
    )
    style_memory = build_style_memory(db, user.id)
    result = await quick_generate(
        hot_topic=hot_topic,
        angle=angle,
        platform=platform,
        fact_block=effective_fact_block,
        discussion_brief=resolved_brief,
        api_key=api_key,
        style_memory=style_memory,
    )

    if checkin is not None:
        checkin.topic = hot_topic
        if topic_record is not None:
            checkin.topic_source = topic_record.source
            checkin.topic_url = topic_record.url
            checkin.topic_summary = topic_record.summary
            checkin.topic_published_at = topic_record.published_at
        checkin.content = result["content"]
        checkin.status = CheckInStatus.draft_ready
        update_generation_context(
            checkin,
            generation_mode="quick",
            platform=result["platform"],
            selected_angle=angle,
            discussion_brief=resolved_brief,
            char_count=result["char_count"],
            fact_guard_result={"pass": result["fact_pass"], "issues": result["fact_issues"]},
            discussion_guard_result={
                "pass": result["discussion_pass"],
                "issues": result["discussion_issues"],
            },
            hot_topic_id=topic_record.id if topic_record else None,
            hot_topic_score=topic_record.score if topic_record else None,
            hot_topic_category=topic_record.category if topic_record else None,
            source_angle=topic_record.ai_angle if topic_record else None,
            counter_angle=topic_record.ai_counter_angle if topic_record else counter_angle,
            prompt_version=prompts.version,
            enriched_facts=effective_fact_block,
        )
        db.commit()

    # Charge a free-trial credit if this draft ran on the shared key.
    if charge_free_quota:
        from .free_quota import consume_free_quota

        consume_free_quota(db, user)

    return result
