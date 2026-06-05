"""
Admin-only read-only endpoints for monitoring prompt and content quality.

These endpoints are for local development and internal monitoring only.
Do NOT expose to the miniprogram or public frontend.
"""

import json
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..dependencies import get_admin_user, get_db
from ..models import CheckIn, CheckInStatus, User
from ..services.prompt_templates import prompts

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
