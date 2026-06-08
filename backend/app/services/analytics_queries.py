"""Read-side analytics queries for the admin funnel + north-star endpoint.

This is the read counterpart to `app.services.analytics.track`. It computes:
- the registration→publish funnel (distinct user counts per step + step-to-step
  conversion rates), and
- the north-star "≥3-day streak ratio" from `users.streak`.

Why this lives in `services/` (not `routers/admin.py`):
- It lets unit tests exercise the math without spinning up FastAPI.
- It keeps the router file focused on HTTP wiring.
- It is the single place to change funnel definitions.

Funnel definition (kept in sync with W1.2 event names):
    register → key_configured → topic_selected → discuss_round
    → draft_generated → publish
A user "reaches" a step if they have at least one row in `events` with that
event name. We count distinct users, not raw events — repeated retries do not
inflate the funnel.

North-star definition (per PRD W1.3):
    ratio = users with streak ≥ 3 / users with at least one publish event
This is "what fraction of people who have ever published are still hooked
≥3 days in." A low ratio is the strongest signal that the streak mechanic
isn't doing the work the design assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Event, User
from .feature_flags import in_subtraction_experiment

# Valid cohort selectors for the subtraction experiment. None = both arms.
COHORTS = ("control", "subtraction")

# Funnel steps in order. Each value is the `event` name in the events table.
FUNNEL_STEPS: list[tuple[str, str]] = [
    ("register", "注册"),
    ("key_configured", "配置 Key"),
    ("topic_selected", "选题"),
    ("discuss_round", "讨论"),
    ("draft_generated", "初稿"),
    ("publish", "发布"),
]

NORTH_STAR_STREAK_THRESHOLD = 3


@dataclass(frozen=True)
class FunnelStep:
    """One stage in the funnel.

    Attributes:
        event: the Event.event name we look for.
        label: human-readable Chinese label for the admin UI.
        users: number of distinct users who reached this stage in the window.
        conversion_from_first: users / users_in_first_step (0..1).
        conversion_from_prev: users / users_in_prev_step (0..1, 0 if no prev).
    """

    event: str
    label: str
    users: int
    conversion_from_first: float
    conversion_from_prev: float


@dataclass(frozen=True)
class FunnelReport:
    """Full funnel result for one time window.

    Attributes:
        since: optional lower-bound timestamp (UTC). None means "all time".
        steps: the ordered funnel stages.
        window_days: convenience for the UI; 0 means "all time".
    """

    since: datetime | None
    steps: list[FunnelStep]
    window_days: int


def _in_cohort(user_id: int, cohort: str | None) -> bool:
    """Whether a user belongs to the requested experiment arm.

    cohort=None means "both arms" (legacy, unfiltered). The arm membership is a
    pure function of user_id via `in_subtraction_experiment`, so no extra column
    or join is needed — the same deterministic bucketing the app uses at runtime
    is replayed here at read time.
    """
    if cohort is None:
        return True
    if cohort == "subtraction":
        return in_subtraction_experiment(user_id)
    if cohort == "control":
        return not in_subtraction_experiment(user_id)
    raise ValueError(f"unknown cohort: {cohort!r}")


def _distinct_user_ids(db: Session, event_name: str, since: datetime | None) -> set[int]:
    """Distinct, non-anonymous user ids who triggered the given event."""
    q = db.query(Event.user_id).filter(
        Event.event == event_name,
        Event.user_id.is_not(None),
    )
    if since is not None:
        q = q.filter(Event.ts >= since)
    return {row[0] for row in q.distinct().all()}


def _distinct_user_count(
    db: Session, event_name: str, since: datetime | None, cohort: str | None = None
) -> int:
    """Count distinct users who triggered the given event, optionally restricted
    to one experiment arm.

    Anonymous events (user_id IS NULL) are excluded — the funnel is about
    real users, not unknown visitors.
    """
    ids = _distinct_user_ids(db, event_name, since)
    if cohort is None:
        return len(ids)
    return sum(1 for uid in ids if _in_cohort(uid, cohort))


def get_funnel(
    db: Session,
    since: datetime | None = None,
    window_days: int = 0,
    cohort: str | None = None,
) -> FunnelReport:
    """Compute the registration→publish funnel for an optional time window.

    Args:
        db: SQLAlchemy session.
        since: only count events at or after this timestamp. None = all time.
        window_days: convenience label for the response; pass 0 for "all time".
        cohort: restrict to one experiment arm ("control" / "subtraction"); None
            counts both arms (legacy behaviour).
    """
    counts = {event: _distinct_user_count(db, event, since, cohort) for event, _ in FUNNEL_STEPS}
    first_count = next(iter(counts.values()), 0) if counts else 0
    prev_count = 0
    steps: list[FunnelStep] = []
    for idx, (event, label) in enumerate(FUNNEL_STEPS):
        users = counts[event]
        if idx == 0:
            conv_first = 1.0 if first_count > 0 else 0.0
            conv_prev = 0.0
        else:
            conv_first = round(users / first_count, 3) if first_count > 0 else 0.0
            conv_prev = round(users / prev_count, 3) if prev_count > 0 else 0.0
        steps.append(
            FunnelStep(
                event=event,
                label=label,
                users=users,
                conversion_from_first=conv_first,
                conversion_from_prev=conv_prev,
            )
        )
        prev_count = users
    return FunnelReport(since=since, steps=steps, window_days=window_days)


@dataclass(frozen=True)
class NorthStarReport:
    """The PRD's north-star metric: what fraction of publishers hit ≥3-day streak.

    Attributes:
        threshold: the streak cutoff (always 3 in v1, kept in the struct so
            future admins can experiment without re-reading the source).
        total_users: every user that has ever published (denominator).
        qualifying_users: subset with streak >= threshold.
        ratio: qualifying / total_users, 0 if denominator is 0.
        total_registered_users: every user that has ever registered (regardless
            of whether they published). Useful for context.
    """

    threshold: int
    total_users: int
    qualifying_users: int
    ratio: float
    total_registered_users: int


def get_north_star(
    db: Session,
    threshold: int = NORTH_STAR_STREAK_THRESHOLD,
    cohort: str | None = None,
) -> NorthStarReport:
    """Compute the north-star streak ratio, optionally per experiment arm.

    A user "counts" if they have at least one `publish` event (they finished
    the funnel at least once). The qualifying subset has `users.streak >=
    threshold` at the moment this is called. When `cohort` is set, both the
    denominator and numerator are restricted to that experiment arm so the two
    arms can be compared directly.
    """
    publisher_ids = {
        row[0]
        for row in db.query(Event.user_id)
        .filter(Event.event == "publish", Event.user_id.is_not(None))
        .distinct()
        .all()
    }
    if cohort is not None:
        publisher_ids = {uid for uid in publisher_ids if _in_cohort(uid, cohort)}

    total = len(publisher_ids)
    qualifying = (
        db.query(func.count(User.id))
        .filter(User.id.in_(publisher_ids))
        .filter(User.streak >= threshold)
        .scalar()
        or 0
        if publisher_ids
        else 0
    )

    registered_ids = {row[0] for row in db.query(User.id).all()}
    if cohort is not None:
        registered_ids = {uid for uid in registered_ids if _in_cohort(uid, cohort)}
    total_registered = len(registered_ids)

    ratio = round(qualifying / total, 3) if total > 0 else 0.0
    return NorthStarReport(
        threshold=threshold,
        total_users=int(total),
        qualifying_users=int(qualifying),
        ratio=ratio,
        total_registered_users=int(total_registered),
    )


# Frontend distribution events are namespaced by channel/format, e.g.
# "copy_to_xiaohongshu", "copy_to_moments", "export_md", "export_txt".
# We match on the prefix so new platforms/formats are counted automatically.
COPY_EVENT_PREFIX = "copy_to_%"
EXPORT_EVENT_PREFIX = "export_%"


@dataclass(frozen=True)
class DistributionReport:
    """Did people who published actually take the content out to distribute?

    The out-of-app "copy" / "export" clicks are tracked by the frontend as
    `copy_to_{platform}` / `export_{format}` events. This report answers the
    W1.4 question — *is distribution a real need?* — by measuring, among users
    who finished the funnel (published at least once), how many also copied or
    exported.

    The denominator anchors on publishers (same as the north-star) so the rates
    stay in [0, 1] and are directly comparable. A user who copies but never
    fires a `publish` event is intentionally excluded — they are counted by the
    raw `copy_to_*` events, but not by these publisher-anchored rates.

    Attributes:
        total_publishers: distinct users with a `publish` event (denominator).
        copy_users: publishers who copied at least once.
        export_users: publishers who exported at least once.
        distributed_users: publishers who copied OR exported.
        copy_rate: copy_users / total_publishers.
        export_rate: export_users / total_publishers.
        distribution_rate: distributed_users / total_publishers.
    """

    total_publishers: int
    copy_users: int
    export_users: int
    distributed_users: int
    copy_rate: float
    export_rate: float
    distribution_rate: float


def _distinct_users_like(
    db: Session, like_pattern: str, since: datetime | None, restrict_to: set[int]
) -> set[int]:
    """Distinct, non-anonymous user ids whose event name matches `like_pattern`,
    intersected with `restrict_to` (the publisher set)."""
    if not restrict_to:
        return set()
    q = (
        db.query(Event.user_id)
        .filter(Event.event.like(like_pattern), Event.user_id.is_not(None))
        .distinct()
    )
    if since is not None:
        q = q.filter(Event.ts >= since)
    return {row[0] for row in q.all()} & restrict_to


def get_distribution_metrics(
    db: Session, since: datetime | None = None
) -> DistributionReport:
    """Compute the publisher-anchored copy/export distribution rates."""
    pub_q = (
        db.query(Event.user_id)
        .filter(Event.event == "publish", Event.user_id.is_not(None))
        .distinct()
    )
    if since is not None:
        pub_q = pub_q.filter(Event.ts >= since)
    publishers = {row[0] for row in pub_q.all()}
    total = len(publishers)
    if total == 0:
        return DistributionReport(0, 0, 0, 0, 0.0, 0.0, 0.0)

    copy_users = _distinct_users_like(db, COPY_EVENT_PREFIX, since, publishers)
    export_users = _distinct_users_like(db, EXPORT_EVENT_PREFIX, since, publishers)
    distributed = copy_users | export_users

    return DistributionReport(
        total_publishers=total,
        copy_users=len(copy_users),
        export_users=len(export_users),
        distributed_users=len(distributed),
        copy_rate=round(len(copy_users) / total, 3),
        export_rate=round(len(export_users) / total, 3),
        distribution_rate=round(len(distributed) / total, 3),
    )


@dataclass(frozen=True)
class UserFunnelPosition:
    """Where one user currently sits in the funnel.

    Attributes:
        user_id: the user.
        last_event: the most recent event the user emitted.
        last_event_ts: when that happened.
        furthest_step: the latest funnel stage the user has reached (event name).
        furthest_step_label: human-readable label.
        has_published: convenience boolean.
    """

    user_id: int
    last_event: str | None
    last_event_ts: datetime | None
    furthest_step: str | None
    furthest_step_label: str | None
    has_published: bool

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "last_event": self.last_event,
            "last_event_ts": self.last_event_ts.isoformat() if self.last_event_ts else None,
            "furthest_step": self.furthest_step,
            "furthest_step_label": self.furthest_step_label,
            "has_published": self.has_published,
        }


def get_user_funnel_position(db: Session, user_id: int) -> UserFunnelPosition:
    """Compute one user's furthest-funnel-stage and last-event.

    Returns a UserFunnelPosition with has_published=False and furthest_step=None
    for a user with no events yet.
    """
    last_row = (
        db.query(Event)
        .filter(Event.user_id == user_id)
        .order_by(Event.ts.desc())
        .first()
    )
    user_events = (
        db.query(Event.event)
        .filter(Event.user_id == user_id)
        .distinct()
        .all()
    )
    event_names = {row[0] for row in user_events}

    furthest_event: str | None = None
    furthest_label: str | None = None
    for event, label in FUNNEL_STEPS:
        if event in event_names:
            furthest_event = event
            furthest_label = label

    return UserFunnelPosition(
        user_id=user_id,
        last_event=last_row.event if last_row else None,
        last_event_ts=last_row.ts if last_row else None,
        furthest_step=furthest_event,
        furthest_step_label=furthest_label,
        has_published="publish" in event_names,
    )
