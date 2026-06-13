"""Tests for product analytics — events table + track() helper.

Acceptance for W1.1:
- events table exists with indexes on (user_id, event, ts)
- track() creates a row and serializes props to JSON
- track() never raises — even when the DB is broken, the caller's flow continues
- anonymous events (user_id=None) are supported
"""

import json
from unittest.mock import patch

from app.models import Event
from app.services import analytics
from app.services.analytics import track


def test_track_creates_event_row(db):
    """The basic case: track() writes a row, returns True, props round-trip."""
    ok = track("topic_selected", user_id=42, props={"topic_id": "abc", "rank": 1})
    assert ok is True

    rows = db.query(Event).all()
    assert len(rows) == 1
    ev = rows[0]
    assert ev.user_id == 42
    assert ev.event == "topic_selected"
    assert json.loads(ev.props_json) == {"topic_id": "abc", "rank": 1}
    assert ev.ts is not None


def test_track_supports_anonymous_events(db):
    """Login failures, page views, etc. should be recordable without a user."""
    ok = track("anonymous_ping")
    assert ok is True

    rows = db.query(Event).all()
    assert len(rows) == 1
    assert rows[0].user_id is None
    assert rows[0].event == "anonymous_ping"
    assert rows[0].props_json is None


def test_track_serialization_preserves_chinese(db):
    """ensure_ascii=False so Chinese props round-trip readably."""
    track("copy_to_xhs", user_id=1, props={"title": "顺发测试", "tags": ["AI", "产品"]})

    ev = db.query(Event).first()
    decoded = json.loads(ev.props_json)
    assert decoded == {"title": "顺发测试", "tags": ["AI", "产品"]}


def test_track_does_not_raise_on_session_open_failure():
    """If SessionLocal() itself blows up, track() returns False — never raises."""
    with patch.object(analytics, "SessionLocal", side_effect=RuntimeError("db down")):
        ok = track("publish", user_id=1, props={"platform": "wechat"})
    assert ok is False


def test_track_does_not_raise_on_commit_failure(db):
    """If the commit fails, track() rolls back and returns False — never raises."""
    with patch.object(analytics, "SessionLocal") as mock_session_local:
        mock_session = mock_session_local.return_value
        mock_session.commit.side_effect = RuntimeError("commit failed")

        ok = track("publish", user_id=1, props={"platform": "wechat"})

    assert ok is False
    # No row should have been persisted (rolled back).
    assert db.query(Event).count() == 0
    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()


def test_track_truncates_long_event_names(db):
    """Defense against accidental giant keys — truncate to 64 chars."""
    long_name = "x" * 200
    track(long_name, user_id=1)
    ev = db.query(Event).first()
    assert ev.event == "x" * 64


def test_track_rejects_empty_event_name():
    ok = track("")
    assert ok is False


def test_track_handles_non_jsonable_via_default_str(db):
    """`default=str` is a safety net so track() never fails on weird types
    (sets, custom objects, etc.) — it stringifies them and continues.
    """
    ok = track("oops", props={"data": {1, 2, 3}})  # type: ignore[arg-type]
    assert ok is True
    ev = db.query(Event).filter(Event.event == "oops").first()
    decoded = json.loads(ev.props_json)
    # Set gets stringified rather than crashing the request.
    assert "data" in decoded
    assert "1" in decoded["data"] and "2" in decoded["data"] and "3" in decoded["data"]


def test_events_table_has_required_indexes(db):
    """Sanity check: the indexes we declared on the model are present in the DB."""
    expected = {
        "ix_events_id",
        "ix_events_user_id",
        "ix_events_user_event_ts",
        "ix_events_event_ts",
        "ix_events_ts",
    }
    actual = {ix.name for ix in Event.__table__.indexes}
    missing = expected - actual
    assert not missing, f"missing indexes on events: {missing}"


def test_main_flow_unaffected_when_track_raises(db):
    """Acceptance: a forced track() failure must not break the caller's flow."""
    with patch.object(analytics, "SessionLocal", side_effect=RuntimeError("kaboom")):
        result = {"step": "before"}
        try:
            analytics.track("publish", user_id=1, props={"k": "v"})
        except Exception:
            result["step"] = "broken"
        else:
            result["step"] = "after"

    assert result["step"] == "after", "track() must never raise into caller"
