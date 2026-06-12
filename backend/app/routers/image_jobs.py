"""Paste-to-cards endpoints (added 2026-06).

A standalone formatting tool: paste an article, get back deterministic
pagination, then render the pages to PNG cards with a chosen template.
NOT linked to streak/points — see ImageJob docstring.

W2.x (2026-06): also returns AI-generated Xiaohongshu-style title + tags
on the create + get endpoints, so the user can one-tap copy the post copy
to their clipboard after rendering. The AI call is best-effort: on failure
the response still succeeds with empty ai_title / ai_tags.
"""

import base64

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..dependencies import get_current_user, get_db, get_resolved_api_key
from ..models import ImageJob, ImageJobStatus, User
from ..schemas import (
    ImageJobCreateRequest,
    ImageJobRenderRequest,
    ImageJobRenderResponse,
    ImageJobResponse,
    PageModel,
)
from ..services.analytics import track
from ..services.compose_service import generate_post_copy
from ..services.paginate_service import PaginationResult, paginate
from ..services.render_service import render_cards

router = APIRouter(prefix="/image_jobs", tags=["image_jobs"])


def _pages_to_models(result: PaginationResult) -> list[PageModel]:
    return [
        PageModel(index=p.index, kind=p.kind, title=p.title, paragraphs=p.paragraphs)
        for p in result.pages
    ]


def _parse_ai_copy(ai_copy: str | None) -> tuple[str, list[str]]:
    """Read ImageJob.ai_copy (JSON `{"title": str, "tags": list[str]}`) into
    the flat fields the API returns. Returns ("", []) on any corruption
    (legacy rows, manual edits, partial writes)."""
    if not ai_copy:
        return "", []
    import json

    try:
        data = json.loads(ai_copy)
    except (json.JSONDecodeError, TypeError):
        return "", []
    title = str(data.get("title", "")).strip()
    raw_tags = data.get("tags", [])
    if not isinstance(raw_tags, list):
        return title, []
    tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    return title, tags


def _get_owned_job(job_id: int, user: User, db: Session) -> ImageJob:
    job = (
        db.query(ImageJob)
        .filter(ImageJob.id == job_id, ImageJob.user_id == user.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Image job not found")
    return job


@router.post("", response_model=ImageJobResponse)
async def create_image_job(
    body: ImageJobCreateRequest,
    current_user: User = Depends(get_current_user),
    api_key: str = Depends(get_resolved_api_key),
    db: Session = Depends(get_db),
) -> ImageJobResponse:
    result = paginate(body.raw_text, body.cover_title)

    # Best-effort AI copy generation. Never blocks the request — on any LLM
    # failure the user still gets a 200 response with empty ai_title/ai_tags
    # and can still use the rendered image cards.
    copy = await generate_post_copy(body.raw_text, api_key=api_key)

    import json

    job = ImageJob(
        user_id=current_user.id,
        raw_text=body.raw_text,
        template=body.template,
        cover_title=body.cover_title,
        page_count=result.page_count,
        ai_copy=json.dumps(copy, ensure_ascii=False) if copy["title"] or copy["tags"] else None,
        status=ImageJobStatus.draft,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    track(
        "paste_compose",
        user_id=current_user.id,
        props={
            "template": body.template,
            "char_count": len(body.raw_text),
            "page_count": result.page_count,
            "ai_copy_generated": bool(copy["title"] or copy["tags"]),
        },
    )

    return ImageJobResponse(
        job_id=job.id,
        template=job.template,
        cover_title=job.cover_title,
        pages=_pages_to_models(result),
        page_count=result.page_count,
        overflow=result.overflow,
        status=job.status.value,
        ai_title=copy["title"],
        ai_tags=copy["tags"],
    )


@router.get("/{job_id}", response_model=ImageJobResponse)
def get_image_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageJobResponse:
    job = _get_owned_job(job_id, current_user, db)
    result = paginate(job.raw_text, job.cover_title)
    ai_title, ai_tags = _parse_ai_copy(job.ai_copy)
    return ImageJobResponse(
        job_id=job.id,
        template=job.template,
        cover_title=job.cover_title,
        pages=_pages_to_models(result),
        page_count=result.page_count,
        overflow=result.overflow,
        status=job.status.value,
        ai_title=ai_title,
        ai_tags=ai_tags,
    )


@router.post("/{job_id}/render", response_model=ImageJobRenderResponse)
async def render_image_job(
    job_id: int,
    body: ImageJobRenderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageJobRenderResponse:
    job = _get_owned_job(job_id, current_user, db)
    if body.template:
        job.template = body.template

    result = paginate(job.raw_text, job.cover_title)
    try:
        images = await render_cards(result.pages, job.template)
    except Exception as exc:
        job.status = ImageJobStatus.failed
        db.commit()
        raise HTTPException(status_code=502, detail="图片渲染失败，请稍后重试") from exc

    job.status = ImageJobStatus.rendered
    job.page_count = result.page_count
    db.commit()

    track(
        "image_rendered",
        user_id=current_user.id,
        props={"template": job.template, "page_count": result.page_count},
    )

    encoded = [base64.b64encode(img).decode("ascii") for img in images]
    return ImageJobRenderResponse(
        job_id=job.id,
        template=job.template,
        images=encoded,
        page_count=result.page_count,
    )
