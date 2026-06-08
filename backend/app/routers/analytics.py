"""Generic event-tracking endpoint for frontend-only events.

Why this exists: copy-to-XHS / export-to-md / share-button clicks live in the
browser. We don't want to send every such event through a full route, so this
endpoint just accepts `{event, props}` from an authenticated user, calls
`analytics.track()`, and returns 204 No Content.

The endpoint is best-effort by design: if the DB is unhealthy, track() returns
False silently — we still return 204 so the UI never sees a tracking failure.
"""

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from ..dependencies import get_current_user
from ..models import User
from ..services.analytics import track

router = APIRouter()


class TrackEventRequest(BaseModel):
    event: str
    props: dict | None = None


@router.post("/event/track", status_code=204)
async def track_event(
    body: TrackEventRequest,
    current_user: User = Depends(get_current_user),
):
    """Best-effort: store a frontend event. Never raises. Returns 204."""
    track(body.event, user_id=current_user.id, props=body.props)
    # Returning a Response is the cleanest way to send 204 without a body in
    # FastAPI. (Returning None would be 200 with body null.)
    return Response(status_code=204)
