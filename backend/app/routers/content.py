from fastapi import APIRouter, Depends, HTTPException, Path, Request
from sqlalchemy.orm import Session

from ..config import settings
from ..dependencies import get_current_user, get_db, get_resolved_api_key
from ..models import CheckIn, CheckInStatus, HotTopic, User
from ..rate_limit import limiter
from ..schemas import (
    ComposePostAssetsRequest,
    ComposePostAssetsResponse,
    ConfirmContentRequest,
    ConfirmPublishRequest,
    ContentFeedbackRequest,
    ContentFeedbackResponse,
    FormatPostRequest,
    FormattedPostResponse,
    MessageRequest,
    MessageResponse,
    PublishResponse,
    QuickGenerateRequest,
    QuickGenerateResponse,
    ReviewContentRequest,
    ReviewContentResponse,
    ReviseContentRequest,
    ReviseContentResponse,
)
from ..services.analytics import track
from ..services.compose_service import compose_post_assets
from ..services.content_service import AlreadyPublishedError, confirm_publish
from ..services.discussion_service import process_message
from ..services.draft_service import (
    confirm_content,
    review_content_quality,
    revise_content_with_feedback,
)
from ..services.fact_enrichment_service import enrich_facts
from ..services.generation_context import (
    build_discussion_brief,
    build_fact_block_from_checkin,
    load_generation_context,
    parse_generation_context,
    update_generation_context,
)
from ..services.generation_orchestrator import run_quick_generation
from ..services.prompt_templates import prompts
from ..utils.time_utils import get_now_cst, get_today_cst

router = APIRouter()


def get_today_hot_topic_or_404(topic_id: int, db: Session) -> HotTopic:
    topic = (
        db.query(HotTopic)
        .filter(
            HotTopic.id == topic_id,
            HotTopic.topic_date == get_today_cst(),
        )
        .first()
    )
    if not topic:
        raise HTTPException(status_code=404, detail="Today's hot topic not found")
    return topic


def get_checkin_or_404(checkin_id: int, user_id: int, db: Session) -> CheckIn:
    checkin = db.query(CheckIn).filter(CheckIn.id == checkin_id, CheckIn.user_id == user_id).first()
    if not checkin:
        raise HTTPException(status_code=404, detail="CheckIn not found")
    return checkin


def get_checkin_for_update(checkin_id: int, user_id: int, db: Session) -> CheckIn:
    """Fetch checkin with row lock to prevent concurrent updates (e.g. double-publish)."""
    checkin = (
        db.query(CheckIn)
        .filter(CheckIn.id == checkin_id, CheckIn.user_id == user_id)
        .with_for_update()
        .first()
    )
    if not checkin:
        raise HTTPException(status_code=404, detail="CheckIn not found")
    return checkin


@router.post("/quick_generate", response_model=QuickGenerateResponse)
@limiter.limit(settings.generation_rate_limit)
async def quick_generate_endpoint(
    request: Request,
    body: QuickGenerateRequest,
    current_user: User = Depends(get_current_user),
    api_key: str = Depends(get_resolved_api_key),
    db: Session = Depends(get_db),
):
    """Quick mode: generate content in ~30s from a hot topic + angle. Stateless."""
    checkin = None
    if body.checkin_id is not None:
        checkin = get_checkin_or_404(body.checkin_id, current_user.id, db)
        if checkin.status == CheckInStatus.completed:
            raise HTTPException(status_code=400, detail="今日已完成发布")

    topic_record = None
    if body.topic_id is not None:
        topic_record = get_today_hot_topic_or_404(body.topic_id, db)

    result = await run_quick_generation(
        db=db,
        user=current_user,
        api_key=api_key,
        hot_topic=body.hot_topic,
        angle=body.angle,
        platform=body.platform.value,
        discussion_brief=body.discussion_brief,
        opportunities=body.opportunities,
        risks=body.risks,
        checkin=checkin,
        topic_record=topic_record,
        charge_free_quota=getattr(request.state, "api_key_source", None) == "free_quota",
    )
    return QuickGenerateResponse(**result)


@router.post("/generate_content", response_model=MessageResponse)
@limiter.limit(settings.generation_rate_limit)
async def generate_content(
    request: Request,
    body: MessageRequest,
    current_user: User = Depends(get_current_user),
    api_key: str = Depends(get_resolved_api_key),
    db: Session = Depends(get_db),
):
    """Send a message in the discussion flow."""
    checkin = get_checkin_or_404(body.checkin_id, current_user.id, db)

    if checkin.status == CheckInStatus.completed:
        raise HTTPException(status_code=400, detail="今日已完成发布")

    if checkin.status not in (CheckInStatus.topic_selected, CheckInStatus.discussing):
        raise HTTPException(
            status_code=400, detail=f"当前状态不支持发送消息: {checkin.status.value}"
        )

    if checkin.status == CheckInStatus.topic_selected:
        checkin.status = CheckInStatus.discussing
        db.commit()

    context = parse_generation_context(checkin)
    if body.angle or body.platform or body.discussion_brief:
        context = update_generation_context(
            checkin,
            selected_angle=body.angle,
            platform=body.platform.value if body.platform else None,
            discussion_brief=body.discussion_brief,
            generation_mode="deep",
            prompt_version=prompts.version,
        )
        db.commit()
    platform = body.platform.value if body.platform else context.get("platform", "xiaohongshu")
    angle = body.angle or context.get("selected_angle", "")
    fact_block = build_fact_block_from_checkin(checkin)
    # Fact enrichment: reuse cached enrichment if available, else fetch
    if context.get("enriched_facts"):
        fact_block = context["enriched_facts"]
    else:
        fact_block = await enrich_facts(
            base_fact_block=fact_block,
            article_url=checkin.topic_url or "",
            hot_topic=checkin.topic,
            angle=angle,
        )
        if fact_block != build_fact_block_from_checkin(checkin):
            update_generation_context(checkin, enriched_facts=fact_block)
            db.commit()
    discussion_brief = (
        body.discussion_brief
        or context.get("discussion_brief")
        or build_discussion_brief(
            topic=checkin.topic,
            fact_block=fact_block,
            angle=angle,
            platform=platform,
            counter_angle=context.get("counter_angle", ""),
        )
    )
    result = await process_message(
        checkin,
        body.message,
        db,
        api_key=api_key,
        angle=angle,
        platform=platform,
        fact_block=fact_block,
        discussion_brief=discussion_brief,
    )
    track(
        "discuss_round",
        user_id=current_user.id,
        props={"checkin_id": checkin.id, "platform": platform},
    )
    # If this round produced a draft, mark the funnel transition and charge a
    # free-trial credit (discussion rounds that don't produce a draft stay free).
    if result.get("status") == CheckInStatus.draft_ready and result.get("draft"):
        track(
            "draft_generated",
            user_id=current_user.id,
            props={"checkin_id": checkin.id, "platform": platform},
        )
        if getattr(request.state, "api_key_source", None) == "free_quota":
            from ..services.free_quota import consume_free_quota

            consume_free_quota(db, current_user)
    return MessageResponse(**result)


@router.post("/confirm_content")
@limiter.limit(settings.ai_analysis_rate_limit)
async def confirm_content_endpoint(
    request: Request,
    body: ConfirmContentRequest,
    current_user: User = Depends(get_current_user),
    api_key: str = Depends(get_resolved_api_key),
    db: Session = Depends(get_db),
):
    """User confirms (possibly edited) draft content. Returns quality check result."""
    checkin = get_checkin_or_404(body.checkin_id, current_user.id, db)

    try:
        qc_result = await confirm_content(checkin, body.content, db, api_key=api_key)
        return {
            "status": "pending",
            "content_approved": qc_result["quality_pass"],
            "quality_issues": qc_result["quality_issues"],
            "quality_available": qc_result["quality_available"],
            "fact_pass": qc_result["fact_pass"],
            "fact_issues": qc_result["fact_issues"],
            "discussion_pass": qc_result["discussion_pass"],
            "discussion_issues": qc_result["discussion_issues"],
            "topic": qc_result["topic"],
            "message": "内容已确认。以下为质量提示，不影响发布。",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/review_content", response_model=ReviewContentResponse)
@limiter.limit(settings.ai_analysis_rate_limit)
async def review_content_endpoint(
    request: Request,
    body: ReviewContentRequest,
    current_user: User = Depends(get_current_user),
    api_key: str = Depends(get_resolved_api_key),
    db: Session = Depends(get_db),
):
    """Review content quality without changing the checkin status."""
    checkin = get_checkin_or_404(body.checkin_id, current_user.id, db)
    result = await review_content_quality(checkin, body.content, api_key=api_key)
    return ReviewContentResponse(
        content_approved=result["quality_pass"],
        quality_issues=result["quality_issues"],
        quality_available=result["quality_available"],
        fact_pass=result["fact_pass"],
        fact_issues=result["fact_issues"],
        discussion_pass=result["discussion_pass"],
        discussion_issues=result["discussion_issues"],
        topic=result["topic"],
    )


@router.post("/revise_content", response_model=ReviseContentResponse)
@limiter.limit(settings.generation_rate_limit)
async def revise_content_endpoint(
    request: Request,
    body: ReviseContentRequest,
    current_user: User = Depends(get_current_user),
    api_key: str = Depends(get_resolved_api_key),
    db: Session = Depends(get_db),
):
    """Rewrite the current draft using quality feedback from confirm_content."""
    checkin = get_checkin_or_404(body.checkin_id, current_user.id, db)
    try:
        result = await revise_content_with_feedback(
            checkin,
            body.content,
            body.issues,
            db,
            api_key=api_key,
            instruction=body.instruction or "",
        )
        return ReviseContentResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/content_feedback", response_model=ContentFeedbackResponse)
async def content_feedback_endpoint(
    request: ContentFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    checkin = get_checkin_or_404(request.checkin_id, current_user.id, db)
    if checkin.status not in (
        CheckInStatus.draft_ready,
        CheckInStatus.pending,
        CheckInStatus.completed,
    ):
        raise HTTPException(status_code=400, detail="当前阶段暂不支持反馈")

    checkin.content_feedback = request.feedback
    checkin.content_feedback_at = get_now_cst()
    update_generation_context(
        checkin,
        feedback_reason_tags=request.reason_tags,
        feedback_free_text=request.free_text,
    )
    db.commit()

    return ContentFeedbackResponse(checkin_id=checkin.id, feedback=request.feedback)


@router.get("/checkin/{checkin_id}")
async def get_checkin(
    checkin_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get checkin data including topic."""
    checkin = get_checkin_or_404(checkin_id, current_user.id, db)
    return {
        "id": checkin.id,
        "topic": checkin.topic,
        "topic_source": checkin.topic_source,
        "topic_url": checkin.topic_url,
        "topic_summary": checkin.topic_summary,
        "topic_published_at": checkin.topic_published_at,
        "content": checkin.content,
        "status": checkin.status.value,
        "content_approved": checkin.content_approved,
        "content_feedback": checkin.content_feedback,
        "generation_context": parse_generation_context(checkin),
    }


@router.post("/confirm_publish", response_model=PublishResponse)
@limiter.limit(settings.publish_rate_limit)
async def confirm_publish_endpoint(
    request: Request,
    body: ConfirmPublishRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """User confirms publish. Final step."""
    checkin = get_checkin_for_update(body.checkin_id, current_user.id, db)

    try:
        result = await confirm_publish(checkin, db, current_user)
        track(
            "publish",
            user_id=current_user.id,
            props={"checkin_id": checkin.id},
        )
        return PublishResponse(**result)
    except AlreadyPublishedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/compose_post_assets", response_model=ComposePostAssetsResponse)
@limiter.limit(settings.ai_analysis_rate_limit)
async def compose_post_assets_endpoint(
    request: Request,
    body: ComposePostAssetsRequest,
    current_user: User = Depends(get_current_user),
    api_key: str = Depends(get_resolved_api_key),
    db: Session = Depends(get_db),
) -> ComposePostAssetsResponse:
    """Generate post assets (pages, title, tags) from checkin content for image rendering."""
    checkin = get_checkin_or_404(body.checkin_id, current_user.id, db)
    result = await compose_post_assets(checkin, api_key)
    return ComposePostAssetsResponse(**result)


# ── W1.4: multi-platform format + export ────────────────────────────────────


def _serialize_compose_tags(checkin: CheckIn) -> list[str]:
    """Best-effort pull of tags from generation_context.compose_tags.

    The compose service stores its full result inside generation_context.
    On older checkins (before W1.4) this key may be missing — return [].
    """
    tags = load_generation_context(checkin).compose_tags
    return [str(t) for t in tags if t]


def _build_text_response(platform: str, requested: str, post) -> dict:
    """Combine title+body+tags into a single paste-ready string.

    Convention: we use double newlines (`\\n\\n`) between every section, and
    the platform-specific tag style. This matches the byte length that
    `format_post` already computed (its `char_count` reflects the
    `\n\n`-joined form), so the response's `char_count` and `len(text)`
    are always equal.
    """
    sections: list[str] = []
    if post.title:
        sections.append(post.title)
    if post.body:
        sections.append(post.body)
    if post.tags:
        if platform == "wechat_official":
            # 公众号 uses no inline hashtags in the body at all.
            pass
        elif platform == "weibo":
            sections.append(" ".join(f"#{t}#" for t in post.tags))
        elif platform == "moments":
            sections.append(" ".join(f"# {t}" for t in post.tags))
        else:
            sections.append(" ".join(f"#{t}" for t in post.tags))
    if post.truncated and post.truncated_marker:
        sections.append(post.truncated_marker)
    text = "\n\n".join(sections)
    return {
        "platform": platform,
        "requested_platform": requested,
        "title": post.title,
        "body": post.body,
        "tags": post.tags,
        "char_count": len(text),  # recompute from the actual `text` to stay in sync
        "truncated": post.truncated,
        "truncated_marker": post.truncated_marker,
        "text": text,
    }


@router.post("/preview/format", response_model=FormattedPostResponse)
async def preview_format_endpoint(
    body: FormatPostRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FormattedPostResponse:
    """Format one checkin for one target platform.

    This is the step-2 of the W1.4 "≤2 steps" promise. It is intentionally
    non-LLM: the formatters are deterministic and run in < 50ms. Frontend
    then gives the user a one-click "复制" button.

    Unknown platform ids fall back to `generic`. The response echoes both
    the requested and the actual platform so the UI can warn.
    """
    checkin = get_checkin_or_404(body.checkin_id, current_user.id, db)
    if not checkin.content:
        raise HTTPException(status_code=400, detail="CheckIn has no content to format")

    from ..services.publish_format_service import (
        SUPPORTED_PLATFORMS,
        format_post,
    )

    requested = body.platform
    if requested not in SUPPORTED_PLATFORMS:
        # Silent fallback. The "fallback" semantics are also why we don't
        # return 400 — we'd rather give the user something to paste than
        # a confusing error on a typo'd platform id.
        used_platform = "generic"
    else:
        used_platform = requested

    provided_tags = _serialize_compose_tags(checkin)
    post = format_post(
        topic=checkin.topic or "",
        content=checkin.content or "",
        platform=used_platform,
        provided_tags=provided_tags,
    )
    payload = _build_text_response(used_platform, requested, post)
    return FormattedPostResponse(checkin_id=checkin.id, **payload)


@router.get("/preview/export")
async def preview_export_endpoint(
    checkin_id: int,
    format: str = "md",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download the checkin content as .md or .txt.

    `format` is `md` (default) or `txt`. The response is a plain-text
    attachment so the browser can save it directly.
    """
    from fastapi.responses import PlainTextResponse

    from ..services.publish_format_service import export_markdown, export_plain

    fmt = (format or "md").lower()
    if fmt not in ("md", "txt"):
        raise HTTPException(status_code=400, detail="format must be 'md' or 'txt'")

    checkin = get_checkin_or_404(checkin_id, current_user.id, db)
    if not checkin.content:
        raise HTTPException(status_code=400, detail="CheckIn has no content to export")

    provided_tags = _serialize_compose_tags(checkin)
    topic = checkin.topic or "未命名"
    if fmt == "md":
        body = export_markdown(topic, checkin.content, provided_tags)
        media = "text/markdown; charset=utf-8"
        suffix = "md"
    else:
        body = export_plain(topic, checkin.content, provided_tags)
        media = "text/plain; charset=utf-8"
        suffix = "txt"

    # ASCII-safe filename for HTTP header. We keep the topic in the body,
    # the filename stays ASCII to dodge encoding-edge-case browsers.
    filename = f"shunfa-checkin-{checkin.id}.{suffix}"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    return PlainTextResponse(content=body, media_type=media, headers=headers)
