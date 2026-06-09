"""Paste-to-cards endpoints (added 2026-06).

A standalone formatting tool: paste an article, get back deterministic
pagination, then render the pages to PNG cards with a chosen template.
NOT linked to streak/points — see ImageJob docstring.
"""

import base64

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..dependencies import get_current_user, get_db
from ..models import ImageJob, ImageJobStatus, User
from ..schemas import (
    ImageJobCreateRequest,
    ImageJobRenderRequest,
    ImageJobRenderResponse,
    ImageJobResponse,
    PageModel,
)
from ..services.analytics import track
from ..services.paginate_service import PaginationResult, paginate
from ..services.render_service import render_cards

router = APIRouter(prefix="/image_jobs", tags=["image_jobs"])


def _pages_to_models(result: PaginationResult) -> list[PageModel]:
    return [
        PageModel(index=p.index, kind=p.kind, title=p.title, paragraphs=p.paragraphs)
        for p in result.pages
    ]


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
def create_image_job(
    body: ImageJobCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageJobResponse:
    result = paginate(body.raw_text, body.cover_title)
    job = ImageJob(
        user_id=current_user.id,
        raw_text=body.raw_text,
        template=body.template,
        cover_title=body.cover_title,
        page_count=result.page_count,
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
    )


@router.get("/{job_id}", response_model=ImageJobResponse)
def get_image_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageJobResponse:
    job = _get_owned_job(job_id, current_user, db)
    result = paginate(job.raw_text, job.cover_title)
    return ImageJobResponse(
        job_id=job.id,
        template=job.template,
        cover_title=job.cover_title,
        pages=_pages_to_models(result),
        page_count=result.page_count,
        overflow=result.overflow,
        status=job.status.value,
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
