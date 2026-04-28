from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from ..dependencies import get_current_user, get_db
from ..models import CheckIn, CheckInStatus, HotTopic, User
from ..schemas import (
    ConfirmContentRequest,
    ConfirmPublishRequest,
    ContentFeedbackRequest,
    ContentFeedbackResponse,
    MessageRequest,
    MessageResponse,
    PublishResponse,
    QuickGenerateRequest,
    QuickGenerateResponse,
)
from ..services.content_service import confirm_publish
from ..services.draft_service import (
    build_quick_generate_context,
    build_quick_generate_context_from_checkin,
    confirm_content,
    quick_generate,
)
from ..services.discussion_service import process_message
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


@router.post("/quick_generate", response_model=QuickGenerateResponse)
async def quick_generate_endpoint(
    request: QuickGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Quick mode: generate content in ~30s from a hot topic + angle. Stateless."""
    hot_topic = request.hot_topic
    fact_block = None
    topic_record = None
    if request.topic_id is not None:
        topic_record = get_today_hot_topic_or_404(request.topic_id, db)
        hot_topic = topic_record.title
        fact_block = build_quick_generate_context(
            hot_topic=topic_record.title,
            summary=topic_record.summary or "",
            source=topic_record.source,
            published_at=topic_record.published_at,
            url=topic_record.url,
        )
    elif request.checkin_id is not None:
        checkin = get_checkin_or_404(request.checkin_id, current_user.id, db)
        if any([checkin.topic_source, checkin.topic_summary, checkin.topic_url, checkin.topic_published_at]):
            hot_topic = checkin.topic
            fact_block = build_quick_generate_context_from_checkin(checkin)

    result = await quick_generate(
        hot_topic=hot_topic,
        angle=request.angle,
        platform=request.platform.value,
        fact_block=fact_block,
    )
    if request.checkin_id is not None:
        checkin = get_checkin_or_404(request.checkin_id, current_user.id, db)
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
        db.commit()
    return QuickGenerateResponse(**result)


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


@router.post("/generate_content", response_model=MessageResponse)
async def generate_content(
    request: MessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a message in the discussion flow."""
    checkin = get_checkin_or_404(request.checkin_id, current_user.id, db)

    if checkin.status == CheckInStatus.completed:
        raise HTTPException(status_code=400, detail="今日已完成发布")

    if checkin.status not in (CheckInStatus.topic_selected, CheckInStatus.discussing):
        raise HTTPException(status_code=400, detail=f"当前状态不支持发送消息: {checkin.status.value}")

    # Change status to discussing if just started
    if checkin.status == CheckInStatus.topic_selected:
        checkin.status = CheckInStatus.discussing
        db.commit()

    result = await process_message(checkin, request.message, db)
    return MessageResponse(**result)

@router.post("/confirm_content")
async def confirm_content_endpoint(
    request: ConfirmContentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """User confirms (possibly edited) draft content. Returns quality check result."""
    checkin = get_checkin_or_404(request.checkin_id, current_user.id, db)

    try:
        qc_result = await confirm_content(checkin, request.content, db)
        return {
            "status": "pending",
            "content_approved": qc_result["quality_pass"],
            "quality_issues": qc_result["quality_issues"],
            "quality_available": qc_result["quality_available"],
            "topic": qc_result["topic"],
            "message": "内容已确认。以下为质量提示，不影响发布。"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    }

@router.post("/confirm_publish", response_model=PublishResponse)
async def confirm_publish_endpoint(
    request: ConfirmPublishRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """User confirms publish. Final step."""
    checkin = get_checkin_for_update(request.checkin_id, current_user.id, db)

    try:
        result = await confirm_publish(checkin, db, current_user)
        return PublishResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
