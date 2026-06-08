"""
Admin-only read-only endpoints for monitoring prompt and content quality.

These endpoints are for local development and internal monitoring only.
Do NOT expose to the miniprogram or public frontend.
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_admin_user, get_db
from ..models import CheckIn, CheckInStatus, Event, User
from ..schemas import GamificationOverrideRequest
from ..services.analytics import track
from ..services.analytics_queries import (
    FUNNEL_STEPS,
    get_distribution_metrics,
    get_funnel,
    get_north_star,
    get_user_funnel_position,
)
from ..services.prompt_templates import prompts
from ..utils.time_utils import get_now_cst

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/prompt_health")
def prompt_health(
    version: str | None = None,
    _current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Aggregate content quality signals grouped by prompt_version.

    Metrics:
      - total_checkins: checkins that reached draft_ready or beyond
      - completed: checkins that reached completed status
      - completion_rate: completed / total_checkins
      - avg_topic_refreshes: average refresh_count per checkin (proxy for topic dissatisfaction)
      - revision_count: checkins that have content_feedback = "down" (proxy for draft dissatisfaction)
      - revision_rate: revision_count / total_checkins
      - avg_content_length: average character count of final content
      - avg_discussion_turns: average number of user messages in conversation_history

    Filter by ?version=<prompt_version> or leave blank to see all versions.
    """
    query = db.query(CheckIn).filter(
        CheckIn.status.in_(
            [
                CheckInStatus.draft_ready,
                CheckInStatus.pending,
                CheckInStatus.completed,
            ]
        )
    )

    rows = query.all()

    # Group by prompt_version found in generation_context JSON
    groups: dict[str, list[CheckIn]] = defaultdict(list)
    for row in rows:
        ctx = {}
        if row.generation_context:
            try:
                ctx = json.loads(row.generation_context)
            except Exception:
                pass
        pv = ctx.get("prompt_version", "unknown")
        groups[pv].append(row)

    def _count_turns(checkin: CheckIn) -> int:
        if not checkin.conversation_history:
            return 0
        try:
            history = json.loads(checkin.conversation_history)
            if isinstance(history, list):
                return sum(1 for m in history if isinstance(m, dict) and m.get("role") == "user")
        except Exception:
            pass
        return 0

    def _summarize(checkins: list[CheckIn]) -> dict:
        total = len(checkins)
        if total == 0:
            return {}
        completed = sum(1 for c in checkins if c.status == CheckInStatus.completed)
        revisions = sum(1 for c in checkins if c.content_feedback == "down")
        lengths = [len(c.content) for c in checkins if c.content]
        turns = [_count_turns(c) for c in checkins]
        return {
            "total_checkins": total,
            "completed": completed,
            "completion_rate": round(completed / total, 3),
            "avg_topic_refreshes": round(sum(c.refresh_count for c in checkins) / total, 2),
            "revision_count": revisions,
            "revision_rate": round(revisions / total, 3),
            "avg_content_length": round(sum(lengths) / len(lengths), 1) if lengths else 0,
            "avg_discussion_turns": round(sum(turns) / total, 2),
        }

    if version:
        target_groups = {version: groups.get(version, [])}
    else:
        target_groups = dict(groups)

    result = {
        "current_prompt_version": prompts.version,
        "by_version": {pv: _summarize(items) for pv, items in sorted(target_groups.items())},
    }
    return result


# ── Funnel + North-Star (W1.3) ────────────────────────────────────────────────


@router.get("/metrics/funnel")
def metrics_funnel(
    window_days: int = Query(
        0,
        ge=0,
        le=365,
        description="Restrict to events within the last N days. 0 = all time.",
    ),
    cohort: str | None = Query(
        None,
        pattern="^(control|subtraction)$",
        description=(
            "Restrict to one subtraction-experiment arm: 'control' (gamification "
            "on) or 'subtraction' (gamification off). Omit to combine both arms."
        ),
    ),
    src: str | None = Query(
        None,
        max_length=64,
        description="Restrict the funnel to users who registered with this flywheel source token (Appendix B). Omit for all sources.",
    ),
    _current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> dict:
    """Global funnel: register → key_configured → topic_selected → discuss_round
    → draft_generated → publish, plus the north-star streak ratio.

    The funnel is computed from distinct users that fired each event. Numbers
    in early days will be 0 for downstream steps — that is the point: this
    endpoint is the only place we can see the leak.
    """
    if window_days == 0:
        since: datetime | None = None
    else:
        # Use CST-now so the "last N days" window aligns with our other date logic.
        since = get_now_cst() - timedelta(days=window_days)

    funnel = get_funnel(db, since=since, window_days=window_days, cohort=cohort, src=src)
    north_star = get_north_star(db, cohort=cohort)
    distribution = get_distribution_metrics(db, since=since)

    return {
        "window_days": window_days,
        "cohort": cohort,
        "src": src,
        "since": since.isoformat() if since else None,
        "distribution": {
            "total_publishers": distribution.total_publishers,
            "copy_users": distribution.copy_users,
            "export_users": distribution.export_users,
            "distributed_users": distribution.distributed_users,
            "copy_rate": distribution.copy_rate,
            "export_rate": distribution.export_rate,
            "distribution_rate": distribution.distribution_rate,
        },
        "funnel": [
            {
                "event": s.event,
                "label": s.label,
                "users": s.users,
                "conversion_from_first": s.conversion_from_first,
                "conversion_from_prev": s.conversion_from_prev,
            }
            for s in funnel.steps
        ],
        "north_star": {
            "threshold": north_star.threshold,
            "total_publishers": north_star.total_users,
            "qualifying_users": north_star.qualifying_users,
            "ratio": north_star.ratio,
            "total_registered_users": north_star.total_registered_users,
        },
    }


@router.get("/metrics/funnel/user/{user_id}")
def metrics_funnel_for_user(
    user_id: int,
    _current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> dict:
    """Where is this user in the funnel right now?

    Useful for support: paste a user id, see their furthest step + last event
    timestamp, decide if they're stuck at 'discuss_round' (3 days idle) or
    bounced right after 'key_configured'.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    pos = get_user_funnel_position(db, user_id)
    return {
        "user_id": pos.user_id,
        "openid": user.openid,
        "username": user.username,
        "current_streak": user.streak,
        "longest_streak": user.longest_streak,
        "points": user.points,
        "last_event": pos.last_event,
        "last_event_ts": pos.last_event_ts.isoformat() if pos.last_event_ts else None,
        "furthest_step": pos.furthest_step,
        "furthest_step_label": pos.furthest_step_label,
        "has_published": pos.has_published,
        "funnel_definition": [{"event": ev, "label": lbl} for ev, lbl in FUNNEL_STEPS],
    }


# ── Appendix A: per-user gamification override (within-subject switch) ─────────


@router.post("/gamification_override")
def set_gamification_override(
    body: GamificationOverrideRequest,
    _current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> dict:
    """Force a user's gamification arm on/off, or clear back to the md5 bucket.

    Records a `gamification_override_changed` event on the *target* user's
    timeline so the within-subject (ABAB) dashboard can attribute later
    publish/discuss behaviour to the arm that was active at the time.
    """
    if body.override not in (None, "on", "off"):
        raise HTTPException(status_code=400, detail="override must be 'on', 'off', or null")

    user = db.query(User).filter(User.id == body.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    from_value = user.gamification_override or "default"
    to_value = body.override or "default"
    user.gamification_override = body.override
    db.commit()

    track(
        "gamification_override_changed",
        user_id=user.id,
        props={"from": from_value, "to": to_value},
    )
    return {
        "user_id": user.id,
        "gamification_override": user.gamification_override,
        "from": from_value,
        "to": to_value,
    }
