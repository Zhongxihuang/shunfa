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
from ..services.compose_service import compose_post_assets
from ..services.content_service import confirm_publish
from ..services.discussion_service import process_message
from ..services.draft_service import (
    build_quick_generate_context,
    build_quick_generate_context_from_checkin,
    confirm_content,
    quick_generate,
    review_content_quality,
    revise_content_with_feedback,
)
from ..services.generation_context import (
    build_discussion_brief,
    build_fact_block_from_checkin,
    parse_generation_context,
    update_generation_context,
)
from ..utils.time_utils import get_now_cst, get_today_cst

router = APIRouter()


def get_today_hot_topic_or_404(topic_id: int, db: Session) -> HotTopic:
    topic = db.query(HotTopic).filter(
        HotTopic.id == topic_id,
        HotTopic.topic_date == get_today_cst(),
    ).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Today's hot topic not found")
    return topic


def get_checkin_or_404(checkin_id: int, user_id: int, db: Session) -> CheckIn:
    checkin = db.query(CheckIn).filter(
        CheckIn.id == checkin_id,
        CheckIn.user_id == user_id
    ).first()
    if not checkin:
        raise HTTPException(status_code=404, detail="CheckIn not found")
    return checkin


def get_checkin_for_update(checkin_id: int, user_id: int, db: Session) -> CheckIn:
    """Fetch checkin with row lock to prevent concurrent updates (e.g. double-publish)."""
    checkin = db.query(CheckIn).filter(
        CheckIn.id == checkin_id,
        CheckIn.user_id == user_id
    ).with_for_update().first()
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
    hot_topic = body.hot_topic
    fact_block = None
    topic_record = None
    counter_angle = ""
    if body.topic_id is not None:
        topic_record = get_today_hot_topic_or_404(body.topic_id, db)
        hot_topic = topic_record.title
        counter_angle = topic_record.ai_counter_angle or ""
        fact_block = build_quick_generate_context(
            hot_topic=topic_record.title,
            summary=topic_record.summary or "",
            source=topic_record.source,
            published_at=topic_record.published_at,
            url=topic_record.url,
        )
    elif body.checkin_id is not None:
        checkin = get_checkin_or_404(body.checkin_id, current_user.id, db)
        context = parse_generation_context(checkin)
        counter_angle = context.get("counter_angle", "")
        if any([checkin.topic_source, checkin.topic_summary, checkin.topic_url, checkin.topic_published_at]):
            hot_topic = checkin.topic
            fact_block = build_quick_generate_context_from_checkin(checkin)

    effective_fact_block = fact_block or build_quick_generate_context(hot_topic)
    discussion_brief = body.discussion_brief or build_discussion_brief(
        topic=hot_topic,
        fact_block=effective_fact_block,
        angle=body.angle,
        platform=body.platform.value,
        opportunities=body.opportunities,
        risks=body.risks,
        counter_angle=counter_angle,
    )
    result = await quick_generate(
        hot_topic=hot_topic,
        angle=body.angle,
        platform=body.platform.value,
        fact_block=effective_fact_block,
        discussion_brief=discussion_brief,
        api_key=api_key,
    )
    if body.checkin_id is not None:
        checkin = get_checkin_or_404(body.checkin_id, current_user.id, db)
        if checkin.status == CheckInStatus.completed:
            raise HTTPException(status_code=400, detail="今日已完成发布")
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
            selected_angle=body.angle,
            discussion_brief=discussion_brief,
            char_count=result["char_count"],
            fact_guard_result={"pass": result["fact_pass"], "issues": result["fact_issues"]},
            discussion_guard_result={"pass": result["discussion_pass"], "issues": result["discussion_issues"]},
            hot_topic_id=topic_record.id if topic_record else None,
            hot_topic_score=topic_record.score if topic_record else None,
            hot_topic_category=topic_record.category if topic_record else None,
            source_angle=topic_record.ai_angle if topic_record else None,
            counter_angle=topic_record.ai_counter_angle if topic_record else counter_angle,
        )
        db.commit()
    return QuickGenerateResponse(**result)


@router.post("/generate_content", response_model=MessageResponse)
@limiter.limit(settings.generation_rate_limit)
async def generate_content(
    request: Request,
    body: MessageRequest,
    current_user: User = Depends(get_current_user),
    api_key: str = Depends(get_resolved_api_key),
    db: Session = Depends(get_db)
):
    """Send a message in the discussion flow."""
    checkin = get_checkin_or_404(body.checkin_id, current_user.id, db)

    if checkin.status == CheckInStatus.completed:
        raise HTTPException(status_code=400, detail="今日已完成发布")

    if checkin.status not in (CheckInStatus.topic_selected, CheckInStatus.discussing):
        raise HTTPException(status_code=400, detail=f"当前状态不支持发送消息: {checkin.status.value}")

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
        )
        db.commit()
    platform = body.platform.value if body.platform else context.get("platform", "xiaohongshu")
    angle = body.angle or context.get("selected_angle", "")
    fact_block = build_fact_block_from_checkin(checkin)
    discussion_brief = body.discussion_brief or context.get("discussion_brief") or build_discussion_brief(
        topic=checkin.topic,
        fact_block=fact_block,
        angle=angle,
        platform=platform,
        counter_angle=context.get("counter_angle", ""),
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
    return MessageResponse(**result)

@router.post("/confirm_content")
async def confirm_content_endpoint(
    request: ConfirmContentRequest,
    current_user: User = Depends(get_current_user),
    api_key: str = Depends(get_resolved_api_key),
    db: Session = Depends(get_db)
):
    """User confirms (possibly edited) draft content. Returns quality check result."""
    checkin = get_checkin_or_404(request.checkin_id, current_user.id, db)

    try:
        qc_result = await confirm_content(checkin, request.content, db, api_key=api_key)
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
            "message": "内容已确认。以下为质量提示，不影响发布。"
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
    db: Session = Depends(get_db)
):
    checkin = get_checkin_or_404(request.checkin_id, current_user.id, db)
    if checkin.status not in (CheckInStatus.draft_ready, CheckInStatus.pending, CheckInStatus.completed):
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
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
):
    """User confirms publish. Final step."""
    checkin = get_checkin_for_update(body.checkin_id, current_user.id, db)

    try:
        result = await confirm_publish(checkin, db, current_user)
        return PublishResponse(**result)
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
